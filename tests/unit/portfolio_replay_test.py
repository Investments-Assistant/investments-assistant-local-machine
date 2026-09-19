"""Shared-cash portfolio replay with explicit times, currencies and realistic fills."""

from decimal import Decimal as D
from datetime import UTC, datetime, timedelta

import pytest

from src.research.replay import Bar, Costs
from src.research.portfolio import replay_portfolio

pytestmark = pytest.mark.unit


def bars(symbol="SPYL", prices=(100, 110, 120, 130, 200), currency="EUR", fx="1"):
    start = datetime(2024, 1, 29, 8, tzinfo=UTC)
    return [
        Bar(
            symbol,
            start + timedelta(days=i),
            start + timedelta(days=i, hours=8),
            D(price),
            D(price),
            D("100000"),
            currency,
            D(fx),
            start + timedelta(days=i),
        )
        for i, price in enumerate(prices)
    ]


def replay(series, strategy="momentum", costs=None, **params):
    return replay_portfolio(
        series,
        capital=D("100"),
        base_currency="EUR",
        strategy=strategy,
        params=params or {"lookback_days": 2, "top_n": 1},
        costs=costs
        or Costs(
            commission_bps=D(0),
            minimum_commission=D(0),
            spread_bps=D(0),
            slippage_bps=D(0),
            fx_bps=D(0),
        ),
        source={"fixture": True},
    )


def test_momentum_uses_later_open_and_marks_final_holdings_without_fake_sale():
    result = replay({"SPYL": bars()})
    assert D(result["final_value"]) == D("153.83")
    assert len(result["trades"]) == 1 and result["trades"][0]["action"] == "BUY"
    assert result["trades"][0]["filled_at"] > result["trades"][0]["signal_at"]
    assert D(result["cash"]) >= 0 and D(result["quantities"]["SPYL"]) > 0


def test_multi_currency_shared_cash_never_labels_usd_as_eur():
    result = replay(
        {"EUR": bars("EUR", (10, 10, 10)), "USD": bars("USD", (20, 20, 20), "USD", ".5")},
        strategy="buy_and_hold",
    )
    assert D(result["final_value"]) == 100
    assert {key: D(value) for key, value in result["quantities"].items()} == {
        "EUR": D(5),
        "USD": D(5),
    }
    assert result["base_currency"] == "EUR"
    assert all(D(trade["price_in_base"]) == 10 for trade in result["trades"])


@pytest.mark.parametrize(
    "strategy,params",
    [
        ("buy_and_hold", {}),
        ("sma_crossover", {"fast": 2, "slow": 3}),
        ("rsi_mean_reversion", {"rsi_buy": 30, "rsi_sell": 70}),
    ],
)
def test_retained_strategy_flows_have_costs_and_later_fills(strategy, params):
    prices = tuple(range(120, 99, -1)) + tuple(range(100, 130))
    result = replay({"SPYL": bars(prices=prices)}, strategy=strategy, costs=Costs(), **params)
    assert result["trades"]
    assert D(result["fees"]) > 0 and D(result["cash"]) >= 0
    assert all(trade["filled_at"] > trade["signal_at"] for trade in result["trades"])
    assert result["input_hash"]


def test_saved_evidence_reproduces_offline_and_detects_edits():
    from unittest.mock import patch

    from src.tools.simulator import run_simulation
    from scripts.replay_saved_evidence import reproduce

    with patch("src.tools.simulator._download", return_value=({"SPYL": bars()}, {"fixture": True})):
        result = run_simulation(
            "Fixture",
            ["SPYL"],
            {"type": "momentum", "params": {"lookback_days": 2, "top_n": 1}},
            initial_capital=100,
            base_currency="EUR",
        )
    evidence = result["strategy"]["research"]
    assert reproduce(evidence)["status"] == "PASS"
    evidence["bars"]["SPYL"][0]["close"] = "999"
    with pytest.raises(ValueError, match="hash mismatch"):
        reproduce(evidence)


def test_split_and_dividend_are_ledger_events_without_double_counting():
    from dataclasses import replace

    source = bars(prices=(100, 100, 50, 50))
    source[2] = replace(source[2], split=D(2), dividend=D(1))
    result = replay({"SPYL": source}, strategy="buy_and_hold")
    assert D(result["quantities"]["SPYL"]) == 2
    assert D(result["dividends"]) == 2
    assert D(result["final_value"]) == 102
    assert D(result["unrealized_pnl"]) == 0


def test_sma_requires_a_cross_not_merely_an_initial_uptrend():
    result = replay(
        {"SPYL": bars(prices=tuple(range(100, 120)))}, strategy="sma_crossover", fast=2, slow=3
    )
    assert result["trades"] == []


def test_rsi_trade_signals_match_retained_wilder_indicator():
    import pandas as pd
    from ta.momentum import RSIIndicator

    prices = tuple(range(120, 99, -1)) + tuple(range(100, 130))
    source = bars(prices=prices)
    result = replay({"SPYL": source}, strategy="rsi_mean_reversion", rsi_buy=30, rsi_sell=70)
    indicator = RSIIndicator(pd.Series(prices, dtype=float), window=14).rsi()
    first_buy = next(i for i in range(14, len(prices)) if indicator.iloc[i] < 30)
    first_sell = next(i for i in range(first_buy + 1, len(prices)) if indicator.iloc[i] > 70)
    assert [trade["signal_at"] for trade in result["trades"][:2]] == [
        source[first_buy].close_at.isoformat(),
        source[first_sell].close_at.isoformat(),
    ]
