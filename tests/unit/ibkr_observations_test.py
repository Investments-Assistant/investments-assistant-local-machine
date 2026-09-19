"""SDK-shaped events only; no network or application broker credentials."""

from types import SimpleNamespace as Obj
from datetime import UTC, datetime, timedelta

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
    def __init__(self):
        self.execDetailsEvent = Event()
        self.commissionReportEvent = Event()
        self.orderStatusEvent = Event()
        self.disconnectedEvent = Event()
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
