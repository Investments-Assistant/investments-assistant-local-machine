"""Compare simulator materialized balances with persisted execution evidence.

This is internal-ledger reconciliation, not an external broker reconciliation.
The caller holds the owned account lock. No balances or events are overwritten.
"""

import re
from decimal import Decimal, InvalidOperation
from datetime import datetime
from collections import defaultdict

from sqlalchemy import select

from src.execution.models import ExecutionEvent, SimulatorOrder, SimulatorPosition
from src.execution.policy import digest, order_details

MAX_ROWS = 10_000


def number(value):
    value = Decimal(str(value))
    if not value.is_finite() or value < 0:
        raise ValueError("Invalid ledger number")
    return value


def dated(value):
    if datetime.fromisoformat(value).tzinfo is None:
        raise ValueError("Undated FX")


def conversion(payload, source_key, account):
    source = payload[source_key]
    fx = number(payload["fx_to_base"])
    if not isinstance(source, str) or not re.fullmatch(r"[A-Z]{3}", source) or fx <= 0:
        raise ValueError("Invalid source currency or FX")
    if source == account.currency and fx != 1:
        raise ValueError("Inconsistent same-currency FX")
    return fx


async def reconcile_account(session, account):
    orders = (
        await session.scalars(
            select(SimulatorOrder)
            .where(
                SimulatorOrder.account_id == account.id,
            )
            .order_by(SimulatorOrder.id)
            .limit(MAX_ROWS + 1)
        )
    ).all()
    events = (
        await session.scalars(
            select(ExecutionEvent)
            .join(
                SimulatorOrder,
                SimulatorOrder.id == ExecutionEvent.order_id,
            )
            .where(SimulatorOrder.account_id == account.id, ExecutionEvent.kind.in_(["fill", "commission"]))
            .order_by(ExecutionEvent.id)
            .limit(MAX_ROWS + 1)
        )
    ).all()
    positions = (
        await session.scalars(
            select(SimulatorPosition)
            .where(
                SimulatorPosition.account_id == account.id,
            )
            .order_by(SimulatorPosition.id)
            .limit(MAX_ROWS + 1)
        )
    ).all()
    if any(len(rows) > MAX_ROWS for rows in (orders, events, positions)):
        return {"status": "unverified", "reason": "RECONCILIATION_CAPACITY", "scope": "simulator_internal"}
    errors, unknown = [], []
    latest = {}
    fills = defaultdict(list)
    for event in events:
        payload = event.payload
        if not isinstance(payload, dict):
            unknown.append("INVALID_EVENT_EVIDENCE")
            continue
        if event.kind == "fill":
            fills[event.order_id].append(event)
        else:
            try:
                key = event.order_id, payload["execution_id"]
                revision = payload["revision"]
                if type(revision) is not int or revision < 0:
                    raise ValueError("Invalid revision")
                if payload["base_currency"] != account.currency:
                    raise ValueError("Invalid base currency")
                dated(payload["fx_as_of"])
                fee = number(payload["fee_base"])
                if number(payload["amount"]) * conversion(payload, "currency", account) != fee:
                    raise ValueError("Inconsistent conversion")
                if key not in latest or revision > latest[key][0]:
                    latest[key] = revision, fee
                elif revision == latest[key][0] and fee != latest[key][1]:
                    unknown.append("CONFLICTING_COMMISSION_REVISION")
            except (KeyError, ValueError, TypeError, InvalidOperation):
                unknown.append("INVALID_COMMISSION_EVIDENCE")
    expected_positions = defaultdict(lambda: [Decimal(0), Decimal(0)])
    expected_cash = Decimal(str(account.initial_capital))
    expected_reserved = Decimal(0)
    seen_fills = set()

    def compare(field, actual, expected):
        if actual != expected:
            errors.append({"field": field, "actual": str(actual), "expected": str(expected)})

    for order in orders:
        if order.user_id != account.user_id or order.side != "buy":
            unknown.append("ORDER_SCOPE_OR_SIDE_UNSUPPORTED")
        if digest(order_details(order)) != order.details_hash:
            errors.append({"field": "order_details", "order_id": order.id, "reason": "CHANGED_AFTER_PROPOSAL"})
        try:
            if order.status not in {
                "proposed",
                "submitted",
                "acknowledged",
                "partially_filled",
                "cancel_requested",
                "cancelled",
                "rejected",
                "filled",
                "uncertain",
            }:
                unknown.append("UNKNOWN_ORDER_STATE")
            if order.status == "uncertain":
                unknown.append("UNCERTAIN_EXECUTION")
            reserved = number(order.reserve)
            expected_reserved += reserved
            if order.status in {"proposed", "filled", "cancelled", "rejected"}:
                compare("terminal_or_proposed_reserve", reserved, Decimal(0))
            quantity, fees, released = Decimal(0), Decimal(0), Decimal(0)
            releases_known = True
            for event in fills[order.id]:
                p = event.payload
                if not event.event_key.startswith("fill:"):
                    raise ValueError("Unknown execution identity")
                key = order.id, event.event_key.removeprefix("fill:")
                seen_fills.add(key)
                q, principal = number(p["quantity"]), number(p["principal_base"])
                if p["base_currency"] != account.currency:
                    raise ValueError("Invalid fill currency")
                dated(p["fx_as_of"])
                if (
                    q <= 0
                    or q * number(p["price"]) * number(p["multiplier"]) * conversion(p, "source_currency", account)
                    != principal
                ):
                    raise ValueError("Inconsistent fill valuation")
                if "released_reserve_base" in p:
                    released += number(p["released_reserve_base"])
                else:
                    releases_known = False
                fee = latest[key][1] if key in latest else number(p["applied_fee_base"])
                quantity += q
                fees += fee
                expected_cash -= principal + fee
                expected_positions[order.instrument_id][0] += q
                expected_positions[order.instrument_id][1] += principal + fee
            compare("order_filled", order.filled, quantity)
            compare("order_fees", order.fees, fees)
            if order.status in {"submitted", "acknowledged", "partially_filled", "cancel_requested"}:
                if not releases_known or not isinstance(order.approval, dict):
                    unknown.append("RESERVATION_PROVENANCE_UNAVAILABLE")
                else:
                    initial_reserve = number(order.approval["reserved_base"])
                    compare("order_remaining_reserve", reserved, initial_reserve - released)
            if quantity > order.quantity:
                errors.append({"field": "order_quantity", "reason": "OVERFILL"})
        except (KeyError, ValueError, TypeError, InvalidOperation):
            unknown.append("FILL_OR_RESERVATION_EVIDENCE_UNAVAILABLE")
    if set(latest) - seen_fills:
        unknown.append("COMMISSION_AWAITING_EXECUTION")
    # Incomplete evidence cannot establish expected aggregate balances.
    if not unknown:
        compare("cash", account.cash, expected_cash)
        compare("reserved", account.reserved, expected_reserved)
        actual_positions = {row.instrument_id: row for row in positions}
        for instrument_id in sorted(set(actual_positions) | set(expected_positions)):
            actual = actual_positions.get(instrument_id)
            expected = expected_positions[instrument_id]
            compare("position_quantity", actual.quantity if actual else Decimal(0), expected[0])
            compare("position_cost_basis", actual.cost_basis if actual else Decimal(0), expected[1])
    result = {
        "scope": "simulator_internal",
        "status": "unverified" if unknown else "discrepant" if errors else "consistent",
        "unknown_reasons": sorted(set(unknown)),
        "discrepancy_count": len(errors),
        "discrepancies": errors[:100],
        "orders_checked": len(orders),
        "events_checked": len(events),
        "positions_checked": len(positions),
        "base_currency": account.currency,
        "balance_policy": "No external flows; no silent balance replacement",
        "inputs_sha256": digest(
            {
                "account": [
                    account.id,
                    account.currency,
                    str(account.initial_capital),
                    str(account.cash),
                    str(account.reserved),
                ],
                "orders": [
                    [o.id, o.details_hash, o.status, str(o.filled), str(o.fees), str(o.reserve), o.approval]
                    for o in orders
                ],
                "events": [[e.id, e.order_id, e.event_key, e.kind, e.payload] for e in events],
                "positions": [[p.instrument_id, str(p.quantity), str(p.cost_basis)] for p in positions],
            }
        ),
    }
    result["evidence_sha256"] = digest(result)
    return result
