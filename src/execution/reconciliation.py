"""Compare simulator materialized balances with persisted execution evidence.

This is internal-ledger reconciliation, not an external broker reconciliation.
The caller holds the owned account lock. No balances or events are overwritten.
"""

import re
from decimal import Decimal, InvalidOperation, localcontext
from datetime import datetime
from collections import defaultdict

from sqlalchemy import select

from src.execution.models import ExecutionEvent, SimulatorOrder, SimulatorPosition, AccountLedgerEvent
from src.execution.policy import digest, order_details
from src.execution.inventory import allocation_inventory
from src.execution.accounting import (
    AccountingFill,
    AccountingSplit,
    AccountingCashFlow,
    AccountingDividendPayment,
    AccountingDividendSettlement,
    AccountingDividendEntitlement,
    replay_events,
)

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


def allocation_for_order(order, submissions):
    """Resolve ownership only from matching retained submission provenance."""
    if order.status == "proposed" and order.approval is None and not submissions:
        return None
    if len(submissions) != 1 or not isinstance(order.approval, dict):
        raise ValueError("ALLOCATION_PROVENANCE_UNAVAILABLE")
    event = submissions[0]
    approval = order.approval
    if event.payload != approval or approval.get("environment") != "simulator":
        raise ValueError("ALLOCATION_PROVENANCE_UNAVAILABLE")
    actor = approval.get("actor")
    if actor == "authenticated_browser":
        if (
            event.event_key != "approval"
            or approval.get("mandate_id") is not None
            or approval.get("details_hash") != order.details_hash
        ):
            raise ValueError("ALLOCATION_PROVENANCE_UNAVAILABLE")
        return "manual"
    if actor == "approved_simulator_mandate":
        mandate = approval.get("mandate_id")
        mandate_hash = approval.get("mandate_hash")
        if (
            event.event_key != "mandate-submission"
            or not isinstance(mandate, str)
            or not mandate
            or order.session_id != "mandate:" + mandate
            or not isinstance(mandate_hash, str)
            or not re.fullmatch(r"[a-f0-9]{64}", mandate_hash)
        ):
            raise ValueError("ALLOCATION_PROVENANCE_UNAVAILABLE")
        return mandate
    raise ValueError("ALLOCATION_PROVENANCE_UNAVAILABLE")


async def reconcile_account(
    session, account, *, _include_ledger=False, _pending_fees_for_fill=False, _include_execution_evidence=False
):
    # Decimal context is task-local on the supported Python runtime. Preserve the
    # caller's context while keeping every valuation and aggregate deterministic.
    with localcontext() as context:
        context.prec = 80
        return await _reconcile_account(
            session,
            account,
            _include_ledger=_include_ledger,
            _pending_fees_for_fill=_pending_fees_for_fill,
            _include_execution_evidence=_include_execution_evidence,
        )


async def _reconcile_account(
    session, account, *, _include_ledger=False, _pending_fees_for_fill=False, _include_execution_evidence=False
):
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
            .where(
                SimulatorOrder.account_id == account.id,
                ExecutionEvent.kind.in_(["fill", "commission", "submitted"]),
            )
            .order_by(ExecutionEvent.ledger_sequence)
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
    account_events = (
        await session.scalars(
            select(AccountLedgerEvent)
            .where(
                AccountLedgerEvent.account_id == account.id,
            )
            .order_by(AccountLedgerEvent.ledger_sequence)
            .limit(MAX_ROWS + 1)
        )
    ).all()
    if any(len(rows) > MAX_ROWS for rows in (orders, events, positions, account_events)):
        result = {
            "status": "unverified",
            "reason": "RECONCILIATION_CAPACITY",
            "scope": "simulator_internal",
            "allocation_inventory": None,
        }
        return (result, None) if _include_ledger else result
    errors, unknown = [], []
    from src.execution.account_events import event_evidence

    accounting_actions = []
    account_events_by_id = {event.id: event for event in account_events}
    for event in account_events:
        try:
            payload = event.payload
            if (
                event.user_id != account.user_id
                or event.kind not in {"cash_flow", "split", "dividend_payment",
                                       "dividend_entitlement", "dividend_settlement"}
                or digest(event_evidence(event)) != event.evidence_hash
                or payload["environment"] != "simulator"
                or payload["currency"] != account.currency
                or payload["origin"] != "synthetic_fixture_receipt"
            ):
                raise ValueError("Invalid account evidence")
            if event.kind == "dividend_entitlement":
                accounting_actions.append(AccountingDividendEntitlement(
                    event.id, event.ledger_sequence, payload["action_id"], payload["instrument_id"],
                    payload["allocation_id"], Decimal(payload["eligible_quantity"]),
                    Decimal(payload["gross_base"]), Decimal(payload["withholding_base"])))
                continue
            if event.kind == "dividend_settlement":
                earned = account_events_by_id.get(payload["entitlement_id"])
                if (earned is None or earned.kind != "dividend_entitlement" or event.effective_at < earned.effective_at
                        or any(payload[key] != earned.payload[key] for key in (
                            "instrument_id", "allocation_id", "action_id", "eligible_quantity",
                            "gross_base", "withholding_base", "currency"))):
                    raise ValueError("Invalid dividend settlement link")
                accounting_actions.append(AccountingDividendSettlement(event.id, event.ledger_sequence, earned.id))
                continue
            if event.kind == "dividend_payment":
                accounting_actions.append(
                    AccountingDividendPayment(
                        event.id,
                        event.ledger_sequence,
                        payload["instrument_id"],
                        payload["allocation_id"],
                        Decimal(payload["gross_base"]),
                        Decimal(payload["withholding_base"]),
                    )
                )
                continue
            if event.kind == "split":
                accounting_actions.append(
                    AccountingSplit(
                        event.id,
                        event.ledger_sequence,
                        payload["instrument_id"],
                        payload["numerator"],
                        payload["denominator"],
                    )
                )
                continue
            value = Decimal(payload["amount_base"])
            if not value.is_finite() or not value:
                raise ValueError("Invalid flow")
            accounting_actions.append(AccountingCashFlow(event.id, event.ledger_sequence, value))
        except (KeyError, TypeError, ValueError, InvalidOperation):
            unknown.append("ACCOUNT_EVENT_EVIDENCE_UNAVAILABLE")
    latest = {}
    fills = defaultdict(list)
    submissions = defaultdict(list)
    allocations = {}
    for event in events:
        payload = event.payload
        if not isinstance(payload, dict):
            unknown.append("INVALID_EVENT_EVIDENCE")
            continue
        if event.kind == "submitted":
            submissions[event.order_id].append(event)
        elif event.kind == "fill":
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
    accounting_rows = []
    expected_reserved = Decimal(0)
    seen_fills = set()

    def compare(field, actual, expected):
        if actual != expected:
            errors.append({"field": field, "actual": str(actual), "expected": str(expected)})

    for order in orders:
        try:
            allocations[order.id] = allocation_for_order(order, submissions[order.id])
        except ValueError:
            unknown.append("ALLOCATION_PROVENANCE_UNAVAILABLE")
        if order.user_id != account.user_id or order.side not in {"buy", "sell"}:
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
                accounting_rows.append((event, order, q, principal, fee))
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

    def settled_balances_known():
        # Pending commissions have no settled cash effect until their fill arrives.
        # This exception exposes only a private pre-fill balance, never verified inventory.
        return not unknown or (_pending_fees_for_fill and set(unknown) == {"COMMISSION_AWAITING_EXECUTION"})

    # Database-generated sequence survives wall-clock changes and reconnects.
    # Owned account locking serializes callback writes for each ledger.
    ledger = None
    if settled_balances_known():
        try:
            ledger = replay_events(
                Decimal(str(account.initial_capital)),
                [
                    AccountingFill(
                        execution_id=event.id,
                        sequence=event.ledger_sequence,
                        instrument_id=order.instrument_id,
                        allocation_id=allocations[order.id],
                        side=order.side,
                        quantity=q,
                        principal_base=principal,
                        fee_base=fee,
                    )
                    for event, order, q, principal, fee in accounting_rows
                ]
                + accounting_actions,
            )
            for (_, instrument_id), position in ledger.positions.items():
                expected_positions[instrument_id][0] += position.quantity
                expected_positions[instrument_id][1] += position.cost_basis
        except (ValueError, TypeError, InvalidOperation):
            unknown.append("ACCOUNTING_EVIDENCE_UNSUPPORTED")
    # Incomplete evidence cannot establish expected aggregate balances.
    if ledger is not None and settled_balances_known():
        compare("realized_pnl", account.realized_pnl, ledger.realized_pnl)
        compare("cash", account.cash, ledger.cash)
        compare("reserved", account.reserved, expected_reserved)
        actual_positions = {row.instrument_id: row for row in positions}
        for instrument_id in sorted(set(actual_positions) | set(expected_positions)):
            actual = actual_positions.get(instrument_id)
            expected = expected_positions[instrument_id]
            compare("position_quantity", actual.quantity if actual else Decimal(0), expected[0])
            compare("position_cost_basis", actual.cost_basis if actual else Decimal(0), expected[1])
    inventory = None
    if ledger is not None and not unknown and not errors:
        try:
            inventory = allocation_inventory(ledger, orders, allocations)
        except (ValueError, TypeError, InvalidOperation):
            unknown.append("ALLOCATION_INVENTORY_UNVERIFIED")
    result = {
        "allocation_inventory": inventory,
        "scope": "simulator_internal",
        "status": "unverified" if unknown else "discrepant" if errors else "consistent",
        "unknown_reasons": sorted(set(unknown)),
        "discrepancy_count": len(errors),
        "discrepancies": errors[:100],
        "orders_checked": len(orders),
        "events_checked": len(events),
        "positions_checked": len(positions),
        "account_events_checked": len(account_events),
        "net_external_flows": str(ledger.net_external_flows)
        if ledger is not None and not unknown and not errors
        else None,
        "base_currency": account.currency,
        "balance_policy": "Explicit synthetic cash-flow evidence; no silent balance replacement",
        "inputs_sha256": digest(
            {
                "account": [
                    account.id,
                    account.currency,
                    str(account.initial_capital),
                    str(account.cash),
                    str(account.reserved),
                    str(account.realized_pnl),
                ],
                "orders": [
                    [o.id, o.details_hash, o.status, str(o.filled), str(o.fees), str(o.reserve), o.approval]
                    for o in orders
                ],
                "events": [[e.id, e.ledger_sequence, e.order_id, e.event_key, e.kind, e.payload] for e in events],
                "account_events": [
                    [e.id, e.ledger_sequence, event_evidence(e), e.evidence_hash] for e in account_events
                ],
                "positions": [[p.instrument_id, str(p.quantity), str(p.cost_basis)] for p in positions],
            }
        ),
    }
    for label, attribute in (
        ("dividend_gross", "dividend_gross_by_allocation"),
        ("dividend_withholding", "dividend_withholding_by_allocation"),
    ):
        result[label] = (
            str(sum(getattr(ledger, attribute).values(), Decimal(0))) if result["status"] == "consistent" else None
        )
    result["dividend_receivable"] = str(ledger.dividend_receivable) if result["status"] == "consistent" else None
    if _include_execution_evidence and result["status"] == "consistent":
        result["reconciled_dividends"] = [
            dict(
                event_id=e.id,
                ledger_sequence=e.ledger_sequence,
                booked_at=e.observed_at.isoformat(),
                effective_at=e.effective_at.isoformat(),
                instrument_id=e.payload["instrument_id"],
                allocation_id=e.payload["allocation_id"],
                gross_base=e.payload["gross_base"],
                withholding_base=e.payload["withholding_base"],
                net_base=str(Decimal(e.payload["gross_base"]) - Decimal(e.payload["withholding_base"])),
                currency=account.currency,
                evidence_sha256=e.evidence_hash,
                entitlement_id=e.payload.get("entitlement_id"),
            )
            for e in account_events
            if e.kind in {"dividend_payment", "dividend_settlement"}
        ]
        result["reconciled_dividend_entitlements"] = [
            dict(event_id=e.id, booked_at=e.observed_at.isoformat(), effective_at=e.effective_at.isoformat(),
                 instrument_id=e.payload["instrument_id"], allocation_id=e.payload["allocation_id"],
                 gross_base=e.payload["gross_base"], withholding_base=e.payload["withholding_base"],
                 net_base=str(Decimal(e.payload["gross_base"]) - Decimal(e.payload["withholding_base"])),
                 eligible_quantity=e.payload["eligible_quantity"], currency=account.currency,
                 evidence_sha256=e.evidence_hash)
            for e in account_events if e.kind == "dividend_entitlement"
        ]
        result["reconciled_cash_flows"] = [
            dict(
                event_id=e.id,
                ledger_sequence=e.ledger_sequence,
                booked_at=e.observed_at.isoformat(),
                effective_at=e.effective_at.isoformat(),
                amount_base=e.payload["amount_base"],
                currency=account.currency,
                evidence_sha256=e.evidence_hash,
            )
            for e in account_events
            if e.kind == "cash_flow"
        ]
        result["reconciled_corporate_actions"] = [
            dict(
                event_id=e.id,
                ledger_sequence=e.ledger_sequence,
                booked_at=e.observed_at.isoformat(),
                effective_at=e.effective_at.isoformat(),
                instrument_id=e.payload["instrument_id"],
                numerator=e.payload["numerator"],
                denominator=e.payload["denominator"],
                evidence_sha256=e.evidence_hash,
                kind=e.kind,
            )
            for e in account_events
            if e.kind == "split"
        ]
        disposals = {row.execution_id: row for row in ledger.disposals}
        result["reconciled_executions"] = [
            dict(
                event_id=event.id,
                order_id=order.id,
                allocation_id=allocations[order.id],
                instrument_id=order.instrument_id,
                ledger_sequence=event.ledger_sequence,
                booked_at=event.observed_at.isoformat(),
                side=order.side,
                quantity=str(quantity),
                principal_base=str(principal),
                source_currency=event.payload["source_currency"],
                principal_source=str(quantity * number(event.payload["price"]) * number(event.payload["multiplier"])),
                fee_base=str(fee),
                realized_pnl=str(disposals[event.id].realized_pnl) if event.id in disposals else "0",
            )
            for event, order, quantity, principal, fee in sorted(
                accounting_rows, key=lambda row: row[0].ledger_sequence
            )
        ]
    result["evidence_sha256"] = digest(result)
    return (result, ledger if settled_balances_known() else None) if _include_ledger else result
