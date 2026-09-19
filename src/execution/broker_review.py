"""Review retained callback evidence without inferring complete broker balances."""

from collections import defaultdict

from src.execution.policy import digest
from src.execution.broker_balances import compare_balance_evidence
from src.execution.broker_attribution import explain_balance_changes


def review_observations(observations, *, truncated=False):
    executions, commissions, families = defaultdict(set), defaultdict(set), defaultdict(set)
    invalid = 0
    for row in observations:
        payload = row["payload"]
        if digest(payload) != row["payload_sha256"]:
            invalid += 1
            continue
        kind, identity = row["kind"], row["identity_sha256"]
        if kind == "execution":
            executions[identity].add(row["payload_sha256"])
            families[payload["correction_family"]].add(identity)
        elif kind == "commission":
            commissions[identity].add(row["payload_sha256"])
    counts = {
        "conflicting_execution_identities": sum(len(versions) > 1 for versions in executions.values()),
        "conflicting_commission_identities": sum(len(versions) > 1 for versions in commissions.values()),
        "execution_correction_families": sum(len(identities) > 1 for identities in families.values()),
        "executions_without_commission": len(executions.keys() - commissions.keys()),
        "commissions_without_execution": len(commissions.keys() - executions.keys()),
        "invalid_evidence_hashes": invalid,
    }
    codes = {
        "conflicting_execution_identities": "CONFLICTING_EXECUTION_OBSERVATIONS",
        "conflicting_commission_identities": "CONFLICTING_COMMISSION_OBSERVATIONS",
        "execution_correction_families": "EXECUTION_CORRECTION_REVIEW_REQUIRED",
        "executions_without_commission": "COMMISSION_EVIDENCE_PENDING",
        "commissions_without_execution": "EXECUTION_EVIDENCE_PENDING",
        "invalid_evidence_hashes": "BROKER_EVIDENCE_HASH_MISMATCH",
    }
    reasons = [codes[key] for key, count in counts.items() if count]
    balance_review = compare_balance_evidence(observations)
    if balance_review["status"] == "needs_review":
        reasons.extend(balance_review["reason_codes"])
    elif balance_review["status"] == "changed":
        reasons.append("BALANCE_CHANGE_RECONCILIATION_REQUIRED")
    if truncated:
        reasons.append("REVIEW_WINDOW_TRUNCATED")
    result = {
        "status": "needs_review" if reasons else "unverified" if observations else "unavailable",
        "scope": "retained_callback_evidence_only",
        "reason_codes": reasons,
        "counts": counts,
        "observations_checked": len(observations),
        "balance_reconciliation": "not_established",
        "history_coverage": "not_established",
        "strategy_order_ownership": "not_established",
        "execution_authority": "none",
        "policy": "Conflicting/corrected callbacks are retained, never summed as additional fills.",
        "inputs_sha256": digest(observations),
        "balance_observations": balance_review,
        "execution_explanation": explain_balance_changes(observations, truncated=truncated),
    }
    result["evidence_sha256"] = digest(result)
    return result
