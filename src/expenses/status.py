"""Owner-scoped sync clocks, independent of the displayed transaction page."""

from sqlalchemy import func, select

from src.db.models import ExpenseTransaction
from src.operations.models import BankSyncState


async def sync_clocks(session, user_id: str) -> dict:
    received = await session.scalar(
        select(func.max(ExpenseTransaction.synced_at)).where(ExpenseTransaction.user_id == user_id)
    )
    provider = (
        await session.execute(
            select(
                func.max(BankSyncState.last_received_at), func.max(BankSyncState.last_success_at)
            ).where(BankSyncState.user_id == user_id)
        )
    ).one()
    clocks = [value for value in (received, provider[0]) if value is not None]
    return {
        "last_received_at": max(clocks).isoformat() if clocks else None,
        "provider_last_success_at": provider[1].isoformat() if provider[1] else None,
        "provider_timestamp_scope": "most_recent_success_across_owned_connections",
    }
