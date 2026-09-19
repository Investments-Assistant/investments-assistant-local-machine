"""Bound expensive worker admission and retain capacity until native work stops."""

import asyncio
from functools import partial
from threading import BoundedSemaphore
from contextvars import copy_context


class WorkloadBusy(RuntimeError):
    pass


class WorkPool:
    def __init__(self, slots: int, name: str):
        self._slots = BoundedSemaphore(slots)
        self.name = name

    def _acquire(self):
        if not self._slots.acquire(blocking=False):
            raise WorkloadBusy(self.name + "_BUSY")

    def _finish(self, call):
        try:
            return call()
        finally:
            self._slots.release()

    def run(self, function, *args, **kwargs):
        self._acquire()
        return self._finish(partial(function, *args, **kwargs))

    async def arun(self, function, *args, timeout=120, **kwargs):
        self._acquire()
        context = copy_context()
        call = partial(context.run, partial(function, *args, **kwargs))
        try:
            future = asyncio.get_running_loop().run_in_executor(None, self._finish, call)
        except BaseException:
            self._slots.release()
            raise
        # A cancelled HTTP task cannot kill native work or release its admission slot.
        # Retrieve detached failures without logging private inputs or tracebacks.
        future.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        async with asyncio.timeout(timeout):
            return await asyncio.shield(future)


simulation_work = WorkPool(2, "SIMULATION")
pdf_work = WorkPool(1, "PDF")
