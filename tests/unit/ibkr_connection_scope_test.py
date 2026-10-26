"""Installed IB/Client/Decoder contracts over a socket-free in-memory wire."""

from types import SimpleNamespace
import socket
import struct
import asyncio
import logging
import threading
from contextlib import contextmanager

import pytest
import ib_async
from ib_async import (
    IB as ActualIB,
    ExecutionFilter,
)
from ib_async.connection import Connection

from src.tools.brokers import ibkr
from src.tools.broker_accounts import BrokerAccountConfig

pytestmark = pytest.mark.unit
SELECTED = "SYNTHETIC-SELECTED"
FINANCIAL = {6, 7, 16, 61, 62, 74, 76, 99}


def account():
    return BrokerAccountConfig("fixture", "owner", "ibkr", "Synthetic", dict(
        enabled=True, read_authorized=True, broker_account_id=SELECTED,
        environment="paper", client_id=77,
    ))


def packet(*fields):
    body = ("\0".join(str(field) for field in fields) + "\0").encode()
    return struct.pack(">I", len(body)) + body


class MemoryTransport:
    def __init__(self, wire, connection):
        self.wire, self.connection, self.closed = wire, connection, False

    def write(self, data):
        wire = self.wire
        if data.startswith(b"API\0"):
            wire.loop.call_later(wire.handshake_delay, self.connection.data_received, packet(178, "synthetic-time"))
            return
        fields = data[4:].decode().split("\0")[:-1]
        wire.requests.append(fields)
        if fields[0] == "71":
            messages = [packet(9, 1, 100), packet(15, 1, ",".join(wire.accounts))]
            if wire.order == "accounts_first":
                messages.reverse()
            if wire.initial_health is not None:
                messages.insert(0, packet(4, 2, -1, wire.initial_health, "synthetic health", ""))
            payload = b"".join(messages)
            chunks = [payload] if not wire.fragment else [payload[:3], payload[3:11], payload[11:]]
            for chunk in chunks:
                wire.loop.call_soon(self.connection.data_received, chunk)
        elif fields[0] == "6" and fields[2] == "1" and wire.reply_account is not None:
            wire.loop.call_later(wire.primary_delay, self.connection.data_received, packet(54, 1, wire.reply_account))

    def write_eof(self):
        pass

    def close(self):
        self.closed = True
        self.connection.transport = None
        self.wire.trace.append(("disconnect", threading.get_ident()))


class Wire:
    def __init__(self, monkeypatch, *, accounts=(SELECTED,), order="id_first", fragment=False,
                 reply_account=SELECTED, initial_health=None, handshake_delay=0, primary_delay=0,
                 account_end_override=False):
        self.accounts, self.order, self.fragment = accounts, order, fragment
        self.reply_account, self.initial_health = reply_account, initial_health
        self.handshake_delay, self.primary_delay = handshake_delay, primary_delay
        self.end_override = None
        self.requests, self.connected, self.trace = [], [], []
        self.ib = self.loop = self.transport = self.connection = None

        def make_ib():
            self.ib, self.loop = ActualIB(), asyncio.get_event_loop()
            if account_end_override:
                original_end = self.ib.wrapper.accountDownloadEnd
                self.end_override = lambda actual: original_end(actual)
                self.ib.wrapper.accountDownloadEnd = self.end_override
            self.ib.connectedEvent += lambda: self.connected.append(True)
            return self.ib

        async def connect(connection, host, port):
            self.connection = connection
            connection.reset()
            self.transport = connection.transport = MemoryTransport(self, connection)
            self.trace.append(("connect", threading.get_ident()))

        def denied(*_args, **_kwargs):
            raise AssertionError("No real network or high-level IB bootstrap is allowed")

        monkeypatch.setattr(ib_async, "IB", make_ib)
        monkeypatch.setattr(Connection, "connectAsync", connect)
        monkeypatch.setattr(ActualIB, "connectAsync", denied)
        monkeypatch.setattr(socket.socket, "connect", denied)
        monkeypatch.setattr(socket.socket, "connect_ex", denied)
        monkeypatch.setattr(socket, "getaddrinfo", denied)
        monkeypatch.setattr(asyncio.BaseEventLoop, "create_connection", denied)

    @property
    def financial(self):
        return [fields for fields in self.requests if int(fields[0]) in FINANCIAL]

    def deliver(self, *fields):
        self.connection.data_received(packet(*fields))


@pytest.mark.parametrize("order", ["id_first", "accounts_first"])
@pytest.mark.parametrize("fragment", [False, True])
def test_metadata_precedes_selected_primary_download_without_default_warmups(monkeypatch, order, fragment):
    wire = Wire(monkeypatch, order=order, fragment=fragment)
    with ibkr._connection(account()) as (sdk, actual):
        assert sdk is wire.ib and actual == SELECTED
        assert wire.financial == [["6", "2", "1", SELECTED]]
        assert wire.requests[0] == ["71", "2", "77", ""]
        assert sdk.wrapper.clientId == 77
        assert wire.connected == [True]
        assert "accountDownloadEnd" not in vars(sdk.wrapper)
        assert sdk.RequestTimeout == 10 and sdk.RaiseRequestErrors is True
    assert wire.transport.closed and wire.loop.is_closed()
    assert not ibkr._connection_lock.locked()


@pytest.mark.parametrize("accounts", [
    ("SYNTHETIC-OTHER",), (SELECTED, "SYNTHETIC-OTHER"), (SELECTED, SELECTED),
])
def test_mismatched_ambiguous_duplicate_metadata_emit_no_financial_request(monkeypatch, accounts):
    wire = Wire(monkeypatch, accounts=accounts)
    with pytest.raises(ValueError, match="^IBKR_SOLE_MANAGED_ACCOUNT_REQUIRED$"), ibkr._connection(account()):
        pytest.fail("Unqualified connection was admitted")
    assert wire.financial == [] and wire.connected == []
    assert wire.transport.closed and wire.loop.is_closed()
    assert not ibkr._connection_lock.locked()


def test_empty_metadata_times_out_without_any_financial_request_and_releases_owner(monkeypatch):
    wire = Wire(monkeypatch, accounts=())
    original_wait_for = asyncio.wait_for
    deadlines = []

    def short_timeout(awaitable, timeout):
        deadlines.append(timeout)
        return original_wait_for(awaitable, min(timeout, .03))

    monkeypatch.setattr(asyncio, "wait_for", short_timeout)
    with pytest.raises(TimeoutError), ibkr._connection(account()):
        pytest.fail("Missing metadata was admitted")
    assert deadlines and all(timeout == 10 for timeout in deadlines)
    assert wire.financial == [] and wire.connected == []
    assert wire.transport.closed and wire.loop.is_closed()
    assert not ibkr._connection_lock.locked()


@pytest.mark.parametrize("reply", ["SYNTHETIC-OTHER", ""])
def test_primary_completion_must_name_selected_account(monkeypatch, reply):
    wire = Wire(monkeypatch, reply_account=reply)
    with pytest.raises(ValueError, match="^IBKR_SOLE_MANAGED_ACCOUNT_REQUIRED$"), ibkr._connection(account()):
        pytest.fail("Wrong accountDownloadEnd completed admission")
    assert wire.financial == [["6", "2", "1", SELECTED]]
    assert wire.connected == []
    assert "accountDownloadEnd" not in vars(wire.ib.wrapper)
    assert wire.transport.closed and wire.loop.is_closed()


def test_primary_download_shares_single_request_timeout_budget(monkeypatch):
    wire = Wire(monkeypatch, reply_account=None)
    original_wait_for = asyncio.wait_for
    deadlines = []

    def short_timeout(awaitable, timeout):
        deadlines.append(timeout)
        return original_wait_for(awaitable, min(timeout, .03))

    monkeypatch.setattr(asyncio, "wait_for", short_timeout)
    with pytest.raises(TimeoutError), ibkr._connection(account()):
        pytest.fail("Unfinished primary download was admitted")
    # The IB._run outer timeout covers handshake AND the primary Future; there
    # is no second synchronous run with a newly replenished timeout budget.
    assert deadlines == [10, 10, 10]
    assert wire.financial == [["6", "2", "1", SELECTED]]
    assert wire.connected == [] and wire.transport.closed and wire.loop.is_closed()
    assert "accountDownloadEnd" not in vars(wire.ib.wrapper)


@pytest.mark.parametrize("delay,success", [(.005, True), (.09, False)])
def test_delayed_handshake_consumes_primary_download_budget(monkeypatch, delay, success):
    wire = Wire(monkeypatch, handshake_delay=delay, primary_delay=delay)
    original_wait_for = asyncio.wait_for

    def bounded_timeout(awaitable, timeout):
        assert timeout == 10
        return original_wait_for(awaitable, .15)

    monkeypatch.setattr(asyncio, "wait_for", bounded_timeout)
    if success:
        with ibkr._connection(account()):
            assert wire.connected == [True]
    else:
        with pytest.raises(TimeoutError), ibkr._connection(account()):
            pytest.fail("Handshake and primary download replenished the shared budget")
        assert wire.connected == []
    assert wire.financial == [["6", "2", "1", SELECTED]]
    assert wire.transport.closed and wire.loop.is_closed()


@pytest.mark.parametrize("reply", [SELECTED, "SYNTHETIC-OTHER"])
def test_primary_download_restores_preexisting_instance_callback_override(monkeypatch, reply):
    wire = Wire(monkeypatch, reply_account=reply, account_end_override=True)
    if reply == SELECTED:
        with ibkr._connection(account()) as (sdk, _actual):
            assert sdk.wrapper.accountDownloadEnd is wire.end_override
    else:
        with pytest.raises(ValueError, match="^IBKR_SOLE_MANAGED_ACCOUNT_REQUIRED$"), ibkr._connection(account()):
            pytest.fail("Foreign primary completion was admitted")
    assert wire.ib.wrapper.accountDownloadEnd is wire.end_override


@pytest.mark.parametrize("code", [1100, 1101, 1102, 1300])
def test_startup_connection_gap_denies_admission_without_automatic_summary(monkeypatch, code):
    wire = Wire(monkeypatch, initial_health=code)
    with pytest.raises(RuntimeError, match="^IBKR_SESSION_NOT_READY$"), ibkr._connection(account()):
        pytest.fail("A known startup observation gap was admitted")
    assert wire.financial == [] and wire.connected == []
    assert wire.transport.closed and wire.loop.is_closed()


@pytest.mark.parametrize("code", [1100, 1101, 1102, 1300])
def test_later_connection_gap_denies_reads_but_preserves_final_drain_until_owned_cleanup(monkeypatch, code):
    wire = Wire(monkeypatch)
    with ibkr._connection(account()) as (sdk, actual):
        wire.deliver(4, 2, -1, code, "synthetic health", "")
        assert sdk.isConnected() and not wire.transport.closed
        with pytest.raises(RuntimeError, match="^IBKR_SESSION_NOT_READY$"):
            ibkr.require_selected_account(sdk, actual)
        with pytest.raises(RuntimeError, match="^IBKR_SESSION_NOT_READY$"):
            sdk.client.reqPositions()
        assert wire.financial == [["6", "2", "1", SELECTED]]
        assert not asyncio.all_tasks(wire.loop)
    assert wire.transport.closed and wire.loop.is_closed()
    assert len(wire.ib.errorEvent) == 0


def test_account_expansion_then_reversion_is_sticky_and_stops_existing_subscription(monkeypatch):
    wire = Wire(monkeypatch)
    with ibkr._connection(account()) as (sdk, actual):
        # Exercise the actual broad request method before scope changes.
        sdk.client.reqPositions()
        assert wire.financial[-1] == ["61", "1"]
        wire.deliver(15, 1, SELECTED + ",SYNTHETIC-OTHER")
        assert wire.transport.closed and not sdk.isConnected()
        sdk.wrapper.managedAccounts(SELECTED)
        assert sdk.managedAccounts() == [SELECTED]
        with pytest.raises(ValueError, match="^IBKR_SOLE_MANAGED_ACCOUNT_REQUIRED$"):
            ibkr.require_selected_account(sdk, actual)
        before = list(wire.requests)
        with pytest.raises(ValueError, match="^IBKR_SOLE_MANAGED_ACCOUNT_REQUIRED$"):
            sdk.client.reqPositions()
        assert wire.requests == before


@pytest.mark.parametrize("method,args", [
    ("reqPositions", ()), ("reqAllOpenOrders", ()),
    ("reqAccountSummary", (101, "All", "NetLiquidation")),
    ("reqExecutions", (101, ExecutionFilter(acctCode=SELECTED))),
    ("reqAccountUpdates", (True, SELECTED)),
])
def test_native_financial_sends_recheck_current_scope_before_wire(monkeypatch, method, args):
    wire = Wire(monkeypatch)
    with ibkr._connection(account()) as (sdk, _actual):
        sdk.wrapper.accounts = [SELECTED, "SYNTHETIC-OTHER"]
        before = list(wire.requests)
        with pytest.raises(ValueError, match="^IBKR_SOLE_MANAGED_ACCOUNT_REQUIRED$"):
            getattr(sdk.client, method)(*args)
        assert wire.requests == before


def test_primary_subscription_rejects_other_account_but_cleanup_can_unsubscribe_when_invalid(monkeypatch):
    wire = Wire(monkeypatch)
    with ibkr._connection(account()) as (sdk, _actual):
        before = list(wire.requests)
        with pytest.raises(ValueError, match="^IBKR_SOLE_MANAGED_ACCOUNT_REQUIRED$"):
            sdk.client.reqAccountUpdates(True, "SYNTHETIC-OTHER")
        assert wire.requests == before
        sdk._ia_account_scope_invalid = True
        sdk.client.reqAccountUpdates(False, SELECTED)
        assert wire.financial[-1] == ["6", "2", "0", SELECTED]


def test_routed_read_rechecks_before_operation_and_before_publishing_result(monkeypatch):
    from src.tools.brokers import ibkr_session

    sdk = SimpleNamespace(managedAccounts=lambda: [SELECTED])
    monkeypatch.setattr(ibkr_session, "route_read", lambda _account, operation: (True, operation(sdk, SELECTED)))

    def changed(*_args):
        sdk.managedAccounts = lambda: [SELECTED, "SYNTHETIC-OTHER"]
        return {"must_not_be_published": True}

    with pytest.raises(ValueError, match="^IBKR_SOLE_MANAGED_ACCOUNT_REQUIRED$"):
        ibkr._read(account(), changed)
    with pytest.raises(ValueError, match="^IBKR_SOLE_MANAGED_ACCOUNT_REQUIRED$"):
        ibkr._read(account(), lambda *_args: pytest.fail("Invalid scope operation started"))


def test_direct_read_rechecks_before_publishing_and_sanitizes_failure(monkeypatch):
    from src.tools.brokers import ibkr_session

    sdk = SimpleNamespace(managedAccounts=lambda: [SELECTED])

    def changed_summary(**_kwargs):
        sdk.managedAccounts = lambda: [SELECTED, "SYNTHETIC-OTHER"]
        return []

    sdk.accountSummary = changed_summary

    @contextmanager
    def connected(_account):
        yield sdk, SELECTED

    monkeypatch.setattr(ibkr, "_connection", connected)
    monkeypatch.setattr(ibkr_session, "route_read", lambda *_args: (False, None))
    result = ibkr.get_ibkr_account(account())
    assert result == {"broker": "ibkr", "available": False,
                      "error": "IBKR_SOLE_MANAGED_ACCOUNT_REQUIRED"}
    assert SELECTED not in str(result) and "SYNTHETIC-OTHER" not in str(result)


def test_owned_sdk_logs_do_not_emit_wire_or_provider_payloads_or_change_global_loggers(monkeypatch, caplog, capsys):
    names = ("ib_async.ib", "ib_async.client", "ib_async.wrapper", "ib_async.decoder")
    originals = {name: (logging.getLogger(name).level, list(logging.getLogger(name).handlers),
                        logging.getLogger(name).propagate) for name in names}
    sentinel = "SYNTHETIC-PRIVATE-SENTINEL"
    wire = Wire(monkeypatch)
    caplog.set_level(logging.DEBUG)
    with ibkr._connection(account()) as (sdk, _actual):
        wire.deliver(6, 2, "PrivateValue", sentinel, "USD", SELECTED)
        wire.deliver(4, 2, -1, 999, sentinel, "")
        sdk._logger.info(sentinel)
        sdk.client._logger.debug(sentinel)
        sdk.wrapper._logger.error(sentinel)
        sdk.client.decoder.logger.warning(sentinel)
        assert all(logger.propagate is False for logger in
                   (sdk._logger, sdk.client._logger, sdk.wrapper._logger, sdk.client.decoder.logger))
    assert sentinel not in caplog.text
    captured = capsys.readouterr()
    assert sentinel not in captured.out + captured.err
    assert originals == {name: (logging.getLogger(name).level, list(logging.getLogger(name).handlers),
                                logging.getLogger(name).propagate) for name in names}


def test_scope_callback_disconnect_failure_never_throws_into_decoder_or_restores_authority(monkeypatch):
    wire = Wire(monkeypatch)
    with ibkr._connection(account()) as (sdk, actual):
        real_disconnect = sdk.disconnect

        def failed_disconnect():
            raise RuntimeError("Synthetic cleanup failure")

        monkeypatch.setattr(sdk, "disconnect", failed_disconnect)
        sdk.wrapper.managedAccounts(SELECTED + ",SYNTHETIC-OTHER")
        assert wire.transport.closed  # lower-level fallback still closes transport
        with pytest.raises(ValueError, match="^IBKR_SOLE_MANAGED_ACCOUNT_REQUIRED$"):
            ibkr.require_selected_account(sdk, actual)
        monkeypatch.setattr(sdk, "disconnect", real_disconnect)
