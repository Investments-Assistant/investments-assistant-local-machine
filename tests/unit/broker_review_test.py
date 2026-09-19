"""Evidence gaps cannot become holdings, cash, authority, or complete history."""

from src.execution.policy import digest
from src.execution.broker_review import review_observations


def row(kind, identity, *, amount="1", family="family"):
    payload = dict(amount=amount, correction_family=family)
    return dict(kind=kind, identity_sha256=identity, payload=payload, payload_sha256=digest(payload))


def test_corrections_conflicts_and_orphans_remain_distinct_review_reasons():
    rows = [
        row("execution", "one"),
        row("execution", "one", amount="2"),
        row("execution", "two"),
        row("commission", "one"),
        row("commission", "one", amount="3"),
        row("commission", "orphan"),
    ]
    result = review_observations(rows)
    assert result["status"] == "needs_review"
    assert result["counts"] == dict(
        conflicting_execution_identities=1,
        conflicting_commission_identities=1,
        execution_correction_families=1,
        executions_without_commission=1,
        commissions_without_execution=1,
        invalid_evidence_hashes=0,
    )
    assert result["balance_reconciliation"] == "not_established" and result["execution_authority"] == "none"
    assert result["evidence_sha256"] == review_observations(rows)["evidence_sha256"]


def test_paired_evidence_is_not_complete_history_or_strategy_ownership():
    result = review_observations([row("execution", "one"), row("commission", "one")])
    assert result["status"] == "unverified" and result["reason_codes"] == []
    assert result["history_coverage"] == result["strategy_order_ownership"] == "not_established"
    assert review_observations([])["status"] == "unavailable"
    assert review_observations([], truncated=True)["reason_codes"] == ["REVIEW_WINDOW_TRUNCATED"]


def test_tampered_payload_is_not_counted_as_valid_evidence():
    event = row("execution", "one")
    event["payload"]["amount"] = "999"
    result = review_observations([event])
    assert result["counts"]["invalid_evidence_hashes"] == 1
    assert result["counts"]["executions_without_commission"] == 0
    assert result["status"] == "needs_review"
