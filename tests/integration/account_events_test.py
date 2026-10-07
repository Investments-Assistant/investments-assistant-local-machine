"""Observed synthetic cash flows are durable evidence, never real transfers."""

from decimal import Decimal
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from src.execution.risk import enforce_account_risk
from src.execution.models import SimulatorAccount, AccountLedgerEvent
from src.execution.policy import PolicyDenied
from src.execution.account_events import record_cash_flow
from src.execution.reconciliation import reconcile_account
from tests.integration.execution_test import seed, proposal, confirmation

pytestmark = pytest.mark.integration


async def cash_flow(session, ids, *, amount="200", key="deposit", **overrides):
    args = dict(
        user_id=ids[0],
        account_id=ids[1],
        event_key=key,
        amount_base=amount,
        currency="EUR",
        effective_at=datetime.now(UTC),
        source_reference="synthetic-receipt",
        fixture_event=True,
    )
    return await record_cash_flow(session, **(args | overrides))


async def test_flow_persisted_and_reconciled_without_inventing_profit_or_policy(db_session):
    ids = await seed(db_session)
    account = await db_session.get(SimulatorAccount, ids[1])
    before = await enforce_account_risk(db_session, account)
    at = datetime.now(UTC)
    first = await cash_flow(db_session, ids, effective_at=at)
    duplicate = await cash_flow(db_session, ids, effective_at=at)
    assert duplicate["deduplicated"] and duplicate["event_id"] == first["event_id"]
    await db_session.flush()
    db_session.expire_all()
    account = await db_session.get(SimulatorAccount, ids[1])
    checked = await reconcile_account(db_session, account)
    assert checked["status"] == "consistent"
    assert checked["net_external_flows"] == "200"
    assert account.cash == 1200 and account.initial_capital == 1000 and account.max_order == 500
    after = await enforce_account_risk(db_session, account)
    assert Decimal(before["daily_pnl"]) == Decimal(after["daily_pnl"]) == 0
    assert Decimal(after["capital_pnl"]) == 0
    await cash_flow(db_session, ids, amount="-100", key="withdrawal")
    risk = await enforce_account_risk(db_session, account)
    assert Decimal(risk["capital_pnl"]) == Decimal(risk["daily_pnl"]) == 0
    assert account.realized_pnl == 0 and account.cash == 1100


async def test_cash_flow_rejects_scope_conflict_and_reserved_cash(db_session):
    ids = await seed(db_session)
    other = await seed(db_session)
    with pytest.raises(PolicyDenied, match="ACCOUNT_NOT_OWNED"):
        await cash_flow(db_session, ids, user_id=other[0])
    with pytest.raises(PolicyDenied, match="SIMULATOR_EVENT_REQUIRED"):
        await cash_flow(db_session, ids, fixture_event=False)
    with pytest.raises(PolicyDenied, match="CASH_FLOW_CURRENCY_MISMATCH"):
        await cash_flow(db_session, ids, currency="USD")
    proposed = await proposal(db_session, ids)
    await confirmation(db_session, ids, proposed)
    with pytest.raises(PolicyDenied, match="INSUFFICIENT_UNRESERVED_CASH"):
        await cash_flow(db_session, ids, amount="-950")
    await cash_flow(db_session, ids)
    with pytest.raises(PolicyDenied, match="CONFLICTING_ACCOUNT_EVENT"):
        await cash_flow(db_session, ids, amount="201")
    assert (
        len((await db_session.scalars(select(AccountLedgerEvent).where(AccountLedgerEvent.account_id == ids[1]))).all())
        == 1
    )


async def test_tampered_cash_flow_evidence_is_unverified(db_session):
    ids = await seed(db_session)
    await cash_flow(db_session, ids)
    event = await db_session.scalar(select(AccountLedgerEvent).where(AccountLedgerEvent.account_id == ids[1]))
    event.payload = dict(event.payload, amount_base="1000")
    await db_session.flush()
    account = await db_session.get(SimulatorAccount, ids[1])
    result = await reconcile_account(db_session, account)
    assert result["status"] == "unverified" and result["allocation_inventory"] is None
    assert account.cash == 1200


async def test_deposit_cannot_hide_a_marked_loss(db_session):
    from src.execution.risk import RiskDenied
    from src.execution.models import SimulatorInstrument
    from src.execution.service import record_fill

    ids = await seed(db_session)
    proposed = await proposal(db_session, ids)
    await confirmation(db_session, ids, proposed)
    await record_fill(
        db_session,
        user_id=ids[0],
        account_id=ids[1],
        order_id=proposed["order_id"],
        execution_id="fill",
        quantity="1",
        price="100",
    )
    await cash_flow(db_session, ids, amount="500")
    account = await db_session.get(SimulatorAccount, ids[1])
    instrument = await db_session.get(SimulatorInstrument, ids[2])
    instrument.price = 40
    with pytest.raises(RiskDenied, match="MARKED_ACCOUNT_LOSS_LIMIT"):
        await enforce_account_risk(db_session, account)
    assert account.halted and Decimal(account.mandate["account_risk"]["capital_pnl"]) == -60


async def test_strategy_withdrawal_is_not_drawdown_and_does_not_expand_limits(db_session):
    from datetime import timedelta

    from src.execution.models import SimulatorMandate, SimulatorInstrument
    from src.execution.autonomy import run_tick
    from src.execution.mandates import approve_mandate
    from tests.integration.mandates_test import prepare

    args = await prepare(db_session)
    await approve_mandate(db_session, **args, human_event=True)
    mandate = await db_session.get(SimulatorMandate, args["mandate_id"])
    specification = dict(mandate.specification)
    instrument = await db_session.get(SimulatorInstrument, specification["instrument_ids"][0])
    now = datetime.now(UTC)
    instrument.as_of = now
    tick = {key: args[key] for key in ("user_id", "account_id", "mandate_id")}
    await run_tick(db_session, **tick, tick_id="before-flow", now=now)
    await cash_flow(db_session, (args["user_id"], args["account_id"]), amount="-200")
    later = now + timedelta(minutes=2)
    instrument.as_of = later
    await run_tick(db_session, **tick, tick_id="after-flow", now=later)
    account = await db_session.get(SimulatorAccount, args["account_id"])
    risk = account.mandate["risk_observation"]
    assert Decimal(risk["drawdown"]) == Decimal(risk["daily_pnl"]) == 0
    assert mandate.specification == specification


async def test_report_cash_flow_interval_and_owner_evidence(db_session):
    from datetime import timedelta

    from src.execution.reporting import collect_execution_period

    ids = await seed(db_session)
    other = await seed(db_session)
    await cash_flow(db_session, ids)
    await cash_flow(db_session, other, amount="999")
    now = datetime.now(UTC)
    event = await db_session.scalar(select(AccountLedgerEvent).where(AccountLedgerEvent.account_id == ids[1]))
    event.observed_at = now - timedelta(days=2)
    await db_session.flush()
    result = await collect_execution_period(db_session, user_id=ids[0], start=now - timedelta(days=3), end=now)
    account = result["accounts"][0]
    assert Decimal(account["net_external_flows"]) == 200 and account["cash_flow_count"] == 1
    assert account["cash_flows"][0]["event_id"] == event.id
    assert Decimal(account["realized_pnl"]) == 0
    excluded = await collect_execution_period(db_session, user_id=ids[0], start=now - timedelta(days=1), end=now)
    assert Decimal(excluded["accounts"][0]["net_external_flows"]) == 0


async def test_concurrent_withdrawals_cannot_consume_same_cash(integration_engine):
    import asyncio

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from src.db.models import User
    from src.execution.models import SimulatorInstrument

    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with factory.begin() as session:
        ids = await seed(session)

    async def withdraw(key):
        async with factory.begin() as session:
            try:
                await cash_flow(session, ids, amount="-600", key=key)
                return "applied"
            except PolicyDenied as exc:
                return str(exc)

    try:
        outcomes = await asyncio.gather(withdraw("one"), withdraw("two"))
        assert sorted(outcomes) == ["INSUFFICIENT_UNRESERVED_CASH", "applied"]
        async with factory() as session:
            account = await session.get(SimulatorAccount, ids[1])
            assert account.cash == 400
            checked = await reconcile_account(session, account)
            assert checked["status"] == "consistent"
            assert Decimal(checked["net_external_flows"]) == -600
    finally:
        async with factory.begin() as session:
            for model in (AccountLedgerEvent, SimulatorInstrument):
                await session.execute(delete(model).where(model.account_id == ids[1]))
            await session.execute(delete(SimulatorAccount).where(SimulatorAccount.id == ids[1]))
            await session.execute(delete(User).where(User.id == ids[0]))
