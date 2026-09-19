"""Real leases and marked-risk monitoring without model or broker availability."""

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select

from src.agent import clients
from src.db.models import User
from src.execution import monitor
from tests.integration import manual_risk_test
from src.execution.models import SimulatorAccount, SimulatorInstrument
from src.operations.models import JobLease, OperationalAlert

account_fixture = manual_risk_test.account_fixture

pytestmark = pytest.mark.integration


async def test_risk_monitor_requires_opt_in_and_deduplicates_concurrent_workers(account_fixture, monkeypatch):
    factory, ids, _, _ = account_fixture
    monkeypatch.setattr(monitor, "async_session", factory)

    def unavailable_model():
        raise AssertionError("Deterministic risk must not construct a model client")

    monkeypatch.setattr(clients, "create_llm_client", unavailable_model)
    async with factory.begin() as session:
        account = await session.get(SimulatorAccount, ids[1])
        account.mandate = dict(account.mandate, fixture=True)
        quote = await session.get(SimulatorInstrument, ids[2])
        quote.price, quote.as_of = 40, datetime.now(UTC)
    assert await monitor.monitor_simulator_risk(user_id=ids[0]) == []
    try:
        async with factory.begin() as session:
            user = await session.get(User, ids[0])
            user.preferences = {"monitoring_enabled": True}
        results = await asyncio.gather(
            monitor.monitor_simulator_risk(user_id=ids[0]),
            monitor.monitor_simulator_risk(user_id=ids[0]),
        )
        flattened = [result for batch in results for result in batch]
        assert len(flattened) == 1
        assert flattened[0]["status"] == "halted" and flattened[0]["reason"] == "MARKED_ACCOUNT_LOSS_LIMIT"
        async with factory.begin() as session:
            account = await session.get(SimulatorAccount, ids[1])
            assert account.halted and account.reserved == 0
            job = await session.scalar(select(JobLease).where(JobLease.user_id == ids[0]))
            assert job.last_success and job.checkpoint["execution"] == "risk_only_no_orders"
            assert job.checkpoint["status"] == "halted" and job.failure_code is None
            alerts = (await session.scalars(select(OperationalAlert).where(OperationalAlert.user_id == ids[0]))).all()
            assert len(alerts) == 1 and alerts[0].occurrences == 1
        assert await monitor.monitor_simulator_risk(user_id=ids[0]) == []
    finally:
        async with factory.begin() as session:
            await session.execute(delete(JobLease).where(JobLease.user_id == ids[0]))


async def test_malformed_opt_in_is_not_coerced_or_allowed_to_break_monitoring(account_fixture, monkeypatch):
    factory, ids, _, _ = account_fixture
    monkeypatch.setattr(monitor, "async_session", factory)
    async with factory.begin() as session:
        user = await session.get(User, ids[0])
        user.preferences = {"monitoring_enabled": "not a boolean"}
        account = await session.get(SimulatorAccount, ids[1])
        account.mandate = dict(account.mandate, fixture=True)
    assert await monitor.monitor_simulator_risk(user_id=ids[0]) == []


async def test_expired_worker_cannot_publish_halt_or_success_checkpoint(account_fixture, monkeypatch):
    factory, ids, _, _ = account_fixture
    monkeypatch.setattr(monitor, "async_session", factory)
    original_acquire, original_check = monitor.acquire, monitor.enforce_account_risk
    reached_check = asyncio.Event()

    async def short_lease(session, **kwargs):
        return await original_acquire(session, **(kwargs | {"lease_seconds": 1}))

    async def delayed_check(session, account):
        try:
            return await original_check(session, account)
        finally:
            reached_check.set()
            await asyncio.sleep(1.1)

    monkeypatch.setattr(monitor, "acquire", short_lease)
    monkeypatch.setattr(monitor, "enforce_account_risk", delayed_check)
    async with factory.begin() as session:
        user = await session.get(User, ids[0])
        user.preferences = {"monitoring_enabled": True}
        account = await session.get(SimulatorAccount, ids[1])
        account.mandate = dict(account.mandate, fixture=True)
        quote = await session.get(SimulatorInstrument, ids[2])
        quote.price, quote.as_of = 40, datetime.now(UTC)
    try:
        result = await monitor.monitor_simulator_risk(user_id=ids[0])
        assert reached_check.is_set()
        assert result[0]["status"] == "failed" and result[0]["reason"] == "STALE_JOB_LEASE"
        async with factory.begin() as session:
            account = await session.get(SimulatorAccount, ids[1])
            job = await session.scalar(select(JobLease).where(JobLease.user_id == ids[0]))
            assert not account.halted and job.last_success is None and job.checkpoint == {}
            assert not (await session.scalars(select(OperationalAlert).where(OperationalAlert.user_id == ids[0]))).all()
    finally:
        async with factory.begin() as session:
            await session.execute(delete(JobLease).where(JobLease.user_id == ids[0]))
