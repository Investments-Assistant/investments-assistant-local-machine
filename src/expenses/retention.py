"""Explicit owner-scoped raw-payload retention; never deletes financial history."""

from datetime import UTC, datetime, timedelta

from pydantic import Field, BaseModel, ConfigDict
from sqlalchemy import Text, cast, func, text, select, update

from src.db.models import User, ExpenseTransaction
from src.expenses.models import ExpenseAudit
from src.execution.policy import PolicyDenied, digest

BATCH_SIZE = 500


class RawRetentionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    retain_days: int = Field(ge=1, le=36525, strict=True)
    as_of: datetime

    def cutoff(self, now: datetime):
        if self.as_of.tzinfo is None or not now - timedelta(minutes=10) <= self.as_of <= now:
            raise PolicyDenied("RETENTION_PREVIEW_EXPIRED")
        return self.as_of - timedelta(days=self.retain_days)


async def raw_payload_plan(session, *, user_id: str, policy: RawRetentionPolicy, lock=False, now=None):
    now = now or datetime.now(UTC)
    cutoff = policy.cutoff(now)
    principal_query = select(User.id).where(User.id == user_id, User.is_active.is_(True))
    if lock:
        principal_query = principal_query.with_for_update()
    if not user_id or not await session.scalar(principal_query):
        raise PolicyDenied("PRINCIPAL_INACTIVE")
    query = (
        select(
            ExpenseTransaction.id,
            ExpenseTransaction.synced_at,
            ExpenseTransaction.updated_at,
            func.encode(
                func.sha256(func.convert_to(cast(ExpenseTransaction.raw_data, Text), "UTF8")), "hex"
            ).label("raw_sha256"),
        )
        .where(
            ExpenseTransaction.user_id == user_id,
            ExpenseTransaction.synced_at < cutoff,
            # Literal matches the partial-index predicate even for prepared plans.
            text("raw_data::jsonb <> '{}'::jsonb"),
        )
        .order_by(ExpenseTransaction.synced_at, ExpenseTransaction.id)
        .limit(BATCH_SIZE)
    )
    if lock:
        query = query.with_for_update()
    rows = (await session.execute(query)).all()
    identity = {
        "owner": user_id,
        "scope": "expense_raw_payload_only",
        "policy": policy.model_dump(mode="json"),
        "rows": [
            {"id": row.id, "received": row.synced_at.isoformat(), "raw_sha256": row.raw_sha256} for row in rows
        ],
    }
    return {
        "scope": identity["scope"],
        "policy": identity["policy"],
        "count": len(rows),
        "batch_limit": BATCH_SIZE,
        "plan_sha256": digest(identity),
        "may_have_more": len(rows) == BATCH_SIZE,
        "retained": "Normalized transactions, categories, financial history and receipt clocks",
    }, rows


async def remove_raw_payloads(session, *, user_id: str, policy: RawRetentionPolicy, expected_plan: str, now=None):
    """Caller owns the transaction; row locks keep preview comparison and audit atomic."""
    plan, rows = await raw_payload_plan(session, user_id=user_id, policy=policy, lock=True, now=now)
    if plan["plan_sha256"] != expected_plan:
        raise PolicyDenied("RETENTION_PLAN_CHANGED")
    for row in rows:
        previous_hash = row.raw_sha256
        # Explicit clocks prevent SQLAlchemy onupdate defaults from impersonating a receipt.
        await session.execute(
            update(ExpenseTransaction)
            .where(ExpenseTransaction.id == row.id, ExpenseTransaction.user_id == user_id)
            .values(raw_data={}, updated_at=row.updated_at, synced_at=row.synced_at)
        )
        session.add(
            ExpenseAudit(
                user_id=user_id,
                transaction_id=row.id,
                action="raw_payload_retention",
                changes={"previous_sha256": previous_hash, "plan_sha256": expected_plan, "policy": plan["policy"]},
            )
        )
    await session.flush()
    return {"status": "complete", "removed_raw_payloads": len(rows), "scope": plan["scope"]}
