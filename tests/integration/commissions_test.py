"""Simulator callback ordering and commission accounting; no external broker calls."""

import asyncio
from decimal import Decimal
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.models import User
from src.execution.models import (
    ExecutionEvent,
    SimulatorOrder,
    SimulatorAccount,
    SimulatorPosition,
    SimulatorInstrument,
)
from src.execution.policy import PolicyDenied
from src.execution.service import record_fill
from src.execution.commissions import record_commission
from tests.integration.execution_test import seed, proposal, confirmation

pytestmark = pytest.mark.integration


def callback(ids, order_id, stamp, **overrides):
    return (
        dict(
            user_id=ids[0],
            account_id=ids[1],
            order_id=order_id,
            execution_id="fixture-exec",
            revision=1,
            amount="0.05",
            currency="EUR",
            fx_to_base="1",
            fx_as_of=stamp,
        )
        | overrides
    )


async def fill(session, ids, order_id):
    return await record_fill(
        session,
        user_id=ids[0],
        account_id=ids[1],
        order_id=order_id,
        execution_id="fixture-exec",
        quantity=1,
        price=100,
    )


async def test_commission_before_fill_revisions_and_immutable_fx_evidence(db_session):
    ids = await seed(db_session)
    proposed = await proposal(db_session, ids)
    await confirmation(db_session, ids, proposed)
    order_id, stamp = proposed["order_id"], datetime.now(UTC)
    high = callback(ids, order_id, stamp, revision=2)
    assert (await record_commission(db_session, **high))["status"] == "awaiting_fill"
    assert (await record_commission(db_session, **(high | {"revision": 1, "amount": "0.03"})))[
        "status"
    ] == "older_revision_recorded"
    await fill(db_session, ids, order_id)
    account = await db_session.get(SimulatorAccount, ids[1])
    order = await db_session.get(SimulatorOrder, order_id)
    assert account.cash == Decimal("899.95") and order.fees == Decimal("0.05")
    instrument = await db_session.get(SimulatorInstrument, ids[2])
    instrument.fx_to_base = 2  # later fixture quote cannot change saved settlement evidence
    await db_session.flush()
    assert (await fill(db_session, ids, order_id))["deduplicated"]
    revised = high | {"revision": 3, "amount": "0.04"}
    await record_commission(db_session, **revised)
    assert (await record_commission(db_session, **revised))["status"] == "deduplicated"
    assert account.cash == Decimal("899.96") and order.fees == Decimal("0.04")
    position = await db_session.scalar(select(SimulatorPosition).where(SimulatorPosition.account_id == ids[1]))
    assert position.cost_basis == Decimal("100.04") and position.quantity == 1
    event = await db_session.scalar(
        select(ExecutionEvent).where(ExecutionEvent.order_id == order_id, ExecutionEvent.kind == "fill")
    )
    assert Decimal(event.payload["fx_to_base"]) == 1
    assert event.payload["base_currency"] == "EUR" and Decimal(event.payload["principal_base"]) == 100
    with pytest.raises(PolicyDenied, match="CONFLICTING_DUPLICATE_COMMISSION"):
        await record_commission(db_session, **(revised | {"amount": "0.06"}))


async def test_commission_cost_overrun_is_recorded_and_halts_new_orders(db_session):
    ids = await seed(db_session)
    proposed = await proposal(db_session, ids)
    await confirmation(db_session, ids, proposed)
    await fill(db_session, ids, proposed["order_id"])
    # Explicit source USD fee and dated conversion to the account's EUR.
    args = callback(ids, proposed["order_id"], datetime.now(UTC), amount="0.25", currency="USD", fx_to_base="0.8")
    result = await record_commission(db_session, **args)
    account = await db_session.get(SimulatorAccount, ids[1])
    assert result["status"] == "applied" and result["halted"]
    assert account.cash == Decimal("899.8") and account.halt_reason == "COMMISSION_BUDGET_EXCEEDED"
    with pytest.raises(PolicyDenied, match="OPERATOR_HALTED"):
        await proposal(db_session, ids)
    other = await seed(db_session)
    with pytest.raises(PolicyDenied, match="ACCOUNT_NOT_OWNED"):
        await record_commission(db_session, **(args | {"user_id": other[0]}))


async def test_concurrent_duplicate_commission_after_new_session_charges_once(integration_engine):
    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with factory.begin() as session:
        ids = await seed(session)
        proposed = await proposal(session, ids)
        await confirmation(session, ids, proposed)
        await fill(session, ids, proposed["order_id"])
    order_id = proposed["order_id"]
    try:
        args = callback(ids, order_id, datetime.now(UTC))

        async def deliver():
            async with factory.begin() as session:
                return await record_commission(session, **args)

        results = await asyncio.gather(deliver(), deliver())
        assert sorted(result["status"] for result in results) == ["applied", "deduplicated"]
        async with factory.begin() as session:
            account = await session.get(SimulatorAccount, ids[1])
            order = await session.get(SimulatorOrder, order_id)
            assert account.cash == Decimal("899.95") and order.fees == Decimal("0.05")
    finally:
        async with factory.begin() as session:
            await session.execute(delete(ExecutionEvent).where(ExecutionEvent.order_id == order_id))
            await session.execute(delete(SimulatorOrder).where(SimulatorOrder.id == order_id))
            await session.execute(delete(SimulatorPosition).where(SimulatorPosition.account_id == ids[1]))
            await session.execute(delete(SimulatorInstrument).where(SimulatorInstrument.account_id == ids[1]))
            await session.execute(delete(SimulatorAccount).where(SimulatorAccount.id == ids[1]))
            await session.execute(delete(User).where(User.id == ids[0]))
