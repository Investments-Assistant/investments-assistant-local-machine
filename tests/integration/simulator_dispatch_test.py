"""Durable fair dispatch and expired-worker rollback using independent sessions."""

import asyncio

import pytest
from sqlalchemy import delete, select
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.models import User
from src.execution import runtime
from src.execution.models import (
    ExecutionEvent,
    SimulatorOrder,
    SimulatorAccount,
    SimulatorMandate,
    StrategyDecision,
    SimulatorPosition,
    SimulatorInstrument,
)
from src.operations.models import JobLease, OperationalAlert
from src.execution.mandates import approve_mandate
from tests.integration.mandates_test import prepare

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def dispatch_fixture(integration_engine, monkeypatch):
    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    scopes = []
    async with factory.begin() as session:
        for _ in range(2):
            args = await prepare(session)
            await approve_mandate(session, **args, human_event=True)
            scopes.append(args)
    scopes.sort(key=lambda args: args["mandate_id"])
    monkeypatch.setattr(runtime, "async_session", factory)
    try:
        yield factory, scopes
    finally:
        async with factory.begin() as session:
            for args in scopes:
                orders = select(SimulatorOrder.id).where(SimulatorOrder.account_id == args["account_id"])
                await session.execute(delete(ExecutionEvent).where(ExecutionEvent.order_id.in_(orders)))
                for model in (
                    StrategyDecision,
                    SimulatorOrder,
                    SimulatorPosition,
                    SimulatorMandate,
                    SimulatorInstrument,
                    OperationalAlert,
                ):
                    await session.execute(delete(model).where(model.account_id == args["account_id"]))
                await session.execute(delete(SimulatorAccount).where(SimulatorAccount.id == args["account_id"]))
                await session.execute(delete(JobLease).where(JobLease.user_id == args["user_id"]))
                await session.execute(delete(User).where(User.id == args["user_id"]))


@pytest.mark.parametrize("workers", [1, 2])
async def test_denied_first_batch_cannot_starve_later_mandates(dispatch_fixture, monkeypatch, workers):
    factory, scopes = dispatch_fixture
    monkeypatch.setattr(runtime, "MAX_DISPATCH_BATCH", 1)
    async with factory.begin() as session:
        account = await session.get(SimulatorAccount, scopes[0]["account_id"])
        account.halted, account.halt_reason = True, "OPERATOR_HALT"
    results = []
    for _ in range(2):
        batches = await asyncio.gather(*(runtime.run_simulator_strategies() for _ in range(workers)))
        results.extend(result for batch in batches for result in batch)
    assert sum(result["status"] == "filled" for result in results) == 1
    assert sum(result.get("reason") == "OPERATOR_HALTED" for result in results) == 1
    assert await runtime.run_simulator_strategies() == []
    async with factory() as session:
        for index, args in enumerate(scopes):
            jobs = (await session.scalars(select(JobLease).where(JobLease.user_id == args["user_id"]))).all()
            assert len(jobs) == 1 and jobs[0].next_due > jobs[0].lease_until
            orders = (
                await session.scalars(
                    select(SimulatorOrder).where(
                        SimulatorOrder.account_id == args["account_id"],
                    )
                )
            ).all()
            assert len(orders) == index
            if index == 0:
                assert jobs[0].failure_code == "OPERATOR_HALTED"
                assert (await session.get(SimulatorAccount, args["account_id"])).halted
            else:
                assert jobs[0].last_success and jobs[0].checkpoint["status"] == "filled"


async def test_expired_dispatch_rolls_back_order_fill_quote_and_decision(dispatch_fixture, monkeypatch):
    factory, scopes = dispatch_fixture
    acquire, run_tick = runtime.acquire, runtime.run_tick

    async def short_lease(session, **kwargs):
        return await acquire(session, **kwargs, lease_seconds=1)

    async def delayed_tick(session, **kwargs):
        result = await run_tick(session, **kwargs)
        await asyncio.sleep(1.1)
        return result

    monkeypatch.setattr(runtime, "acquire", short_lease)
    monkeypatch.setattr(runtime, "run_tick", delayed_tick)
    async with factory() as session:
        original = {
            quote.id: quote.as_of
            for quote in (
                await session.scalars(
                    select(SimulatorInstrument).where(
                        SimulatorInstrument.account_id.in_([args["account_id"] for args in scopes]),
                    )
                )
            ).all()
        }
    results = await runtime.run_simulator_strategies()
    assert len(results) == 2 and all(result.get("reason") == "STALE_JOB_LEASE" for result in results)
    async with factory() as session:
        for args in scopes:
            account = await session.get(SimulatorAccount, args["account_id"])
            assert account.cash == 1000 and account.reserved == 0 and not account.halted
            for model in (SimulatorOrder, StrategyDecision, SimulatorPosition):
                assert not (await session.scalars(select(model).where(model.account_id == account.id))).all()
            for quote in (
                await session.scalars(
                    select(SimulatorInstrument).where(
                        SimulatorInstrument.account_id == account.id,
                    )
                )
            ).all():
                assert quote.as_of == original[quote.id]
            job = await session.scalar(select(JobLease).where(JobLease.user_id == args["user_id"]))
            assert job.last_success is None and job.checkpoint == {}


async def test_deactivation_after_claim_prevents_quote_writes_and_orders(dispatch_fixture, monkeypatch):
    factory, scopes = dispatch_fixture
    acquire = runtime.acquire

    async def deactivate_after_claim(session, **kwargs):
        lease = await acquire(session, **kwargs)
        user = await session.get(User, kwargs["user_id"])
        user.is_active = False
        return lease

    monkeypatch.setattr(runtime, "acquire", deactivate_after_claim)
    async with factory() as session:
        original = {
            quote.id: quote.as_of
            for quote in (
                await session.scalars(
                    select(SimulatorInstrument).where(
                        SimulatorInstrument.account_id.in_([args["account_id"] for args in scopes]),
                    )
                )
            ).all()
        }
    results = await runtime.run_simulator_strategies()
    assert len(results) == 2 and all(result.get("reason") == "PRINCIPAL_INACTIVE" for result in results)
    async with factory() as session:
        for args in scopes:
            assert not (
                await session.scalars(
                    select(SimulatorOrder).where(
                        SimulatorOrder.account_id == args["account_id"],
                    )
                )
            ).all()
            for quote in (
                await session.scalars(
                    select(SimulatorInstrument).where(
                        SimulatorInstrument.account_id == args["account_id"],
                    )
                )
            ).all():
                assert quote.as_of == original[quote.id]
    assert await runtime.run_simulator_strategies() == []


@pytest.mark.parametrize("persistence_available", [True, False])
async def test_job_timeout_rolls_back_trading_and_reports_durable_failure(
    dispatch_fixture,
    monkeypatch,
    persistence_available,
):
    from sqlalchemy.exc import OperationalError

    factory, scopes = dispatch_fixture
    run_tick = runtime.run_tick
    monkeypatch.setattr(runtime, "MAX_JOB_SECONDS", 1)

    async def slow_tick(session, **kwargs):
        result = await run_tick(session, **kwargs)
        await asyncio.sleep(1.1)
        return result

    async def unavailable_alert(*args, **kwargs):
        raise OperationalError("synthetic alert storage unavailable", {}, Exception("fixture"))

    monkeypatch.setattr(runtime, "run_tick", slow_tick)
    if not persistence_available:
        monkeypatch.setattr(runtime, "emit", unavailable_alert)
    results = await runtime.run_simulator_strategies()
    assert len(results) == 2
    assert all(result["status"] == "failed" and result["reason"] == "SIMULATOR_JOB_TIMEOUT" for result in results)
    if not persistence_available:
        assert all(result["failure_persistence"] == "unavailable" for result in results)
    async with factory() as session:
        for args in scopes:
            account = await session.get(SimulatorAccount, args["account_id"])
            assert account.cash == 1000 and account.reserved == 0
            for model in (SimulatorOrder, StrategyDecision, SimulatorPosition):
                assert not (await session.scalars(select(model).where(model.account_id == account.id))).all()
            job = await session.scalar(select(JobLease).where(JobLease.user_id == args["user_id"]))
            alerts = (
                await session.scalars(
                    select(OperationalAlert).where(
                        OperationalAlert.account_id == account.id,
                    )
                )
            ).all()
            assert job.last_success is None
            if persistence_available:
                assert job.failure_code == "SIMULATOR_JOB_TIMEOUT"
                assert len(alerts) == 1 and alerts[0].observed_value == "SIMULATOR_JOB_TIMEOUT"
                assert alerts[0].delivery_status == "in_app"
            else:
                assert job.failure_code is None and alerts == []


@pytest.mark.parametrize("failure", ["cancel", "code_error", "cycle_timeout"])
async def test_cancellation_and_code_errors_cannot_publish_partial_work(dispatch_fixture, monkeypatch, failure):
    factory, scopes = dispatch_fixture
    run_tick = runtime.run_tick
    reached = asyncio.Event()
    if failure == "cycle_timeout":
        monkeypatch.setattr(runtime, "MAX_CYCLE_SECONDS", 1)

    async def interrupted_tick(session, **kwargs):
        await run_tick(session, **kwargs)
        reached.set()
        if failure == "code_error":
            raise ValueError("synthetic programmer error must propagate")
        await asyncio.sleep(2)
        raise AssertionError("Should have been cancelled")

    monkeypatch.setattr(runtime, "run_tick", interrupted_tick)
    task = asyncio.create_task(runtime.run_simulator_strategies())
    await asyncio.wait_for(reached.wait(), timeout=5)
    if failure == "cancel":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    elif failure == "code_error":
        with pytest.raises(ValueError, match="programmer error"):
            await task
    else:
        result = await task
        assert result == [
            {"status": "partial_failure", "reason": "SIMULATOR_CYCLE_TIMEOUT", "failure_persistence": "unavailable"}
        ]
    async with factory() as session:
        for args in scopes:
            account = await session.get(SimulatorAccount, args["account_id"])
            assert account.cash == 1000 and account.reserved == 0
            assert not (
                await session.scalars(
                    select(SimulatorOrder).where(
                        SimulatorOrder.account_id == account.id,
                    )
                )
            ).all()


async def test_locked_account_times_out_without_blocking_other_mandates(dispatch_fixture):
    factory, scopes = dispatch_fixture
    async with factory.begin() as blocker:
        await blocker.scalar(
            select(SimulatorAccount)
            .where(
                SimulatorAccount.id == scopes[0]["account_id"],
            )
            .with_for_update()
        )
        results = await runtime.run_simulator_strategies()
    assert len(results) == 2
    assert results[0]["status"] == "failed" and results[0]["reason"] == "SIMULATOR_STORAGE_FAILED"
    assert results[1]["status"] == "filled"
    async with factory() as session:
        denied = await session.get(SimulatorAccount, scopes[0]["account_id"])
        assert denied.cash == 1000 and denied.reserved == 0
        assert not (
            await session.scalars(
                select(SimulatorOrder).where(
                    SimulatorOrder.account_id == denied.id,
                )
            )
        ).all()
        job = await session.scalar(select(JobLease).where(JobLease.user_id == scopes[0]["user_id"]))
        assert job.failure_code == "SIMULATOR_STORAGE_FAILED" and job.last_success is None
        alert = await session.scalar(select(OperationalAlert).where(OperationalAlert.account_id == denied.id))
        assert alert.observed_value == "SIMULATOR_STORAGE_FAILED"
