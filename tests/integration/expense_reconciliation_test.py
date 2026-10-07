"""Explicit owner resolution preserves booked values and suppresses only reviewed pending identity."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from src.db.models import ExpenseTransaction
from src.expenses.models import ExpenseAudit
from src.execution.policy import PolicyDenied
from src.expenses.persistence import upsert_transaction
from src.expenses.reconciliation import reconcile_pending, reconciliation_plan
from tests.integration.expense_retention_test import seed

pytestmark = pytest.mark.integration


async def pair(session):
    owners, rows, _, now = await seed(session)
    pending, booked = rows[:2]
    pending.pending, pending.lifecycle = True, "pending"
    pending.category, pending.subcategory = "health", "pharmacy"
    booked.category_override = False
    await session.flush()
    return owners, rows, dict(user_id=owners[0], pending_id=pending.id, booked_id=booked.id, as_of=now, now=now)


async def test_review_export_atomic_resolution_audit_and_reimport_suppression(db_session):
    owners, rows, args = await pair(db_session)
    pending, booked = rows[:2]
    item = {
        column.name: getattr(pending, column.name)
        for column in ExpenseTransaction.__table__.columns
        if column.name not in {"id", "user_id", "created_at", "updated_at", "synced_at"}
    }
    before = booked.amount, booked.currency, booked.occurred_at, booked.synced_at
    plan, exported, _, _ = await reconciliation_plan(db_session, **args)
    assert "secret_fixture" not in str(exported) and "raw_data" not in exported["pending"]
    assert plan["copy_pending_category"]
    result = await reconcile_pending(
        db_session, **args, expected_plan=plan["plan_sha256"], export_sha256=plan["export_sha256"]
    )
    assert result["removed_pending"] == 1 and not result["booked_amount_changed"]
    assert (booked.amount, booked.currency, booked.occurred_at, booked.synced_at) == before
    assert booked.category_override and booked.category == "health"
    assert not await db_session.scalar(select(ExpenseTransaction.id).where(ExpenseTransaction.id == pending.id))
    audit = await db_session.scalar(select(ExpenseAudit).where(ExpenseAudit.transaction_id == pending.id))
    assert audit.changes["basis"] == "explicit_owner_confirmation" and "secret_fixture" not in str(audit.changes)
    assert await upsert_transaction(db_session, user_id=owners[0], item=item, received_at=args["now"]) is None
    assert await upsert_transaction(db_session, user_id=owners[1], item=item, received_at=args["now"]) is True


async def test_changed_pair_expired_preview_wrong_owner_export_and_replay_denied(db_session):
    owners, rows, args = await pair(db_session)
    plan, _, _, _ = await reconciliation_plan(db_session, **args)
    apply = args | dict(expected_plan=plan["plan_sha256"], export_sha256=plan["export_sha256"])
    with pytest.raises(PolicyDenied, match="RECONCILIATION_EXPORT_MISMATCH"):
        await reconcile_pending(db_session, **(apply | {"export_sha256": "0" * 64}))
    with pytest.raises(PolicyDenied, match="TRANSACTIONS_NOT_OWNED"):
        await reconcile_pending(db_session, **(apply | {"user_id": owners[1]}))
    with pytest.raises(PolicyDenied, match="RECONCILIATION_PREVIEW_EXPIRED"):
        await reconcile_pending(db_session, **(apply | {"now": args["now"] + timedelta(minutes=11)}))
    rows[1].amount += 1
    await db_session.flush()
    with pytest.raises(PolicyDenied, match="RECONCILIATION_PLAN_CHANGED"):
        await reconcile_pending(db_session, **apply)
    fresh, _, _, _ = await reconciliation_plan(db_session, **args)
    await reconcile_pending(
        db_session, **args, expected_plan=fresh["plan_sha256"], export_sha256=fresh["export_sha256"]
    )
    with pytest.raises(PolicyDenied, match="TRANSACTIONS_NOT_OWNED"):
        await reconcile_pending(db_session, **apply)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("currency", "USD", "RECONCILIATION_SCOPE_MISMATCH"),
        ("account_key", "other", "RECONCILIATION_SCOPE_MISMATCH"),
        ("provider", "other", "RECONCILIATION_SCOPE_MISMATCH"),
        ("transaction_type", "income", "RECONCILIATION_SCOPE_MISMATCH"),
        ("lifecycle", "deleted", "PENDING_AND_SETTLED_REQUIRED"),
        ("category_override", True, "CATEGORY_OVERRIDE_CONFLICT"),
    ],
)
async def test_mismatched_scope_or_settled_state_and_category_conflict_rejected(db_session, field, value, reason):
    _, rows, args = await pair(db_session)
    setattr(rows[1], field, value)
    await db_session.flush()
    with pytest.raises(PolicyDenied, match=reason):
        await reconciliation_plan(db_session, **args)


async def test_unknown_transfer_direction_is_not_guessed(db_session):
    _, rows, args = await pair(db_session)
    for row in rows[:2]:
        row.transaction_type = "transfer"
    await db_session.flush()
    with pytest.raises(PolicyDenied, match="TRANSFER_DIRECTION_UNVERIFIED"):
        await reconciliation_plan(db_session, **args)


async def test_resolution_failure_rolls_back_removal_suppression_and_category(db_session):
    from unittest.mock import AsyncMock, patch

    from src.expenses.models import ExpenseRetirement

    owners, rows, args = await pair(db_session)
    ids = [row.id for row in rows[:2]]
    plan, _, _, _ = await reconciliation_plan(db_session, **args)
    with pytest.raises(RuntimeError, match="fixture storage failure"):
        async with db_session.begin_nested():
            with patch.object(db_session, "flush", AsyncMock(side_effect=RuntimeError("fixture storage failure"))):
                await reconcile_pending(
                    db_session, **args, expected_plan=plan["plan_sha256"], export_sha256=plan["export_sha256"]
                )
    assert (
        len((await db_session.scalars(select(ExpenseTransaction.id).where(ExpenseTransaction.id.in_(ids)))).all()) == 2
    )
    booked = await db_session.get(ExpenseTransaction, ids[1])
    assert not booked.category_override
    assert not (await db_session.scalars(select(ExpenseRetirement).where(ExpenseRetirement.user_id == owners[0]))).all()
    assert not (await db_session.scalars(select(ExpenseAudit).where(ExpenseAudit.user_id == owners[0]))).all()


async def test_concurrent_import_waits_then_cannot_resurrect_resolved_pending(integration_engine):
    import asyncio

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from src.db.models import User
    from src.expenses.models import ExpenseRetirement

    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    owners, task = [], None
    try:
        async with factory.begin() as session:
            owners, rows, args = await pair(session)
            item = {
                column.name: getattr(rows[0], column.name)
                for column in ExpenseTransaction.__table__.columns
                if column.name not in {"id", "user_id", "created_at", "updated_at", "synced_at"}
            }
            plan, _, _, _ = await reconciliation_plan(session, **args)
        started = asyncio.Event()

        async def reimport():
            async with factory.begin() as session:
                started.set()
                return await upsert_transaction(session, user_id=owners[0], item=item, received_at=args["now"])

        async with factory.begin() as session:
            await reconcile_pending(
                session, **args, expected_plan=plan["plan_sha256"], export_sha256=plan["export_sha256"]
            )
            task = asyncio.create_task(reimport())
            await asyncio.wait_for(started.wait(), 5)
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), 0.1)
        assert await asyncio.wait_for(task, 5) is None
        async with factory() as session:
            assert not await session.get(ExpenseTransaction, args["pending_id"])
            assert await session.get(ExpenseTransaction, args["booked_id"])
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if owners:
            async with factory.begin() as session:
                for model in (ExpenseTransaction, ExpenseAudit, ExpenseRetirement):
                    await session.execute(delete(model).where(model.user_id.in_(owners)))
                await session.execute(delete(User).where(User.id.in_(owners)))
