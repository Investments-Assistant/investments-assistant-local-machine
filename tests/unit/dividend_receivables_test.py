"""Received cash and accrued dividend assets must not be counted twice."""

from decimal import Decimal, localcontext
from dataclasses import replace

import pytest

from src.execution.accounting import (
    AccountingSplit,
    AccountingDividendSettlement,
    AccountingDividendEntitlement,
    replay_events,
)
from tests.unit.execution_accounting_test import fill


def entitlement(**changes):
    event = AccountingDividendEntitlement("entitlement", 2, "issuer-action", "fixture", "manual",
                                           Decimal(2), Decimal(10), Decimal("2.5"))
    return replace(event, **changes)


def test_accrual_creates_only_receivable_and_settlement_moves_it_to_cash():
    buy = fill(1, "buy", "2", "200")
    accrued = replay_events(Decimal(1000), [buy, entitlement()])
    assert accrued.cash == 800 and accrued.dividend_receivable == Decimal("7.5")
    assert accrued.dividend_gross_by_allocation == {}
    assert accrued.dividend_receivables_by_allocation == {"manual": Decimal("7.5")}
    assert accrued.positions["manual", "fixture"].cost_basis == 200
    receipt = AccountingDividendSettlement("payment", 3, "entitlement")
    paid = replay_events(Decimal(1000), [receipt, entitlement(), buy])
    assert paid.cash == Decimal("807.5") and paid.dividend_receivable == 0
    assert paid.dividend_gross_by_allocation == {"manual": Decimal(10)}
    assert paid.dividend_withholding_by_allocation == {"manual": Decimal("2.5")}
    assert accrued.cash + accrued.dividend_receivable == paid.cash + paid.dividend_receivable
    assert paid.realized_pnl == accrued.realized_pnl == 0


def test_later_sale_or_split_does_not_erase_or_resize_earned_entitlement():
    rows = [fill(1, "buy", "2", "200"), entitlement(), AccountingSplit("split", 3, "fixture", 2, 1),
            fill(4, "sell", "4", "240"), AccountingDividendSettlement("payment", 5, "entitlement")]
    with localcontext() as context:
        context.prec = 5
        accrued = replay_events(Decimal(1000), rows[:-1])
        paid = replay_events(Decimal(1000), rows)
    assert accrued.positions["manual", "fixture"].quantity == 0
    assert accrued.dividend_receivable == Decimal("7.5")
    assert paid.cash == Decimal("1047.5") and paid.realized_pnl == 40


@pytest.mark.parametrize("changes", [
    {"eligible_quantity": Decimal(3)}, {"eligible_quantity": Decimal(0)},
    {"eligible_quantity": Decimal("NaN")}, {"gross_base": Decimal("Infinity")},
    {"withholding_base": Decimal(-1)}, {"withholding_base": Decimal(11)},
    {"gross_base": Decimal("0.00000000001")}, {"allocation_id": "other"},
    {"instrument_id": "other"}, {"action_id": ""},
])
def test_unknown_eligibility_or_invalid_amount_fails_closed(changes):
    with pytest.raises(ValueError):
        replay_events(Decimal(1000), [fill(1, "buy", "2", "200"), entitlement(**changes)])


def test_duplicate_action_and_duplicate_or_early_settlement_are_rejected():
    buy, earned = fill(1, "buy", "2", "200"), entitlement()
    for rows in (
        [buy, earned, replace(earned, event_id="different-id", sequence=3)],
        [buy, earned, AccountingDividendSettlement("early", 0, "entitlement")],
        [buy, earned, AccountingDividendSettlement("missing", 3, "unknown")],
        [buy, earned, AccountingDividendSettlement("payment", 3, "entitlement"),
         AccountingDividendSettlement("second-payment", 4, "entitlement")],
    ):
        with pytest.raises(ValueError):
            replay_events(Decimal(1000), rows)


def test_partial_allocations_have_separate_earnings_for_the_same_issuer_action():
    rows = [fill(1, "buy", "2", "200"), fill(2, "buy", ".004", ".4", allocation="long-term"),
            entitlement(sequence=3), entitlement(event_id="protected", sequence=4, allocation_id="long-term",
                eligible_quantity=Decimal(".004"), gross_base=Decimal(".02"), withholding_base=Decimal(".005"))]
    result = replay_events(Decimal(1000), rows)
    assert result.dividend_receivables_by_allocation == {"manual": Decimal("7.5"), "long-term": Decimal(".015")}
    assert result.cash == Decimal("799.6") and result.dividend_receivable == Decimal("7.515")


def test_aggregate_receivables_cannot_exceed_accounting_capacity():
    earned = entitlement(gross_base=Decimal("999999999999999999"), withholding_base=Decimal(0))
    with pytest.raises(ValueError, match="ACCOUNTING_INVALID_AMOUNT"):
        replay_events(Decimal(1000), [fill(1, "buy", "2", "200"), earned,
            replace(earned, event_id="second", action_id="second-action", sequence=3)])
