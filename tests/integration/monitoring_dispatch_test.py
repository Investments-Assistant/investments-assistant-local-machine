"""Opted-in monitoring cannot starve behind inactive preferences or recent jobs."""

import uuid
import asyncio
from datetime import UTC, datetime, timedelta
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

from src.db.models import User
from src.operations import runner
from src.operations.jobs import acquire, complete
from src.operations.models import JobLease, OperationalAlert

pytestmark = pytest.mark.integration


class SharedSession:
    def __init__(self, session):
        self.session = session

    @asynccontextmanager
    async def __call__(self):
        yield self.session

    begin = __call__


async def test_monitoring_selects_due_opted_in_users_before_bounding(db_session, monkeypatch):
    prefix = "000-monitor-" + uuid.uuid4().hex[:8]
    excluded = [
        User(id=f"{prefix}-{index:03}", username=f"{prefix}-{index}",
             password_hash="fixture", is_active=True, preferences={})
        for index in range(105)
    ]
    opted = [
        User(id=f"{prefix}-yes-{index}", username=f"{prefix}-yes-{index}",
             password_hash="fixture", is_active=True, preferences={"monitoring_enabled": True})
        for index in range(3)
    ]
    db_session.add_all(excluded + opted)
    await db_session.flush()
    monkeypatch.setattr(runner, "async_session", SharedSession(db_session))
    monkeypatch.setattr(runner, "MAX_MONITORING_BATCH", 2, raising=False)
    name = "fixture-" + uuid.uuid4().hex
    first = await runner.monitoring_users(name)
    assert first == [row.id for row in opted[:2]]
    for owner in first:
        lease_id, token = await acquire(db_session, user_id=owner, name=name)
        await complete(db_session, lease_id=lease_id, token=token,
                       checkpoint={"fresh": True}, interval_seconds=3600)
    assert await runner.monitoring_users(name) == [opted[2].id]
    # Independent report schedule still has its own due work.
    assert await runner.monitoring_users(name + "-report") == first


@pytest.mark.parametrize("preferences,active", [
    ({"monitoring_enabled": "true"}, True),
    ({"monitoring_enabled": 1}, True),
    ({"monitoring_enabled": True}, False),
    ([], True),
])
async def test_malformed_or_inactive_opt_in_is_not_dispatched(db_session, monkeypatch, preferences, active):
    owner = "000-denied-" + uuid.uuid4().hex[:16]
    db_session.add(User(id=owner, username=owner, password_hash="fixture",
                        is_active=active, preferences=preferences))
    await db_session.flush()
    monkeypatch.setattr(runner, "async_session", SharedSession(db_session))
    assert owner not in await runner.monitoring_users("fixture-denied")


async def test_opt_out_after_selection_prevents_callback(db_session, monkeypatch):
    owner = "000-optout-" + uuid.uuid4().hex[:16]
    row = User(id=owner, username=owner, password_hash="fixture", is_active=True,
               preferences={"monitoring_enabled": True})
    db_session.add(row)
    await db_session.flush()
    monkeypatch.setattr(runner, "async_session", SharedSession(db_session))
    name = "optout-" + uuid.uuid4().hex
    assert owner in await runner.monitoring_users(name)
    row.preferences = {"monitoring_enabled": False}
    await db_session.flush()
    observed = []

    async def callback(user_id):
        observed.append(user_id)

    assert await runner.run_scoped(owner, name, callback) == {"status": "monitoring_disabled"}
    assert observed == []
    assert await db_session.scalar(select(JobLease.id).where(JobLease.user_id == owner)) is None


@pytest.mark.parametrize("failure", ["network", "cancellation"])
async def test_failed_or_interrupted_read_job_recovers_once_with_fresh_work(db_session, monkeypatch, failure):
    owner = "000-recover-" + uuid.uuid4().hex[:16]
    db_session.add(User(id=owner, username=owner, password_hash="fixture", is_active=True,
                       preferences={"monitoring_enabled": True}))
    await db_session.flush()
    monkeypatch.setattr(runner, "async_session", SharedSession(db_session))
    name = "recovery-" + uuid.uuid4().hex
    observed = []

    async def failed(user_id):
        observed.append("failed")
        if failure == "cancellation":
            raise asyncio.CancelledError
        raise ConnectionError("synthetic offline dependency")

    if failure == "cancellation":
        with pytest.raises(asyncio.CancelledError):
            await runner.run_scoped(owner, name, failed)
    else:
        assert await runner.run_scoped(owner, name, failed) == {"status": "failed"}
    lease = await db_session.scalar(select(JobLease).where(JobLease.user_id == owner))
    assert lease.last_success is None and lease.checkpoint == {}
    alerts = list(await db_session.scalars(select(OperationalAlert).where(OperationalAlert.user_id == owner)))
    assert len(alerts) == (1 if failure == "network" else 0)
    assert owner not in await runner.monitoring_users(name)
    # A two-day missed interval is represented in this disposable row, not the host clock.
    lease.lease_until = lease.next_due = datetime.now(UTC) - timedelta(days=2)
    await db_session.flush()
    assert owner in await runner.monitoring_users(name)

    async def fresh(user_id):
        assert user_id == owner
        observed.append("fresh")

    assert await runner.run_scoped(owner, name, fresh) == {"status": "complete"}
    assert await runner.run_scoped(owner, name, fresh) == {"status": "leased_or_not_due"}
    await db_session.refresh(lease)
    assert observed == ["failed", "fresh"]
    assert lease.last_success and lease.failure_code is None
    assert lease.checkpoint["execution"] == "read_only"
