"""Explicit finite read capture; not registered as a job, tool or HTTP endpoint.

Deployment activation and real-account consent remain separate gates. No retry,
reconnect, trading action or external notification is performed by this service.
"""

import time
import asyncio
from datetime import UTC, datetime
from contextlib import asynccontextmanager

from sqlalchemy import text

from src.db.database import async_session
from src.execution.policy import PolicyDenied
from src.operations.alerts import emit
from src.tools.broker_accounts import BrokerAccountConfig
from src.execution.broker_monitor import _record_failure
from src.tools.brokers.ibkr_session import ReadSessionWorker
from src.execution.broker_stream_journal import begin_stream, checkpoint_batch
from src.tools.brokers.ibkr_observations import CallbackWindow


@asynccontextmanager
async def transaction():
    async with asyncio.timeout(10), async_session.begin() as session:
        await session.execute(text("SET LOCAL lock_timeout = '2s'"))
        await session.execute(text("SET LOCAL statement_timeout = '5s'"))
        yield session


async def capture_observations(*, user_id, account_id, duration_seconds=60, batch_seconds=5):
    """Capture continuously between bounded drains, rechecking DB authority each time.

    Matching scoped adapter reads share this SDK owner; other scopes fail busy.
    Background activation remains a separate explicit decision. Its final
    status describes only this finite interval, not full broker reconciliation.
    """
    if (type(duration_seconds) is not int or not 1 <= duration_seconds <= 480
            or type(batch_seconds) is not int or not 1 <= batch_seconds <= 10):
        raise ValueError("Invalid bounded capture duration")
    async with transaction() as session:
        config, scope = await begin_stream(session, user_id=user_id, account_id=account_id,
                                           maximum_seconds=duration_seconds + 90)
    worker = None
    try:
        selected = BrokerAccountConfig(account_id, user_id, "ibkr", "Selected account", config)
        window = CallbackWindow(config["broker_account_id"])
        worker = ReadSessionWorker(selected, maximum_seconds=duration_seconds + 60,
                                   subscription=lambda ib, _actual: window.subscribed(ib))
        worker.register_reads()
        await asyncio.to_thread(worker.start, timeout=15)
        deadline = time.monotonic() + duration_seconds

        def drain(ib, actual, *, initial=False, final=False):
            if initial:
                from ib_insync import ExecutionFilter
                window.request_snapshot(ib, ExecutionFilter(acctCode=actual))
            # Detach in this same owner operation on any detected gap, before
            # returning its final batch to the async persistence coordinator.
            return window.drain(final=final or bool(window.failures))

        initial = True
        while True:
            due = time.monotonic() >= deadline
            batch = await asyncio.to_thread(worker.call,
                lambda ib, actual, initial=initial, due=due: drain(ib, actual, initial=initial, final=due), timeout=20)
            initial = False
            final = not batch["capture_active"]
            if final and not await asyncio.to_thread(worker.close, timeout=10):
                raise TimeoutError("IBKR_SESSION_CLEANUP_PENDING")
            if final and worker.failure_code:
                raise RuntimeError("BROKER_STREAM_CLEANUP_FAILED")
            async with transaction() as session:
                summary = await checkpoint_batch(session, scope=scope,
                    observations=batch["observations"], final=final, failures=batch["failures"])
                if batch["failures"]:
                    await emit(session, user_id=user_id, account_id=account_id,
                        rule="broker_callback_evidence", observed_value=batch["failures"][0],
                        threshold="review callback gaps and conflicts",
                        message="Broker callback capture was partial. Review evidence before another read.",
                        evidence_at=datetime.now(UTC))
            if final:
                return summary
            await asyncio.sleep(max(0, min(batch_seconds, deadline - time.monotonic())))
    except BaseException as exc:
        if worker is not None:
            # Signal immediately even if cancellation interrupts a queued/native
            # to_thread operation. No late result is persisted after this branch.
            worker.stop()
        code = ("BROKER_STREAM_CANCELLED" if isinstance(exc, asyncio.CancelledError)
                else exc.code if isinstance(exc, PolicyDenied)
                else "BROKER_STREAM_TIMEOUT" if isinstance(exc, TimeoutError)
                else "BROKER_STREAM_INTERRUPTED")
        await _record_failure(scope.lease, user_id, account_id, code, keep_lease=True)
        raise
    finally:
        if worker is not None:
            worker.stop()
            # Native timeout/cancellation retains SDK ownership until real cleanup.
            # The failure branch deliberately leaves admission leased meanwhile.
            await asyncio.to_thread(worker.wait_closed, timeout=1)
