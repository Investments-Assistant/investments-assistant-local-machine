"""Human bank-consent controls; unavailable unless separately configured.

No credentials or bank passwords are accepted from model tools. Consent account
IDs stay encrypted; the browser selects an opaque account handle.
"""

import asyncio

from fastapi import Depends, Request, APIRouter, HTTPException
from pydantic import Field, BaseModel, ConfigDict
from sqlalchemy import select

from src import config
from src.web.auth import require_csrf, require_authenticated
from src.db.models import User
from src.db.database import async_session
from src.expenses.runtime import configured, dependencies
from src.operations.models import BankSyncState
from src.expenses.providers import ProviderError
from src.expenses.provider_sync import (
    unseal,
    disconnect,
    account_key,
    owned_state,
    begin_consent,
    choose_account,
)

router = APIRouter(prefix="/api/banks", dependencies=[Depends(require_authenticated)])


class ConsentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    institution: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class AccountInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_handle: str = Field(pattern=r"^[a-f0-9]{64}$")


async def browser(request):
    principal = await require_authenticated(request)
    if not principal.user_id or principal.mechanism != "cookie":
        raise HTTPException(403, "An authenticated browser account is required")
    return principal.user_id


def denied(exc):
    return HTTPException(409, detail={"reason_code": exc.code})


@router.get("")
async def status(request: Request):
    user_id = await browser(request)
    async with async_session() as session:
        rows = (
            (
                await session.execute(
                    select(BankSyncState)
                    .where(BankSyncState.user_id == user_id)
                    .order_by(BankSyncState.id)
                    .limit(50)
                )
            )
            .scalars()
            .all()
        )
    return {
        "external_access_enabled": configured(),
        "consent_setup_available": configured() and bool(
            config.settings.gocardless_secret_id and config.settings.gocardless_secret_key
        ),
        "connections": [
            {
                "id": row.id,
                "provider": row.provider,
                "status": row.status,
                "error_code": row.error_code,
                "last_received_at": row.last_received_at.isoformat()
                if row.last_received_at
                else None,
                "provider_last_success_at": row.last_success_at.isoformat()
                if row.last_success_at
                else None,
            }
            for row in rows
        ],
    }


@router.post("/consent", dependencies=[Depends(require_csrf)])
async def consent(body: ConsentInput, request: Request):
    user_id = await browser(request)
    try:
        provider, vault = dependencies()
        if not config.settings.gocardless_secret_id or not config.settings.gocardless_secret_key:
            raise ProviderError("PROVIDER_CREDENTIALS_UNAVAILABLE")
        async with async_session.begin() as session:
            await session.execute(select(User.id).where(User.id == user_id).with_for_update())
            ids = (
                (
                    await session.execute(
                        select(BankSyncState.id).where(BankSyncState.user_id == user_id).limit(10)
                    )
                )
                .scalars()
                .all()
            )
            if len(ids) >= 10:
                raise ProviderError("BANK_CONNECTION_LIMIT")
            return await begin_consent(
                session,
                user_id=user_id,
                provider=provider,
                vault=vault,
                credentials={
                    "secret_id": config.settings.gocardless_secret_id,
                    "secret_key": config.settings.gocardless_secret_key,
                },
                institution=body.institution,
                redirect=config.settings.bank_consent_redirect,
                human_event=True,
            )
    except ProviderError as exc:
        raise denied(exc) from exc
    except TimeoutError as exc:
        raise HTTPException(504, "Consent provider timed out; verify before retrying") from exc


@router.get("/{state_id}/accounts")
async def accounts(state_id: str, request: Request):
    user_id = await browser(request)
    try:
        provider, vault = dependencies()
        async with async_session.begin() as session:
            state = await owned_state(session, user_id, state_id)
            async with asyncio.timeout(30):
                credentials = await provider.token(unseal(vault, state.encrypted_credentials))
                ids = await provider.accounts(credentials)
            return {
                "accounts": [
                    {
                        "handle": account_key(provider.name, value),
                        "label": f"Consented account {i + 1}",
                    }
                    for i, value in enumerate(ids)
                ]
            }
    except ProviderError as exc:
        raise denied(exc) from exc


@router.post("/{state_id}/account", dependencies=[Depends(require_csrf)])
async def select_account(state_id: str, body: AccountInput, request: Request):
    user_id = await browser(request)
    try:
        provider, vault = dependencies()
        async with async_session.begin() as session:
            state = await owned_state(session, user_id, state_id)
            async with asyncio.timeout(30):
                credentials = await provider.token(unseal(vault, state.encrypted_credentials))
                ids = await provider.accounts(credentials)
                selected = [
                    value
                    for value in ids
                    if account_key(provider.name, value) == body.account_handle
                ]
                if len(selected) != 1:
                    raise ProviderError("ACCOUNT_NOT_CONSENTED")
                return await choose_account(
                    session,
                    user_id=user_id,
                    state_id=state_id,
                    selected_account=selected[0],
                    provider=provider,
                    vault=vault,
                    human_event=True,
                )
    except ProviderError as exc:
        raise denied(exc) from exc


@router.delete("/{state_id}", dependencies=[Depends(require_csrf)])
async def stop_sync(state_id: str, request: Request):
    user_id = await browser(request)
    try:
        async with async_session.begin() as session:
            return await disconnect(session, user_id=user_id, state_id=state_id)
    except ProviderError as exc:
        raise denied(exc) from exc


@router.post("/{state_id}/reconnect", dependencies=[Depends(require_csrf)])
async def reconnect(state_id: str, body: ConsentInput, request: Request):
    user_id = await browser(request)
    try:
        provider, vault = dependencies()
        async with async_session.begin() as session:
            return await begin_consent(
                session,
                user_id=user_id,
                state_id=state_id,
                provider=provider,
                vault=vault,
                human_event=True,
                credentials={
                    "secret_id": config.settings.gocardless_secret_id,
                    "secret_key": config.settings.gocardless_secret_key,
                },
                institution=body.institution,
                redirect=config.settings.bank_consent_redirect,
            )
    except ProviderError as exc:
        raise denied(exc) from exc
    except TimeoutError as exc:
        raise HTTPException(504, "Consent provider timed out; verify before retrying") from exc
