"""Active SDK owner routing never opens another connection or crosses principals."""

from copy import deepcopy
import asyncio
import threading
from contextlib import contextmanager
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.tools.brokers import ibkr
from tests.unit.ibkr_session_test import SDK, account, connection
from src.tools.brokers.ibkr_session import ReadSessionWorker, route_read


def test_scoped_adapter_reads_share_active_owner_and_one_connection(monkeypatch):
    selected, sdk, trace = account(), SDK(), []
    sdk.accountSummary = lambda **_: []
    sdk.portfolio = lambda **_: []
    sdk.reqAllOpenOrders = lambda: []
    worker = ReadSessionWorker(selected, connection_factory=lambda _: connection(sdk, trace))
    worker.register_reads()
    worker.start()
    monkeypatch.setattr(ibkr, "_connection", lambda *_: pytest.fail("Opened a second SDK connection"))
    try:
        assert ibkr.get_ibkr_account(selected)["managed_account_match"]
        assert ibkr.get_ibkr_positions(selected) == []
        assert ibkr.get_ibkr_orders(selected) == []
        monkeypatch.setattr(ibkr, "qualify_stock", lambda *_args, **_kwargs: {"thread": threading.get_ident()})
        contract = ibkr.resolve_ibkr_contract("SPYL", "IBIS2", "EUR", selected)
        assert contract["thread"] == trace[0][1] != threading.get_ident()
        assert [item[0] for item in trace] == ["connect"]
    finally:
        assert worker.close(timeout=1)
    assert route_read(selected, lambda *_: pytest.fail("Closed owner was routed")) == (False, None)


@pytest.mark.parametrize("change,reason", [
    ("owner", "IBKR_CLIENT_BUSY"), ("account", "IBKR_CLIENT_BUSY"),
    ("config", "IBKR_SESSION_CONFIGURATION_CHANGED"), ("consent", "IBKR_READ_CONSENT_REQUIRED"),
])
def test_registry_rejects_wrong_scope_or_changed_config_without_fallback(monkeypatch, change, reason):
    selected, sdk, trace = account(), SDK(), []
    other = deepcopy(selected)
    if change == "owner":
        other = replace(other, user_id="other-owner")
    elif change == "account":
        other = replace(other, id="other-account")
    elif change == "config":
        other.config["client_id"] = 99
    else:
        other.config["read_authorized"] = False
    worker = ReadSessionWorker(selected, connection_factory=lambda _: connection(sdk, trace))
    worker.register_reads()
    worker.start()
    monkeypatch.setattr(ibkr, "_connection", lambda *_: pytest.fail("Unsafe fallback"))
    try:
        assert ibkr.get_ibkr_account(other)["error"] == reason
    finally:
        assert worker.close(timeout=1)


def test_registry_retains_timed_out_owner_until_actual_cleanup():
    selected, sdk, trace = account(), SDK(), []
    worker = ReadSessionWorker(selected, connection_factory=lambda _: connection(sdk, trace))
    worker.register_reads()
    worker.start()
    entered, release = threading.Event(), threading.Event()

    def slow(*_):
        entered.set()
        assert release.wait(2)

    replacement = ReadSessionWorker(selected, connection_factory=lambda _: connection(sdk, trace))
    try:
        with ThreadPoolExecutor(1) as executor:
            running = executor.submit(worker.call, slow, timeout=.1)
            assert entered.wait(1)
            with pytest.raises(TimeoutError):
                running.result(timeout=1)
            assert worker.close(timeout=.01) is False
            with pytest.raises(RuntimeError, match="IBKR_CLIENT_BUSY"):
                replacement.register_reads()
            with pytest.raises(RuntimeError, match="IBKR_SESSION_STOPPING"):
                route_read(selected, lambda *_: pytest.fail("Timed out owner accepted work"))
    finally:
        release.set()
        assert worker.close(timeout=1)
    replacement.register_reads()
    replacement.stop()  # Never-started reservations must also be released.
    assert route_read(selected, lambda *_: None) == (False, None)


async def test_sync_adapter_cannot_block_async_caller_even_with_registered_owner():
    selected, sdk, trace = account(), SDK(), []
    worker = ReadSessionWorker(selected, connection_factory=lambda _: connection(sdk, trace))
    worker.register_reads()
    await asyncio.to_thread(worker.start)
    try:
        assert ibkr.get_ibkr_account(selected)["error"] == "IBKR_SYNC_ADAPTER_REQUIRES_WORKER_THREAD"
    finally:
        assert await asyncio.to_thread(worker.close, timeout=1)


def test_snapshot_read_keeps_continuous_subscription_attached(monkeypatch):
    import sys
    from types import SimpleNamespace

    from tests.unit.ibkr_observations_test import SDK as CallbackSDK
    from src.tools.brokers.ibkr_observations import CallbackWindow, collect_ibkr_observations

    class CombinedSDK(CallbackSDK, SDK):
        def __init__(self):
            CallbackSDK.__init__(self)
            SDK.__init__(self)

    selected, sdk = account(), CombinedSDK()
    selected.config["broker_account_id"] = "synthetic"
    persistent = CallbackWindow("synthetic")

    @contextmanager
    def connected(_):
        yield sdk, "synthetic"

    monkeypatch.setitem(sys.modules, "ib_insync", SimpleNamespace(ExecutionFilter=lambda **_: "fixture-account-filter"))
    worker = ReadSessionWorker(selected, connection_factory=connected,
                               subscription=lambda ib, _: persistent.subscribed(ib))
    worker.register_reads()
    worker.start()
    try:
        result = collect_ibkr_observations(selected)
        assert result["status"] == "observed" and len(result["observations"]) == 4
        # Only the temporary snapshot handlers were detached. The persistent
        # subscription also received live callbacks on that same SDK event loop.
        assert len(sdk.execDetailsEvent.handlers) == len(sdk.commissionReportEvent.handlers) == 1
        batch = worker.call(lambda *_: persistent.drain())
        assert batch["capture_active"] and [item.kind for item in batch["observations"]] == ["commission", "execution"]
    finally:
        assert worker.close(timeout=1)
    assert not sdk.execDetailsEvent.handlers
