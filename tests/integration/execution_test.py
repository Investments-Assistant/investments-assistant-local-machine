"""Real PostgreSQL authority, ledger and callback tests; no broker connections."""

import uuid
import asyncio
from decimal import Decimal
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.models import User
from src.execution.models import (
    SimulatorOrder,
    SimulatorAccount,
    SimulatorPosition,
    SimulatorInstrument,
)
from src.execution.policy import PolicyDenied
from src.execution.service import halt, approve, propose, transition, record_fill

pytestmark = pytest.mark.integration


async def seed(session, *, cash=1000, max_order=500):
    now = datetime.now(UTC)
    user = User(
        id=str(uuid.uuid4()),
        username="fixture-" + uuid.uuid4().hex,
        password_hash="synthetic-non-login",
        is_active=True,
    )
    account = SimulatorAccount(
        id=str(uuid.uuid4()),
        user_id=user.id,
        currency="EUR",
        cash=Decimal(cash),
        initial_capital=Decimal(cash),
        reserved=0,
        max_order=Decimal(max_order),
        loss_limit=50,
        realized_pnl=0,
        halted=False,
        mandate={
            "environment": "simulator",
            "fee_bps": "10",
            "expires_at": (now + timedelta(hours=1)).isoformat(),
        },
    )
    instrument = SimulatorInstrument(
        id=str(uuid.uuid4()),
        account_id=account.id,
        symbol="FIXTURE",
        exchange="SIMULATOR",
        currency="EUR",
        multiplier=1,
        lot=Decimal("0.001"),
        tick=Decimal("0.01"),
        price=100,
        fx_to_base=1,
        as_of=now,
        protected=False,
        security_type="stock",
    )
    session.add_all([user, account])
    await session.flush()
    session.add(instrument)
    await session.flush()
    return user.id, account.id, instrument.id


async def proposal(session, ids, *, key=None, quantity="1"):
    user, account, instrument = ids
    return await propose(
        session,
        user_id=user,
        session_id="human-session",
        account_id=account,
        instrument_id=instrument,
        quantity=quantity,
        limit_price="100",
        idempotency_key=key or uuid.uuid4().hex,
    )


async def confirmation(session, ids, result, **overrides):
    args = dict(
        user_id=ids[0],
        account_id=ids[1],
        session_id="human-session",
        order_id=result["order_id"],
        nonce=result["nonce"],
        details_hash=result["details_hash"],
        human_event=True,
    )
    return await approve(session, **(args | overrides))


async def test_approval_is_independent_single_use_and_immutable(db_session):
    ids = await seed(db_session)
    result = await proposal(db_session, ids)
    for override, code in [
        ({"human_event": False}, "HUMAN_APPROVAL_REQUIRED"),
        ({"session_id": "different"}, "PROPOSAL_NOT_OWNED"),
        ({"nonce": "wrong"}, "INVALID_NONCE"),
        ({"details_hash": "wrong"}, "ORDER_CHANGED_AFTER_PROPOSAL"),
        ({"now": datetime.now(UTC) + timedelta(minutes=6)}, "APPROVAL_EXPIRED"),
    ]:
        with pytest.raises(PolicyDenied, match=code):
            await confirmation(db_session, ids, result, **override)
    await confirmation(db_session, ids, result)
    with pytest.raises(PolicyDenied, match="APPROVAL_ALREADY_CONSUMED"):
        await confirmation(db_session, ids, result)


async def test_edited_order_cannot_use_previous_approval(db_session):
    ids = await seed(db_session)
    result = await proposal(db_session, ids)
    order = await db_session.get(SimulatorOrder, result["order_id"])
    order.quantity = Decimal(2)
    await db_session.flush()
    with pytest.raises(PolicyDenied, match="ORDER_CHANGED_AFTER_PROPOSAL"):
        await confirmation(db_session, ids, result)


async def test_partial_duplicate_late_ack_and_commissions(db_session):
    ids = await seed(db_session)
    result = await proposal(db_session, ids)
    await confirmation(db_session, ids, result)
    args = dict(user_id=ids[0], account_id=ids[1], order_id=result["order_id"])
    first = await record_fill(
        db_session, **args, execution_id="part-1", quantity=".4", price=100, fee=".04"
    )
    assert first["status"] == "partially_filled"
    assert (
        await record_fill(
            db_session, **args, execution_id="part-1", quantity=".4", price=100, fee=".04"
        )
    )["deduplicated"]
    assert (await transition(db_session, **args, status="acknowledged", event_key="late-ack"))[
        "status"
    ] == "partially_filled"
    await record_fill(
        db_session, **args, execution_id="part-2", quantity=".6", price=100, fee=".06"
    )
    account = await db_session.get(SimulatorAccount, ids[1])
    assert account.cash == Decimal("899.9")
    assert account.reserved == 0
    position = await db_session.scalar(
        select(SimulatorPosition).where(SimulatorPosition.account_id == ids[1])
    )
    assert position.quantity == 1
    assert position.cost_basis == Decimal("100.1")


async def test_uncertain_submission_reserves_and_cancel_fill_race_halts(db_session):
    ids = await seed(db_session)
    result = await proposal(db_session, ids)
    await confirmation(db_session, ids, result)
    args = dict(user_id=ids[0], account_id=ids[1], order_id=result["order_id"])
    await transition(db_session, **args, status="uncertain", event_key="timeout")
    account = await db_session.get(SimulatorAccount, ids[1])
    assert account.reserved == Decimal("100.1")
    duplicate = await proposal(db_session, ids, key=result["details"]["idempotency_key"])
    assert duplicate["deduplicated"] and duplicate["status"] == "uncertain"
    await transition(db_session, **args, status="cancelled", event_key="cancel-ack")
    assert account.reserved == 0
    await record_fill(db_session, **args, execution_id="late-fill", quantity=1, price=100)
    assert account.halted
    assert account.halt_reason == "FILL_RECONCILIATION_DISCREPANCY"
    assert account.cash == 900


async def test_protected_stale_and_deactivated_rejected(db_session):
    ids = await seed(db_session)
    instrument = await db_session.get(SimulatorInstrument, ids[2])
    instrument.protected = True
    with pytest.raises(PolicyDenied, match="PROTECTED_ALLOCATION"):
        await proposal(db_session, ids)
    instrument.protected = False
    instrument.as_of = datetime.now(UTC) - timedelta(minutes=2)
    with pytest.raises(PolicyDenied, match="STALE_QUOTE"):
        await proposal(db_session, ids)
    user = await db_session.get(User, ids[0])
    user.is_active = False
    with pytest.raises(PolicyDenied, match="PRINCIPAL_INACTIVE"):
        await proposal(db_session, ids)


async def test_cross_user_cannot_use_account(db_session):
    ids = await seed(db_session)
    other = await seed(db_session)
    with pytest.raises(PolicyDenied, match="ACCOUNT_NOT_OWNED"):
        await propose(
            db_session,
            user_id=other[0],
            account_id=ids[1],
            session_id="human-session",
            instrument_id=ids[2],
            quantity=1,
            limit_price=100,
            idempotency_key="cross-user",
        )


async def test_concurrent_approval_reservations_and_restart_halt(integration_engine):
    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with factory.begin() as session:
        ids = await seed(session, cash=150)
        proposals = [await proposal(session, ids), await proposal(session, ids)]

    async def confirm(result):
        try:
            async with factory.begin() as session:
                return await confirmation(session, ids, result)
        except PolicyDenied as exc:
            return exc.code

    results = await asyncio.gather(*(confirm(result) for result in proposals))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert "INSUFFICIENT_UNRESERVED_CASH" in results
    async with factory.begin() as session:
        await halt(session, user_id=ids[0], account_id=ids[1])
    # New connection/session is the process restart persistence boundary.
    async with factory.begin() as session:
        account = await session.get(SimulatorAccount, ids[1])
        assert account.halted and account.reserved == Decimal("100.1")
        with pytest.raises(PolicyDenied, match="OPERATOR_HALTED"):
            await proposal(session, ids)
