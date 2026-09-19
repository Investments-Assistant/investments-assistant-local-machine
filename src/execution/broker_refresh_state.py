"""Durable scoped read attempts; no order retry or financial authority."""

from sqlalchemy import func, select

from src.operations.jobs import acquire, complete
from src.execution.policy import PolicyDenied, digest
from src.operations.models import JobLease


def lease_name(account_id):
    return "broker-read:" + digest(account_id)[:40]


async def begin_refresh(session, *, user_id, account_id):
    lease = await acquire(session, user_id=user_id, name=lease_name(account_id), lease_seconds=90)
    if lease is None:
        raise PolicyDenied("BROKER_READ_LEASED_OR_NOT_DUE")
    row = await session.get(JobLease, lease[0])
    row.checkpoint = {
        "status": "running",
        "scope": "broker_read_only",
        "started_at": (await session.scalar(select(func.clock_timestamp()))).isoformat(),
    }
    return lease


async def finish_refresh(session, *, lease, user_id, summary, failure_code=None, keep_lease=False):
    row = await session.scalar(
        select(JobLease)
        .where(JobLease.id == lease[0], JobLease.user_id == user_id, JobLease.token == lease[1])
        .with_for_update()
    )
    now = await session.scalar(select(func.clock_timestamp()))
    if row is None or row.lease_until <= now:
        raise PolicyDenied("STALE_JOB_LEASE")
    if keep_lease:
        # Timed-out/cancelled native reads may still be cleaning up. Do not release
        # their durable admission immediately or mark successful completion.
        row.failure_code = failure_code
        row.next_due = row.lease_until
    else:
        await complete(
            session,
            lease_id=lease[0],
            token=lease[1],
            checkpoint=summary,
            interval_seconds=30,
            failure_code=failure_code,
        )
    row.checkpoint = dict(
        summary,
        scope="broker_read_only",
        completed_at=now.isoformat(),
        native_completion="unknown" if keep_lease else "returned",
    )


async def refresh_state(session, *, user_id, account_id):
    row = await session.scalar(
        select(JobLease).where(JobLease.user_id == user_id, JobLease.name == lease_name(account_id))
    )
    if row is None:
        return {"status": "never_attempted", "scope": "broker_read_only"}
    now = await session.scalar(select(func.clock_timestamp()))
    active = row.lease_until > now
    state = dict(row.checkpoint)
    if state.get("status") == "running" and not active:
        state["status"] = "interrupted"
    return state | {
        "lease_active": active,
        "failure_code": row.failure_code,
        "next_due": max(row.next_due, row.lease_until).isoformat(),
        "last_success": row.last_success.isoformat() if row.last_success else None,
    }
