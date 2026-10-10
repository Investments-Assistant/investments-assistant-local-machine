"""Persist and recheck an operator halt only in the marked container fixture."""

import sys
import asyncio
from decimal import Decimal
from datetime import UTC, datetime

from sqlalchemy import text

from src.db.models import User
from src.db.database import engine, async_session
from src.execution.models import SimulatorAccount, SimulatorInstrument
from src.execution.policy import PolicyDenied
from src.execution.service import halt, propose


async def main():
    token, action = sys.argv[1:]
    user_id, account_id, instrument_id = "fixture-user", "fixture-account", "fixture-instrument"
    async with async_session.begin() as session:
        identity = (await session.execute(text("SELECT current_database(),token FROM ia_disposable_marker"))).one()
        assert tuple(identity) == ("test_container", token), "Not our disposable database"
        if action == "seed":
            session.add(
                User(id=user_id, username="runtime-fixture", password_hash="no-login", is_active=True, preferences={})
            )
            session.add(
                SimulatorAccount(
                    id=account_id,
                    user_id=user_id,
                    currency="EUR",
                    cash=1000,
                    initial_capital=1000,
                    max_order=500,
                    loss_limit=50,
                    mandate={"environment": "simulator", "fixture": True},
                )
            )
            await session.flush()
            session.add(
                SimulatorInstrument(
                    id=instrument_id,
                    account_id=account_id,
                    symbol="FIXTURE",
                    exchange="SIMULATOR",
                    currency="EUR",
                    multiplier=1,
                    lot=Decimal("0.001"),
                    tick=Decimal("0.01"),
                    price=100,
                    fx_to_base=1,
                    as_of=datetime.now(UTC),
                    protected=False,
                )
            )
            await session.flush()
            response = await halt(session, user_id=user_id, account_id=account_id)
            assert response == {"halted": True, "pending_orders_cancelled": False, "positions_liquidated": False}
        else:
            assert action == "verify"
            account = await session.get(SimulatorAccount, account_id)
            assert account.halted and account.halt_reason == "OPERATOR_HALT"
            assert account.cash == 1000 and account.reserved == 0
            try:
                await propose(
                    session,
                    user_id=user_id,
                    session_id="fixture-human",
                    account_id=account_id,
                    instrument_id=instrument_id,
                    quantity="1",
                    limit_price="100",
                    idempotency_key="restart-denied",
                )
            except PolicyDenied as exc:
                assert str(exc) == "OPERATOR_HALTED", str(exc)
            else:
                raise AssertionError("Persisted operator halt permitted a new proposal")
    await engine.dispose()
    print("Operator halt fixture " + action + " PASS")


asyncio.run(main())
