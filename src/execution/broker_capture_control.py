"""Explicit, finite read-capture activation. Never starts on import or restart."""

import asyncio

from src.execution.policy import PolicyDenied
from src.execution.broker_stream import transaction, capture_observations
from src.execution.broker_observations import selected_account


class CaptureController:
    """One process-local task; durable leases and native ownership remain separate."""

    def __init__(self):
        self.task = None
        self.scope = None
        self.state = "inactive"
        self.closed = False

    def status(self, *, user_id, account_id):
        # Never disclose another owner's activity or failure details.
        state = self.state if self.scope == (user_id, account_id) else "inactive"
        return {"status": state, "complete_history": False, "execution_authority": "none",
                "native_cleanup_verified": False, "automatic_restart": False}

    async def start(self, *, user_id, account_id, duration_seconds):
        if type(duration_seconds) is not int or not 1 <= duration_seconds <= 480:
            raise PolicyDenied("INVALID_CAPTURE_DURATION")
        # Recheck real current consent before admitting a task. The coordinator
        # checks again when acquiring the durable lease and before every batch.
        async with transaction() as session:
            await selected_account(session, user_id=user_id, account_id=account_id)
        # No await between checking the slot and publishing task ownership.
        if self.closed:
            raise PolicyDenied("BROKER_CAPTURE_SHUTTING_DOWN")
        if self.task is not None and not self.task.done():
            raise PolicyDenied("BROKER_CAPTURE_BUSY")
        self.scope = (user_id, account_id)
        self.state = "starting"
        self.task = asyncio.create_task(self._run(user_id, account_id, duration_seconds))
        self.task.add_done_callback(self._finished)
        return self.status(user_id=user_id, account_id=account_id)

    def _finished(self, task):
        if self.task is task and task.cancelled():
            # Cancellation can happen before _run executes its first line.
            self.state = "interrupted"

    async def _run(self, user_id, account_id, duration):
        self.state = "running"
        try:
            summary = await capture_observations(user_id=user_id, account_id=account_id,
                                                 duration_seconds=duration)
            self.state = "observed" if summary.get("status") == "observed" else "partial"
        except asyncio.CancelledError:
            self.state = "interrupted"
            raise
        except Exception:
            # Durable checkpoint/failure alert is authoritative; private SDK
            # exceptions must not become browser-visible messages.
            self.state = "failed"

    async def stop(self, *, user_id, account_id):
        if self.scope != (user_id, account_id):
            raise PolicyDenied("BROKER_CAPTURE_NOT_OWNED")
        if self.task is not None and not self.task.done() and self.state != "stop_requested":
            self.state = "stop_requested"
            self.task.cancel()
        # Cancellation is a request, not proof that native SDK cleanup finished.
        return self.status(user_id=user_id, account_id=account_id)

    async def shutdown(self):
        self.closed = True
        if self.task is not None and not self.task.done():
            if self.state != "stop_requested":
                self.state = "stop_requested"
                self.task.cancel()
            await asyncio.wait({self.task}, timeout=15)


capture_control = CaptureController()
