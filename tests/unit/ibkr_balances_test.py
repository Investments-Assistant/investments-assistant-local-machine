"""Realistic SDK-shaped balance rows; never a broker connection."""

from types import SimpleNamespace as Obj

import pytest
from pydantic import ValidationError

from src.tools.brokers.ibkr_balances import collect_balances
from src.execution.broker_observations import OBSERVATION


class Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.handlers.remove(handler)
        return self

    def emit(self, row):
        for handler in list(self.handlers):
            handler(row)


class SDK:
    def managedAccounts(self):
        return ["selected"]

    def __init__(self):
        self.positions = [
            Obj(
                account="selected",
                contract=Obj(conId=123, currency="EUR", secType="STK"),
                position="0.004",
                avgCost="100",
            ),
            Obj(account="other", contract=None),
        ]
        self.values = [
            Obj(account="selected", tag="CashBalance", currency="EUR", value="100"),
            Obj(account="selected", tag="$LEDGER-CashBalance", currency="USD", value="25"),
            Obj(account="selected", tag="CashBalance", currency="BASE", value="125"),
            Obj(account="other", tag="CashBalance", currency="EUR", value="999"),
        ]
        self.summary_requested = False
        self.accountValueEvent = Event()
        self.wrapper = Obj(
            accountDownloadEnd=self.account_download_end,
            updateAccountValue=self.account_value,
            accountUpdateMulti=self.multi_value,
        )
        self.client = Obj(reqAccountUpdates=self.subscription)
        self.subscription_calls = []
        self.download_complete = False
        self.completed_accounts = []
        self.ready_value = "true"
        self.end_accounts = ["selected"]
        self.return_without_end = False
        self.read_failure = None

    def reqPositions(self):
        return self.positions

    def reqAccountSummary(self):
        self.summary_requested = True

    def accountSummary(self, account):
        assert account == "selected" and self.summary_requested
        return self.values

    def subscription(self, subscribed, account):
        assert account == "selected"
        self.subscription_calls.append((subscribed, account))

    def account_download_end(self, account):
        # Model the actual SDK wrapper: any account ends its shared future.
        self.completed_accounts.append(account)
        self.download_complete = True

    def account_value(self, tag, value, currency, account):
        self.accountValueEvent.emit(Obj(account=account, tag=tag, value=value, currency=currency))

    def multi_value(self, _request, account, model, tag, value, currency):
        self.accountValueEvent.emit(
            Obj(account=account, tag=tag, value=value, currency=currency, modelCode=model)
        )

    def reqAccountUpdates(self, account):
        assert account == "selected"
        self.download_complete = False
        self.client.reqAccountUpdates(True, account)
        if self.ready_value is not None:
            self.wrapper.updateAccountValue("AccountReady", self.ready_value, "", account)
        for row in self.values:
            self.wrapper.updateAccountValue(row.tag, row.value, row.currency, row.account)
        if self.read_failure is not None:
            raise self.read_failure
        for ended_account in self.end_accounts:
            self.wrapper.accountDownloadEnd(ended_account)
        if not self.download_complete and not self.return_without_end:
            raise TimeoutError("Synthetic selected-account download did not finish")


def test_explicit_snapshot_preserves_fractional_quantity_and_separate_cash_currencies():
    result = OBSERVATION.validate_python(collect_balances(SDK(), "selected"))
    values = result.model_dump(mode="json")["balances"]
    assert values["positions"][0]["quantity"] == "0.004"
    assert len(values["positions"]) == 1
    assert [(item["currency"], item["amount"]) for item in values["cash"]] == [("EUR", "100"), ("USD", "25")]
    assert values["position_request_complete"] and values["cash_request_complete"]
    assert values["atomic_snapshot"] is False
    assert "selected" not in str(result.model_dump(mode="json"))


@pytest.mark.parametrize("accounts", [[], ["other"], ["selected", "other"], ["selected", "selected"]])
def test_balance_request_rejects_unselected_or_ambiguous_session_before_download(accounts):
    sdk = SDK()
    sdk.managedAccounts = lambda: accounts
    sdk.reqPositions = lambda: pytest.fail("Requested balances before verifying account scope")
    with pytest.raises(ValueError):
        collect_balances(sdk, "selected")
    assert sdk.subscription_calls == []


def test_empty_positions_are_explicit_but_missing_cash_is_not_zero():
    sdk = SDK()
    sdk.positions, sdk.values = [], []
    result = OBSERVATION.validate_python(collect_balances(sdk, "selected"))
    assert result.balances.position_request_complete and result.balances.positions == []
    assert not result.balances.cash_request_complete and result.balances.cash == []


def test_fresh_selected_account_cash_is_not_lost_to_aggregate_summary():
    """Summary ledger rows can be All while completed account updates are scoped."""
    class ScopedSDK(SDK):
        def __init__(self):
            super().__init__()
            self.positions = []
            self.values = [Obj(account="All", tag="CashBalance", currency="EUR", value="125")]
            self.accountValueEvent = Event()
            self.download_complete = False
            # An SDK cache is not a new observation window. This old currency
            # must not be promoted to a fresh completed snapshot.
            self.cached = [Obj(account="selected", tag="CashBalance", currency="GBP", value="777")]

        def reqAccountUpdates(self, account):
            assert account == "selected"
            self.client.reqAccountUpdates(True, account)
            fresh = [
                Obj(account="selected", tag="AccountReady", currency="", value="true"),
                Obj(account="selected", tag="$LEDGER-CashBalance", currency="EUR", value="100"),
                Obj(account="selected", tag="CashBalance", currency="USD", value="25"),
                Obj(account="selected", tag="CashBalance", currency="BASE", value="125"),
                Obj(account="other", tag="CashBalance", currency="EUR", value="999"),
            ]
            for row in fresh:
                self.cached.append(row)
                self.wrapper.updateAccountValue(row.tag, row.value, row.currency, row.account)
            # The blocking SDK call returns only after accountDownloadEnd.
            self.wrapper.accountDownloadEnd(account)

        def accountValues(self, account):
            assert account == "selected" and self.download_complete
            return [row for row in self.cached if row.account == account]

    sdk = ScopedSDK()
    result = OBSERVATION.validate_python(collect_balances(sdk, "selected"))
    assert [(row.currency, row.amount) for row in result.balances.cash] == [
        ("EUR", 100), ("USD", 25),
    ]
    assert result.balances.cash_request_complete
    assert sdk.download_complete
    assert sdk.accountValueEvent.handlers == []


def test_conflicting_currency_or_duplicate_contract_is_not_silently_overwritten():
    sdk = SDK()
    sdk.values.append(Obj(account="selected", tag="$LEDGER-CashBalance", currency="EUR", value="200"))
    result = OBSERVATION.validate_python(collect_balances(sdk, "selected"))
    assert result.balances.cash == [] and not result.balances.cash_request_complete
    sdk = SDK()
    sdk.positions.append(sdk.positions[0])
    with pytest.raises(ValidationError, match="Ambiguous duplicate contract"):
        OBSERVATION.validate_python(collect_balances(sdk, "selected"))


def test_repeated_key_keeps_latest_exact_value_and_equal_sources_do_not_double_count():
    sdk = SDK()
    sdk.values += [
        Obj(account="selected", tag="CashBalance", currency="EUR", value="100.00000000000000000001"),
        Obj(account="selected", tag="$LEDGER-CashBalance", currency="EUR", value="100.00000000000000000001"),
    ]
    result = OBSERVATION.validate_python(collect_balances(sdk, "selected"))
    assert str(result.balances.cash[0].amount) == "100.00000000000000000001"
    assert len(result.balances.cash) == 2 and result.balances.cash_request_complete
    assert sdk.subscription_calls == [(False, "selected"), (True, "selected"), (False, "selected")]


@pytest.mark.parametrize("ready", [None, "false", "TRUE", "", True])
def test_missing_or_invalid_readiness_never_promotes_cash(ready):
    sdk = SDK()
    sdk.ready_value = ready
    result = OBSERVATION.validate_python(collect_balances(sdk, "selected"))
    assert result.balances.cash == [] and not result.balances.cash_request_complete
    assert not sdk.accountValueEvent.handlers


def test_not_ready_and_currency_conflict_are_sticky_for_the_whole_request():
    for extra in (
        [Obj(account="selected", tag="AccountReady", currency="", value="false"),
         Obj(account="selected", tag="AccountReady", currency="", value="true")],
        [Obj(account="selected", tag="$LEDGER-CashBalance", currency="EUR", value="200"),
         Obj(account="selected", tag="$LEDGER-CashBalance", currency="EUR", value="100")],
    ):
        sdk = SDK()
        sdk.values += extra
        result = OBSERVATION.validate_python(collect_balances(sdk, "selected"))
        assert result.balances.cash == [] and not result.balances.cash_request_complete


def test_foreign_download_end_cannot_complete_the_selected_account_request():
    sdk = SDK()
    original = sdk.wrapper.accountDownloadEnd
    sdk.end_accounts = ["other"]
    with pytest.raises(TimeoutError):
        collect_balances(sdk, "selected")
    assert sdk.completed_accounts == []
    assert sdk.wrapper.accountDownloadEnd is original
    assert sdk.accountValueEvent.handlers == []
    assert sdk.subscription_calls[-1] == (False, "selected")


def test_return_without_selected_end_marker_is_still_incomplete():
    sdk = SDK()
    sdk.end_accounts, sdk.return_without_end = ["other"], True
    result = OBSERVATION.validate_python(collect_balances(sdk, "selected"))
    assert result.balances.cash == [] and not result.balances.cash_request_complete


def test_guard_intercepts_real_sdk_decoder_dispatch_without_any_socket():
    from ib_async.decoder import Decoder

    sdk = SDK()
    decoder = Decoder(sdk.wrapper, 178)
    original = sdk.wrapper.accountDownloadEnd

    def request(account):
        sdk.client.reqAccountUpdates(True, account)
        decoder.interpret(["73", "1", "99", account, "", "AccountReady", "false", ""])
        decoder.interpret(["73", "1", "99", account, "", "CashBalance", "777", "GBP"])
        decoder.interpret(["6", "2", "AccountReady", "true", "", account])
        decoder.interpret(["6", "2", "CashBalance", "100", "EUR", account])
        decoder.interpret(["54", "1", "other"])
        decoder.interpret(["6", "2", "CashBalance", "25", "USD", account])
        decoder.interpret(["6", "2", "CashBalance", "999", "JPY", "other"])
        decoder.interpret(["6", "2", "CashBalance", "125", "BASE", account])
        decoder.interpret(["54", "1", account])
        # A later periodic update belongs outside this completed download.
        decoder.interpret(["6", "2", "AccountReady", "false", "", account])
        decoder.interpret(["6", "2", "CashBalance", "9999", "EUR", account])

    sdk.reqAccountUpdates = request
    result = OBSERVATION.validate_python(collect_balances(sdk, "selected"))
    assert result.balances.cash_request_complete
    assert [(row.currency, row.amount) for row in result.balances.cash] == [("EUR", 100), ("USD", 25)]
    assert sdk.completed_accounts == ["selected"]
    assert sdk.wrapper.accountDownloadEnd is original


def test_multi_update_cannot_supply_missing_primary_readiness():
    sdk = SDK()
    sdk.ready_value = None
    original = sdk.reqAccountUpdates

    def request(account):
        # Emit through the same public event after the actual send, but using
        # the distinct Multi channel the default SDK connection also subscribes.
        send = sdk.client.reqAccountUpdates

        def with_multi(subscribed, selected):
            send(subscribed, selected)
            sdk.wrapper.accountUpdateMulti(99, selected, "", "AccountReady", "true", "")

        sdk.client.reqAccountUpdates = with_multi
        try:
            original(account)
        finally:
            sdk.client.reqAccountUpdates = send

    sdk.reqAccountUpdates = request
    result = OBSERVATION.validate_python(collect_balances(sdk, "selected"))
    assert result.balances.cash == [] and not result.balances.cash_request_complete


def test_callbacks_during_send_do_not_become_fresh_download_evidence():
    sdk = SDK()
    original = sdk.client.reqAccountUpdates

    def request(subscribed, account):
        original(subscribed, account)
        if subscribed:
            sdk.wrapper.updateAccountValue("AccountReady", "false", "", account)
            sdk.wrapper.updateAccountValue("CashBalance", "777", "GBP", account)
            sdk.wrapper.accountDownloadEnd(account)

    sdk.client.reqAccountUpdates = request
    result = OBSERVATION.validate_python(collect_balances(sdk, "selected"))
    assert result.balances.cash_request_complete
    assert [row.currency for row in result.balances.cash] == ["EUR", "USD"]
    assert sdk.completed_accounts == ["selected"]


def test_class_callback_and_client_descriptors_are_restored_without_instance_overrides():
    sdk = SDK()

    class Wrapper:
        def updateAccountValue(self, *args):
            sdk.account_value(*args)

        def accountDownloadEnd(self, account):
            sdk.account_download_end(account)

    class Client:
        def reqAccountUpdates(self, subscribed, account):
            sdk.subscription(subscribed, account)

    sdk.wrapper, sdk.client = Wrapper(), Client()
    before_wrapper, before_client = dict(vars(sdk.wrapper)), dict(vars(sdk.client))
    result = OBSERVATION.validate_python(collect_balances(sdk, "selected"))
    assert result.balances.cash_request_complete
    assert vars(sdk.wrapper) == before_wrapper and vars(sdk.client) == before_client


@pytest.mark.parametrize("value", ["NaN", "Infinity", "not-a-number", "1e99999", "1" * 129])
def test_malformed_cash_numeric_is_incomplete_and_never_logged(value, caplog):
    sdk = SDK()
    sdk.values.append(Obj(account="selected", tag="CashBalance", currency="EUR", value=value))
    result = OBSERVATION.validate_python(collect_balances(sdk, "selected"))
    assert result.balances.cash == [] and not result.balances.cash_request_complete
    assert caplog.records == []


def test_initial_unsubscribe_failure_preserves_original_error_and_existing_hooks():
    sdk = SDK()
    original_end, original_value = sdk.wrapper.accountDownloadEnd, sdk.wrapper.updateAccountValue
    error = OSError("Synthetic initial unsubscribe failure")
    original = sdk.client.reqAccountUpdates

    def request(subscribed, account):
        original(subscribed, account)
        if len(sdk.subscription_calls) == 1:
            raise error

    sdk.client.reqAccountUpdates = request
    with pytest.raises(OSError) as failure:
        collect_balances(sdk, "selected")
    assert failure.value is error
    assert sdk.wrapper.accountDownloadEnd is original_end
    assert sdk.wrapper.updateAccountValue is original_value
    assert sdk.client.reqAccountUpdates is request
    assert sdk.subscription_calls == [(False, "selected"), (False, "selected")]
    assert sdk._ia_primary_portfolio_stale is True


def test_installed_sdk_native_request_timeout_cleans_up_without_a_socket():
    import asyncio

    from ib_async import IB

    class WaitingSDK(SDK):
        RequestTimeout = 0.01
        reqAccountUpdates = IB.reqAccountUpdates
        reqAccountUpdatesAsync = IB.reqAccountUpdatesAsync
        _run = IB._run

    sdk = WaitingSDK()
    originals = dict(vars(sdk.wrapper))
    original_subscription = sdk.client.reqAccountUpdates
    with asyncio.Runner() as runner:
        loop = runner.get_loop()
        sdk.wrapper.startReq = lambda _key: loop.create_future()

        def request(subscribed, account):
            original_subscription(subscribed, account)
            if subscribed:
                loop.call_soon(sdk.wrapper.updateAccountValue, "AccountReady", "true", "", account)
                loop.call_soon(sdk.wrapper.updateAccountValue, "CashBalance", "100", "EUR", account)
                loop.call_soon(sdk.wrapper.accountDownloadEnd, "other")

        sdk.client.reqAccountUpdates = request
        with pytest.raises(TimeoutError):
            collect_balances(sdk, "selected")
    for name, original in originals.items():
        assert getattr(sdk.wrapper, name) is original
    assert sdk.client.reqAccountUpdates is request
    assert sdk.subscription_calls == [(False, "selected"), (True, "selected"), (False, "selected")]
    assert sdk.completed_accounts == []
    assert sdk.RequestTimeout == 0.01


@pytest.mark.parametrize("currency_count, complete", [(100, True), (101, False)])
def test_exact_currency_capacity_and_overflow(currency_count, complete):
    sdk = SDK()
    sdk.values = [
        Obj(account="selected", tag="CashBalance", currency=f"A{chr(65 + i // 26)}{chr(65 + i % 26)}", value="1")
        for i in range(currency_count)
    ]
    result = OBSERVATION.validate_python(collect_balances(sdk, "selected"))
    assert result.balances.cash_request_complete is complete
    assert len(result.balances.cash) == (currency_count if complete else 0)


def test_original_callback_error_cannot_escape_into_decoder_payload_logging(caplog):
    from ib_async.decoder import Decoder

    sdk = SDK()
    decoder = Decoder(sdk.wrapper, 178)

    def broken_value(*_args):
        raise ValueError("Synthetic private callback failure")

    sdk.wrapper.updateAccountValue = broken_value

    def request(account):
        sdk.client.reqAccountUpdates(True, account)
        decoder.interpret(["6", "2", "CashBalance", "100", "EUR", account])
        decoder.interpret(["54", "1", account])

    sdk.reqAccountUpdates = request
    result = OBSERVATION.validate_python(collect_balances(sdk, "selected"))
    assert result.balances.cash == [] and not result.balances.cash_request_complete
    assert sdk.wrapper.updateAccountValue is broken_value
    assert caplog.records == []


def test_currency_overflow_and_malformed_callbacks_stay_incomplete_without_logging(caplog):
    sdk = SDK()
    sdk.values = [
        Obj(account="selected", tag="CashBalance", currency=f"A{chr(65 + i // 26)}{chr(65 + i % 26)}", value="1")
        for i in range(101)
    ]
    result = OBSERVATION.validate_python(collect_balances(sdk, "selected"))
    assert result.balances.cash == [] and not result.balances.cash_request_complete
    sdk = SDK()
    sdk.values.append(Obj(account="selected", tag="CashBalance", currency="EUR", value=object()))
    result = OBSERVATION.validate_python(collect_balances(sdk, "selected"))
    assert result.balances.cash == [] and not result.balances.cash_request_complete
    assert caplog.records == []


def test_cleanup_restores_hooks_and_preserves_original_native_failure():
    sdk = SDK()
    original = sdk.wrapper.accountDownloadEnd
    error = TimeoutError("Synthetic original read failure")
    sdk.read_failure = error
    original_subscription = sdk.client.reqAccountUpdates

    def subscription(subscribed, account):
        original_subscription(subscribed, account)
        if len(sdk.subscription_calls) == 3:
            raise ValueError("Synthetic private cleanup error")

    sdk.client.reqAccountUpdates = subscription
    with pytest.raises(TimeoutError) as failure:
        collect_balances(sdk, "selected")
    assert failure.value is error
    assert sdk.wrapper.accountDownloadEnd is original
    assert sdk.accountValueEvent.handlers == []


def test_cleanup_failure_without_prior_error_is_sanitized():
    sdk = SDK()
    original_subscription = sdk.client.reqAccountUpdates

    def subscription(subscribed, account):
        original_subscription(subscribed, account)
        if len(sdk.subscription_calls) == 3:
            raise ValueError("Synthetic private cleanup error")

    sdk.client.reqAccountUpdates = subscription
    with pytest.raises(RuntimeError, match="^BROKER_ACCOUNT_UPDATE_CLEANUP_FAILED$"):
        collect_balances(sdk, "selected")
    assert sdk.accountValueEvent.handlers == []


def snapshot_row(*, minute, quantity="0.004", eur="100", usd="25"):
    from datetime import UTC, datetime

    from src.execution.policy import digest

    value = OBSERVATION.validate_python(collect_balances(SDK(), "selected")).model_dump(mode="json")
    value["balances"]["request_started_at"] = datetime(2026, 9, 1, 12, minute, tzinfo=UTC).isoformat()
    value["balances"]["positions"][0]["quantity"] = quantity
    value["balances"]["cash"][0]["amount"] = eur
    value["balances"]["cash"][1]["amount"] = usd
    payload = {"balances": value["balances"]}
    return dict(
        kind="balance_snapshot",
        observed_at=datetime(2026, 9, 1, 12, minute, 1, tzinfo=UTC).isoformat(),
        payload=payload,
        payload_sha256=digest(payload),
    )


def test_snapshot_changes_are_exact_separate_currency_deltas_not_pnl():
    from src.execution.broker_balances import compare_balance_evidence

    before = snapshot_row(minute=0)
    after = snapshot_row(minute=1, quantity="0.008", eur="99.6", usd="24.95")
    result = compare_balance_evidence([after, before])
    assert result["status"] == "changed" and result["difference_count"] == 3
    assert result["differences"][0]["delta"] == "0.004"
    assert [(item["currency"], item["delta"]) for item in result["differences"][1:]] == [
        ("EUR", "-0.4"),
        ("USD", "-0.05"),
    ]
    assert result["balance_reconciliation"] == "not_established"
    assert before["payload"]["balances"]["positions"][0]["quantity"] == "0.004"


def test_snapshot_missing_cash_and_overlap_cannot_establish_comparison():
    from src.execution.policy import digest
    from src.execution.broker_balances import compare_balance_evidence

    before = snapshot_row(minute=0)
    assert compare_balance_evidence([before])["status"] == "baseline_only"
    assert compare_balance_evidence([before, before])["reason_codes"] == ["OVERLAPPING_BALANCE_WINDOWS"]
    after = snapshot_row(minute=1)
    after["payload"]["balances"]["cash_request_complete"] = False
    after["payload_sha256"] = digest(after["payload"])
    assert compare_balance_evidence([before, after])["reason_codes"] == ["BALANCE_REQUEST_INCOMPLETE"]
    after["payload"]["balances"]["cash_request_complete"] = True
    assert compare_balance_evidence([before, after])["reason_codes"] == ["INVALID_BALANCE_EVIDENCE"]


def test_reported_cost_precision_and_large_cash_delta_are_preserved():
    from src.execution.policy import digest
    from src.execution.broker_balances import compare_balance_evidence

    sdk = SDK()
    sdk.positions[0].avgCost = "100.1234567890123456"
    observed = OBSERVATION.validate_python(collect_balances(sdk, "selected"))
    assert (
        observed.model_dump(mode="json")["balances"]["positions"][0]["average_cost_reported"] == "100.1234567890123456"
    )
    before = snapshot_row(minute=0, eur="12345678901234567890.12345678901234567890")
    after = snapshot_row(minute=1, eur="12345678901234567891.12345678901234567891")
    assert before["payload_sha256"] == digest(before["payload"])
    result = compare_balance_evidence([before, after])
    assert result["status"] == "changed"
    assert result["differences"] == [
        dict(
            kind="cash",
            currency="EUR",
            before="12345678901234567890.12345678901234567890",
            after="12345678901234567891.12345678901234567891",
            delta="1.00000000000000000001",
        )
    ]
