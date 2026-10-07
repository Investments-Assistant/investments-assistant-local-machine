import uuid
from decimal import Decimal
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from src.execution.models import SimulatorAccount, SimulatorPosition, SimulatorInstrument
from src.execution.policy import PolicyDenied
from src.execution.service import propose, transition, record_fill
from src.execution.commissions import record_commission
from src.execution.reconciliation import reconcile_account
from tests.integration.execution_test import seed, proposal, confirmation
from tests.integration.commissions_test import callback

pytestmark = pytest.mark.integration


async def owned(session):
    ids = await seed(session)
    account = await session.get(SimulatorAccount, ids[1])
    account.mandate = dict(account.mandate, fixture=True, manual_sales=True)
    buy = await proposal(session, ids, quantity="2")
    await confirmation(session, ids, buy)
    await record_fill(session, user_id=ids[0], account_id=ids[1], order_id=buy["order_id"],
                      execution_id="buy", quantity="2", price="100")
    instrument = await session.get(SimulatorInstrument, ids[2])
    instrument.price = Decimal(120)
    instrument.as_of = datetime.now(UTC)
    return ids, account, buy


async def sell(session, ids, quantity="1", key=None):
    return await propose(session, user_id=ids[0], account_id=ids[1], session_id="human-session",
                         instrument_id=ids[2], quantity=quantity, limit_price="120", side="sell",
                         idempotency_key=key or uuid.uuid4().hex)


@pytest.mark.parametrize("fee_before", [False, True])
async def test_manual_sale_approval_fill_and_late_purchase_fee(db_session, fee_before):
    ids, account, buy = await owned(db_session)
    sale = await sell(db_session, ids)
    assert sale["details"]["side"] == "sell"
    await confirmation(db_session, ids, sale)
    assert account.reserved == Decimal("0.12")
    if fee_before:
        await record_commission(db_session, **callback(ids, sale["order_id"], datetime.now(UTC),
                                                       execution_id="sale", amount="0.10"))
        pending = await reconcile_account(db_session, account)
        assert pending["status"] == "unverified" and pending["allocation_inventory"] is None
    result = await record_fill(db_session, user_id=ids[0], account_id=ids[1], order_id=sale["order_id"],
                               execution_id="sale", quantity="1", price="120", fee="0.10")
    assert result["status"] == "filled"
    assert account.cash == Decimal("919.90") and account.realized_pnl == Decimal("19.90")
    assert account.reserved == 0
    assert (await reconcile_account(db_session, account))["status"] == "consistent"
    await record_commission(db_session, **callback(ids, buy["order_id"], datetime.now(UTC),
                                                   execution_id="buy", amount="0.20"))
    position = await db_session.scalar(select(SimulatorPosition).where(SimulatorPosition.account_id == ids[1]))
    assert position.quantity == 1 and position.cost_basis == Decimal("100.10")
    assert account.realized_pnl == Decimal("19.80") and account.cash == Decimal("919.70")
    assert (await reconcile_account(db_session, account))["status"] == "consistent"


async def test_sale_reservation_is_checked_again_on_approval_and_cancel_releases(db_session):
    ids, account, _ = await owned(db_session)
    first = await sell(db_session, ids, "2")
    second = await sell(db_session, ids, "1")
    await confirmation(db_session, ids, first)
    with pytest.raises(PolicyDenied, match="INSUFFICIENT_OWNED_QUANTITY"):
        await confirmation(db_session, ids, second)
    await transition(db_session, user_id=ids[0], account_id=ids[1], order_id=first["order_id"],
                     status="cancel_requested", event_key="cancel-request")
    with pytest.raises(PolicyDenied, match="INSUFFICIENT_OWNED_QUANTITY"):
        await confirmation(db_session, ids, second)
    await transition(db_session, user_id=ids[0], account_id=ids[1], order_id=first["order_id"],
                     status="cancelled", event_key="cancel-ack")
    await confirmation(db_session, ids, second)
    assert account.reserved == Decimal("0.12")


async def test_existing_accounts_and_protected_allocations_do_not_gain_sale_authority(db_session):
    ids = await seed(db_session)
    with pytest.raises(PolicyDenied, match="SELL_CAPABILITY_UNAVAILABLE"):
        await sell(db_session, ids)
    account = await db_session.get(SimulatorAccount, ids[1])
    account.mandate = dict(account.mandate, fixture=True, manual_sales=True)
    instrument = await db_session.get(SimulatorInstrument, ids[2])
    instrument.protected = True
    with pytest.raises(PolicyDenied, match="PROTECTED_ALLOCATION"):
        await sell(db_session, ids)


async def test_partial_sale_keeps_remaining_quantity_reserved_and_duplicate_fill_is_idempotent(db_session):
    ids, account, _ = await owned(db_session)
    sale = await sell(db_session, ids, "2")
    await confirmation(db_session, ids, sale)
    args = dict(user_id=ids[0], account_id=ids[1], order_id=sale["order_id"],
                execution_id="partial", quantity="1", price="120", fee="0.10")
    await record_fill(db_session, **args)
    assert account.cash == Decimal("919.90") and account.reserved == Decimal("0.12")
    inventory = (await reconcile_account(db_session, account))["allocation_inventory"][0]
    assert Decimal(inventory["quantity"]) == Decimal(inventory["reserved_quantity"]) == 1
    assert Decimal(inventory["available_quantity"]) == 0
    assert (await record_fill(db_session, **args))["deduplicated"]
    assert account.cash == Decimal("919.90")
    await record_fill(db_session, **(args | {"execution_id": "final"}))
    assert account.cash == Decimal("1039.80") and account.realized_pnl == Decimal("39.80")
    assert account.reserved == 0
    inventory = (await reconcile_account(db_session, account))["allocation_inventory"][0]
    assert Decimal(inventory["quantity"]) == Decimal(inventory["cost_basis"]) == 0


async def test_cancelled_sale_late_fill_is_recorded_and_halts_new_orders(db_session):
    ids, account, _ = await owned(db_session)
    sale = await sell(db_session, ids)
    await confirmation(db_session, ids, sale)
    await transition(db_session, user_id=ids[0], account_id=ids[1], order_id=sale["order_id"],
                     status="cancelled", event_key="cancel-ack")
    result = await record_fill(db_session, user_id=ids[0], account_id=ids[1], order_id=sale["order_id"],
                               execution_id="late", quantity="1", price="120", fee="0.10")
    assert result["status"] == "filled"
    assert account.halted and account.halt_reason == "FILL_RECONCILIATION_DISCREPANCY"
    assert account.cash == Decimal("919.90") and account.realized_pnl == Decimal("19.90")
    with pytest.raises(PolicyDenied, match="OPERATOR_HALTED"):
        await sell(db_session, ids)


async def test_concurrent_sale_approvals_reserve_owned_quantity_once(integration_engine):
    import asyncio

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from src.db.models import User
    from src.execution.models import ExecutionEvent, SimulatorOrder

    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with factory.begin() as session:
        ids, _, _ = await owned(session)
        first = await sell(session, ids, "2")
        second = await sell(session, ids, "2")
    try:
        async def approve_one(candidate):
            try:
                async with factory.begin() as session:
                    return (await confirmation(session, ids, candidate))["status"]
            except PolicyDenied as exc:
                return exc.code

        results = await asyncio.gather(approve_one(first), approve_one(second))
        assert sorted(results) == ["INSUFFICIENT_OWNED_QUANTITY", "submitted"]
        async with factory.begin() as session:
            account = await session.get(SimulatorAccount, ids[1])
            assert account.reserved == Decimal("0.24")
            result = await reconcile_account(session, account)
            assert result["status"] == "consistent"
            inventory = result["allocation_inventory"][0]
            assert Decimal(inventory["reserved_quantity"]) == 2
            assert Decimal(inventory["available_quantity"]) == 0
    finally:
        async with factory.begin() as session:
            orders = select(SimulatorOrder.id).where(SimulatorOrder.account_id == ids[1])
            await session.execute(delete(ExecutionEvent).where(ExecutionEvent.order_id.in_(orders)))
            await session.execute(delete(SimulatorOrder).where(SimulatorOrder.account_id == ids[1]))
            await session.execute(delete(SimulatorPosition).where(SimulatorPosition.account_id == ids[1]))
            await session.execute(delete(SimulatorInstrument).where(SimulatorInstrument.account_id == ids[1]))
            await session.execute(delete(SimulatorAccount).where(SimulatorAccount.id == ids[1]))
            await session.execute(delete(User).where(User.id == ids[0]))


@pytest.mark.parametrize("fee_policy", ["-1", "NaN", "Infinity", "101"])
async def test_sale_fee_reservation_cannot_use_invalid_policy(db_session, fee_policy):
    ids, account, _ = await owned(db_session)
    account.mandate = dict(account.mandate, fee_bps=fee_policy)
    with pytest.raises(PolicyDenied, match="INVALID_FEE_POLICY"):
        await sell(db_session, ids)
    assert account.reserved == 0


@pytest.mark.parametrize("legacy", [False, True])
async def test_late_sale_after_inventory_reuse_keeps_duplicate_unreconciled(db_session, legacy):
    from src.execution.models import ExecutionEvent

    ids, account, _ = await owned(db_session)
    cancelled = await sell(db_session, ids, "2")
    await confirmation(db_session, ids, cancelled)
    await transition(db_session, user_id=ids[0], account_id=ids[1], order_id=cancelled["order_id"],
                     status="cancelled", event_key="cancel-ack")
    replacement = await sell(db_session, ids, "2")
    await confirmation(db_session, ids, replacement)
    await record_fill(db_session, user_id=ids[0], account_id=ids[1], order_id=replacement["order_id"],
                      execution_id="replacement", quantity="2", price="120", fee="0.20")
    settled_cash = account.cash
    args = dict(user_id=ids[0], account_id=ids[1], order_id=cancelled["order_id"],
                execution_id="late-unowned", quantity="2", price="120", fee="0.20")
    result = await record_fill(db_session, **args)
    assert result["status"] == "reconciliation_required" and account.halted
    assert account.cash == settled_cash
    if legacy:
        old_event = await db_session.scalar(select(ExecutionEvent).where(
            ExecutionEvent.order_id == cancelled["order_id"], ExecutionEvent.event_key == "fill:late-unowned",
        ))
        old_event.payload = {key: value for key, value in old_event.payload.items() if key != "accounting_status"}
    await db_session.flush()
    db_session.expire_all()
    repeated = await record_fill(db_session, **args)
    assert repeated["status"] == "reconciliation_required" and repeated["deduplicated"]
    retained = (await db_session.scalars(select(ExecutionEvent).where(
        ExecutionEvent.order_id == cancelled["order_id"], ExecutionEvent.event_key == "fill:late-unowned",
    ))).all()
    assert len(retained) == 1 and retained[0].payload["quantity"] == "2"
    assert retained[0].payload.get("accounting_status") == (None if legacy else "reconciliation_required")
    account = await db_session.get(SimulatorAccount, ids[1])
    reconciliation = await reconcile_account(db_session, account)
    assert reconciliation["status"] == "unverified" and reconciliation["allocation_inventory"] is None
    assert account.cash == settled_cash
