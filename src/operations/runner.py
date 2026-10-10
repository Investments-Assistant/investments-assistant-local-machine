"""Scoped, bounded jobs. Stale schedules fetch fresh evidence instead of replaying orders."""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import or_, cast, func, text, select
from sqlalchemy.dialects.postgresql import JSONB

from src.db.models import User
from src.db.database import async_session
from src.operations.jobs import acquire, complete
from src.operations.alerts import emit
from src.operations.models import JobLease

MAX_MONITORING_BATCH = 100


async def monitoring_users(name: str) -> list[str]:
    """Bound eligible due work, so skipped users and recent jobs cannot starve others."""
    if not name or len(name) > 64:
        raise ValueError("Invalid monitoring job name")
    async with asyncio.timeout(10), async_session() as session:
        await session.execute(text("SET LOCAL statement_timeout = '5s'"))
        await session.execute(text("SET LOCAL lock_timeout = '2s'"))
        rows = await session.scalars(
            select(User.id)
            .outerjoin(JobLease, (JobLease.user_id == User.id) & (JobLease.name == name))
            .where(
                User.is_active.is_(True),
                cast(User.preferences, JSONB).contains({"monitoring_enabled": True}),
                or_(JobLease.id.is_(None),
                    (JobLease.next_due <= func.clock_timestamp())
                    & (JobLease.lease_until <= func.clock_timestamp())),
            )
            .order_by(JobLease.next_due.asc().nullsfirst(), User.id)
            .limit(MAX_MONITORING_BATCH)
        )
        return list(rows)


async def run_scoped(user_id: str, name: str, callback, *, interval_seconds=3600):
    async with asyncio.timeout(10), async_session.begin() as session:
        await session.execute(text("SET LOCAL statement_timeout = '5s'"))
        await session.execute(text("SET LOCAL lock_timeout = '2s'"))
        # Selection can precede dispatch by other users' bounded work. Recheck consent.
        preferences = await session.scalar(
            select(User.preferences).where(User.id == user_id, User.is_active.is_(True))
        )
        if not isinstance(preferences, dict) or preferences.get("monitoring_enabled") is not True:
            return {"status": "monitoring_disabled"}
        lease = await acquire(session, user_id=user_id, name=name, lease_seconds=180)
    if lease is None:
        return {"status": "leased_or_not_due"}
    failure = None
    try:
        async with asyncio.timeout(120):
            await callback(user_id)
    except asyncio.CancelledError:
        # Leave lease for expiration/recovery; no duplicate dispatch on cancellation.
        raise
    except Exception:
        failure = "JOB_DEPENDENCY_FAILED"
    async with asyncio.timeout(10), async_session.begin() as session:
        await session.execute(text("SET LOCAL statement_timeout = '5s'"))
        await session.execute(text("SET LOCAL lock_timeout = '2s'"))
        await complete(
            session,
            lease_id=lease[0],
            token=lease[1],
            checkpoint={"completed_at": datetime.now(UTC).isoformat(), "execution": "read_only"},
            interval_seconds=interval_seconds,
            failure_code=failure,
        )
        if failure:
            await emit(
                session,
                user_id=user_id,
                rule="job_failure:" + name,
                observed_value="failed",
                threshold="successful completion",
                message="Background monitoring needs attention.",
                evidence_at=datetime.now(UTC),
            )
    return {"status": "failed" if failure else "complete"}
