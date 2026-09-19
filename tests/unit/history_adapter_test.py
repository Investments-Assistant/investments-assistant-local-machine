"""Actual exchange calendars with synthetic provider transport; no Yahoo calls."""

from types import SimpleNamespace
from decimal import Decimal
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from src.research.history import load_history

pytestmark = pytest.mark.unit


def frame(dates, prices=(100, 101)):
    return pd.DataFrame(
        {
            "Open": prices,
            "Close": prices,
            "Volume": [10000] * len(prices),
            "Dividends": [0] * len(prices),
            "Stock Splits": [0] * len(prices),
        },
        index=pd.DatetimeIndex(dates),
    )


def ticker(data, currency="EUR", exchange="GER"):
    return SimpleNamespace(
        history=Mock(return_value=data),
        history_metadata={"currency": currency, "exchangeName": exchange},
    )


def test_xetra_calendar_observes_dst_and_preserves_eur():
    data = frame(["2024-03-28", "2024-04-02"])
    with patch("src.research.history.yf.Ticker", return_value=ticker(data)):
        series, source = load_history(["SPYL.DE"], "2024-03-28", "2024-04-03", "EUR")
    assert [bar.open_at.hour for bar in series["SPYL.DE"]] == [8, 7]
    assert all(bar.currency == "EUR" and bar.fx_to_base == 1 for bar in series["SPYL.DE"])
    assert source["instruments"]["SPYL.DE"]["calendar"] == "XETR"


def test_fx_uses_only_a_preceding_daily_close():
    equity = ticker(frame(["2024-04-02", "2024-04-03"]))
    fx = ticker(frame(["2024-04-01", "2024-04-02"], (1.1, 1.2)), currency="USD")
    with patch(
        "src.research.history.yf.Ticker",
        side_effect=lambda symbol: fx if symbol.endswith("=X") else equity,
    ):
        series, _ = load_history(["SPYL.DE"], "2024-04-02", "2024-04-04", "USD")
    first = series["SPYL.DE"][0]
    assert first.fx_to_base == Decimal("1.1")
    assert first.fx_as_of == datetime(2024, 4, 2, tzinfo=UTC)
    assert first.fx_as_of <= first.open_at


@pytest.mark.parametrize("currency,exchange", [(None, "GER"), ("EUR", "UNKNOWN")])
def test_unknown_currency_or_exchange_is_not_guessed(currency, exchange):
    with patch(
        "src.research.history.yf.Ticker",
        return_value=ticker(frame(["2024-04-02", "2024-04-03"]), currency, exchange),
    ), pytest.raises(ValueError, match="currency, supported exchange"):
        load_history(["FIXTURE"], "2024-04-02", "2024-04-04", "EUR")


def test_holiday_bar_is_rejected_instead_of_inventing_a_session():
    with patch(
        "src.research.history.yf.Ticker", return_value=ticker(frame(["2024-03-29", "2024-04-01"]))
    ), pytest.raises(ValueError, match="calendar"):
        load_history(["SPYL.DE"], "2024-03-28", "2024-04-03", "EUR")
