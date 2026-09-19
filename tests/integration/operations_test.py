import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from src.db.models import User
from src.operations.jobs import acquire, complete
from src.execution.policy import PolicyDenied
from src.operations.alerts import emit, acknowledge, deliver_local
from src.operations.models import JobLease, OperationalAlert

pytestmark = pytest.mark.integration


async def user(session):
    row = User(
        id=str(uuid.uuid4()),
        username="operations-" + uuid.uuid4().hex,
        password_hash="synthetic-non-login",
        is_active=True,
    )
    session.add(row)
    await session.flush()
    return row.id


async def test_leases_deduplicate_and_reject_stale_completion(db_session):
    owner = await user(db_session)
    lease_id, token = await acquire(db_session, user_id=owner, name="fixture_scan")
    assert await acquire(db_session, user_id=owner, name="fixture_scan") is None
    with pytest.raises(PolicyDenied, match="STALE_JOB_LEASE"):
        await complete(
            db_session, lease_id=lease_id, token="old-worker", checkpoint={}, interval_seconds=60
        )
    await complete(
        db_session,
        lease_id=lease_id,
        token=token,
        checkpoint={"last_evidence": "fixture"},
        interval_seconds=60,
    )
    assert await acquire(db_session, user_id=owner, name="fixture_scan") is None
    row = await db_session.get(JobLease, lease_id)
    assert row.checkpoint == {"last_evidence": "fixture"} and row.last_success


async def test_expired_lease_recovery_does_not_accept_previous_worker(db_session):
    owner = await user(db_session)
    lease_id, old_token = await acquire(db_session, user_id=owner, name="fixture_scan")
    row = await db_session.get(JobLease, lease_id)
    row.lease_until = datetime.now(UTC) - timedelta(minutes=2)
    row.next_due = row.lease_until
    await db_session.flush()
    _, token = await acquire(db_session, user_id=owner, name="fixture_scan")
    assert token != old_token
    with pytest.raises(PolicyDenied, match="STALE_JOB_LEASE"):
        await complete(
            db_session, lease_id=lease_id, token=old_token, checkpoint={}, interval_seconds=60
        )
    await complete(
        db_session,
        lease_id=lease_id,
        token=token,
        checkpoint={},
        interval_seconds=60,
        failure_code="DEPENDENCY_UNAVAILABLE",
    )
    await db_session.refresh(row)
    assert row.last_success is None and row.failure_code == "DEPENDENCY_UNAVAILABLE"


async def test_alert_dedup_ack_reopen_and_delivery_failure(db_session):
    owner = await user(db_session)
    args = dict(
        user_id=owner,
        rule="stale_data",
        observed_value="120 seconds",
        threshold="60 seconds",
        message="Fixture quote stale",
        evidence_at=datetime.now(UTC),
    )
    alert_id = await emit(db_session, **args)
    assert await emit(db_session, **args) == alert_id
    row = await db_session.get(OperationalAlert, alert_id)
    assert row.occurrences == 2
    bad = AsyncMock(side_effect=RuntimeError("synthetic sink failure"))
    assert await deliver_local(db_session, user_id=owner, alert_id=alert_id, sink=bad) == "failed"
    assert row.delivery_error == "LOCAL_SINK_FAILED"
    sink = AsyncMock()
    assert (
        await deliver_local(db_session, user_id=owner, alert_id=alert_id, sink=sink) == "delivered"
    )
    assert (
        await deliver_local(db_session, user_id=owner, alert_id=alert_id, sink=sink)
        == "deduplicated"
    )
    sink.assert_awaited_once()
    assert await acknowledge(db_session, user_id=owner, alert_id=alert_id) == "acknowledged"
    assert await emit(db_session, **args) == alert_id
    await db_session.refresh(row)
    assert row.status == "acknowledged"
    await acknowledge(db_session, user_id=owner, alert_id=alert_id, resolve=True)
    assert await emit(db_session, **args) == alert_id
    await db_session.refresh(row)
    assert row.status == "open" and row.delivery_status == "in_app"
    other = await user(db_session)
    with pytest.raises(PolicyDenied, match="ALERT_NOT_OWNED"):
        await acknowledge(db_session, user_id=other, alert_id=alert_id)
