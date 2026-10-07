"""Global account limits apply to human approvals as well as strategy mandates."""

import pytest

from src.execution.models import SimulatorAccount, SimulatorInstrument
from src.execution.policy import PolicyDenied
from src.execution.service import propose
from tests.integration.execution_test import seed, proposal, confirmation

pytestmark = pytest.mark.integration


async def capped(session, *, position="300", exposure="600"):
    ids = await seed(session)
    account = await session.get(SimulatorAccount, ids[1])
    account.mandate = dict(account.mandate, global_exposure_limits={
        "max_position_base": position, "max_exposure_base": exposure})
    return ids, account


async def test_manual_proposal_cannot_exceed_global_concentration(db_session):
    ids, _ = await capped(db_session, position="250")
    with pytest.raises(PolicyDenied, match="GLOBAL_POSITION_CAP"):
        await proposal(db_session, ids, quantity="3")


async def test_manual_approval_rechecks_other_pending_orders(db_session):
    ids, account = await capped(db_session)
    first = await proposal(db_session, ids, quantity="2")
    second = await proposal(db_session, ids, quantity="2")
    await confirmation(db_session, ids, first)
    before = account.reserved
    with pytest.raises(PolicyDenied, match="GLOBAL_POSITION_CAP"):
        await confirmation(db_session, ids, second)
    assert account.reserved == before


async def test_other_instrument_reservation_counts_toward_global_exposure(db_session):
    ids, account = await capped(db_session, position="300", exposure="350")
    first = await proposal(db_session, ids, quantity="2")
    await confirmation(db_session, ids, first)
    original = await db_session.get(SimulatorInstrument, ids[2])
    instrument = SimulatorInstrument(account_id=account.id, symbol="SECOND", exchange="SIMULATOR",
        currency="EUR", multiplier=1, lot=1, tick="0.01", price=100, fx_to_base=1,
        as_of=original.as_of, protected=False, security_type="stock")
    db_session.add(instrument)
    await db_session.flush()
    with pytest.raises(PolicyDenied, match="GLOBAL_EXPOSURE_CAP"):
        await propose(db_session, user_id=ids[0], account_id=ids[1], session_id="human-session",
                      instrument_id=instrument.id, quantity="2", limit_price="100", idempotency_key="other")


@pytest.mark.parametrize("policy", [None, {}, {"max_position_base": "NaN", "max_exposure_base": "500"},
                                    {"max_position_base": "600", "max_exposure_base": "500"}])
async def test_missing_or_invalid_global_policy_halts_without_inventing_limits(db_session, policy):
    ids, account = await capped(db_session)
    account.mandate = dict(account.mandate, global_exposure_limits=policy)
    with pytest.raises(PolicyDenied, match="GLOBAL_EXPOSURE_LIMITS_UNAVAILABLE"):
        await proposal(db_session, ids)
    assert account.halted and account.halt_reason == "GLOBAL_EXPOSURE_LIMITS_UNAVAILABLE"


async def test_marked_gain_breach_halts_and_sale_is_not_a_halt_bypass(db_session):
    from decimal import Decimal
    from datetime import UTC, datetime

    from src.execution.risk import enforce_account_risk
    from src.execution.service import record_fill
    from tests.integration.simulator_sales_test import sell

    ids, account = await capped(db_session)
    buy = await proposal(db_session, ids, quantity="2")
    await confirmation(db_session, ids, buy)
    await record_fill(db_session, user_id=ids[0], account_id=ids[1], order_id=buy["order_id"],
                      execution_id="capped-buy", quantity="2", price="100")
    quote = await db_session.get(SimulatorInstrument, ids[2])
    quote.price, quote.as_of = Decimal(200), datetime.now(UTC)
    with pytest.raises(PolicyDenied, match="GLOBAL_POSITION_CAP"):
        await enforce_account_risk(db_session, account)
    assert account.halted and account.halt_reason == "GLOBAL_POSITION_CAP"
    with pytest.raises(PolicyDenied, match="OPERATOR_HALTED"):
        await sell(db_session, ids)


async def test_strategy_cannot_bypass_global_cap_with_its_larger_mandate(db_session):
    from src.execution.service import record_fill
    from src.execution.autonomy import run_tick
    from tests.integration.strategy_sales_test import band

    ids, _ = await capped(db_session, position="150", exposure="600")
    buy = await proposal(db_session, ids)
    await confirmation(db_session, ids, buy)
    await record_fill(db_session, user_id=ids[0], account_id=ids[1], order_id=buy["order_id"],
                      execution_id="manual-buy", quantity="1", price="100")
    args = await band(db_session, ids)
    with pytest.raises(PolicyDenied, match="GLOBAL_POSITION_CAP"):
        await run_tick(db_session, **args, tick_id="global-cap")


async def test_concurrent_approvals_share_global_cap_across_transactions(integration_engine):
    import asyncio
    from decimal import Decimal

    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from src.db.models import User
    from src.execution.models import ExecutionEvent, SimulatorOrder

    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with factory.begin() as session:
        ids, _ = await capped(session, position="300")
        candidates = [await proposal(session, ids, quantity="2") for _ in range(2)]

    async def confirm(candidate):
        try:
            async with factory.begin() as session:
                return await confirmation(session, ids, candidate)
        except PolicyDenied as exc:
            return exc.code

    try:
        results = await asyncio.gather(*(confirm(candidate) for candidate in candidates))
        assert sum(isinstance(item, dict) for item in results) == 1
        assert "GLOBAL_POSITION_CAP" in results
        async with factory() as session:
            account = await session.get(SimulatorAccount, ids[1])
            assert account.reserved == Decimal("200.2") and account.cash == 1000
    finally:
        async with factory.begin() as session:
            orders = select(SimulatorOrder.id).where(SimulatorOrder.account_id == ids[1])
            await session.execute(delete(ExecutionEvent).where(ExecutionEvent.order_id.in_(orders)))
            await session.execute(delete(SimulatorOrder).where(SimulatorOrder.account_id == ids[1]))
            await session.execute(delete(SimulatorInstrument).where(SimulatorInstrument.account_id == ids[1]))
            await session.execute(delete(SimulatorAccount).where(SimulatorAccount.id == ids[1]))
            await session.execute(delete(User).where(User.id == ids[0]))
