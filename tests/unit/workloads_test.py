"""Cancellation never frees capacity while a native worker remains alive."""

import asyncio
from threading import Event
from contextvars import ContextVar

import pytest

from src.operations.workloads import WorkPool, WorkloadBusy

pytestmark = pytest.mark.unit


async def test_cancelled_worker_retains_capacity_until_it_actually_finishes():
    pool = WorkPool(1, "FIXTURE")
    started, release = Event(), Event()

    def native():
        started.set()
        assert release.wait(5)
        return "finished"

    task = asyncio.create_task(pool.arun(native))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(WorkloadBusy, match="FIXTURE_BUSY"):
            await pool.arun(lambda: "must not run")
    finally:
        release.set()
    for _ in range(100):
        await asyncio.sleep(0.01)
        try:
            assert await pool.arun(lambda: "next") == "next"
            break
        except WorkloadBusy:
            continue
    else:
        pytest.fail("Completed worker did not release capacity")


async def test_timeout_preserves_context_and_synchronous_admission_boundary():
    pool = WorkPool(1, "FIXTURE")
    owner = ContextVar("fixture_owner", default=None)
    token = owner.set("current-user")
    release = Event()
    seen = []

    def native():
        seen.append(owner.get())
        assert release.wait(5)

    try:
        with pytest.raises(TimeoutError):
            await pool.arun(native, timeout=0.05)
        assert seen == ["current-user"]
        with pytest.raises(WorkloadBusy):
            pool.run(lambda: None)
    finally:
        release.set()
        owner.reset(token)
