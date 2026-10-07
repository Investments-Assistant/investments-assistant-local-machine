"""Approved price-band simulator strategy cannot consume another allocation."""

from decimal import Decimal
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.execution.models import SimulatorOrder, SimulatorAccount, SimulatorInstrument
from src.execution.policy import PolicyDenied
from src.execution.service import record_fill
from src.execution.autonomy import run_tick
from src.execution.mandates import MandateSpec, approve_mandate, propose_mandate
from src.execution.reconciliation import reconcile_account
from tests.integration.mandates_test import fixture_spec
from tests.integration.execution_test import seed, proposal, confirmation

pytestmark = pytest.mark.integration


async def band(session, ids):
    user, account_id, instrument_id = ids
    account = await session.get(SimulatorAccount, account_id)
    account.mandate = dict(account.mandate, fixture=True)
    spec = MandateSpec.model_validate(fixture_spec(instrument_id).model_dump() | {
        "strategy": "price_band_fixture", "buy_below": "100", "sell_above": "110",
    })
    proposed = await propose_mandate(session, user_id=user, account_id=account_id,
                                    session_id="human-session", spec=spec)
    await approve_mandate(session, user_id=user, account_id=account_id, session_id="human-session",
                          mandate_id=proposed["mandate_id"], nonce=proposed["nonce"],
                          details_hash=proposed["details_hash"], human_event=True)
    return dict(user_id=user, account_id=account_id, mandate_id=proposed["mandate_id"])


async def fill(session, ids, result, *, price, fee):
    return await record_fill(session, user_id=ids[0], account_id=ids[1], order_id=result["order_id"],
                             execution_id="synthetic-strategy-fill", quantity="1", price=price, fee=fee)


async def test_price_band_buys_and_sells_only_its_own_inventory(db_session):
    ids = await seed(db_session)
    manual = await proposal(db_session, ids)
    await confirmation(db_session, ids, manual)
    await fill(db_session, ids, manual, price="100", fee="0.1")
    args = await band(db_session, ids)
    quote = await db_session.get(SimulatorInstrument, ids[2])
    now = datetime.now(UTC)
    quote.as_of = now
    buy = await run_tick(db_session, **args, tick_id="buy", now=now)
    await fill(db_session, ids, buy, price="100", fee="0.1")
    quote.price, quote.as_of = Decimal("120"), now + timedelta(seconds=61)
    sale = await run_tick(db_session, **args, tick_id="sell", now=quote.as_of)
    order = await db_session.get(SimulatorOrder, sale["order_id"])
    assert order.side == "sell" and order.approval["mandate_id"] == args["mandate_id"]
    assert order.reserve == Decimal("0.12")
    assert (await fill(db_session, ids, sale, price="120", fee="0.12"))["status"] == "filled"
    await db_session.flush()
    db_session.expire_all()
    account = await db_session.get(SimulatorAccount, ids[1])
    assert account.cash == Decimal("919.68") and account.realized_pnl == Decimal("19.78")
    assert not account.halted and account.reserved == 0
    assert account.mandate.get("manual_sales") is None
    result = await reconcile_account(db_session, account)
    assert result["status"] == "consistent"
    owned = {row["allocation_id"]: row for row in result["allocation_inventory"]}
    assert Decimal(owned["manual"]["quantity"]) == 1
    assert Decimal(owned["manual"]["cost_basis"]) == Decimal("100.1")
    assert Decimal(owned[args["mandate_id"]]["quantity"]) == 0
    quote = await db_session.get(SimulatorInstrument, ids[2])
    quote.as_of = now + timedelta(seconds=122)
    assert (await run_tick(db_session, **args, tick_id="cannot-sell-manual", now=quote.as_of))["reason"] == (
        "NO_STRATEGY_INVENTORY"
    )


async def test_revised_mandate_does_not_inherit_old_inventory(db_session):
    ids = await seed(db_session)
    first = await band(db_session, ids)
    quote = await db_session.get(SimulatorInstrument, ids[2])
    now = datetime.now(UTC)
    quote.as_of = now
    buy = await run_tick(db_session, **first, tick_id="buy", now=now)
    await fill(db_session, ids, buy, price="100", fee="0.1")
    replacement = await band(db_session, ids)
    quote.price, quote.as_of = Decimal("120"), now + timedelta(seconds=61)
    result = await run_tick(db_session, **replacement, tick_id="replacement", now=quote.as_of)
    assert result["status"] == "no_trade" and result["reason"] == "NO_STRATEGY_INVENTORY"
    with pytest.raises(PolicyDenied, match="APPROVED_MANDATE_REQUIRED"):
        await run_tick(db_session, **first, tick_id="superseded", now=quote.as_of)


async def test_pending_strategy_order_and_neutral_price_do_not_create_more_orders(db_session):
    ids = await seed(db_session)
    args = await band(db_session, ids)
    quote = await db_session.get(SimulatorInstrument, ids[2])
    now = datetime.now(UTC)
    quote.price, quote.as_of = Decimal("105"), now
    assert (await run_tick(db_session, **args, tick_id="neutral", now=now))["reason"] == "PRICE_INSIDE_BAND"
    quote.price = Decimal("100")
    result = await run_tick(db_session, **args, tick_id="buy", now=now)
    assert (await run_tick(db_session, **args, tick_id="buy", now=now))["deduplicated"]
    quote.price, quote.as_of = Decimal("120"), now + timedelta(seconds=61)
    with pytest.raises(PolicyDenied, match="STRATEGY_ORDER_PENDING"):
        await run_tick(db_session, **args, tick_id="pending", now=quote.as_of)
    order = await db_session.get(SimulatorOrder, result["order_id"])
    assert order.side == "buy" and order.filled == 0


@pytest.mark.parametrize("updates", [
    {"strategy": "price_band_fixture"},
    {"strategy": "price_band_fixture", "buy_below": "110", "sell_above": "100"},
    {"strategy": "periodic_fixture_buy", "buy_below": "100", "sell_above": "110"},
])
def test_sale_thresholds_require_separate_explicit_strategy(updates):
    with pytest.raises(ValidationError):
        MandateSpec.model_validate(fixture_spec("synthetic").model_dump() | updates)


@pytest.mark.parametrize("denial", ["protected", "sale_cap", "changed_threshold"])
async def test_strategy_sales_preserve_global_caps_protection_and_approved_hash(db_session, denial):
    ids = await seed(db_session)
    args = await band(db_session, ids)
    quote = await db_session.get(SimulatorInstrument, ids[2])
    now = datetime.now(UTC)
    quote.as_of = now
    buy = await run_tick(db_session, **args, tick_id="buy", now=now)
    await fill(db_session, ids, buy, price="100", fee="0.1")
    quote.price, quote.as_of = Decimal("120"), now + timedelta(seconds=61)
    code = "PROTECTED_ALLOCATION"
    if denial == "protected":
        quote.protected = True
    elif denial == "sale_cap":
        quote.price = Decimal("160")
        code = "MANDATE_ORDER_CAP"
    else:
        from src.execution.models import SimulatorMandate

        mandate = await db_session.get(SimulatorMandate, args["mandate_id"])
        mandate.specification = dict(mandate.specification, sell_above="105")
        code = "MANDATE_CHANGED_AFTER_APPROVAL"
    with pytest.raises(PolicyDenied, match=code):
        await run_tick(db_session, **args, tick_id="denied", now=quote.as_of)
    account = await db_session.get(SimulatorAccount, ids[1])
    assert account.reserved == 0 and account.cash == Decimal("899.9")


async def test_forward_runner_handles_no_trade_without_inventing_a_fill(db_session, monkeypatch):
    from contextlib import asynccontextmanager

    from src.execution.runtime import run_simulator_strategies

    class Factory:
        @asynccontextmanager
        async def __call__(self):
            yield db_session

        begin = __call__

    ids = await seed(db_session)
    await band(db_session, ids)
    quote = await db_session.get(SimulatorInstrument, ids[2])
    quote.price = Decimal("105")
    monkeypatch.setattr("src.execution.runtime.async_session", Factory())
    results = await run_simulator_strategies()
    assert len(results) == 1 and results[0]["status"] == "no_trade"
    assert results[0]["reason"] == "PRICE_INSIDE_BAND" and results[0]["decision_id"]
    account = await db_session.get(SimulatorAccount, ids[1])
    assert account.cash == 1000 and account.reserved == 0 and not account.halted


async def test_no_trade_replay_keeps_original_quote_and_survives_concurrent_restart(integration_engine):
    import asyncio

    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from src.db.models import User
    from src.execution.models import SimulatorMandate, StrategyDecision
    from src.execution.policy import digest

    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with factory.begin() as session:
        ids = await seed(session)
        args = await band(session, ids)
        quote = await session.get(SimulatorInstrument, ids[2])
        now = datetime.now(UTC)
        quote.price, quote.as_of = Decimal("105"), now
    try:
        async def tick():
            async with factory.begin() as session:
                return await run_tick(session, **args, tick_id="neutral-durable", now=now)

        results = await asyncio.gather(tick(), tick())
        assert sum(bool(result.get("deduplicated")) for result in results) == 1
        assert len({result["decision_id"] for result in results}) == 1
        async with factory.begin() as session:
            quote = await session.get(SimulatorInstrument, ids[2])
            quote.price = Decimal("90")
        replay = await tick()
        assert replay["status"] == "no_trade" and replay["deduplicated"]
        async with factory() as session:
            decisions = (await session.scalars(select(StrategyDecision).where(
                StrategyDecision.account_id == ids[1],
            ))).all()
            assert len(decisions) == 1
            evidence = decisions[0].evidence
            assert Decimal(evidence["instrument"]["price"]) == 105
            assert evidence["mandate_hash"] and decisions[0].evidence_hash == digest(evidence)
            assert not (await session.scalars(select(SimulatorOrder).where(
                SimulatorOrder.account_id == ids[1],
            ))).all()
            account = await session.get(SimulatorAccount, ids[1])
            assert account.cash == 1000 and account.reserved == 0
    finally:
        async with factory.begin() as session:
            for model in (StrategyDecision, SimulatorMandate, SimulatorInstrument):
                await session.execute(delete(model).where(model.account_id == ids[1]))
            await session.execute(delete(SimulatorAccount).where(SimulatorAccount.id == ids[1]))
            await session.execute(delete(User).where(User.id == ids[0]))


async def test_altered_decision_evidence_halts_instead_of_recomputing(db_session):
    from src.execution.models import StrategyDecision

    ids = await seed(db_session)
    args = await band(db_session, ids)
    quote = await db_session.get(SimulatorInstrument, ids[2])
    now = datetime.now(UTC)
    quote.price, quote.as_of = Decimal("105"), now
    first = await run_tick(db_session, **args, tick_id="neutral", now=now)
    decision = await db_session.get(StrategyDecision, first["decision_id"])
    decision.evidence = dict(decision.evidence, result={"status": "filled"})
    with pytest.raises(PolicyDenied, match="STRATEGY_EVIDENCE_CONFLICT"):
        await run_tick(db_session, **args, tick_id="neutral", now=now)
    account = await db_session.get(SimulatorAccount, ids[1])
    assert account.halted and account.halt_reason == "STRATEGY_EVIDENCE_CONFLICT"
    assert account.reserved == 0


async def test_decision_history_is_visible_only_to_the_account_owner(db_session, monkeypatch):
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock

    from fastapi import HTTPException

    from src.web import simulator_routes as routes

    class Factory:
        @asynccontextmanager
        async def begin(self):
            yield db_session

    ids = await seed(db_session)
    args = await band(db_session, ids)
    quote = await db_session.get(SimulatorInstrument, ids[2])
    now = datetime.now(UTC)
    quote.price, quote.as_of = Decimal("105"), now
    first = await run_tick(db_session, **args, tick_id="neutral", now=now)
    monkeypatch.setattr(routes, "async_session", Factory())
    monkeypatch.setattr(routes, "browser_identity", AsyncMock(return_value=(ids[0], "human-session")))
    result = await routes.snapshot(ids[1], None)
    assert not result["strategy_decisions_truncated"]
    assert result["strategy_decisions"][0]["id"] == first["decision_id"]
    assert result["strategy_decisions"][0]["evidence"]["result"]["reason"] == "PRICE_INSIDE_BAND"
    other = await seed(db_session)
    monkeypatch.setattr(routes, "browser_identity", AsyncMock(return_value=(other[0], "other-session")))
    with pytest.raises(HTTPException) as caught:
        await routes.snapshot(ids[1], None)
    assert caught.value.status_code == 409 and caught.value.detail["reason_code"] == "ACCOUNT_NOT_OWNED"
