"""Compare retained order-status evidence without inferring current broker state."""

from decimal import Decimal, localcontext
from collections import defaultdict

from src.execution.policy import digest


def _key(payload):
    permanent = payload.get("permanent_id")
    if type(permanent) is not int or permanent < 0:
        raise ValueError("Invalid permanent identity")
    if permanent:
        return "permanent", permanent
    client, order = payload.get("client_id"), payload.get("order_id")
    if any(type(value) is not int or value < 0 for value in (client, order)):
        raise ValueError("Invalid client identity")
    return "client_order_only", client, order


def _quantity(value):
    number = Decimal(value)
    if not number.is_finite() or number < 0 or number >= Decimal("1e40"):
        raise ValueError("Invalid observed quantity")
    return number


def review_order_lifecycle(rows, *, truncated=False):
    result = dict(orders=[], orders_checked=0, reason_codes=[], current_state="not_established",
                  complete_reconciliation=False, strategy_order_ownership="not_established",
                  execution_authority="none")
    if not any(row["kind"] == "order_status" for row in rows):
        return result
    orders, executions, families = defaultdict(list), defaultdict(lambda: defaultdict(dict)), defaultdict(set)
    execution_versions = defaultdict(set)
    reasons = {"ORDER_REVIEW_WINDOW_TRUNCATED"} if truncated else set()
    for row in rows:
        if row["kind"] not in {"order_status", "execution"}:
            continue
        payload = row["payload"]
        if digest(payload) != row["payload_sha256"]:
            reasons.add("BROKER_EVIDENCE_HASH_MISMATCH")
            continue
        try:
            key = _key(payload)
            if row["kind"] == "order_status":
                orders[key].append(payload)
            else:
                identity = row["identity_sha256"]
                executions[key][identity][row["payload_sha256"]] = payload
                execution_versions[identity].add(row["payload_sha256"])
                families[payload["correction_family"]].add(identity)
        except (KeyError, TypeError, ValueError):
            reasons.add("ORDER_IDENTITY_EVIDENCE_INVALID")
    with localcontext() as context:
        context.prec = 160
        for key, statuses in sorted(orders.items(), key=lambda item: digest(item[0])):
            order_reasons = set()
            states = sorted({item.get("status", "unknown") for item in statuses})
            if "Filled" in states and {"Cancelled", "ApiCancelled"}.intersection(states):
                order_reasons.add("ORDER_TERMINAL_STATUS_CONFLICT")
            if key[0] != "permanent":
                order_reasons.add("ORDER_PERMANENT_ID_UNAVAILABLE")
            reported, quantity = None, None
            try:
                reported = max(_quantity(item["filled"]) for item in statuses)
                if any(item["status"] == "Filled" and
                       (_quantity(item["remaining"]) != 0 or _quantity(item["filled"]) == 0)
                       for item in statuses):
                    order_reasons.add("ORDER_FILLED_STATUS_INCONSISTENT")
                selected = []
                for identity, variants in executions[key].items():
                    if len(variants) != 1 or len(execution_versions[identity]) != 1:
                        order_reasons.add("ORDER_EXECUTION_VERSION_UNRESOLVED")
                        continue
                    execution = next(iter(variants.values()))
                    if len(families[execution["correction_family"]]) != 1:
                        order_reasons.add("ORDER_EXECUTION_VERSION_UNRESOLVED")
                        continue
                    selected.append(_quantity(execution["quantity"]))
                if "ORDER_EXECUTION_VERSION_UNRESOLVED" not in order_reasons:
                    quantity = sum(selected, Decimal(0))
                    if reported > quantity:
                        order_reasons.add("ORDER_FILL_EXECUTION_GAP")
                    elif quantity > reported and {"Filled", "Cancelled", "ApiCancelled"}.intersection(states):
                        order_reasons.add("ORDER_TERMINAL_EXECUTION_MISMATCH")
            except (KeyError, TypeError, ValueError, ArithmeticError):
                order_reasons.add("ORDER_QUANTITY_EVIDENCE_INVALID")
                quantity = None
            reasons.update(order_reasons)
            result["orders_checked"] += 1
            if len(result["orders"]) < 100:
                result["orders"].append(dict(
                    order_identity_sha256=digest(key), identity_basis=key[0], statuses_observed=states,
                    maximum_reported_filled=str(reported) if reported is not None else None,
                    execution_quantity=str(quantity) if quantity is not None else None,
                    pending_cancel_observed="PendingCancel" in states,
                    current_state="not_established", reason_codes=sorted(order_reasons),
                ))
    result["details_truncated"] = result["orders_checked"] > len(result["orders"])
    result["reason_codes"] = sorted(reasons)
    return result
