"""HTTP command transaction boundaries persist simulator risk halts after denial."""

from decimal import Decimal
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.web import simulator_routes as routes
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
from src.operations.models import OperationalAlert
from tests.integration.execution_test import seed, proposal, confirmation

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def account_fixture(integration_engine, monkeypatch):
    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with factory.begin() as session:
        ids = await seed(session)
        first = await proposal(session, ids)
        await confirmation(session, ids, first)
        await record_fill(
            session,
            user_id=ids[0],
            account_id=ids[1],
            order_id=first["order_id"],
            execution_id="risk-fixture",
            quantity=1,
            price=100,
        )
        pending = await proposal(session, ids)
    monkeypatch.setattr(routes, "async_session", factory)
    # Authentication is covered by real-browser tests; this tier isolates commit behavior.
    monkeypatch.setattr(routes, "browser_identity", AsyncMock(return_value=(ids[0], "human-session")))
    try:
        yield factory, ids, first, pending
    finally:
        async with factory.begin() as session:
            orders = select(SimulatorOrder.id).where(SimulatorOrder.account_id == ids[1])
            await session.execute(delete(ExecutionEvent).where(ExecutionEvent.order_id.in_(orders)))
            await session.execute(delete(SimulatorOrder).where(SimulatorOrder.account_id == ids[1]))
            await session.execute(delete(SimulatorPosition).where(SimulatorPosition.account_id == ids[1]))
            await session.execute(delete(SimulatorInstrument).where(SimulatorInstrument.account_id == ids[1]))
            await session.execute(delete(SimulatorAccount).where(SimulatorAccount.id == ids[1]))
            await session.execute(delete(OperationalAlert).where(OperationalAlert.user_id == ids[0]))
            await session.execute(delete(User).where(User.id == ids[0]))


@pytest.mark.parametrize(
    "trigger,reason",
    [
        ("loss", "MARKED_ACCOUNT_LOSS_LIMIT"),
        ("stale", "VALUATION_STALE"),
        ("uncertain", "RECONCILIATION_REQUIRED"),
        ("cash_discrepancy", "LEDGER_RECONCILIATION_DISCREPANT"),
    ],
)
async def test_manual_approval_cannot_bypass_marked_risk_and_halt_survives_denial(account_fixture, trigger, reason):
    factory, ids, first, pending = account_fixture
    async with factory.begin() as session:
        instrument = await session.get(SimulatorInstrument, ids[2])
        if trigger == "loss":
            instrument.price, instrument.as_of = Decimal(40), datetime.now(UTC)
        elif trigger == "stale":
            instrument.as_of = datetime.now(UTC) - timedelta(minutes=2)
        elif trigger == "cash_discrepancy":
            account = await session.get(SimulatorAccount, ids[1])
            account.cash += 1
        else:
            previous = await session.get(SimulatorOrder, first["order_id"])
            previous.status = "uncertain"
    body = routes.ApprovalInput(nonce=pending["nonce"], details_hash=pending["details_hash"])
    with pytest.raises(HTTPException) as caught:
        await routes.approve_proposal(ids[1], pending["order_id"], body, None)
    assert caught.value.status_code == 409 and caught.value.detail["reason_code"] == reason
    async with factory.begin() as session:
        account = await session.get(SimulatorAccount, ids[1])
        order = await session.get(SimulatorOrder, pending["order_id"])
        assert account.halted and account.halt_reason == reason
        assert account.realized_pnl == 0  # old realized-only check would miss the mark loss
        assert account.reserved == 0 and order.status == "proposed" and order.approval is None
        alert = await session.scalar(select(OperationalAlert).where(OperationalAlert.user_id == ids[0]))
        assert alert is not None and alert.account_id == ids[1]
        assert alert.observed_value == reason
        assert "Existing orders and positions" in alert.message
        if trigger == "loss":
            assert Decimal(account.mandate["account_risk"]["capital_pnl"]) == -60
        # A refreshed quote and a new connection cannot clear the persisted halt.
        instrument = await session.get(SimulatorInstrument, ids[2])
        instrument.as_of = datetime.now(UTC)
        with pytest.raises(PolicyDenied, match="OPERATOR_HALTED"):
            await proposal(session, ids)
