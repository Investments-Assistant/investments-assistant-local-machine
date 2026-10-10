"""Real database recovery alerts, no OS clock changes or external watchdog calls."""

import uuid
import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.models import User
from src.operations import heartbeat
from src.execution.policy import PolicyDenied
from src.operations.models import JobLease, OperationalAlert

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def heartbeat_owner(integration_engine, monkeypatch):
    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    owner = str(uuid.uuid4())
    async with factory.begin() as session:
        session.add(User(id=owner, username="heartbeat-" + owner, password_hash="fixture",
                         is_active=True, preferences={"monitoring_enabled": True}))
    monkeypatch.setattr(heartbeat, "async_session", factory)
    try:
        yield factory, owner
    finally:
        async with factory.begin() as session:
            await session.execute(delete(OperationalAlert).where(OperationalAlert.user_id == owner))
            await session.execute(delete(JobLease).where(JobLease.user_id == owner))
            await session.execute(delete(User).where(User.id == owner))


async def make_overdue(factory, owner):
    async with factory.begin() as session:
        row = await session.scalar(select(JobLease).where(JobLease.user_id == owner))
        row.next_due = row.lease_until = datetime.now(UTC) - timedelta(hours=2)


async def test_resume_records_one_gap_and_no_historical_replay(heartbeat_owner):
    factory, owner = heartbeat_owner
    initial = await heartbeat.observe_heartbeat(owner)
    assert initial["status"] == "observed" and initial["overdue_seconds"] is None
    await make_overdue(factory, owner)
    results = await asyncio.gather(heartbeat.observe_heartbeat(owner), heartbeat.observe_heartbeat(owner))
    assert sorted(result["status"] for result in results) == ["gap_observed", "leased_or_not_due"]
    async with factory() as session:
        alerts = list(await session.scalars(select(OperationalAlert).where(OperationalAlert.user_id == owner)))
        assert len(alerts) == 1 and alerts[0].occurrences == 1
        assert alerts[0].rule == "monitoring_heartbeat_gap" and alerts[0].delivery_status == "in_app"
        claim = await session.scalar(select(JobLease).where(JobLease.user_id == owner))
        assert claim.checkpoint["execution"] == "read_only_no_orders"
        assert 7200 <= claim.checkpoint["overdue_seconds"] < 7210
    # Repeated recovered gaps reuse the durable alert; no mail/broker/model is invoked.
    await make_overdue(factory, owner)
    assert (await heartbeat.observe_heartbeat(owner))["status"] == "gap_observed"
    async with factory() as session:
        alert = await session.scalar(select(OperationalAlert).where(OperationalAlert.user_id == owner))
        assert alert.occurrences == 2


@pytest.mark.parametrize("mode", ["optout", "inactive", "malformed"])
async def test_heartbeat_requires_active_explicit_opt_in(heartbeat_owner, mode):
    factory, owner = heartbeat_owner
    async with factory.begin() as session:
        user = await session.get(User, owner)
        if mode == "inactive":
            user.is_active = False
        else:
            user.preferences = {"monitoring_enabled": False if mode == "optout" else "true"}
    assert await heartbeat.observe_heartbeat(owner) == {"status": "monitoring_disabled"}
    async with factory() as session:
        assert await session.scalar(select(JobLease.id).where(JobLease.user_id == owner)) is None
        assert await session.scalar(select(OperationalAlert.id).where(OperationalAlert.user_id == owner)) is None


async def test_expired_worker_rolls_back_gap_and_checkpoint(heartbeat_owner, monkeypatch):
    factory, owner = heartbeat_owner
    initial = await heartbeat.observe_heartbeat(owner)
    await make_overdue(factory, owner)
    complete = heartbeat.complete

    async def expired(session, **kwargs):
        row = await session.get(JobLease, kwargs["lease_id"])
        row.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        await session.flush()
        await complete(session, **kwargs)

    monkeypatch.setattr(heartbeat, "complete", expired)
    with pytest.raises(PolicyDenied, match="STALE_JOB_LEASE"):
        await heartbeat.observe_heartbeat(owner)
    async with factory() as session:
        assert await session.scalar(select(OperationalAlert.id).where(OperationalAlert.user_id == owner)) is None
        row = await session.scalar(select(JobLease).where(JobLease.user_id == owner))
        assert row.checkpoint == initial
    monkeypatch.setattr(heartbeat, "complete", complete)
    assert (await heartbeat.observe_heartbeat(owner))["status"] == "gap_observed"
