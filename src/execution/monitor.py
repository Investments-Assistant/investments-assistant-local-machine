"""Leased simulator risk observations for active users who opted into monitoring."""

import asyncio

from sqlalchemy import or_, cast, func, text, select
from sqlalchemy.dialects.postgresql import JSONB

from src.db.models import User
from src.db.database import async_session
from src.execution.risk import RiskDenied, enforce_account_risk
from src.operations.jobs import acquire, complete
from src.execution.models import SimulatorAccount
from src.execution.policy import PolicyDenied
from src.execution.service import account_for_user
from src.operations.alerts import emit
from src.operations.models import JobLease
from src.agent.utils.logger import get_logger

logger = get_logger(__name__)


async def monitor_simulator_risk(*, user_id=None):
    results = []
    try:
        async with asyncio.timeout(20):
            await _monitor_cycle(results, user_id=user_id)
    except TimeoutError:
        logger.warning("RISK_CYCLE_TIMEOUT")
        results.append({"status": "partial_failure", "reason": "RISK_CYCLE_TIMEOUT"})
    return results


async def _monitor_cycle(results, *, user_id):
    async with asyncio.timeout(10), async_session.begin() as session:
        await session.execute(text("SET LOCAL statement_timeout = '5s'"))
        candidates = (
            await session.execute(
                select(SimulatorAccount.id, SimulatorAccount.user_id)
                .join(User, User.id == SimulatorAccount.user_id)
                .outerjoin(JobLease, (JobLease.user_id == User.id) & (JobLease.name == "risk:" + SimulatorAccount.id))
                .where(
                    User.is_active.is_(True),
                    cast(User.preferences, JSONB).contains({"monitoring_enabled": True}),
                    cast(SimulatorAccount.mandate, JSONB).contains({"fixture": True}),
                    SimulatorAccount.halted.is_(False),
                    User.id == user_id if user_id is not None else True,
                    or_(
                        JobLease.id.is_(None), (JobLease.next_due <= func.now()) & (JobLease.lease_until <= func.now())
                    ),
                )
                .order_by(JobLease.next_due.asc().nullsfirst(), SimulatorAccount.id)
                .limit(100)
            )
        ).all()
    for account_id, user_id in candidates:
        lease = None
        try:
            async with asyncio.timeout(5), async_session.begin() as session:
                lease = await acquire(session, user_id=user_id, name="risk:" + account_id, lease_seconds=30)
            if lease is None:
                continue
            async with asyncio.timeout(10), async_session.begin() as session:
                await session.execute(text("SET LOCAL statement_timeout = '5s'"))
                await session.execute(text("SET LOCAL lock_timeout = '2s'"))
                claim = await session.scalar(
                    select(JobLease)
                    .where(
                        JobLease.id == lease[0],
                        JobLease.token == lease[1],
                        JobLease.lease_until > func.clock_timestamp(),
                    )
                    .with_for_update()
                )
                if claim is None:
                    raise PolicyDenied("STALE_JOB_LEASE")
                account = await account_for_user(session, account_id, user_id)
                preferences = await session.scalar(select(User.preferences).where(User.id == user_id))
                outcome = {"status": "disabled", "execution": "risk_only_no_orders"}
                if (
                    isinstance(preferences, dict)
                    and preferences.get("monitoring_enabled") is True
                    and account.mandate.get("fixture") is True
                ):
                    try:
                        if account.halted:
                            raise RiskDenied(account.halt_reason or "OPERATOR_HALTED")
                        observation = await enforce_account_risk(session, account)
                        outcome = {
                            "status": "observed",
                            "execution": "risk_only_no_orders",
                            "observed_at": observation["at"],
                        }
                    except RiskDenied as exc:
                        outcome = {"status": "halted", "reason": exc.code, "execution": "risk_only_no_orders"}
                # Use live DB time, not the transaction-start timestamp, at the final fence.
                if await session.scalar(select(func.clock_timestamp())) >= claim.lease_until:
                    raise PolicyDenied("STALE_JOB_LEASE")
                await complete(session, lease_id=lease[0], token=lease[1], checkpoint=outcome, interval_seconds=60)
            results.append(outcome)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # A failed observation never counts as a successful risk check.
            code = exc.code if isinstance(exc, PolicyDenied) else "RISK_MONITOR_FAILED"
            results.append({"status": "failed", "reason": code})
            if lease is None:
                continue
            try:
                async with asyncio.timeout(5), async_session.begin() as session:
                    await complete(
                        session,
                        lease_id=lease[0],
                        token=lease[1],
                        checkpoint={},
                        interval_seconds=60,
                        failure_code=code,
                    )
                    await emit(
                        session,
                        user_id=user_id,
                        account_id=account_id,
                        rule="risk_monitor_failure",
                        observed_value="unavailable",
                        threshold="successful observation",
                        message="Simulator risk monitoring needs attention.",
                        evidence_at=await session.scalar(select(func.clock_timestamp())),
                    )
            except Exception:
                # Database/authority/lease loss is explicit in the returned failure;
                # no external notification or permissive trading fallback exists.
                results[-1]["failure_persistence"] = "unavailable"
