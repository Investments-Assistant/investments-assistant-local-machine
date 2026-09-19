"""Explain synthetic changes; matching facts never authorize external execution."""

from datetime import UTC, datetime

import pytest

from src.execution.policy import digest
from tests.unit.ibkr_balances_test import snapshot_row
from src.execution.broker_attribution import explain_balance_changes


def stamp(second):
    return datetime(2026, 9, 1, 12, 0, second, tzinfo=UTC).isoformat()


def evidence(kind, payload, identity="execution", observed_at=None):
    return dict(
        kind=kind,
        payload=payload,
        identity_sha256=identity,
        payload_sha256=digest(payload),
        observed_at=observed_at or stamp(40),
    )


def fixture_rows():
    before = snapshot_row(minute=0)
    after = snapshot_row(minute=1, quantity="0.008", eur="99.6", usd="24.95")
    before["identity_sha256"], after["identity_sha256"] = "before", "after"
    execution = evidence(
        "execution",
        dict(
            con_id=123,
            currency="EUR",
            security_type="STK",
            multiplier="1",
            side="BOT",
            quantity="0.004",
            price="100",
            executed_at=stamp(30),
            correction_family="one",
        ),
    )
    fee = evidence("commission", dict(currency="USD", amount="0.05"))
    return [before, execution, fee, after]


def test_fractional_fill_and_foreign_currency_fee_explain_only_observed_change():
    rows = fixture_rows()
    result = explain_balance_changes(rows)
    assert result["status"] == "observed_changes_match", result
    assert result["residuals"] == [] and result["executions_used"] == 1
    assert not result["complete_reconciliation"] and result["execution_authority"] == "none"
    # Replayed exact callback does not double the fill or fee.
    assert explain_balance_changes(rows + [rows[1], rows[2]])["status"] == "observed_changes_match"


def test_external_cash_change_stays_unexplained_without_inventing_a_deposit_or_pnl():
    rows = fixture_rows()
    rows[-1]["payload"]["balances"]["cash"][0]["amount"] = "109.6"
    rows[-1]["payload_sha256"] = digest(rows[-1]["payload"])
    result = explain_balance_changes(rows)
    assert result["status"] == "needs_review"
    assert result["residuals"] == [dict(kind="cash", currency="EUR", unexplained="10.000")]
    assert result["reason_codes"] == ["UNEXPLAINED_BALANCE_CHANGE"]


@pytest.mark.parametrize(
    "change,reason",
    [
        ("late_fee", "EVIDENCE_NOT_AVAILABLE_BY_CLOSING_SNAPSHOT"),
        ("missing_fee", "COMMISSION_MISSING_OR_CONFLICTING"),
        ("missing_multiplier", "EXECUTION_CONTRACT_BASIS_UNAVAILABLE"),
        ("conflict", "CONFLICTING_EXECUTION_OBSERVATIONS"),
        ("correction", "EXECUTION_CORRECTION_REVIEW_REQUIRED"),
        ("boundary", "EXECUTION_DURING_NONATOMIC_SNAPSHOT"),
    ],
)
async def test_incomplete_or_ambiguous_evidence_never_becomes_an_explanation(change, reason):
    rows = fixture_rows()
    if change == "late_fee":
        rows[2]["observed_at"] = "2026-09-01T12:02:00+00:00"
    elif change == "missing_fee":
        del rows[2]
    elif change == "missing_multiplier":
        del rows[1]["payload"]["multiplier"]
        rows[1]["payload_sha256"] = digest(rows[1]["payload"])
    elif change in {"conflict", "correction"}:
        rows.append(
            evidence(
                "execution",
                rows[1]["payload"] | {"quantity": "0.005"},
                identity="execution" if change == "conflict" else "corrected",
            )
        )
    else:
        rows[1]["payload"]["executed_at"] = stamp(1)
        rows[1]["payload_sha256"] = digest(rows[1]["payload"])
    result = explain_balance_changes(rows)
    assert result["status"] == "unverified" and reason in result["reason_codes"]
    assert result["residuals"] == [] and not result["complete_reconciliation"]


def test_partial_journal_page_cannot_prove_execution_coverage():
    assert explain_balance_changes(fixture_rows(), truncated=True)["reason_codes"] == ["ATTRIBUTION_WINDOW_TRUNCATED"]


def test_closed_round_trip_does_not_require_an_open_position_in_either_snapshot():
    rows = fixture_rows()
    before, after = rows[0], rows[-1]
    for snapshot in (before, after):
        snapshot["payload"]["balances"]["positions"] = []
    after["payload"]["balances"]["cash"][0]["amount"] = "108"
    after["payload"]["balances"]["cash"][1]["amount"] = "25"
    for snapshot in (before, after):
        snapshot["payload_sha256"] = digest(snapshot["payload"])
    buy = evidence("execution", rows[1]["payload"] | {"quantity": "1", "correction_family": "buy"}, identity="buy")
    sell = evidence(
        "execution", buy["payload"] | {"side": "SLD", "price": "110", "correction_family": "sell"}, identity="sell"
    )
    fees = [
        evidence("commission", {"currency": "EUR", "amount": "1"}, identity=identity) for identity in ("buy", "sell")
    ]
    result = explain_balance_changes([before, buy, sell, *fees, after])
    assert result["status"] == "observed_changes_match", result
    assert result["executions_used"] == 2 and result["residuals"] == []
    assert not result["complete_reconciliation"]
