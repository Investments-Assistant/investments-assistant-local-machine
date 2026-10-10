"""A failed observation stays visible and cannot turn into a successful cycle."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.operations import heartbeat
from src.execution.policy import PolicyDenied

pytestmark = pytest.mark.unit


async def test_failed_owner_does_not_skip_unrelated_due_observation(monkeypatch):
    monkeypatch.setattr(heartbeat, "monitoring_users", AsyncMock(return_value=["one", "two"]))
    observe = AsyncMock(side_effect=[PolicyDenied("STALE_JOB_LEASE"), {"status": "observed"}])
    monkeypatch.setattr(heartbeat, "observe_heartbeat", observe)
    assert await heartbeat.monitor_heartbeat() == [
        {"status": "failed", "reason": "STALE_JOB_LEASE"}, {"status": "observed"}
    ]
    assert observe.await_count == 2


async def test_cycle_timeout_is_reported_and_cancellation_propagates(monkeypatch):
    selection = AsyncMock(side_effect=TimeoutError)
    monkeypatch.setattr(heartbeat, "monitoring_users", selection)
    assert await heartbeat.monitor_heartbeat() == [
        {"status": "partial_failure", "reason": "HEARTBEAT_CYCLE_UNAVAILABLE"}
    ]
    selection.side_effect = asyncio.CancelledError
    with pytest.raises(asyncio.CancelledError):
        await heartbeat.monitor_heartbeat()
