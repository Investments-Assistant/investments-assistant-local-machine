"""SDK connection/event-loop ownership stays on one bounded worker thread."""

import threading
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.tools.broker_accounts import BrokerAccountConfig
from src.tools.brokers.ibkr_session import ReadSessionWorker

pytestmark = pytest.mark.unit


def account():
    return BrokerAccountConfig("fixture", "owner", "ibkr", "Synthetic", dict(
        enabled=True, read_authorized=True, broker_account_id="SYNTHETIC-SESSION",
        environment="paper", client_id=77,
    ))


class SDK:
    def __init__(self):
        self.threads = []
        self.pumped = threading.Event()
        self.connected = True

    def isConnected(self):
        self.threads.append(threading.get_ident())
        return self.connected

    def sleep(self, seconds):
        self.threads.append(threading.get_ident())
        self.pumped.set()
        threading.Event().wait(min(seconds, .01))


@contextmanager
def connection(sdk, trace):
    trace.append(("connect", threading.get_ident()))
    try:
        yield sdk, "SYNTHETIC-SESSION"
    finally:
        trace.append(("disconnect", threading.get_ident()))


def test_repeated_reads_and_idle_callbacks_share_one_connection_and_owner():
    sdk, trace = SDK(), []
    worker = ReadSessionWorker(account(), connection_factory=lambda _: connection(sdk, trace))
    worker.start()
    try:
        assert sdk.pumped.wait(1)
        first = worker.call(lambda _ib, actual: (actual, threading.get_ident()))
        second = worker.call(lambda _ib, actual: (actual, threading.get_ident()))
        assert first == second and first[1] != threading.get_ident()
        assert [item[0] for item in trace] == ["connect"]
    finally:
        assert worker.close(timeout=1)
    assert [item[0] for item in trace] == ["connect", "disconnect"]
    assert {item[1] for item in trace} == {first[1]} == set(sdk.threads)


def test_timeout_does_not_release_ownership_or_execute_queued_reads():
    sdk, trace = SDK(), []
    entered, release = threading.Event(), threading.Event()
    worker = ReadSessionWorker(account(), connection_factory=lambda _: connection(sdk, trace), queue_capacity=1)
    worker.start()

    def slow(_ib, actual):
        entered.set()
        assert release.wait(2)
        return actual

    try:
        with ThreadPoolExecutor(1) as pool:
            running = pool.submit(worker.call, slow, timeout=.1)
            assert entered.wait(1)
            with pytest.raises(TimeoutError, match="IBKR_READ_TIMEOUT"):
                running.result(timeout=1)
            assert worker.close(timeout=.01) is False
            assert [item[0] for item in trace] == ["connect"]
            with pytest.raises(RuntimeError, match="IBKR_SESSION_STOPPING"):
                worker.call(lambda *_: pytest.fail("A stopped session must not execute new work"))
    finally:
        release.set()
        assert worker.close(timeout=1)
    assert [item[0] for item in trace] == ["connect", "disconnect"]


def test_subscription_cleanup_and_disconnect_run_on_owner_after_failure():
    sdk, trace = SDK(), []

    @contextmanager
    def subscribe(_ib, actual):
        trace.append(("subscribe", threading.get_ident()))
        try:
            yield
        finally:
            trace.append(("unsubscribe", threading.get_ident()))

    worker = ReadSessionWorker(account(), connection_factory=lambda _: connection(sdk, trace), subscription=subscribe)
    worker.start()
    sdk.connected = False
    assert worker.wait_closed(timeout=1)
    assert worker.failure_code == "BROKER_DISCONNECTED"
    assert [item[0] for item in trace] == ["connect", "subscribe", "unsubscribe", "disconnect"]
    assert len({item[1] for item in trace}) == 1


def test_missing_consent_is_rejected_before_a_worker_or_connection_starts():
    selected = account()
    selected.config["read_authorized"] = False
    with pytest.raises(ValueError, match="IBKR_READ_CONSENT_REQUIRED"):
        ReadSessionWorker(selected, connection_factory=lambda _: pytest.fail("No connection allowed"))



def test_default_connection_owns_its_event_loop_and_disconnects_without_sdk_writes(monkeypatch):
    import sys
    from types import SimpleNamespace
    import asyncio

    sdk, trace, loops = SDK(), [], []

    def connect(**kwargs):
        assert kwargs["readonly"] is True and kwargs["account"] == "SYNTHETIC-SESSION"
        loops.append(asyncio.get_event_loop())
        trace.append(("connect", threading.get_ident()))

    def disconnect():
        assert asyncio.get_event_loop() is loops[0]
        trace.append(("disconnect", threading.get_ident()))

    sdk.connect, sdk.disconnect = connect, disconnect
    sdk.managedAccounts = lambda: ["SYNTHETIC-SESSION"]
    monkeypatch.setitem(sys.modules, "ib_insync", SimpleNamespace(IB=lambda: sdk))
    worker = ReadSessionWorker(account())
    worker.start()
    try:
        owner = worker.call(lambda *_: (threading.get_ident(), asyncio.get_event_loop()))
        assert owner[1] is loops[0]
    finally:
        assert worker.close(timeout=1)
    assert loops[0].is_closed()
    assert len({item[1] for item in trace}) == 1


def test_queue_capacity_refuses_excess_work_and_shutdown_rejects_queued_reads(monkeypatch):
    sdk, trace = SDK(), []
    entered, release, queued = threading.Event(), threading.Event(), threading.Event()
    worker = ReadSessionWorker(account(), connection_factory=lambda _: connection(sdk, trace), queue_capacity=1)
    worker.start()

    def slow(*_):
        entered.set()
        assert release.wait(2)

    try:
        with ThreadPoolExecutor(2) as pool:
            first = pool.submit(worker.call, slow, timeout=1)
            assert entered.wait(1)
            original_put = worker._queue.put_nowait

            def put(value):
                original_put(value)
                queued.set()

            monkeypatch.setattr(worker._queue, "put_nowait", put)
            second = pool.submit(worker.call, lambda *_: pytest.fail("Queued read survived shutdown"), timeout=1)
            assert queued.wait(1)
            with pytest.raises(RuntimeError, match="IBKR_READ_QUEUE_FULL"):
                worker.call(lambda *_: pytest.fail("Overload was executed"))
            assert worker.close(timeout=.01) is False
            release.set()
            first.result(timeout=1)
            with pytest.raises(RuntimeError, match="IBKR_SESSION_CLOSED"):
                second.result(timeout=1)
    finally:
        release.set()
        assert worker.close(timeout=1)


def test_session_lifetime_and_budget_validation_are_bounded():
    sdk, trace = SDK(), []
    worker = ReadSessionWorker(account(), connection_factory=lambda _: connection(sdk, trace), maximum_seconds=.03)
    worker.start()
    assert worker.wait_closed(timeout=1)
    assert worker.failure_code == "IBKR_SESSION_EXPIRED"
    for seconds in [0, -1, float("nan"), float("inf"), 601, True]:
        with pytest.raises(ValueError):
            ReadSessionWorker(account(), maximum_seconds=seconds)


def test_existing_snapshot_collector_runs_on_owned_session_and_removes_handlers(monkeypatch):
    import sys
    from types import SimpleNamespace

    from tests.unit.ibkr_observations_test import SDK as CallbackSDK
    from src.tools.brokers.ibkr_observations import collect_ibkr_observations

    class ConnectedSDK(CallbackSDK, SDK):
        def __init__(self):
            CallbackSDK.__init__(self)
            SDK.__init__(self)
            self.trace = []

        def connect(self, **kwargs):
            assert kwargs["readonly"] is True and kwargs["account"] == "synthetic"
            self.trace.append(("connect", threading.get_ident()))

        def managedAccounts(self):
            return ["synthetic"]

        def disconnect(self):
            self.trace.append(("disconnect", threading.get_ident()))

    sdk = ConnectedSDK()
    monkeypatch.setitem(sys.modules, "ib_insync", SimpleNamespace(
        IB=lambda: sdk, ExecutionFilter=lambda **kwargs: "fixture-account-filter",
    ))
    selected = account()
    selected.config["broker_account_id"] = "synthetic"
    result = collect_ibkr_observations(selected)
    assert result["status"] == "observed" and result["execution_authority"] == "none"
    assert len(result["observations"]) == 4
    assert [item[0] for item in sdk.trace] == ["connect", "disconnect"]
    assert len({item[1] for item in sdk.trace}) == 1
    assert sdk.trace[0][1] != threading.get_ident()
    assert all(not event.handlers for event in (
        sdk.execDetailsEvent, sdk.commissionReportEvent, sdk.orderStatusEvent, sdk.disconnectedEvent,
    ))
