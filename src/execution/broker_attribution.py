"""Explain observed balance changes with scoped evidence, never grant authority."""

from decimal import Decimal, localcontext
from datetime import datetime
from collections import defaultdict

from src.execution.policy import digest
from src.execution.broker_balances import compare_balance_evidence


def explain_balance_changes(rows, *, truncated=False):
    result = {
        "status": "unverified",
        "reason_codes": [],
        "residuals": [],
        "execution_authority": "none",
        "complete_reconciliation": False,
        "basis": "Only retained executions and fees available by the closing observation",
        "limitations": ["Non-atomic source snapshots", "Unverified flow/corporate-action/history completeness"],
    }
    if truncated:
        result["reason_codes"] = ["ATTRIBUTION_WINDOW_TRUNCATED"]
        return result
    comparison = compare_balance_evidence(rows)
    if comparison["status"] not in {"changed", "unchanged"}:
        result["reason_codes"] = ["BALANCE_PAIR_UNAVAILABLE"]
        return result
    snapshots = sorted(
        (row for row in rows if row["kind"] == "balance_snapshot"),
        key=lambda row: (datetime.fromisoformat(row["observed_at"]), row["payload_sha256"]),
    )[-2:]
    opening, closing = snapshots
    start = datetime.fromisoformat(opening["observed_at"])
    end = datetime.fromisoformat(closing["payload"]["balances"]["request_started_at"])
    cutoff = datetime.fromisoformat(closing["observed_at"])
    opening_start = datetime.fromisoformat(opening["payload"]["balances"]["request_started_at"])
    executions, commissions, families = defaultdict(dict), defaultdict(dict), defaultdict(set)
    reasons = set()
    eligible = set()
    try:
        for row in rows:
            if digest(row["payload"]) != row["payload_sha256"]:
                reasons.add("BROKER_EVIDENCE_HASH_MISMATCH")
                continue
            kind, identity, payload = row["kind"], row["identity_sha256"], row["payload"]
            if kind == "commission":
                commissions[identity][row["payload_sha256"]] = row
            elif kind == "execution":
                executions[identity][row["payload_sha256"]] = row
                families[payload["correction_family"]].add(identity)
                stamp = datetime.fromisoformat(payload["executed_at"])
                if stamp.tzinfo is None:
                    raise ValueError("Unknown execution timezone")
                if opening_start <= stamp <= start or end <= stamp <= cutoff:
                    reasons.add("EXECUTION_DURING_NONATOMIC_SNAPSHOT")
                if start < stamp < end:
                    eligible.add(identity)
        with localcontext() as context:
            context.prec = 160
            quantity_changes, cash_changes = defaultdict(Decimal), defaultdict(Decimal)
            before = opening["payload"]["balances"]
            after = closing["payload"]["balances"]
            contracts = {p["con_id"]: p for p in before["positions"] + after["positions"]}
            for identity in sorted(eligible):
                variants = list(executions[identity].values())
                if len(variants) != 1:
                    reasons.add("CONFLICTING_EXECUTION_OBSERVATIONS")
                    continue
                row = variants[0]
                execution = row["payload"]
                if len(families[execution["correction_family"]]) != 1:
                    reasons.add("EXECUTION_CORRECTION_REVIEW_REQUIRED")
                    continue
                fees = list(commissions[identity].values())
                if len(fees) != 1:
                    reasons.add("COMMISSION_MISSING_OR_CONFLICTING")
                    continue
                fee = fees[0]
                if any(datetime.fromisoformat(item["observed_at"]) > cutoff for item in (row, fee)):
                    reasons.add("EVIDENCE_NOT_AVAILABLE_BY_CLOSING_SNAPSHOT")
                    continue
                contract = contracts.get(execution["con_id"])
                if (
                    not execution.get("security_type")
                    or execution.get("multiplier") is None
                    or (
                        contract is not None
                        and (
                            contract["currency"] != execution["currency"]
                            or contract["security_type"] != execution["security_type"]
                        )
                    )
                ):
                    reasons.add("EXECUTION_CONTRACT_BASIS_UNAVAILABLE")
                    continue
                sign = Decimal(1) if execution["side"] == "BOT" else Decimal(-1)
                quantity = Decimal(execution["quantity"])
                multiplier, price = Decimal(execution["multiplier"]), Decimal(execution["price"])
                amount = Decimal(fee["payload"]["amount"])
                if (
                    not all(value.is_finite() for value in (quantity, multiplier, price, amount))
                    or quantity <= 0
                    or multiplier <= 0
                ):
                    raise ValueError("Invalid amount")
                quantity_changes[execution["con_id"]] += sign * quantity
                cash_changes[execution["currency"]] -= sign * quantity * price * multiplier
                cash_changes[fee["payload"]["currency"]] -= amount
            if reasons:
                result["reason_codes"] = sorted(reasons)
                return result
            old_positions = {p["con_id"]: Decimal(p["quantity"]) for p in before["positions"]}
            new_positions = {p["con_id"]: Decimal(p["quantity"]) for p in after["positions"]}
            residuals = []
            for contract in sorted(old_positions.keys() | new_positions.keys() | quantity_changes.keys()):
                change = new_positions.get(contract, Decimal(0)) - old_positions.get(contract, Decimal(0))
                residual = change - quantity_changes[contract]
                if residual:
                    residuals.append(dict(kind="position_quantity", con_id=contract, unexplained=str(residual)))
            old_cash = {p["currency"]: Decimal(p["amount"]) for p in before["cash"]}
            new_cash = {p["currency"]: Decimal(p["amount"]) for p in after["cash"]}
            for currency in sorted(old_cash.keys() | new_cash.keys() | cash_changes.keys()):
                if currency not in old_cash or currency not in new_cash:
                    reasons.add("CURRENCY_BALANCE_UNAVAILABLE")
                    continue
                residual = new_cash[currency] - old_cash[currency] - cash_changes[currency]
                if residual:
                    residuals.append(dict(kind="cash", currency=currency, unexplained=str(residual)))
    except (KeyError, TypeError, ValueError, ArithmeticError):
        result["reason_codes"] = ["INVALID_ATTRIBUTION_EVIDENCE"]
        return result
    if residuals:
        reasons.add("UNEXPLAINED_BALANCE_CHANGE")
    result.update(
        status="needs_review" if reasons else "observed_changes_match",
        reason_codes=sorted(reasons),
        residuals=residuals[:100],
        residual_count=len(residuals),
        executions_used=len(eligible),
        inputs_sha256=digest(rows),
    )
    result["evidence_sha256"] = digest(result)
    return result
