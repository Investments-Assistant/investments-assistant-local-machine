"""Cash flows and splits must not manufacture trading profit or move ownership."""

from decimal import Decimal, localcontext
from dataclasses import replace

import pytest

from src.execution.accounting import AccountingSplit, AccountingCashFlow, replay_events
from tests.unit.execution_accounting_test import fill


def test_deposits_and_withdrawals_are_separate_from_realized_profit():
    rows = [
        AccountingCashFlow("deposit", 1, Decimal(200)),
        fill(2, "buy", "2", "100"),
        fill(3, "sell", "1", "70"),
        AccountingCashFlow("withdrawal", 4, Decimal(-50)),
    ]
    with localcontext() as context:
        context.prec = 6
        result = replay_events(Decimal(100), list(reversed(rows)))
    assert result.cash == 220
    assert result.net_external_flows == 150
    assert result.realized_pnl == 20
    assert result.positions["manual", "fixture"].cost_basis == 50


def test_split_applies_to_each_owned_allocation_and_preserves_total_basis():
    rows = [
        fill(1, "buy", "2", "100", allocation="protected"),
        fill(2, "buy", "1", "60", allocation="experiment"),
        AccountingSplit("split", 3, "fixture", 2, 1),
        fill(4, "sell", "1", "40", allocation="experiment"),
    ]
    result = replay_events(Decimal(1000), rows)
    assert result.positions["protected", "fixture"].quantity == 4
    assert result.positions["protected", "fixture"].cost_basis == 100
    assert result.positions["experiment", "fixture"].quantity == 1
    assert result.positions["experiment", "fixture"].cost_basis == 30
    assert result.realized_by_allocation["protected"] == 0
    assert result.realized_by_allocation["experiment"] == 10
    assert result.cash == 880 and result.net_external_flows == 0
    rows[0] = replace(rows[0], fee_base=Decimal(2))
    corrected = replay_events(Decimal(1000), rows)
    assert corrected.positions["protected", "fixture"].cost_basis == 102
    assert corrected.realized_pnl == 10 and corrected.cash == 878


def test_reverse_split_preserves_fractional_quantity_and_final_basis_release():
    rows = [
        fill(1, "buy", "3", "100", fee="0.01"),
        AccountingSplit("split", 2, "fixture", 1, 2),
        fill(3, "sell", "1.5", "120", fee="0.02"),
    ]
    result = replay_events(Decimal(1000), rows)
    assert result.realized_pnl == Decimal("19.97")
    assert result.positions["manual", "fixture"].quantity == 0
    assert result.positions["manual", "fixture"].cost_basis == 0
    assert result.cash == Decimal("1019.97")


def test_unrepresentable_reverse_split_requires_explicit_cash_in_lieu_evidence():
    with pytest.raises(ValueError, match="ACCOUNTING_UNSUPPORTED_PRECISION"):
        replay_events(Decimal(1000), [fill(1, "buy", "1", "100"), AccountingSplit("split", 2, "fixture", 1, 3)])


@pytest.mark.parametrize("numerator,denominator", [(0, 1), (1, 0), (-1, 1), (True, 1), (1, 1.5), (10**10, 1)])
def test_invalid_split_ratios_rejected(numerator, denominator):
    with pytest.raises(ValueError, match="ACCOUNTING_INVALID_SPLIT"):
        replay_events(Decimal(1000), [AccountingSplit("split", 1, "fixture", numerator, denominator)])


def test_duplicate_sequence_or_identity_across_event_types_rejected():
    first = fill(1, "buy", "1", "100")
    for flow in [AccountingCashFlow("flow", 1, Decimal(10)), AccountingCashFlow("1", 2, Decimal(10))]:
        with pytest.raises(ValueError, match="ACCOUNTING_AMBIGUOUS_EXECUTION_ORDER"):
            replay_events(Decimal(1000), [first, flow])


def test_split_does_not_make_unowned_sales_valid():
    with pytest.raises(ValueError, match="ACCOUNTING_UNOWNED_SALE"):
        replay_events(
            Decimal(1000),
            [
                fill(1, "buy", "1", "100", allocation="protected"),
                AccountingSplit("split", 2, "fixture", 2, 1),
                fill(3, "sell", "1", "50", allocation="experiment"),
            ],
        )


def test_only_positions_held_at_split_sequence_are_adjusted():
    rows = [
        fill(1, "buy", "1", "100"),
        AccountingSplit("split", 2, "fixture", 2, 1),
        fill(3, "buy", "1", "60"),
        fill(4, "buy", "1", "50", instrument="other"),
    ]
    result = replay_events(Decimal(1000), list(reversed(rows)))
    assert result.positions["manual", "fixture"].quantity == 3
    assert result.positions["manual", "fixture"].cost_basis == 160
    assert result.positions["manual", "other"].quantity == 1
    assert result.cash == 790 and result.realized_pnl == 0


@pytest.mark.parametrize("value", ["0", "NaN", "Infinity", "0.00000000001", "1000000000000000000"])
def test_invalid_cash_flow_is_not_silently_rounded(value):
    with pytest.raises(ValueError):
        replay_events(Decimal(1000), [AccountingCashFlow("flow", 1, Decimal(value))])


def test_dividend_after_sale_preserves_allocation_income_and_fee_restatement():
    from src.execution.accounting import AccountingDividendPayment

    rows = [
        fill(1, "buy", "2", "100", allocation="income"),
        fill(2, "sell", "2", "120", allocation="income"),
        AccountingDividendPayment("paid", 3, "fixture", "income", Decimal(10), Decimal("2.5")),
    ]
    with localcontext() as context:
        context.prec = 6
        result = replay_events(Decimal(1000), list(reversed(rows)))
    assert result.cash == Decimal("1027.5") and result.realized_pnl == 20
    assert result.dividend_gross_by_allocation == {"income": Decimal(10)}
    assert result.dividend_withholding_by_allocation == {"income": Decimal("2.5")}
    assert result.positions["income", "fixture"].cost_basis == 0
    assert result.net_external_flows == 0
    rows[0] = replace(rows[0], fee_base=Decimal("0.20"))
    corrected = replay_events(Decimal(1000), rows)
    assert corrected.cash == Decimal("1027.30") and corrected.realized_pnl == Decimal("19.80")
    assert corrected.dividend_gross_by_allocation == result.dividend_gross_by_allocation
    rows[-1] = replace(rows[-1], allocation_id="unowned")
    with pytest.raises(ValueError, match="DIVIDEND_OWNERSHIP_UNVERIFIED"):
        replay_events(Decimal(1000), rows)
