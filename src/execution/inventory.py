"""Allocation-owned holdings and pending-sale claims from reconciled evidence.

Callers hold the owned account lock while reading this view and changing orders.
This calculator is not sale authorization and never reserves anticipated buys.
"""

from decimal import Decimal, localcontext

from src.execution.accounting import amount

PENDING = {"submitted", "acknowledged", "partially_filled", "cancel_requested", "uncertain"}
TERMINAL = {"filled", "cancelled", "rejected"}


def allocation_inventory(ledger, orders, allocations):
    if len(orders) > 10000:
        raise ValueError("INVENTORY_CAPACITY")
    with localcontext() as context:
        context.prec = 80
        reserved = {}
        seen = set()
        for order in orders:
            if order.id in seen:
                raise ValueError("INVENTORY_DUPLICATE_ORDER")
            seen.add(order.id)
            if order.side == "buy":
                continue
            if order.side != "sell" or order.status not in PENDING | TERMINAL | {"proposed"}:
                raise ValueError("INVENTORY_UNSUPPORTED_ORDER")
            quantity, filled = amount(order.quantity), amount(order.filled)
            if quantity <= 0 or filled > quantity or (order.status == "filled" and filled != quantity):
                raise ValueError("INVENTORY_INVALID_FILL_QUANTITY")
            if order.status not in PENDING:
                continue
            allocation = allocations.get(order.id)
            if not allocation:
                raise ValueError("INVENTORY_OWNERSHIP_UNVERIFIED")
            key = allocation, order.instrument_id
            reserved[key] = reserved.get(key, Decimal(0)) + quantity - filled
        rows = []
        for key in sorted(set(ledger.positions) | set(reserved)):
            position = ledger.positions.get(key)
            owned = position.quantity if position else Decimal(0)
            claimed = reserved.get(key, Decimal(0))
            if claimed > owned:
                raise ValueError("INVENTORY_OVERRESERVED")
            rows.append({
                "allocation_id": key[0], "instrument_id": key[1],
                "quantity": str(owned), "cost_basis": str(position.cost_basis if position else Decimal(0)),
                "reserved_quantity": str(claimed), "available_quantity": str(owned - claimed),
            })
        return rows
