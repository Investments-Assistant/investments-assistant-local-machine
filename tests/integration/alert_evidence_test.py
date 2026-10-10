"""Repeated alerts must describe one coherent, latest observation."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from src.operations import alerts
from src.operations.alerts import emit, acknowledge
from src.operations.models import OperationalAlert
from tests.integration.operations_test import user

pytestmark = pytest.mark.integration


async def test_alert_latest_observation_updates_all_display_fields(db_session):
    owner = await user(db_session)
    at = datetime.now(UTC) - timedelta(minutes=5)
    args = dict(user_id=owner, rule="fixture_resource_pressure", observed_value="80",
                threshold="75", message="Warning at 80", severity="warning", evidence_at=at)
    key = await emit(db_session, **args)
    newer = dict(args, observed_value="95", threshold="90", message="Critical at 95",
                 severity="critical", evidence_at=at + timedelta(minutes=1))
    assert await emit(db_session, **newer) == key
    row = await db_session.get(OperationalAlert, key)
    assert (row.observed_value, row.threshold, row.message, row.severity) == (
        "95", "90", "Critical at 95", "critical"
    )
    assert row.evidence_at == newer["evidence_at"]
    await emit(db_session, **args)
    await db_session.refresh(row)
    assert (row.observed_value, row.threshold, row.message, row.severity) == (
        "95", "90", "Critical at 95", "critical"
    )


async def test_delayed_evidence_cannot_reopen_resolved_alert(db_session):
    owner = await user(db_session)
    at = datetime.now(UTC) - timedelta(minutes=5)
    args = dict(user_id=owner, rule="fixture_resource_pressure", observed_value="95",
                threshold="90", message="Current evidence", severity="critical", evidence_at=at)
    key = await emit(db_session, **args)
    await acknowledge(db_session, user_id=owner, alert_id=key, resolve=True)
    row = await db_session.get(OperationalAlert, key)
    resolved_at = row.resolved_at
    await emit(db_session, **dict(args, evidence_at=at - timedelta(minutes=1)))
    await db_session.refresh(row)
    assert row.status == "resolved" and row.resolved_at == resolved_at
    assert row.evidence_at == at
    row.delivery_status, row.delivery_error = "failed", "LOCAL_SINK_FAILED"
    await db_session.flush()
    await emit(db_session, **dict(args, evidence_at=at + timedelta(minutes=1)))
    await db_session.refresh(row)
    assert row.status == "open" and row.resolved_at is None
    assert row.delivery_status == "in_app" and row.delivery_error is None


async def test_stalled_local_sink_times_out_and_can_retry(db_session, monkeypatch):
    owner = await user(db_session)
    key = await emit(db_session, user_id=owner, rule="fixture_delivery", observed_value="1",
                     threshold="0", message="Local fixture", evidence_at=datetime.now(UTC))
    cancelled = asyncio.Event()
    never = asyncio.Event()

    async def stalled(payload):
        try:
            await never.wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(alerts, "DELIVERY_TIMEOUT_SECONDS", 0.02, raising=False)
    # The outer bound makes the original unbounded implementation fail promptly.
    result = await asyncio.wait_for(
        alerts.deliver_local(db_session, user_id=owner, alert_id=key, sink=stalled), 0.5
    )
    assert result == "failed" and cancelled.is_set()
    row = await db_session.get(OperationalAlert, key)
    assert row.delivery_error == "LOCAL_SINK_TIMEOUT"
    delivered = []

    async def healthy(payload):
        delivered.append(payload["id"])

    assert await alerts.deliver_local(db_session, user_id=owner, alert_id=key, sink=healthy) == "delivered"
    assert row.delivery_error is None and delivered == [key]
    assert await alerts.deliver_local(db_session, user_id=owner, alert_id=key, sink=healthy) == "deduplicated"
    assert delivered == [key]


async def test_delivery_caller_cancellation_is_not_reported_as_success(db_session):
    owner = await user(db_session)
    key = await emit(db_session, user_id=owner, rule="fixture_cancel", observed_value="1",
                     threshold="0", message="Local fixture", evidence_at=datetime.now(UTC))
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def sink(payload):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    task = asyncio.create_task(alerts.deliver_local(db_session, user_id=owner, alert_id=key, sink=sink))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    row = await db_session.get(OperationalAlert, key)
    assert cancelled.is_set() and row.delivery_status == "in_app"
