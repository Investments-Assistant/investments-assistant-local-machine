"""Raw retention changes only approved owned payloads on disposable PostgreSQL."""

import uuid
from decimal import Decimal
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from src.expenses import retention
from src.db.models import User, ExpenseTransaction
from src.expenses.models import ExpenseAudit
from src.execution.policy import PolicyDenied

pytestmark = pytest.mark.integration


async def seed(session):
    now = datetime.now(UTC)
    owners = [str(uuid.uuid4()), str(uuid.uuid4())]
    session.add_all(
        [User(id=owner, username=uuid.uuid4().hex, password_hash="fixture", is_active=True) for owner in owners]
    )
    rows = []
    for index, (owner, days) in enumerate([(owners[0], 60), (owners[0], 60), (owners[0], 1), (owners[1], 60)]):
        row = ExpenseTransaction(
            id=str(uuid.uuid4()),
            user_id=owner,
            provider="fixture",
            external_id=str(index),
            account_key="fixture",
            account_name="Synthetic",
            merchant="Fixture",
            description="Fixture",
            amount=Decimal("0.004"),
            currency="EUR",
            transaction_type="expense",
            category="other",
            category_override=True,
            occurred_at=now - timedelta(days=90),
            raw_data={"secret_fixture": str(index)},
            synced_at=now - timedelta(days=days),
            updated_at=now - timedelta(days=days),
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    return owners, rows, retention.RawRetentionPolicy(retain_days=30, as_of=now), now


async def test_retention_preserves_financial_history_and_receipt_clocks(db_session, monkeypatch):
    owners, rows, policy, now = await seed(db_session)
    monkeypatch.setattr(retention, "BATCH_SIZE", 1)
    plan, selected = await retention.raw_payload_plan(db_session, user_id=owners[0], policy=policy, now=now)
    assert plan["count"] == 1 and plan["may_have_more"]
    assert "secret_fixture" not in str(plan)
    row = await db_session.get(ExpenseTransaction, selected[0].id)
    clocks = row.synced_at, row.updated_at
    result = await retention.remove_raw_payloads(
        db_session, user_id=owners[0], policy=policy, expected_plan=plan["plan_sha256"], now=now
    )
    await db_session.refresh(row)
    assert result["removed_raw_payloads"] == 1 and row.raw_data == {}
    assert (row.synced_at, row.updated_at) == clocks
    assert row.amount == Decimal("0.004") and row.currency == "EUR" and row.category_override
    assert all(other.raw_data for other in rows if other.id != row.id)
    audits = (await db_session.scalars(select(ExpenseAudit).where(ExpenseAudit.user_id == owners[0]))).all()
    assert len(audits) == 1 and "secret_fixture" not in str(audits[0].changes)
    with pytest.raises(PolicyDenied, match="RETENTION_PLAN_CHANGED"):
        await retention.remove_raw_payloads(
            db_session, user_id=owners[0], policy=policy, expected_plan=plan["plan_sha256"], now=now
        )


async def test_retention_rejects_changed_data_owner_expiry_and_inactive_principal(db_session):
    owners, rows, policy, now = await seed(db_session)
    plan, _ = await retention.raw_payload_plan(db_session, user_id=owners[0], policy=policy, now=now)
    with pytest.raises(PolicyDenied, match="RETENTION_PLAN_CHANGED"):
        await retention.remove_raw_payloads(
            db_session, user_id=owners[1], policy=policy, expected_plan=plan["plan_sha256"], now=now
        )
    rows[0].raw_data = {"revised": True}
    await db_session.flush()
    with pytest.raises(PolicyDenied, match="RETENTION_PLAN_CHANGED"):
        await retention.remove_raw_payloads(
            db_session, user_id=owners[0], policy=policy, expected_plan=plan["plan_sha256"], now=now
        )
    with pytest.raises(PolicyDenied, match="RETENTION_PREVIEW_EXPIRED"):
        await retention.raw_payload_plan(db_session, user_id=owners[0], policy=policy, now=now + timedelta(minutes=11))
    user = await db_session.get(User, owners[0])
    user.is_active = False
    await db_session.flush()
    with pytest.raises(PolicyDenied, match="PRINCIPAL_INACTIVE"):
        await retention.raw_payload_plan(db_session, user_id=owners[0], policy=policy, now=now)


async def test_retention_audit_failure_rolls_back_payload_removal(db_session):
    owners, rows, policy, now = await seed(db_session)
    row_id = rows[0].id
    plan, _ = await retention.raw_payload_plan(db_session, user_id=owners[0], policy=policy, now=now)
    with pytest.raises(RuntimeError, match="audit fixture"):
        async with db_session.begin_nested():
            with patch.object(db_session, "flush", AsyncMock(side_effect=RuntimeError("audit fixture"))):
                await retention.remove_raw_payloads(
                    db_session, user_id=owners[0], policy=policy, expected_plan=plan["plan_sha256"], now=now
                )
    row = await db_session.get(ExpenseTransaction, row_id)
    assert row.raw_data
    assert not (await db_session.scalars(select(ExpenseAudit).where(ExpenseAudit.user_id == owners[0]))).all()
