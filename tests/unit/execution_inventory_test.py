from types import SimpleNamespace
from decimal import Decimal

import pytest

from src.execution.inventory import allocation_inventory
from src.execution.accounting import AccountingFill, replay_fills


def ledger():
    return replay_fills(Decimal(1000), [
        AccountingFill("manual-fill", 1, "fixture", "manual", "buy", Decimal(2), Decimal(200), Decimal(0)),
        AccountingFill("mandate-fill", 2, "fixture", "mandate", "buy", Decimal(3), Decimal(300), Decimal(0)),
    ])


def order(identity="sell-1", status="submitted", quantity="1", filled="0", side="sell"):
    return SimpleNamespace(id=identity, status=status, side=side, instrument_id="fixture",
                           quantity=Decimal(quantity), filled=Decimal(filled))


@pytest.mark.parametrize("status", ["submitted", "acknowledged", "partially_filled", "cancel_requested", "uncertain"])
def test_pending_sale_claims_only_its_allocations_remaining_quantity(status):
    rows = allocation_inventory(ledger(), [order(status=status, quantity="1.5", filled="0.5")], {"sell-1": "manual"})
    manual = next(row for row in rows if row["allocation_id"] == "manual")
    strategy = next(row for row in rows if row["allocation_id"] == "mandate")
    assert Decimal(manual["reserved_quantity"]) == 1 and Decimal(manual["available_quantity"]) == 1
    assert Decimal(strategy["reserved_quantity"]) == 0 and Decimal(strategy["available_quantity"]) == 3


@pytest.mark.parametrize("status", ["proposed", "cancelled", "rejected", "filled"])
def test_only_terminal_or_unapproved_orders_release_claims(status):
    filled = "1" if status == "filled" else "0"
    rows = allocation_inventory(ledger(), [order(status=status, filled=filled)], {"sell-1": "manual"})
    assert all(Decimal(row["reserved_quantity"]) == 0 for row in rows)


def test_two_pending_sales_cannot_claim_same_owned_shares():
    with pytest.raises(ValueError, match="INVENTORY_OVERRESERVED"):
        allocation_inventory(ledger(), [order(quantity="1.5"), order("sell-2", quantity="1")],
                             {"sell-1": "manual", "sell-2": "manual"})


def test_another_allocation_and_unfilled_buys_cannot_cover_sale():
    with pytest.raises(ValueError, match="INVENTORY_OVERRESERVED"):
        allocation_inventory(ledger(), [order(quantity="3"), order("buy-2", side="buy", quantity="100")],
                             {"sell-1": "manual", "buy-2": "manual"})


def test_missing_ownership_and_duplicate_order_fail_closed():
    with pytest.raises(ValueError, match="INVENTORY_OWNERSHIP_UNVERIFIED"):
        allocation_inventory(ledger(), [order()], {})
    with pytest.raises(ValueError, match="INVENTORY_DUPLICATE_ORDER"):
        allocation_inventory(ledger(), [order(), order()], {"sell-1": "manual"})
