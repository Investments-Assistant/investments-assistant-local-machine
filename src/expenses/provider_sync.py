"""Atomic expense ingestion and consent checkpoints, independent of trading.

Caller owns the transaction. Network work is bounded and rows are locked; one
account cannot advance its cursor without committing the corresponding records.
"""

import json
import asyncio
import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import func, select
from cryptography.fernet import InvalidToken

from src.expenses.sync import normalise_transaction
from src.operations.models import BankSyncState
from src.security.sessions import assert_active
from src.expenses.providers import ProviderError, identifier
from src.expenses.persistence import upsert_transaction


def account_key(provider, account):
    return hashlib.sha256((provider + "|" + account).encode()).hexdigest()


def seal(vault, credentials):
    return vault.encrypt(json.dumps(credentials, separators=(",", ":")).encode()).decode()


def unseal(vault, value):
    try:
        result = json.loads(vault.decrypt(value.encode()))
        if not isinstance(result, dict):
            raise ValueError("Invalid shape")
        return result
    except (InvalidToken, ValueError, TypeError, AttributeError) as exc:
        raise ProviderError("PROVIDER_CREDENTIALS_UNAVAILABLE") from exc


async def owned_state(session, user_id, state_id):
    await assert_active(session, user_id)
    state = await session.scalar(
        select(BankSyncState)
        .where(
            BankSyncState.id == state_id,
            BankSyncState.user_id == user_id,
        )
        .with_for_update()
    )
    if state is None:
        raise ProviderError("BANK_CONNECTION_NOT_OWNED")
    return state


async def begin_consent(
    session,
    *,
    user_id,
    provider,
    vault,
    credentials,
    institution,
    redirect,
    human_event,
    state_id=None,
):
    await assert_active(session, user_id)
    if human_event is not True:
        raise ProviderError("HUMAN_CONSENT_REQUIRED")
    existing = await owned_state(session, user_id, state_id) if state_id else None
    if existing and existing.status not in {"disconnected", "reconnect_required"}:
        raise ProviderError("BANK_RECONNECT_NOT_REQUIRED")
    reference = secrets.token_urlsafe(32)
    async with asyncio.timeout(30):
        tokens = await provider.token(credentials)
        consent = await provider.consent(
            tokens, institution=institution, redirect=redirect, reference=reference
        )
    encrypted = seal(
        vault,
        {
            **tokens,
            "reference": reference,
            "requisition_id": consent["requisition_id"],
            "expected_account_key": existing.account_key if existing else None,
        },
    )
    if existing:
        state = existing
        state.encrypted_credentials = encrypted
        state.status, state.error_code = "consent_pending", None
    else:
        state = BankSyncState(
            user_id=user_id,
            provider=provider.name,
            account_key=account_key(provider.name, reference),
            status="consent_pending",
            encrypted_credentials=encrypted,
            checkpoint={"schema": 1},
        )
        session.add(state)
    await session.flush()
    return {"connection_id": state.id, "status": state.status, "consent_url": consent["link"]}


async def choose_account(
    session, *, user_id, state_id, selected_account, provider, vault, human_event
):
    state = await owned_state(session, user_id, state_id)
    if human_event is not True or state.status != "consent_pending":
        raise ProviderError("HUMAN_ACCOUNT_SELECTION_REQUIRED")
    selected = identifier(selected_account)
    async with asyncio.timeout(30):
        tokens = await provider.token(unseal(vault, state.encrypted_credentials))
        if selected not in await provider.accounts(tokens):
            raise ProviderError("ACCOUNT_NOT_CONSENTED")
    selected_key = account_key(provider.name, selected)
    if tokens.get("expected_account_key") and tokens["expected_account_key"] != selected_key:
        raise ProviderError("RECONNECT_ACCOUNT_MISMATCH")
    state.account_key = selected_key
    state.encrypted_credentials = seal(vault, {**tokens, "account_id": selected})
    state.status = "connected"
    state.error_code = None
    state.checkpoint = {key: value for key, value in state.checkpoint.items() if key != "retry_at"}
    await session.flush()
    return {"status": state.status, "connection_id": state.id}


async def sync_account(session, *, user_id, state_id, provider, vault):
    state = await owned_state(session, user_id, state_id)
    if state.status not in {"connected", "retry_wait"}:
        raise ProviderError("BANK_CONNECTION_DISCONNECTED")
    now = await session.scalar(select(func.clock_timestamp()))
    retry = state.checkpoint.get("retry_at")
    if retry and datetime.fromisoformat(retry) > now:
        return {"status": "retry_wait", "error_code": state.error_code}
    # Account data is polled with a 7-day overlap for revisions, not claimed real-time.
    cursor = state.checkpoint.get("through")
    since = (
        datetime.fromisoformat(cursor).date() - timedelta(days=7)
        if cursor
        else now.date() - timedelta(days=90)
    )
    try:
        async with asyncio.timeout(30):
            tokens = await provider.token(unseal(vault, state.encrypted_credentials))
            if (
                state.provider != provider.name
                or account_key(provider.name, tokens.get("account_id", "")) != state.account_key
            ):
                raise ProviderError("BANK_ACCOUNT_IDENTITY_MISMATCH")
            records = await provider.transactions(tokens, since=since)
            if len(records) > 5000:
                raise ProviderError("PROVIDER_BATCH_TOO_LARGE")
            normalised = [
                normalise_transaction(item, provider.name, "Consented bank account")
                for item in records
            ]
            if any(item["account_key"] != state.account_key for item in normalised):
                raise ProviderError("BANK_ACCOUNT_IDENTITY_MISMATCH")
            # Roll back the entire batch if any record/database check fails. No partial cursor.
            async with session.begin_nested():
                for item in normalised:
                    await upsert_transaction(session, user_id=user_id, item=item, received_at=now)
                await assert_active(session, user_id)
        state.encrypted_credentials = seal(vault, tokens)
        state.last_received_at = now
        state.last_success_at = now
        state.checkpoint = {"schema": 1, "through": now.isoformat(), "records": len(records)}
        state.status, state.error_code = "connected", None
        await session.flush()
        return {
            "status": "complete",
            "records": len(records),
            "provider_last_success_at": now.isoformat(),
            "last_received_at": now.isoformat(),
        }
    except (ProviderError, ValueError, TimeoutError) as exc:
        code = (
            exc.code
            if isinstance(exc, ProviderError)
            else "INVALID_PROVIDER_DATA"
            if isinstance(exc, ValueError)
            else "PROVIDER_TIMEOUT"
        )
        reconnect = code in {
            "CONSENT_OR_TOKEN_REQUIRED",
            "ACCOUNT_NOT_CONSENTED",
            "CONSENT_REFERENCE_MISMATCH",
            "PROVIDER_CREDENTIALS_UNAVAILABLE",
            "BANK_ACCOUNT_IDENTITY_MISMATCH",
            "PROVIDER_ACCESS_REQUIRES_DECISION",
        }
        state.status = "reconnect_required" if reconnect else "retry_wait"
        delay = max(300, getattr(exc, "retry_after", 300))
        state.error_code = code
        state.checkpoint = {
            **state.checkpoint,
            "retry_at": (now + timedelta(seconds=delay)).isoformat(),
        }
        await session.flush()
        return {"status": state.status, "error_code": code}


async def disconnect(session, *, user_id, state_id):
    state = await owned_state(session, user_id, state_id)
    state.encrypted_credentials = None
    state.status, state.error_code = "disconnected", None
    await session.flush()
    return {
        "status": "disconnected",
        "provider_consent_revoked": False,
        "message": (
            "Local polling stopped and local tokens removed. Manage bank consent with the provider."
        ),
    }
