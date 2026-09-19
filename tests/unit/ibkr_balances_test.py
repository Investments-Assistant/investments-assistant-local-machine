"""Realistic SDK-shaped balance rows; never a broker connection."""

from types import SimpleNamespace as Obj

import pytest
from pydantic import ValidationError

from src.tools.brokers.ibkr_balances import collect_balances
from src.execution.broker_observations import OBSERVATION


class SDK:
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

    def reqPositions(self):
        return self.positions

    def reqAccountSummary(self):
        self.summary_requested = True

    def accountSummary(self, account):
        assert account == "selected" and self.summary_requested
        return self.values


def test_explicit_snapshot_preserves_fractional_quantity_and_separate_cash_currencies():
    result = OBSERVATION.validate_python(collect_balances(SDK(), "selected"))
    values = result.model_dump(mode="json")["balances"]
    assert values["positions"][0]["quantity"] == "0.004"
    assert len(values["positions"]) == 1
    assert [(item["currency"], item["amount"]) for item in values["cash"]] == [("EUR", "100"), ("USD", "25")]
    assert values["position_request_complete"] and values["cash_request_complete"]
    assert values["atomic_snapshot"] is False
    assert "selected" not in str(result.model_dump(mode="json"))


def test_empty_positions_are_explicit_but_missing_cash_is_not_zero():
    sdk = SDK()
    sdk.positions, sdk.values = [], []
    result = OBSERVATION.validate_python(collect_balances(sdk, "selected"))
    assert result.balances.position_request_complete and result.balances.positions == []
    assert not result.balances.cash_request_complete and result.balances.cash == []


def test_conflicting_currency_or_duplicate_contract_is_not_silently_overwritten():
    sdk = SDK()
    sdk.values.append(Obj(account="selected", tag="CashBalance", currency="EUR", value="200"))
    with pytest.raises(ValidationError, match="Ambiguous duplicate currency"):
        OBSERVATION.validate_python(collect_balances(sdk, "selected"))
    sdk = SDK()
    sdk.positions.append(sdk.positions[0])
    with pytest.raises(ValidationError, match="Ambiguous duplicate contract"):
        OBSERVATION.validate_python(collect_balances(sdk, "selected"))


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
