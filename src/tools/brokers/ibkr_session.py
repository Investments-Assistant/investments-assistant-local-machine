"""One SDK owner thread with bounded read admission and explicit session lifetime.

No session starts automatically. A caller must supply already scoped read consent;
continuous persistence must separately recheck current database authority. Stopping
cannot kill a native request: ownership is retained until its actual cleanup ends.
"""

from copy import deepcopy
import math
import time
import queue
import asyncio
import threading
from contextlib import ExitStack
from concurrent.futures import (
    Future,
    TimeoutError as FutureTimeout,
)

from src.tools.brokers.ibkr import _error, _config, _connection

_registry_lock = threading.Lock()
_registered_worker = None


def route_read(account, operation):
    """Route only an exactly matching scoped configuration; never fall back on error."""
    _config(account)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError("IBKR_SYNC_ADAPTER_REQUIRES_WORKER_THREAD")
    with _registry_lock:
        owner = _registered_worker
        if owner is None:
            return False, None
        if (owner.account.id, owner.account.user_id) != (account.id, account.user_id):
            raise RuntimeError("IBKR_CLIENT_BUSY")
        if owner.account.config != account.config:
            raise RuntimeError("IBKR_SESSION_CONFIGURATION_CHANGED")
    return True, owner.call(operation, timeout=20)


def _seconds(value, *, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Invalid session time budget")
    if not 0 < value <= maximum:
        raise ValueError("Invalid session time budget")
    return value


class ReadSessionWorker:
    def __init__(self, account, *, maximum_seconds=60, queue_capacity=4,
                 connection_factory=None, subscription=None):
        _config(account)  # Reject missing scope/consent before thread or SDK construction.
        self.account = deepcopy(account)
        self.maximum_seconds = _seconds(maximum_seconds, maximum=600)
        if type(queue_capacity) is not int or not 1 <= queue_capacity <= 16:
            raise ValueError("Invalid read queue capacity")
        self._connection = connection_factory or _connection
        self._subscription = subscription
        self._queue = queue.Queue(maxsize=queue_capacity)
        self._gate = threading.Lock()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._closed = threading.Event()
        self._thread = None
        self.failure_code = None

    def register_reads(self):
        """Reserve shared read routing before startup, until actual native cleanup."""
        global _registered_worker
        with self._gate, _registry_lock:
            if self._thread is not None or self._stop.is_set():
                raise RuntimeError("IBKR_SESSION_ALREADY_STARTED_OR_CLOSED")
            if _registered_worker is not None:
                raise RuntimeError("IBKR_CLIENT_BUSY")
            _registered_worker = self

    def _unregister(self):
        global _registered_worker
        with _registry_lock:
            if _registered_worker is self:
                _registered_worker = None

    def start(self, *, timeout=15):
        timeout = _seconds(timeout, maximum=30)
        with self._gate:
            if self._thread is not None or self._stop.is_set():
                raise RuntimeError("IBKR_SESSION_ALREADY_STARTED_OR_CLOSED")
            self._thread = threading.Thread(target=self._run, name="ibkr-read-owner", daemon=True)
            self._thread.start()
        if not self._ready.wait(timeout):
            self._stop.set()
            raise TimeoutError("IBKR_SESSION_START_TIMEOUT")
        if self.failure_code:
            raise RuntimeError(self.failure_code)
        return self

    def call(self, operation, *, timeout=15):
        timeout = _seconds(timeout, maximum=30)
        if threading.current_thread() is self._thread:
            raise RuntimeError("IBKR_OWNER_REENTRANT_CALL")
        future = Future()
        with self._gate:
            if self._stop.is_set() or self._closed.is_set():
                raise RuntimeError("IBKR_SESSION_STOPPING")
            if not self._ready.is_set():
                raise RuntimeError("IBKR_SESSION_NOT_READY")
            try:
                self._queue.put_nowait((future, operation, time.monotonic() + timeout))
            except queue.Full:
                raise RuntimeError("IBKR_READ_QUEUE_FULL") from None
        try:
            return future.result(timeout=timeout)
        except FutureTimeout:
            # Cancel unstarted work; in-flight native work retains its owner.
            future.cancel()
            self._stop.set()
            raise TimeoutError("IBKR_READ_TIMEOUT") from None

    def stop(self):
        """Signal cancellation without blocking or pretending native cleanup ended."""
        with self._gate:
            self._stop.set()
            if self._thread is None:
                self._unregister()
                self._closed.set()

    def close(self, *, timeout=1):
        timeout = _seconds(timeout, maximum=30)
        self.stop()
        if threading.current_thread() is self._thread:
            return False
        return self._closed.wait(timeout)

    def wait_closed(self, *, timeout=1):
        return self._closed.wait(_seconds(timeout, maximum=30))

    def _run(self):
        try:
            with ExitStack() as stack:
                ib, actual = stack.enter_context(self._connection(self.account))
                if self._subscription is not None:
                    stack.enter_context(self._subscription(ib, actual))
                deadline = time.monotonic() + self.maximum_seconds
                self._ready.set()
                while not self._stop.is_set():
                    if time.monotonic() >= deadline:
                        self.failure_code = "IBKR_SESSION_EXPIRED"
                        break
                    if not ib.isConnected():
                        self.failure_code = "BROKER_DISCONNECTED"
                        break
                    try:
                        future, operation, due = self._queue.get_nowait()
                    except queue.Empty:
                        # SDK event-loop pumping, not time.sleep or tick-cache polling.
                        ib.sleep(.05)
                        continue
                    if time.monotonic() >= due:
                        future.cancel()
                        continue
                    if not future.set_running_or_notify_cancel():
                        continue
                    try:
                        future.set_result(operation(ib, actual))
                    except Exception as exc:
                        future.set_exception(RuntimeError(_error(exc)["error"]))
                    ib.sleep(0)  # A busy request queue must not starve SDK callbacks.
        except Exception as exc:
            self.failure_code = _error(exc)["error"]
        finally:
            with self._gate:
                self._stop.set()
                while True:
                    try:
                        future, _, _ = self._queue.get_nowait()
                    except queue.Empty:
                        break
                    if future.set_running_or_notify_cancel():
                        future.set_exception(RuntimeError(self.failure_code or "IBKR_SESSION_CLOSED"))
                self._unregister()
                self._closed.set()
                self._ready.set()
