"""Internal simulator ledger evidence; never connects to an external broker."""

from decimal import Decimal
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from src.execution.models import ExecutionEvent, SimulatorAccount, SimulatorPosition
from src.execution.policy import PolicyDenied
from src.execution.service import record_fill
from src.execution.commissions import record_commission
from src.execution.reconciliation import reconcile_account
from tests.integration.execution_test import seed, proposal, confirmation
from tests.integration.commissions_test import callback

pytestmark = pytest.mark.integration


async def setup_order(session, quantity="1"):
    ids = await seed(session)
    proposed = await proposal(session, ids, quantity=quantity)
    await confirmation(session, ids, proposed)
    return ids, proposed["order_id"], await session.get(SimulatorAccount, ids[1])


async def execution(session, ids, order, execution_id="fixture-exec", quantity="1", price="100"):
    return await record_fill(
        session,
        user_id=ids[0],
        account_id=ids[1],
        order_id=order,
        execution_id=execution_id,
        quantity=quantity,
        price=price,
    )


async def test_partial_fills_late_commissions_and_database_round_trip(db_session):
    ids, order, account = await setup_order(db_session, "3")
    for index in range(3):
        await execution(db_session, ids, order, execution_id=f"part-{index}")
        await db_session.flush()
        await db_session.refresh(account)
        result = await reconcile_account(db_session, account)
        assert result["status"] == "consistent", result
    await record_commission(db_session, **callback(ids, order, datetime.now(UTC), execution_id="part-0"))
    await db_session.flush()
    db_session.expire_all()
    account = await db_session.get(SimulatorAccount, ids[1])
    result = await reconcile_account(db_session, account)
    assert result["status"] == "consistent" and result["events_checked"] == 4
    assert (await reconcile_account(db_session, account))["evidence_sha256"] == result["evidence_sha256"]


@pytest.mark.parametrize("field", ["cash", "reserved", "position_quantity", "position_cost_basis"])
async def test_discrepancy_detected_without_overwriting_balances(db_session, field):
    ids, order, account = await setup_order(db_session)
    await execution(db_session, ids, order)
    position = await db_session.scalar(select(SimulatorPosition).where(SimulatorPosition.account_id == ids[1]))
    target, attr = (position, field.removeprefix("position_")) if field.startswith("position_") else (account, field)
    original = getattr(target, attr)
    setattr(target, attr, original + Decimal(1))
    await db_session.flush()
    result = await reconcile_account(db_session, account)
    assert result["status"] == "discrepant"
    assert field in {item["field"] for item in result["discrepancies"]}
    assert getattr(target, attr) == original + 1
    other = await seed(db_session)
    assert (await reconcile_account(db_session, await db_session.get(SimulatorAccount, other[1])))[
        "status"
    ] == "consistent"


async def test_incomplete_evidence_is_unverified_not_fabricated_cash(db_session):
    ids, order, account = await setup_order(db_session)
    await record_commission(db_session, **callback(ids, order, datetime.now(UTC)))
    assert (await reconcile_account(db_session, account))["status"] == "unverified"
    await execution(db_session, ids, order)
    event = await db_session.scalar(
        select(ExecutionEvent).where(ExecutionEvent.order_id == order, ExecutionEvent.kind == "fill")
    )
    event.payload = {key: value for key, value in event.payload.items() if key != "principal_base"}
    await db_session.flush()
    result = await reconcile_account(db_session, account)
    assert result["status"] == "unverified"
    assert "cash" not in {item["field"] for item in result["discrepancies"]}
    assert account.cash == Decimal("899.95")


async def test_unrepresentable_fill_principal_rejected_before_ledger_changes(db_session):
    ids, order, account = await setup_order(db_session)
    with pytest.raises(PolicyDenied, match="UNSUPPORTED_PRECISION"):
        await execution(db_session, ids, order, quantity="0.001", price="99.1234567891")
    assert account.cash == 1000
    assert (await reconcile_account(db_session, account))["status"] == "consistent"


async def test_joint_reservation_tamper_does_not_hide_behind_matching_totals(db_session):
    ids, order_id, account = await setup_order(db_session, "2")
    await execution(db_session, ids, order_id)
    from src.execution.models import SimulatorOrder

    order = await db_session.get(SimulatorOrder, order_id)
    before = await reconcile_account(db_session, account)
    assert before["status"] == "consistent"
    order.reserve += 1
    account.reserved += 1
    await db_session.flush()
    after = await reconcile_account(db_session, account)
    assert after["status"] == "discrepant"
    assert "order_remaining_reserve" in {item["field"] for item in after["discrepancies"]}
    assert before["inputs_sha256"] != after["inputs_sha256"]


async def test_partial_release_retains_subscale_dust_until_final_fill(db_session):
    ids = await seed(db_session)
    account = await db_session.get(SimulatorAccount, ids[1])
    account.mandate = dict(account.mandate, fee_bps="0.000001")
    proposed = await proposal(db_session, ids, quantity="3")
    await confirmation(db_session, ids, proposed)
    assert account.reserved == Decimal("300.00000003")
    await execution(db_session, ids, proposed["order_id"], execution_id="first", quantity="0.001")
    await db_session.refresh(account)
    assert account.reserved == Decimal("299.90000003")
    assert (await reconcile_account(db_session, account))["status"] == "consistent"
    await execution(db_session, ids, proposed["order_id"], execution_id="last", quantity="2.999")
    await db_session.refresh(account)
    assert account.reserved == 0 and account.cash == 700
    assert (await reconcile_account(db_session, account))["status"] == "consistent"
