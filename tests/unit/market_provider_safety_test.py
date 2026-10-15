"""Yahoo permission and safe provider failures, using only synthetic transports."""

import json
from types import SimpleNamespace
import builtins
from unittest.mock import Mock, MagicMock

import pytest

from src.tools import forex, market_data
from src.config import Settings

pytestmark = pytest.mark.unit

READS = [
    (market_data.get_stock_data, (["FIXTURE"],), "MARKET_DATA_UNAVAILABLE"),
    (market_data.get_crypto_data, (["FIXTURE-USD"],), "MARKET_DATA_UNAVAILABLE"),
    (market_data.get_market_overview, (), "MARKET_OVERVIEW_UNAVAILABLE"),
    (market_data.get_technical_indicators, ("FIXTURE",), "TECHNICAL_INDICATORS_UNAVAILABLE"),
    (market_data.get_options_chain, ("FIXTURE",), "OPTIONS_CHAIN_UNAVAILABLE"),
    (market_data.search_ticker, ("fixture",), "TICKER_SEARCH_UNAVAILABLE"),
    (market_data.get_earnings_calendar, (), "EARNINGS_CALENDAR_UNAVAILABLE"),
    (forex.get_forex_data, (["EURUSD"],), "FOREX_DATA_UNAVAILABLE"),
    (forex.get_forex_rates, (["EURUSD"],), "FOREX_RATE_UNAVAILABLE"),
]


def call_read(function, arguments):
    if function is market_data.get_earnings_calendar:
        return function(*arguments, symbols=["FIXTURE"])
    return function(*arguments)


def error_rows(value):
    if isinstance(value, dict):
        if "error" in value:
            yield value
        for nested in value.values():
            yield from error_rows(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from error_rows(nested)


@pytest.mark.parametrize("function,arguments,code", READS)
def test_production_default_blocks_before_provider_import(monkeypatch, function, arguments, code):
    monkeypatch.delenv("YAHOO_MARKET_DATA_ENABLED", raising=False)
    settings = Settings(_env_file=None, environment="production")
    monkeypatch.setattr(market_data, "get_settings", lambda: settings, raising=False)
    original_import = builtins.__import__
    def restricted_import(name, *args, **kwargs):
        if name in {"yfinance", "ta"}:
            pytest.fail("Unapproved Yahoo read imported its provider")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", restricted_import)

    result = call_read(function, arguments)

    assert result["available"] is False
    assert result["error"] == "YAHOO_MARKET_DATA_DISABLED_PENDING_OPERATOR_REVIEW"
    assert settings.yahoo_market_data_enabled is False


@pytest.mark.parametrize("value", [1, "true", None, MagicMock()])
def test_nonboolean_values_cannot_authorize_provider_work(monkeypatch, value):
    monkeypatch.setattr(
        market_data, "get_settings", lambda: SimpleNamespace(yahoo_market_data_enabled=value), raising=False,
    )
    factory = Mock(side_effect=AssertionError("Provider must not be used"))
    monkeypatch.setattr("yfinance.Ticker", factory)

    assert market_data.get_market_overview()["available"] is False
    assert forex.get_forex_rates(["EURUSD"])["available"] is False
    factory.assert_not_called()


def test_historical_permission_does_not_enable_market_reads(monkeypatch):
    settings = Settings(_env_file=None, environment="production",
                        yahoo_historical_data_enabled=True, yahoo_market_data_enabled=False)
    monkeypatch.setattr(market_data, "get_settings", lambda: settings, raising=False)
    factory = Mock(side_effect=AssertionError("Market provider must not be used"))
    monkeypatch.setattr("yfinance.Ticker", factory)
    assert market_data.get_stock_data(["FIXTURE"])["available"] is False
    assert forex.get_forex_data(["EURUSD"])["available"] is False
    factory.assert_not_called()


def test_market_permission_does_not_enable_historical_research(monkeypatch):
    from src.research import history

    settings = Settings(_env_file=None, environment="production",
                        yahoo_market_data_enabled=True, yahoo_historical_data_enabled=False)
    monkeypatch.setattr(history, "get_settings", lambda: settings)
    factory = Mock(side_effect=AssertionError("Historical provider must not be used"))
    monkeypatch.setattr(history.yf, "Ticker", factory)
    with pytest.raises(ValueError, match="YAHOO_RESEARCH_SOURCE_DISABLED_PENDING_OPERATOR_REVIEW"):
        history.load_history(["FIXTURE"], "2025-01-01", "2025-02-01", "USD")
    factory.assert_not_called()


@pytest.mark.parametrize("function,arguments,code", READS)
def test_internal_provider_failures_never_expose_exception_text(monkeypatch, caplog, function, arguments, code):
    settings = Settings(_env_file=None, environment="production", yahoo_market_data_enabled=True)
    monkeypatch.setattr(market_data, "get_settings", lambda: settings, raising=False)
    private = "fake-market-token fake-account-492 https://fake-user:fake-password@provider.invalid/?token=fake-market-token\nFORGED_MARKET_LOG"
    ticker = Mock(side_effect=RuntimeError(private))
    search = Mock(side_effect=RuntimeError(private))
    monkeypatch.setattr("yfinance.Ticker", ticker)
    monkeypatch.setattr("yfinance.Search", search)

    result = call_read(function, arguments)

    captured = json.dumps(result) + caplog.text
    errors = list(error_rows(result))
    assert errors and all(row["error"] == code and row["available"] is False for row in errors)
    for item in ("fake-market-token", "fake-account-492", "fake-password", "FORGED_MARKET_LOG"):
        assert item not in captured
    assert all(record.exc_info is None for record in caplog.records)
    assert ticker.called or search.called


def test_central_bank_reference_is_available_without_yahoo_permission(monkeypatch):
    monkeypatch.setattr(
        market_data, "get_settings", lambda: SimpleNamespace(yahoo_market_data_enabled=False), raising=False,
    )
    result = forex.get_central_bank_rates(["EUR", "USD"])
    assert result["data_quality"] == "static_reference_only"
    assert result["usable_for_auto_trading"] is False
    assert set(result["rates"]) == {"EUR", "USD"}
