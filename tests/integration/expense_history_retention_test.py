"""Owner-approved normalized-history erasure is export-bound and replay-safe."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from src.db.models import ExpenseTransaction
from src.execution.policy import PolicyDenied
from src.expenses.persistence import upsert_transaction
from src.expenses.history_retention import history_plan, purge_history
from tests.integration.expense_retention_test import seed

pytestmark = pytest.mark.integration


async def test_exact_export_bound_purge_preserves_other_owner_and_blocks_reimport(db_session):
    owners, rows, policy, now = await seed(db_session)
    original = rows[0]
    item = {
        column.name: getattr(original, column.name)
        for column in ExpenseTransaction.__table__.columns
        if column.name not in {"id", "user_id", "synced_at", "updated_at", "created_at"}
    }
    plan, export = await history_plan(db_session, user_id=owners[0], policy=policy, now=now)
    assert plan["count"] == 2  # Recent provider receipt is not silently erased.
    assert "secret_fixture" not in str(plan) and "secret_fixture" not in str(export)
    result = await purge_history(
        db_session,
        user_id=owners[0],
        policy=policy,
        expected_plan=plan["plan_sha256"],
        export_sha256=plan["export_sha256"],
        now=now,
    )
    assert result["removed_transactions"] == 2
    remaining = (await db_session.scalars(select(ExpenseTransaction))).all()
    assert rows[2] in remaining and rows[3] in remaining
    assert await upsert_transaction(db_session, user_id=owners[0], item=item, received_at=now) is None
    assert await upsert_transaction(db_session, user_id=owners[1], item=item, received_at=now) is True
    assert not await db_session.scalar(select(ExpenseTransaction.id).where(ExpenseTransaction.id == original.id))


async def test_stale_changed_wrong_owner_or_missing_export_fails_closed(db_session):
    owners, rows, policy, now = await seed(db_session)
    plan, _ = await history_plan(db_session, user_id=owners[0], policy=policy, now=now)
    args = dict(
        user_id=owners[0],
        policy=policy,
        expected_plan=plan["plan_sha256"],
        export_sha256=plan["export_sha256"],
        now=now,
    )
    with pytest.raises(PolicyDenied, match="RETENTION_EXPORT_MISMATCH"):
        await purge_history(db_session, **(args | {"export_sha256": "0" * 64}))
    with pytest.raises(PolicyDenied, match="RETENTION_PLAN_CHANGED"):
        await purge_history(db_session, **(args | {"user_id": owners[1]}))
    with pytest.raises(PolicyDenied, match="RETENTION_PREVIEW_EXPIRED"):
        await purge_history(db_session, **(args | {"now": now + timedelta(minutes=11)}))
    rows[0].category = "changed"
    await db_session.flush()
    with pytest.raises(PolicyDenied, match="RETENTION_PLAN_CHANGED"):
        await purge_history(db_session, **args)
    assert len((await db_session.scalars(select(ExpenseTransaction))).all()) >= 4


async def test_purge_failure_rolls_back_suppression_and_all_history(db_session):
    from unittest.mock import AsyncMock, patch

    from src.expenses.models import ExpenseRetirement

    owners, rows, policy, now = await seed(db_session)
    plan, _ = await history_plan(db_session, user_id=owners[0], policy=policy, now=now)
    ids = [row.id for row in rows[:2]]
    with pytest.raises(RuntimeError, match="fixture commit failure"):
        async with db_session.begin_nested():
            with patch.object(db_session, "flush", AsyncMock(side_effect=RuntimeError("fixture commit failure"))):
                await purge_history(
                    db_session,
                    user_id=owners[0],
                    policy=policy,
                    expected_plan=plan["plan_sha256"],
                    export_sha256=plan["export_sha256"],
                    now=now,
                )
    assert (
        len((await db_session.scalars(select(ExpenseTransaction.id).where(ExpenseTransaction.id.in_(ids)))).all()) == 2
    )
    assert not (await db_session.scalars(select(ExpenseRetirement).where(ExpenseRetirement.user_id == owners[0]))).all()


async def test_pending_and_active_owner_checks_and_exact_batch(db_session, monkeypatch):
    from src.expenses import history_retention
    from src.db.models import User

    owners, rows, policy, now = await seed(db_session)
    rows[0].pending = True
    await db_session.flush()
    monkeypatch.setattr(history_retention, "BATCH_SIZE", 1)
    plan, exported = await history_plan(db_session, user_id=owners[0], policy=policy, now=now)
    assert plan["count"] == 1 and plan["may_have_more"]
    assert exported["records"][0]["id"] == rows[1].id
    (await db_session.get(User, owners[0])).is_active = False
    await db_session.flush()
    with pytest.raises(PolicyDenied, match="PRINCIPAL_INACTIVE"):
        await purge_history(
            db_session,
            user_id=owners[0],
            policy=policy,
            expected_plan=plan["plan_sha256"],
            export_sha256=plan["export_sha256"],
            now=now,
        )


async def test_concurrent_import_waits_for_purge_then_is_suppressed(integration_engine):
    import asyncio

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from src.db.models import User
    from src.expenses.models import ExpenseAudit, ExpenseRetirement

    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    owners = []
    try:
        async with factory.begin() as session:
            owners, rows, policy, now = await seed(session)
            item = {
                column.name: getattr(rows[0], column.name)
                for column in ExpenseTransaction.__table__.columns
                if column.name not in {"id", "user_id", "synced_at", "updated_at", "created_at"}
            }
            plan, _ = await history_plan(session, user_id=owners[0], policy=policy, now=now)
        started = asyncio.Event()

        async def reimport():
            async with factory.begin() as session:
                started.set()
                return await upsert_transaction(session, user_id=owners[0], item=item, received_at=now)

        async with factory.begin() as session:
            await purge_history(
                session,
                user_id=owners[0],
                policy=policy,
                expected_plan=plan["plan_sha256"],
                export_sha256=plan["export_sha256"],
                now=now,
            )
            pending = asyncio.create_task(reimport())
            await started.wait()
            # The concurrent import stays pending until purge commits.
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(pending), 0.1)
        assert await asyncio.wait_for(pending, 5) is None
        async with factory() as session:
            assert not await session.scalar(
                select(ExpenseTransaction.id).where(
                    ExpenseTransaction.user_id == owners[0], ExpenseTransaction.external_id == item["external_id"]
                )
            )
    finally:
        if owners:
            async with factory.begin() as session:
                for model in (ExpenseTransaction, ExpenseAudit, ExpenseRetirement):
                    await session.execute(delete(model).where(model.user_id.in_(owners)))
                await session.execute(delete(User).where(User.id.in_(owners)))
