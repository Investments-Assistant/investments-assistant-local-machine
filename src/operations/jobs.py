"""PostgreSQL leases use database time and fenced completion, not in-process flags."""

import uuid
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from src.db.models import User
from src.execution.policy import PolicyDenied
from src.operations.models import JobLease


async def acquire(session, *, user_id: str, name: str, lease_seconds=60):
    if not 1 <= lease_seconds <= 600 or not name or len(name) > 64:
        raise ValueError("Invalid bounded lease")
    if not await session.scalar(
        select(User.id).where(User.id == user_id, User.is_active.is_(True))
    ):
        raise PolicyDenied("PRINCIPAL_INACTIVE")
    now = await session.scalar(select(func.now()))
    token = str(uuid.uuid4())
    statement = insert(JobLease).values(
        id=str(uuid.uuid4()),
        user_id=user_id,
        name=name,
        token=token,
        lease_until=now + timedelta(seconds=lease_seconds),
        next_due=now,
        checkpoint={},
    )
    statement = statement.on_conflict_do_update(
        index_elements=["user_id", "name"],
        set_={"token": token, "lease_until": now + timedelta(seconds=lease_seconds)},
        where=(JobLease.lease_until <= now) & (JobLease.next_due <= now),
    ).returning(JobLease.id)
    lease_id = await session.scalar(statement)
    return (lease_id, token) if lease_id else None


async def complete(
    session,
    *,
    lease_id: str,
    token: str,
    checkpoint: dict,
    interval_seconds: int,
    failure_code: str | None = None,
):
    if not 1 <= interval_seconds <= 86400:
        raise ValueError("Invalid job interval")
    now = await session.scalar(select(func.now()))
    values = dict(
        lease_until=now,
        next_due=now + timedelta(seconds=interval_seconds),
        failure_code=failure_code,
    )
    if failure_code is None:
        values.update(last_success=now, checkpoint=checkpoint)
    result = await session.execute(
        update(JobLease)
        .where(JobLease.id == lease_id, JobLease.token == token, JobLease.lease_until >= now)
        .values(**values)
    )
    if result.rowcount != 1:
        raise PolicyDenied("STALE_JOB_LEASE")
