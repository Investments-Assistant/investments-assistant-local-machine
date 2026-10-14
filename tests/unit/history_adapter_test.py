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


@pytest.fixture(autouse=True)
def allow_synthetic_yahoo_transport(monkeypatch):
    """Synthetic transport tests opt in explicitly; they never make requests."""
    monkeypatch.setattr(
        "src.research.history.get_settings",
        lambda: SimpleNamespace(yahoo_historical_data_enabled=True),
    )


def test_yahoo_provider_is_disabled_by_default_before_network(monkeypatch):
    from src.config import Settings
    from src.tools.simulator import _simulate

    monkeypatch.setattr(
        "src.research.history.get_settings", lambda: Settings(_env_file=None)
    )
    provider = Mock(side_effect=AssertionError("provider must not be contacted"))
    monkeypatch.setattr("src.research.history.yf.Ticker", provider)
    with pytest.raises(ValueError, match="YAHOO_RESEARCH_SOURCE_DISABLED"):
        load_history(["SPYL.DE"], "2024-03-28", "2024-04-03", "EUR")
    provider.assert_not_called()
    result = _simulate(
        "blocked fixture",
        ["SPYL.DE"],
        {"type": "buy_and_hold", "params": {}},
        period_start="2024-03-28",
        period_end="2024-04-03",
        base_currency="EUR",
    )
    assert "YAHOO_RESEARCH_SOURCE_DISABLED" in result["error"]
    provider.assert_not_called()


def test_operator_environment_opt_in_is_read(monkeypatch):
    from src.config import Settings

    data = frame(["2024-04-02", "2024-04-03"])
    provider = Mock(return_value=ticker(data))
    monkeypatch.setenv("YAHOO_HISTORICAL_DATA_ENABLED", "true")
    monkeypatch.setattr(
        "src.research.history.get_settings",
        lambda: Settings(_env_file=None),
    )
    monkeypatch.setattr("src.research.history.yf.Ticker", provider)
    series, _ = load_history(["SPYL.DE"], "2024-04-02", "2024-04-04", "EUR")
    assert len(series["SPYL.DE"]) == 2
    provider.assert_called_once_with("SPYL.DE")


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
