from types import SimpleNamespace
from decimal import Decimal

import pandas as pd
import pytest

from src.expenses.sync import normalise_transaction
from src.tools.simulator import _momentum
from src.expenses.summary import summarize_currencies
from src.finance.normalization import portfolio_position


def test_fractional_quantity_and_original_currency_survive():
    row = portfolio_position(
        {"symbol": "fixture", "quantity": "0.004", "price": "100", "currency": "EUR"}
    )
    assert row["quantity"] == 0.004
    assert row["quantity_exact"] == "0.004"
    assert row["price_usd"] is None
    assert row["price"] == 100
    assert row["currency"] == "EUR"


def test_fx_requires_rate_and_timestamp():
    row = {"quantity": "0.004", "price": "100", "currency": "EUR", "fx_to_usd": "1.1"}
    assert portfolio_position(row)["price_usd"] is None
    row["fx_as_of"] = "2026-09-01T00:00:00Z"
    assert portfolio_position(row)["price_usd"] == 110


def test_expense_currency_direction_and_account_are_part_of_fallback_identity():
    raw = {"amount": "-100.004", "date": "2026-09-01", "currency": "EUR"}
    base = normalise_transaction(raw, "fixture", "account-a")
    assert base["amount"] == Decimal("100.004")
    variants = [dict(raw, currency="USD"), dict(raw, amount="100.004")]
    ids = {
        base["external_id"],
        *(normalise_transaction(v, "fixture", "account-a")["external_id"] for v in variants),
        normalise_transaction(raw, "fixture", "account-b")["external_id"],
    }
    assert len(ids) == 4


@pytest.mark.parametrize("missing", ["currency", "date"])
def test_missing_expense_facts_are_rejected(missing):
    raw = {"amount": "-100", "date": "2026-09-01", "currency": "EUR"}
    raw.pop(missing)
    with pytest.raises(ValueError):
        normalise_transaction(raw, "fixture")


def test_mixed_currency_totals_are_never_added():
    rows = [
        SimpleNamespace(amount="100", currency=currency, pending=False, transaction_type="expense")
        for currency in ["EUR", "EUR", "USD"]
    ]
    totals = summarize_currencies(rows)
    assert Decimal(totals["EUR"]["total_expenses"]) == 200
    assert Decimal(totals["USD"]["total_expenses"]) == 100


def test_rebalance_preserves_current_position_value():
    prices = pd.DataFrame(
        {"FIXTURE": [100, 110, 120, 130, 200]}, index=pd.date_range("2024-01-29", periods=5)
    )
    equity, _ = _momentum(prices, 100, lookback_days=2, top_n=1)
    assert equity.loc["2024-02-01"] == pytest.approx(108.333333333333)
    assert equity.loc["2024-02-02"] == pytest.approx(166.666666666667)


def test_portfolio_aggregate_does_not_sum_unconverted_currencies():
    from unittest.mock import Mock

    from src.tools.portfolio import _collect_broker

    result = {
        "positions": [],
        "accounts": [],
        "total_market_value_usd": 0,
        "total_unrealized_pnl_usd": 0,
    }
    _collect_broker(
        "fixture",
        Mock(
            return_value=[
                {"symbol": "A", "market_value": 100, "currency": "USD"},
                {"symbol": "B", "market_value": 100, "currency": "EUR"},
            ]
        ),
        Mock(return_value={"currency": "USD"}),
        result,
    )
    assert result["total_market_value_usd"] is None
    assert result["valuation_status"] == "partial"
