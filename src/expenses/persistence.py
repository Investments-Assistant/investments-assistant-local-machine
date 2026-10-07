"""One atomic write path for imports and provider synchronization.

Conflict identity includes user, provider, bank account and external transaction.
Return True only for a newly inserted generated row identity; never guess counts
from a preceding SELECT that can race a provider update.
"""

import uuid

from sqlalchemy import case, text, select
from sqlalchemy.dialects.postgresql import insert

from src.db.models import User, ExpenseTransaction
from src.expenses.models import ExpenseRetirement
from src.execution.policy import PolicyDenied, digest


def retirement_identity(user_id, item):
    return digest([user_id, item["provider"], item["account_key"], item["external_id"]])


async def expense_write_lock(session, user_id):
    # A transaction-scoped owner lock serializes import with purge. Hash collisions
    # only serialize unrelated owners; they cannot grant access or mix data.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": "expense-history:" + str(user_id)}
    )
    if not user_id or not await session.scalar(
        select(User.id).where(User.id == user_id, User.is_active.is_(True)).with_for_update(read=True)
    ):
        raise PolicyDenied("PRINCIPAL_INACTIVE")


async def upsert_transaction(session, *, user_id, item, received_at):
    """True inserted, False updated, None suppressed by explicit retirement."""
    await expense_write_lock(session, user_id)
    if await session.get(ExpenseRetirement, (user_id, retirement_identity(user_id, item))):
        return None
    row_id = str(uuid.uuid4())
    statement = insert(ExpenseTransaction).values(id=row_id, user_id=user_id, **item, synced_at=received_at)
    updates = {
        key: getattr(statement.excluded, key) for key in item if key not in {"provider", "external_id", "account_key"}
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
