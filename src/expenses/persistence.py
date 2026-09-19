"""One atomic write path for imports and provider synchronization.

Conflict identity includes user, provider, bank account and external transaction.
Return True only for a newly inserted generated row identity; never guess counts
from a preceding SELECT that can race a provider update.
"""

import uuid

from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert

from src.db.models import ExpenseTransaction


async def upsert_transaction(session, *, user_id, item, received_at):
    row_id = str(uuid.uuid4())
    statement = insert(ExpenseTransaction).values(
        id=row_id, user_id=user_id, **item, synced_at=received_at
    )
    updates = {
        key: getattr(statement.excluded, key)
        for key in item
        if key not in {"provider", "external_id", "account_key"}
    }
    for key in ("category", "subcategory"):
        updates[key] = case(
            (ExpenseTransaction.category_override.is_(True), getattr(ExpenseTransaction, key)),
            else_=getattr(statement.excluded, key),
        )
    updates.update(synced_at=received_at, updated_at=received_at)
    result = await session.execute(
        statement.on_conflict_do_update(
            constraint="uq_expense_transactions_user_provider_external",
            set_=updates,
        ).returning(ExpenseTransaction.id)
    )
    return result.scalar_one() == row_id
