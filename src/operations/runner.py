"""Scoped, bounded jobs. Stale schedules fetch fresh evidence instead of replaying orders."""

import asyncio
from datetime import UTC, datetime

from sqlalchemy import select

from src.db.models import User
from src.db.database import async_session
from src.operations.jobs import acquire, complete
from src.operations.alerts import emit


async def monitoring_users() -> list[str]:
    async with async_session() as session:
        rows = (
            await session.execute(
                select(User.id, User.preferences)
                .where(User.is_active.is_(True))
                .order_by(User.id)
                .limit(100)
            )
        ).all()
    return [
        user_id
        for user_id, preferences in rows
        if isinstance(preferences, dict) and preferences.get("monitoring_enabled") is True
    ]


async def run_scoped(user_id: str, name: str, callback, *, interval_seconds=3600):
    async with async_session.begin() as session:
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
    async with async_session.begin() as session:
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
