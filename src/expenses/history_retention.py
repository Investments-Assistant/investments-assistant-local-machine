"""Explicit owner-controlled normalized-history export and removal.

This is not global erasure: downstream reports/chat and backups are separate.
The caller owns the transaction. No model or scheduled caller chooses policy.
"""

from datetime import UTC, datetime

from sqlalchemy import Text, cast, func, delete, select
from sqlalchemy.orm import defer

from src.db.models import ExpenseTransaction
from src.expenses.models import ExpenseAudit, ExpenseRetirement
from src.execution.policy import PolicyDenied, digest
from src.expenses.persistence import expense_write_lock, retirement_identity

BATCH_SIZE = 100


def export_row(row):
    return {
        column.name: (
            getattr(row, column.name).isoformat()
            if isinstance(getattr(row, column.name), datetime)
            else format(getattr(row, column.name), ".10f")
            if column.name == "amount"
            else getattr(row, column.name)
        )
        for column in ExpenseTransaction.__table__.columns
        if column.name not in {"raw_data", "user_id"}
    }


async def history_plan(session, *, user_id, policy, now=None, lock=False):
    now = now or datetime.now(UTC)
    cutoff = policy.cutoff(now)
    # Shared with imports/providers: deletion and re-import suppression are atomic.
    await expense_write_lock(session, user_id)
    query = (
        select(
            ExpenseTransaction,
            func.encode(func.sha256(func.convert_to(cast(ExpenseTransaction.raw_data, Text), "UTF8")), "hex").label(
                "raw_sha256"
            ),
        )
        .where(
            ExpenseTransaction.user_id == user_id,
            ExpenseTransaction.occurred_at < cutoff,
            ExpenseTransaction.synced_at < cutoff,
            ExpenseTransaction.pending.is_(False),
            ExpenseTransaction.lifecycle.in_(["booked", "revised", "deleted"]),
        )
        .order_by(ExpenseTransaction.occurred_at, ExpenseTransaction.id)
        .limit(BATCH_SIZE)
    )
    query = query.options(defer(ExpenseTransaction.raw_data))
    if lock:
        query = query.with_for_update()
    selected = (await session.execute(query)).all()
    exported = [export_row(row) for row, _ in selected]
    export = dict(
        schema=1,
        scope="expense_normalized_history",
        policy=policy.model_dump(mode="json"),
        records=exported,
        count=len(exported),
        status="complete_batch",
        excludes="raw provider payloads",
    )
    export_hash = digest(export)
    identity = dict(
        owner=user_id,
        export_sha256=export_hash,
        rows=[dict(id=row.id, raw_sha256=raw_hash) for row, raw_hash in selected],
    )
    plan = dict(
        scope="expense_normalized_history",
        policy=policy.model_dump(mode="json"),
        count=len(selected),
        plan_sha256=digest(identity),
        export_sha256=export_hash,
        batch_limit=BATCH_SIZE,
        may_have_more=len(selected) == BATCH_SIZE,
        retained="Hashed import-suppression keys and minimal audit; reports/chat/backups are separate",
    )
    return plan, export


async def purge_history(session, *, user_id, policy, expected_plan, export_sha256, now=None):
    plan, export = await history_plan(session, user_id=user_id, policy=policy, now=now, lock=True)
    if plan["plan_sha256"] != expected_plan:
        raise PolicyDenied("RETENTION_PLAN_CHANGED")
    if plan["export_sha256"] != export_sha256:
        raise PolicyDenied("RETENTION_EXPORT_MISMATCH")
    ids = [row["id"] for row in export["records"]]
    for row in export["records"]:
        session.add(
            ExpenseRetirement(
                user_id=user_id, identity_sha256=retirement_identity(user_id, row), plan_sha256=expected_plan
            )
        )
    # Category-change audits may contain retained descriptive categories. Replace
    # the selected history with one minimal removal receipt per transaction.
    await session.execute(
        delete(ExpenseAudit).where(ExpenseAudit.user_id == user_id, ExpenseAudit.transaction_id.in_(ids))
    )
    for row in export["records"]:
        session.add(
            ExpenseAudit(
                user_id=user_id,
                transaction_id=row["id"],
                action="history_retention",
                changes=dict(plan_sha256=expected_plan, export_sha256=export_sha256),
            )
        )
    await session.execute(
        delete(ExpenseTransaction).where(ExpenseTransaction.user_id == user_id, ExpenseTransaction.id.in_(ids))
    )
    await session.flush()
    return dict(status="complete", removed_transactions=len(ids), scope=plan["scope"])
