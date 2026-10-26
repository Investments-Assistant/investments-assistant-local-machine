"""SDK-shaped events only; no network or application broker credentials."""

from types import SimpleNamespace as Obj
from datetime import UTC, datetime, timedelta

import pytest

from src.execution.broker_observations import hash_order_reference
from src.tools.brokers.ibkr_observations import CallbackWindow


class Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.handlers.remove(handler)
        return self

    def emit(self, *args):
        for handler in list(self.handlers):
            handler(*args)


def fill(account="synthetic", identity="fixture.1"):
    return Obj(
        contract=Obj(conId=123, currency="EUR"),
        execution=Obj(
            acctNumber=account,
            execId=identity,
            clientId=7,
            orderId=1,
            permId=9,
            side="BOT",
            shares=0.004,
            price=100,
            time=datetime.now(UTC) - timedelta(seconds=1),
        ),
        commissionReport=Obj(execId="", currency="", commission=0),
    )


class SDK:
    def managedAccounts(self):
        return ["synthetic"]

    def __init__(self):
        self.execDetailsEvent = Event()
        self.commissionReportEvent = Event()
        self.orderStatusEvent = Event()
        self.disconnectedEvent = Event()
        self.errorEvent = Event()
        self.accountValueEvent = Event()
        self.wrapper = Obj(
            accountDownloadEnd=lambda _account: None,
            updateAccountValue=lambda tag, value, currency, account: self.accountValueEvent.emit(
                Obj(account=account, tag=tag, value=value, currency=currency)
            ),
        )
        self.client = Obj(reqAccountUpdates=lambda _subscribed, _account: None)
        self.failed = False

    def reqAllOpenOrders(self):
        return []

    def reqPositions(self):
        return []

    def reqAccountSummary(self):
        return None

    def accountSummary(self, account):
        assert account == "synthetic"
        return []

    def reqAccountUpdates(self, account):
        assert account == "synthetic"
        self.client.reqAccountUpdates(True, account)
        self.wrapper.updateAccountValue("AccountReady", "true", "", account)
        self.wrapper.accountDownloadEnd(account)

    def reqExecutions(self, execution_filter):
        assert execution_filter == "fixture-account-filter"
        observed = fill()
        report = Obj(execId="fixture.1", currency="EUR", commission=0.03)
        self.commissionReportEvent.emit(None, observed, report)
        self.execDetailsEvent.emit(None, observed)
        self.execDetailsEvent.emit(None, fill(account="other"))
        if self.failed:
            self.disconnectedEvent.emit()
            raise TimeoutError("private provider text")
        return [observed]


@pytest.mark.parametrize("accounts", [[], ["other"], ["synthetic", "other"]])
def test_ambiguous_session_cannot_start_an_order_or_execution_snapshot(accounts):
    sdk = SDK()
    sdk.managedAccounts = lambda: accounts
    sdk.reqAllOpenOrders = lambda: pytest.fail("Downloaded orders from ambiguous session")
    sdk.reqExecutions = lambda *_: pytest.fail("Downloaded executions from ambiguous session")
    result = CallbackWindow("synthetic").collect(sdk, "fixture-account-filter")
    assert result["request_finished"] is False
    assert result["status"] == "partial" and result["observations"] == []
    assert result["failures"] == ["BROKER_SNAPSHOT_REQUEST_FAILED"]


def test_out_of_order_events_and_snapshot_keep_missing_commission_truthful():
    sdk = SDK()
    result = CallbackWindow("synthetic").collect(sdk, "fixture-account-filter")
    assert result["request_finished"] and result["status"] == "observed"
    assert not result["late_commissions_complete"]
    assert [item.kind for item in result["observations"]] == [
        "commission",
        "execution",
        "execution",
        "balance_snapshot",
    ]
    assert all(item.actual_account == "synthetic" for item in result["observations"])
    assert all(
        not event.handlers
        for event in (sdk.execDetailsEvent, sdk.commissionReportEvent, sdk.orderStatusEvent, sdk.disconnectedEvent)
    )


def test_disconnect_retains_observations_without_claiming_complete_snapshot():
    sdk = SDK()
    sdk.failed = True
    result = CallbackWindow("synthetic").collect(sdk, "fixture-account-filter")
    assert not result["request_finished"] and result["status"] == "partial"
    assert result["failures"] == ["BROKER_DISCONNECTED_DURING_SNAPSHOT", "BROKER_SNAPSHOT_REQUEST_FAILED"]
    assert len(result["observations"]) == 2
    assert "private provider text" not in str(result)
    assert not sdk.execDetailsEvent.handlers and not sdk.disconnectedEvent.handlers


def test_capacity_malformed_and_mismatched_commission_fail_closed():
    window = CallbackWindow("synthetic", capacity=1)
    window.execution(None, fill())
    window.execution(None, fill())
    assert len(window.observations) == 1 and "BROKER_CALLBACK_CAPACITY" in window.failures
    window.commission(None, fill(), Obj(execId="wrong", currency="EUR", commission=0))
    assert "COMMISSION_EXECUTION_MISMATCH" in window.failures
    window.execution(None, Obj())
    assert "INVALID_BROKER_CALLBACK" in window.failures


def test_only_decoded_execution_reference_is_hashed_not_cached_trade_order():
    window = CallbackWindow("synthetic")
    observed = fill()
    observed.execution.orderRef = "a" * 32
    cached = Obj(order=Obj(orderRef="b" * 32))
    window.execution(cached, observed)
    retained, = window.observations
    assert retained.order_ref_sha256 == hash_order_reference("a" * 32)
    assert "a" * 32 not in str(retained.model_dump())
    del observed.execution.orderRef
    window.execution(cached, observed)
    assert window.observations[-1].order_ref_sha256 is None
    assert "order_ref_sha256" not in window.observations[-1].model_dump(exclude_none=True)


def test_order_status_cached_reference_cannot_supply_correlation_evidence():
    window = CallbackWindow("synthetic")
    trade = Obj(order=Obj(account="synthetic", clientId=7, orderId=1, permId=9, orderRef="c" * 32),
                orderStatus=Obj(status="Submitted", filled=0, remaining=1))
    window.order_status(trade)
    assert len(window.observations) == 1
    assert "order_ref_sha256" not in window.observations[0].model_dump()
    assert "c" * 32 not in str(window.observations[0].model_dump())


def test_subscription_keeps_late_callbacks_between_bounded_drains_and_final_detach():
    sdk = SDK()
    window = CallbackWindow("synthetic")
    with window.subscribed(sdk):
        assert window.request_snapshot(sdk, "fixture-account-filter")
        first = window.drain()
        assert first["capture_active"] and len(first["observations"]) == 4
        late = Obj(execId="fixture.1", currency="EUR", commission=0.04)
        sdk.commissionReportEvent.emit(None, fill(), late)
        second = window.drain(final=True)
        assert not second["capture_active"] and len(second["observations"]) == 1
        assert str(second["observations"][0].amount) == "0.04"
        sdk.commissionReportEvent.emit(None, fill(), late)
        assert window.drain()["observations"] == []
        assert len(first["observations"]) == 4  # Later drains cannot mutate delivered batches.
    assert not sdk.commissionReportEvent.handlers


def test_stream_overflow_stays_partial_after_drain_and_cross_account_events_are_excluded():
    sdk = SDK()
    window = CallbackWindow("synthetic", capacity=1)
    with window.subscribed(sdk):
        sdk.execDetailsEvent.emit(None, fill(account="other"))
        sdk.execDetailsEvent.emit(None, fill())
        sdk.execDetailsEvent.emit(None, fill(identity="fixture.2"))
        result = window.drain()
        assert len(result["observations"]) == 1 and result["status"] == "partial"
        assert result["failures"] == ["BROKER_CALLBACK_CAPACITY"]
        assert window.drain(final=True)["status"] == "partial"


def test_drain_requires_the_subscription_owner_thread():
    import threading

    import pytest

    sdk, window, errors = SDK(), CallbackWindow("synthetic"), []

    def wrong_owner():
        try:
            window.drain()
        except RuntimeError as exc:
            errors.append(str(exc))

    with window.subscribed(sdk):
        worker = threading.Thread(target=wrong_owner)
        worker.start()
        worker.join(timeout=1)
        assert errors == ["BROKER_CALLBACK_OWNER_REQUIRED"]
    with pytest.raises(RuntimeError, match="BROKER_CALLBACK_OWNER_REQUIRED"):
        window.drain()


@pytest.mark.parametrize("code", [1100, 1101, 1102, 1300])
def test_upstream_connection_transition_is_sticky_without_socket_disconnect(code):
    sdk, window = SDK(), CallbackWindow("synthetic")
    with window.subscribed(sdk):
        sdk.execDetailsEvent.emit(None, fill())
        sdk.errorEvent.emit(-1, code, "private-account/provider details", None)
        first = window.drain()
        assert first["status"] == "partial"
        assert first["failures"] == ["BROKER_UPSTREAM_CONNECTION_CHANGED"]
        assert len(first["observations"]) == 1
        sdk.errorEvent.emit(-1, 1102, "restored", None)
        assert window.drain(final=True)["failures"] == first["failures"]
        assert "private" not in str(first)
    assert not sdk.errorEvent.handlers


def test_unrelated_informational_message_does_not_invent_connectivity_loss():
    sdk, window = SDK(), CallbackWindow("synthetic")
    with window.subscribed(sdk):
        sdk.errorEvent.emit(-1, 2104, "market data farm OK", None)
        assert window.drain(final=True)["status"] == "observed"
