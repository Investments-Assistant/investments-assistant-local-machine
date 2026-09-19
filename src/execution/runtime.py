"""Bounded forward simulator ticks; approved fixtures only, no external adapters."""

from decimal import Decimal
from datetime import UTC, datetime

from sqlalchemy import select

from src.db.models import User
from src.db.database import async_session
from src.execution.models import (
    SimulatorOrder,
    SimulatorAccount,
    SimulatorMandate,
    SimulatorInstrument,
)
from src.execution.policy import PolicyDenied
from src.execution.service import record_fill
from src.execution.autonomy import run_tick


async def run_simulator_strategies():
    now = datetime.now(UTC)
    async with async_session() as session:
        rows = (
            await session.execute(
                select(SimulatorMandate.id, SimulatorMandate.account_id, SimulatorMandate.user_id)
                .join(User, User.id == SimulatorMandate.user_id)
                .where(SimulatorMandate.status == "approved", User.is_active.is_(True))
                .order_by(SimulatorMandate.id)
                .limit(100)
            )
        ).all()
    results = []
    for mandate_id, account_id, user_id in rows:
        async with async_session.begin() as session:
            try:
                # This explicitly labelled fixture feed advances time, not market prices.
                account = await session.scalar(
                    select(SimulatorAccount)
                    .where(SimulatorAccount.id == account_id, SimulatorAccount.user_id == user_id)
                    .with_for_update()
                )
                if account is None or account.mandate.get("fixture") is not True:
                    raise PolicyDenied("SIMULATOR_FIXTURE_REQUIRED")
                quotes = (
                    (
                        await session.execute(
                            select(SimulatorInstrument).where(SimulatorInstrument.account_id == account_id)
                        )
                    )
                    .scalars()
                    .all()
                )
                for quote in quotes:
                    if quote.exchange == "SIMULATOR":
                        quote.as_of = now
                result = await run_tick(
                    session,
                    user_id=user_id,
                    account_id=account_id,
                    mandate_id=mandate_id,
                    tick_id=now.strftime("%Y-%m-%dT%H:%M"),
                    now=now,
                )
                if not result.get("deduplicated"):
                    order = await session.get(SimulatorOrder, result["order_id"])
                    quote = await session.get(SimulatorInstrument, order.instrument_id)
                    fee = order.quantity * quote.price * quote.fx_to_base * Decimal(account.mandate["fee_bps"]) / 10000
                    result = await record_fill(
                        session,
                        user_id=user_id,
                        account_id=account_id,
                        order_id=order.id,
                        execution_id="synthetic-forward-tick",
                        quantity=order.quantity,
                        price=quote.price,
                        fee=fee,
                    )
                results.append(result)
            except PolicyDenied as exc:
                # Commit durable risk halts; never roll them back with an HTTP/job error.
                results.append(dict(status="blocked", reason=exc.code, environment="simulator"))
    return results
