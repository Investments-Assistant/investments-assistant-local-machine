"""Observe missed local monitoring intervals after recovery, without external calls."""

import asyncio

from sqlalchemy import func, text, select
from sqlalchemy.exc import DBAPIError

from src.db.models import User
from src.db.database import async_session
from src.operations.jobs import acquire, complete
from src.execution.policy import PolicyDenied
from src.operations.alerts import emit
from src.operations.models import JobLease
from src.operations.runner import monitoring_users
from src.agent.utils.logger import get_logger

NAME = "operations_heartbeat"
INTERVAL_SECONDS = 60
GRACE_SECONDS = 300
logger = get_logger(__name__)


async def _bounds(session):
    await session.execute(text("SET LOCAL statement_timeout = '5s'"))
    await session.execute(text("SET LOCAL lock_timeout = '2s'"))


async def observe_heartbeat(user_id):
    """Atomically publish a gap alert and checkpoint under the current lease."""
    async with asyncio.timeout(10), async_session.begin() as session:
        await _bounds(session)
        # Freeze active ownership and opt-in for this short database-only observation.
        user = await session.scalar(select(User).where(User.id == user_id).with_for_update(read=True))
        if (user is None or not user.is_active or not isinstance(user.preferences, dict)
                or user.preferences.get("monitoring_enabled") is not True):
            return {"status": "monitoring_disabled"}
        lease = await acquire(session, user_id=user_id, name=NAME, lease_seconds=30)
        if lease is None:
            return {"status": "leased_or_not_due"}
        claim = await session.get(JobLease, lease[0], populate_existing=True)
        now = await session.scalar(select(func.clock_timestamp()))
        # No prior successful observation means no baseline, not evidence of an outage.
        delay = max(0, int((now - claim.next_due).total_seconds())) if claim.last_success else None
        gap = delay is not None and delay > GRACE_SECONDS
        if gap:
            await emit(
                session, user_id=user_id, rule="monitoring_heartbeat_gap",
                observed_value=f"{delay} seconds overdue", threshold=f"{GRACE_SECONDS} seconds overdue",
                message="Monitoring resumed after a missed heartbeat. Review service health and account evidence.",
                evidence_at=now,
            )
        outcome = {"status": "gap_observed" if gap else "observed",
                   "observed_at": now.isoformat(), "overdue_seconds": delay,
                   "execution": "read_only_no_orders"}
        # A clock jump or expired lease rolls back the alert too.
        await complete(session, lease_id=lease[0], token=lease[1],
                       checkpoint=outcome, interval_seconds=INTERVAL_SECONDS)
        return outcome


async def monitor_heartbeat():
    results = []
    try:
        async with asyncio.timeout(20):
            for user_id in await monitoring_users(NAME):
                try:
                    results.append(await observe_heartbeat(user_id))
                except (DBAPIError, PolicyDenied, TimeoutError) as exc:
                    code = exc.code if isinstance(exc, PolicyDenied) else "HEARTBEAT_OBSERVATION_FAILED"
                    logger.warning(code)
                    results.append({"status": "failed", "reason": code})
    except (DBAPIError, TimeoutError):
        logger.warning("HEARTBEAT_CYCLE_UNAVAILABLE")
        results.append({"status": "partial_failure", "reason": "HEARTBEAT_CYCLE_UNAVAILABLE"})
    return results
