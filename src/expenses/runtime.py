"""Explicitly gated production factory and durable, user-scoped polling."""

import httpx
from sqlalchemy import select
from cryptography.fernet import Fernet

from src import config
from src.db.models import User
from src.db.database import async_session
from src.operations.models import BankSyncState
from src.operations.runner import run_scoped
from src.expenses.providers import GoCardless, ProviderError
from src.expenses.provider_sync import sync_account


def configured():
    settings = config.settings
    return settings.bank_sync_enabled is True and bool(settings.bank_credentials_key)


def dependencies():
    if not configured():
        raise ProviderError("BANK_ACCESS_NOT_AUTHORIZED")
    try:
        vault = Fernet(config.settings.bank_credentials_key.encode())
    except (ValueError, TypeError) as exc:
        raise ProviderError("PROVIDER_CREDENTIALS_UNAVAILABLE") from exc
    return GoCardless(transport=httpx.AsyncHTTPTransport(retries=0)), vault


async def poll_connections():
    if not configured():
        return
    async with async_session() as session:
        states = (
            await session.execute(
                select(BankSyncState.id, BankSyncState.user_id)
                .join(User, User.id == BankSyncState.user_id)
                .where(
                    User.is_active.is_(True), BankSyncState.status.in_(["connected", "retry_wait"])
                )
                .order_by(BankSyncState.last_success_at.asc().nullsfirst(), BankSyncState.id)
                .limit(20)
            )
        ).all()
    for state_id, user_id in states:

        async def fetch(owner, selected_state=state_id):
            provider, vault = dependencies()
            async with async_session.begin() as session:
                result = await sync_account(
                    session, user_id=owner, state_id=selected_state, provider=provider, vault=vault
                )
            # Commit typed provider state before the scheduler records failure.
            if result["status"] != "complete":
                raise ProviderError(result.get("error_code", "BANK_SYNC_INCOMPLETE"))
            from src.web.routes import _publish_expense_event

            await _publish_expense_event(owner, {"provider": "gocardless", **result})

        await run_scoped(
            user_id,
            "bank:" + state_id,
            fetch,
            interval_seconds=config.settings.bank_sync_interval_seconds,
        )
