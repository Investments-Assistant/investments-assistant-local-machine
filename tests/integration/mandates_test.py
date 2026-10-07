"""Mandate provenance is independent of every model and order proposal."""

from decimal import Decimal
from datetime import UTC, datetime, timedelta

import pytest

from src.execution.models import SimulatorAccount, SimulatorMandate, StrategyDecision
from src.execution.policy import PolicyDenied
from src.operations.models import JobLease
from src.execution.mandates import MandateSpec, approve_mandate, propose_mandate
from tests.integration.execution_test import seed

pytestmark = pytest.mark.integration


def fixture_spec(instrument):
    return MandateSpec(
        environment="simulator",
        strategy="periodic_fixture_buy",
        strategy_version="1",
        instrument_ids=[instrument],
        capital_limit="500",
        max_position="300",
        max_order="150",
        daily_loss_limit="25",
        drawdown_limit="40",
        max_orders_per_day=3,
        min_interval_seconds=60,
        max_quote_age_seconds=30,
        max_fee_bps="10",
        max_spread_bps="5",
        trading_timezone="UTC",
        start_hour=0,
        end_hour=24,
        weekdays=list(range(7)),
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
        quantity_per_order="1",
    )


async def prepare(session):
    user, account, instrument = await seed(session)
    row = await session.get(SimulatorAccount, account)
    row.mandate = dict(row.mandate, fixture=True)
    proposed = await propose_mandate(
        session,
        user_id=user,
        account_id=account,
        session_id="human-session",
        spec=fixture_spec(instrument),
    )
    return dict(
        user_id=user,
        account_id=account,
        session_id="human-session",
        mandate_id=proposed["mandate_id"],
        nonce=proposed["nonce"],
        details_hash=proposed["details_hash"],
    )


async def test_independent_mandate_approval_cannot_be_replayed_or_self_approved(db_session):
    args = await prepare(db_session)
    with pytest.raises(PolicyDenied, match="HUMAN_APPROVAL_REQUIRED"):
        await approve_mandate(db_session, **args, human_event=False)
    with pytest.raises(PolicyDenied, match="MANDATE_NOT_OWNED"):
        await approve_mandate(
            db_session, **dict(args, session_id="other-session"), human_event=True
        )
    with pytest.raises(PolicyDenied, match="INVALID_NONCE"):
        await approve_mandate(db_session, **dict(args, nonce="invalid"), human_event=True)
    assert (await approve_mandate(db_session, **args, human_event=True))["status"] == "approved"
    with pytest.raises(PolicyDenied, match="APPROVAL_ALREADY_CONSUMED"):
        await approve_mandate(db_session, **args, human_event=True)


async def test_edited_or_expired_mandate_requires_new_proposal(db_session):
    args = await prepare(db_session)
    row = await db_session.get(SimulatorMandate, args["mandate_id"])
    row.specification = dict(row.specification, max_order="151")
    with pytest.raises(PolicyDenied, match="MANDATE_CHANGED_AFTER_PROPOSAL"):
        await approve_mandate(db_session, **args, human_event=True)
    with pytest.raises(PolicyDenied, match="APPROVAL_EXPIRED"):
        await approve_mandate(
            db_session, **args, human_event=True, now=datetime.now(UTC) + timedelta(minutes=6)
        )


async def test_autonomous_tick_reserves_once_and_preserves_marked_loss_halt(db_session):
    from src.execution.models import SimulatorOrder, SimulatorInstrument
    from src.execution.service import record_fill
    from src.execution.autonomy import run_tick

    args = await prepare(db_session)
    await approve_mandate(db_session, **args, human_event=True)
    mandate = await db_session.get(SimulatorMandate, args["mandate_id"])
    instrument = await db_session.get(
        SimulatorInstrument, mandate.specification["instrument_ids"][0]
    )
    now = datetime.now(UTC)
    instrument.as_of = now
    tick_args = {key: args[key] for key in ("user_id", "account_id", "mandate_id")}
    result = await run_tick(db_session, **tick_args, tick_id="first", now=now)
    account = await db_session.get(SimulatorAccount, args["account_id"])
    assert str(account.reserved) == "100.1000000000"
    assert (await run_tick(db_session, **tick_args, tick_id="first", now=now))["deduplicated"]
    with pytest.raises(PolicyDenied, match="ORDER_INTERVAL"):
        await run_tick(db_session, **tick_args, tick_id="too-fast", now=now)
    order = await db_session.get(SimulatorOrder, result["order_id"])
    assert order.approval["mandate_id"] == mandate.id
    await record_fill(
        db_session,
        user_id=args["user_id"],
        account_id=args["account_id"],
        order_id=order.id,
        execution_id="fixture-fill",
        quantity="1",
        price="100",
        fee="0.1",
    )
    later = now + timedelta(minutes=2)
    instrument.as_of = later
    instrument.price = 50
    with pytest.raises(PolicyDenied, match="MARKED_LOSS_LIMIT"):
        await run_tick(db_session, **tick_args, tick_id="loss", now=later)
    await db_session.commit()
    await db_session.refresh(account)
    assert account.halted and account.halt_reason == "MARKED_LOSS_LIMIT"
    assert Decimal(account.mandate["risk_observation"]["daily_pnl"]) == Decimal("-50.1")
    assert account.reserved == 0
    with pytest.raises(PolicyDenied, match="OPERATOR_HALTED"):
        await run_tick(db_session, **tick_args, tick_id="after-restart", now=later)


async def test_modified_approved_spec_cannot_gain_execution_authority(db_session):
    from src.execution.autonomy import run_tick

    args = await prepare(db_session)
    await approve_mandate(db_session, **args, human_event=True)
    mandate = await db_session.get(SimulatorMandate, args["mandate_id"])
    mandate.specification = dict(mandate.specification, capital_limit="999")
    with pytest.raises(PolicyDenied, match="MANDATE_CHANGED_AFTER_APPROVAL"):
        await run_tick(
            db_session,
            **{key: args[key] for key in ("user_id", "account_id", "mandate_id")},
            tick_id="tampered",
        )


async def test_forward_runner_fills_only_approved_fixture_and_deduplicates(db_session, monkeypatch):
    from contextlib import asynccontextmanager

    from src.execution.runtime import run_simulator_strategies

    class Factory:
        @asynccontextmanager
        async def __call__(self):
            yield db_session

        begin = __call__

    monkeypatch.setattr("src.execution.runtime.async_session", Factory())
    args = await prepare(db_session)
    assert await run_simulator_strategies() == []
    await approve_mandate(db_session, **args, human_event=True)
    first = await run_simulator_strategies()
    assert first[0]["status"] == "filled"
    second = await run_simulator_strategies()
    assert second == []  # Persisted due time prevents an immediate repeat dispatch.
    account = await db_session.get(SimulatorAccount, args["account_id"])
    assert account.cash == Decimal("899.9") and account.reserved == 0


async def test_concurrent_workers_reserve_one_tick_once(integration_engine):
    import asyncio

    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from src.db.models import User
    from src.execution.models import ExecutionEvent, SimulatorOrder, SimulatorInstrument
    from src.execution.autonomy import run_tick

    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with factory.begin() as session:
        args = await prepare(session)
        await approve_mandate(session, **args, human_event=True)
    tick_args = {key: args[key] for key in ("user_id", "account_id", "mandate_id")}
    try:

        async def tick():
            async with factory.begin() as session:
                return await run_tick(session, **tick_args, tick_id="same-durable-tick")

        results = await asyncio.gather(tick(), tick())
        assert sum(bool(result.get("deduplicated")) for result in results) == 1
        assert len({result["order_id"] for result in results}) == 1
        async with factory() as session:
            account = await session.get(SimulatorAccount, args["account_id"])
            assert account.reserved == Decimal("100.1")
    finally:
        # Fixture engine already proved disposable identity; delete only this synthetic owner.
        async with factory.begin() as session:
            orders = select(SimulatorOrder.id).where(
                SimulatorOrder.account_id == args["account_id"]
            )
            await session.execute(delete(ExecutionEvent).where(ExecutionEvent.order_id.in_(orders)))
            await session.execute(delete(StrategyDecision).where(StrategyDecision.account_id == args["account_id"]))
            for model in [SimulatorOrder, SimulatorMandate, SimulatorInstrument]:
                await session.execute(delete(model).where(model.account_id == args["account_id"]))
            await session.execute(
                delete(SimulatorAccount).where(SimulatorAccount.id == args["account_id"])
            )
            await session.execute(delete(JobLease).where(JobLease.user_id == args["user_id"]))
            await session.execute(delete(User).where(User.id == args["user_id"]))


async def test_mandate_evidence_capacity_stops_before_another_order_and_persists_halt(db_session, monkeypatch):
    from sqlalchemy import select

    from src.execution import autonomy
    from src.execution.models import SimulatorOrder, SimulatorInstrument
    from src.operations.models import OperationalAlert

    args = await prepare(db_session)
    await approve_mandate(db_session, **args, human_event=True)
    mandate = await db_session.get(SimulatorMandate, args["mandate_id"])
    instrument = await db_session.get(SimulatorInstrument, mandate.specification["instrument_ids"][0])
    monkeypatch.setattr(autonomy, "MAX_MANDATE_ROWS", 1)
    now = datetime.now(UTC)
    tick_args = {key: args[key] for key in ("user_id", "account_id", "mandate_id")}
    for index in range(2):
        stamp = now + timedelta(seconds=index * 61)
        instrument.as_of = stamp
        result = await autonomy.run_tick(db_session, **tick_args, tick_id=f"bounded-{index}", now=stamp)
        assert result["status"] == "submitted"
    instrument.as_of = now + timedelta(seconds=122)
    with pytest.raises(PolicyDenied, match="MANDATE_EVIDENCE_CAPACITY"):
        await autonomy.run_tick(db_session, **tick_args, tick_id="overflow", now=instrument.as_of)
    await db_session.flush()
    db_session.expire_all()
    account = await db_session.get(SimulatorAccount, args["account_id"])
    assert account.halted and account.halt_reason == "MANDATE_EVIDENCE_CAPACITY"
    orders = (await db_session.scalars(select(SimulatorOrder).where(
        SimulatorOrder.account_id == account.id,
    ))).all()
    assert len(orders) == 2 and account.reserved == Decimal("200.2")
    alert = await db_session.scalar(select(OperationalAlert).where(OperationalAlert.account_id == account.id))
    assert alert is not None and alert.observed_value == "MANDATE_EVIDENCE_CAPACITY"


async def test_forward_capacity_halt_commits_before_quote_refresh_or_order(integration_engine, monkeypatch):
    import uuid

    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from src.db.models import User
    from src.execution import runtime, autonomy
    from src.execution.models import SimulatorOrder, SimulatorInstrument
    from src.operations.models import OperationalAlert

    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with factory.begin() as session:
        args = await prepare(session)
        await approve_mandate(session, **args, human_event=True)
        mandate = await session.get(SimulatorMandate, args["mandate_id"])
        quote = await session.get(SimulatorInstrument, mandate.specification["instrument_ids"][0])
        original_stamp = quote.as_of
        session.add(SimulatorInstrument(
            id=str(uuid.uuid4()), account_id=args["account_id"], symbol="OTHER-FIXTURE",
            exchange="SIMULATOR", currency="EUR", multiplier=1, lot=1, tick="0.01",
            price=100, fx_to_base=1, as_of=original_stamp, protected=False, security_type="stock",
        ))
    monkeypatch.setattr(runtime, "async_session", factory)
    monkeypatch.setattr(runtime, "MAX_MANDATE_ROWS", 1)
    monkeypatch.setattr(autonomy, "MAX_MANDATE_ROWS", 1)
    try:
        results = await runtime.run_simulator_strategies()
        assert {"status": "blocked", "reason": "MANDATE_EVIDENCE_CAPACITY", "environment": "simulator"} in results
        # An independent connection sees the committed job outcome, not a savepoint.
        async with factory() as session:
            account = await session.get(SimulatorAccount, args["account_id"])
            assert account.halted and account.halt_reason == "MANDATE_EVIDENCE_CAPACITY"
            assert account.cash == 1000 and account.reserved == 0
            quotes = (await session.scalars(select(SimulatorInstrument).where(
                SimulatorInstrument.account_id == account.id,
            ))).all()
            assert len(quotes) == 2 and all(q.as_of == original_stamp for q in quotes)
            assert not (await session.scalars(select(SimulatorOrder).where(
                SimulatorOrder.account_id == account.id,
            ))).all()
            alert = await session.scalar(select(OperationalAlert).where(OperationalAlert.account_id == account.id))
            assert alert is not None and alert.observed_value == "MANDATE_EVIDENCE_CAPACITY"
    finally:
        async with factory.begin() as session:
            for model in [SimulatorMandate, SimulatorInstrument]:
                await session.execute(delete(model).where(model.account_id == args["account_id"]))
            await session.execute(delete(OperationalAlert).where(OperationalAlert.account_id == args["account_id"]))
            await session.execute(delete(SimulatorAccount).where(SimulatorAccount.id == args["account_id"]))
            await session.execute(delete(JobLease).where(JobLease.user_id == args["user_id"]))
            await session.execute(delete(User).where(User.id == args["user_id"]))


async def test_tick_risk_and_reservations_do_not_inherit_caller_precision(db_session):
    from decimal import ROUND_UP, localcontext

    from src.execution.models import SimulatorOrder
    from src.execution.autonomy import run_tick
    args = await prepare(db_session)
    await approve_mandate(db_session, **args, human_event=True)
    with localcontext() as context:
        context.prec, context.rounding = 6, ROUND_UP
        result = await run_tick(db_session,
            **{key: args[key] for key in ('user_id', 'account_id', 'mandate_id')}, tick_id='precision-fixture')
        assert context.prec == 6 and context.rounding == ROUND_UP
    order = await db_session.get(SimulatorOrder, result['order_id'])
    account = await db_session.get(SimulatorAccount, args['account_id'])
    assert order.reserve == Decimal('100.1') and account.reserved == Decimal('100.1')
    assert not account.halted
