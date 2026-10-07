"""Bounded forward simulator ticks; approved fixtures only, no external adapters."""

import asyncio
from decimal import Decimal
from datetime import UTC, datetime

from sqlalchemy import or_, func, text, select
from sqlalchemy.exc import DBAPIError

from src.db.models import User
from src.db.database import async_session
from src.operations.jobs import acquire, complete
from src.execution.models import (
    SimulatorOrder,
    SimulatorMandate,
    SimulatorInstrument,
)
from src.execution.policy import PolicyDenied
from src.execution.service import record_fill, account_for_user
from src.operations.alerts import emit
from src.operations.models import JobLease
from src.agent.utils.logger import get_logger
from src.execution.autonomy import MAX_MANDATE_ROWS, run_tick, require_bounded_evidence

MAX_DISPATCH_BATCH = 100
MAX_CYCLE_SECONDS = 20
MAX_JOB_SECONDS = 10
logger = get_logger(__name__)


async def _database_bounds(session):
    await session.execute(text("SET LOCAL statement_timeout = '5s'"))
    await session.execute(text("SET LOCAL lock_timeout = '2s'"))


async def _persist_failure(lease, *, user_id, account_id, code, result):
    if lease is None:
        result["failure_persistence"] = "unavailable"
        return
    try:
        async with asyncio.timeout(5), async_session.begin() as session:
            await _database_bounds(session)
            await complete(
                session, lease_id=lease[0], token=lease[1], checkpoint={}, interval_seconds=60, failure_code=code
            )
            await emit(
                session,
                user_id=user_id,
                account_id=account_id,
                rule="simulator_dispatch_failure",
                observed_value=code,
                threshold="successful bounded strategy execution",
                message="Simulator strategy execution failed; review its job and account evidence.",
                evidence_at=await session.scalar(select(func.clock_timestamp())),
            )
    except (TimeoutError, DBAPIError, PolicyDenied):
        result["failure_persistence"] = "unavailable"
        logger.warning("SIMULATOR_FAILURE_PERSISTENCE_UNAVAILABLE")


async def run_simulator_strategies():
    results = []
    try:
        async with asyncio.timeout(MAX_CYCLE_SECONDS):
            await _dispatch_cycle(results)
    except (TimeoutError, DBAPIError) as exc:
        code = "SIMULATOR_CYCLE_TIMEOUT" if isinstance(exc, TimeoutError) else "SIMULATOR_STORAGE_FAILED"
        logger.warning(code)
        results.append(dict(status="partial_failure", reason=code, failure_persistence="unavailable"))
    return results


async def _dispatch_cycle(results):
    async with asyncio.timeout(10), async_session.begin() as session:
        await _database_bounds(session)
        rows = (
            await session.execute(
                select(SimulatorMandate.id, SimulatorMandate.account_id, SimulatorMandate.user_id)
                .join(User, User.id == SimulatorMandate.user_id)
                .outerjoin(
                    JobLease,
                    (JobLease.user_id == SimulatorMandate.user_id)
                    & (JobLease.name == "simulator:" + SimulatorMandate.id),
                )
                .where(
                    SimulatorMandate.status == "approved",
                    User.is_active.is_(True),
                    or_(
                        JobLease.id.is_(None),
                        (JobLease.next_due <= func.clock_timestamp())
                        & (JobLease.lease_until <= func.clock_timestamp()),
                    ),
                )
                .order_by(JobLease.next_due.asc().nullsfirst(), SimulatorMandate.id)
                .limit(MAX_DISPATCH_BATCH)
            )
        ).all()
    for mandate_id, account_id, user_id in rows:
        lease = None
        try:
            async with asyncio.timeout(5), async_session.begin() as session:
                await _database_bounds(session)
                lease = await acquire(session, user_id=user_id, name="simulator:" + mandate_id)
            if lease is None:
                continue
            async with asyncio.timeout(MAX_JOB_SECONDS), async_session.begin() as session:
                await _database_bounds(session)
                now = datetime.now(UTC)
                try:
                    # This explicitly labelled fixture feed advances time, not market prices.
                    account = await account_for_user(session, account_id, user_id)
                    if account is None or account.mandate.get("fixture") is not True:
                        raise PolicyDenied("SIMULATOR_FIXTURE_REQUIRED")
                    quotes = (
                        (
                            await session.execute(
                                select(SimulatorInstrument)
                                .where(SimulatorInstrument.account_id == account_id)
                                .order_by(SimulatorInstrument.id)
                                .limit(MAX_MANDATE_ROWS + 1)
                            )
                        )
                        .scalars()
                        .all()
                    )
                    await require_bounded_evidence(session, account, quotes)
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
                    if result.get("status") != "no_trade" and not result.get("deduplicated"):
                        order = await session.get(SimulatorOrder, result["order_id"])
                        quote = await session.get(SimulatorInstrument, order.instrument_id)
                        fee = (
                            order.quantity
                            * quote.price
                            * quote.fx_to_base
                            * Decimal(account.mandate["fee_bps"])
                            / 10000
                        )
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
                except PolicyDenied as exc:
                    # Commit durable risk halts; never roll them back with an HTTP/job error.
                    result = dict(status="blocked", reason=exc.code, environment="simulator")
                # Outside the policy-denial handler: stale completion rolls back
                # all work in this transaction, including orders and quote refresh.
                await complete(
                    session,
                    lease_id=lease[0],
                    token=lease[1],
                    checkpoint=result,
                    interval_seconds=60,
                    failure_code=result.get("reason") if result.get("status") == "blocked" else None,
                )
            results.append(result)
        except PolicyDenied as exc:
            results.append(dict(status="blocked", reason=exc.code, environment="simulator"))
        except (TimeoutError, DBAPIError) as exc:
            code = "SIMULATOR_JOB_TIMEOUT" if isinstance(exc, TimeoutError) else "SIMULATOR_STORAGE_FAILED"
            logger.warning(code)
            result = dict(status="failed", reason=code, environment="simulator")
            await _persist_failure(lease, user_id=user_id, account_id=account_id, code=code, result=result)
            results.append(result)
