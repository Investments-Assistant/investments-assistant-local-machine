"""SDK failures stay visible without exposing provider text or credentials."""

import json
from unittest.mock import Mock

import pytest

from src.tools import portfolio
from src.tools.brokers import alpaca, binance, coinbase
from src.security.errors import safe_exception_code
from src.tools.broker_accounts import BrokerAccountConfig

PRIVATE_FAILURE = (
    "fake-account-48392 fake-token-avoid-leaking "
    "https://fake-user:fake-password@provider.invalid/path?token=fake-token-avoid-leaking\n"
    "FORGED_LOG_ENTRY"
)


def fixture_account(module):
    name = module.__name__.rsplit(".", 1)[-1]
    return BrokerAccountConfig("fixture", "owner", name, "Fixture", {
        "api_key": "synthetic-unused-key", "secret_key": "synthetic-unused-secret",
        "api_secret": "synthetic-unused-secret", "paper": True, "testnet": True,
    })


READS = [
    (alpaca, "get_alpaca_account", "get_account", {}, "ALPACA_ACCOUNT_UNAVAILABLE"),
    (alpaca, "get_alpaca_positions", "get_all_positions", {}, "ALPACA_POSITIONS_UNAVAILABLE"),
    (alpaca, "get_alpaca_orders", "get_orders", {}, "ALPACA_ORDERS_UNAVAILABLE"),
    (coinbase, "get_coinbase_account", "get_accounts", {}, "COINBASE_ACCOUNT_UNAVAILABLE"),
    (coinbase, "get_coinbase_positions", "get_accounts", {}, "COINBASE_ACCOUNT_UNAVAILABLE"),
    (coinbase, "get_coinbase_orders", "list_orders", {}, "COINBASE_ORDERS_UNAVAILABLE"),
    (binance, "get_binance_account", "get_account", {}, "BINANCE_ACCOUNT_UNAVAILABLE"),
    (binance, "get_binance_positions", "get_account", {}, "BINANCE_ACCOUNT_UNAVAILABLE"),
    (binance, "get_binance_orders", "get_all_orders", {"symbol": "FIXTUREUSD"}, "BINANCE_ORDERS_UNAVAILABLE"),
]


@pytest.mark.parametrize("module,function,method,arguments,code", READS)
@pytest.mark.parametrize("construction_failure", [False, True])
def test_provider_exception_is_safe_and_still_unavailable(
    monkeypatch, caplog, module, function, method, arguments, code, construction_failure,
):
    client = Mock()
    getattr(client, method).side_effect = RuntimeError(PRIVATE_FAILURE)
    factory = Mock(return_value=client)
    if construction_failure:
        factory.side_effect = RuntimeError(PRIVATE_FAILURE)
    monkeypatch.setattr(module, "_get_client", factory)

    result = getattr(module, function)(account=fixture_account(module), **arguments)

    rows = result if isinstance(result, list) else [result]
    assert rows and rows[0]["error"] == code
    assert rows[0]["available"] is False
    captured = json.dumps(result) + caplog.text
    for private in ("fake-account-48392", "fake-token-avoid-leaking", "fake-password", "FORGED_LOG_ENTRY"):
        assert private not in captured
    assert all(record.exc_info is None for record in caplog.records)


@pytest.mark.parametrize("failure_path", ["exception", "account_payload", "positions_payload"])
def test_portfolio_rejects_raw_failure_text_and_invalidates_totals(monkeypatch, caplog, failure_path):
    account_fn = Mock(return_value={"currency": "USD"})
    positions_fn = Mock(return_value=[])
    if failure_path == "exception":
        account_fn.side_effect = RuntimeError(PRIVATE_FAILURE)
    elif failure_path == "account_payload":
        account_fn.return_value = {"error": PRIVATE_FAILURE}
    else:
        positions_fn.return_value = [{"error": PRIVATE_FAILURE}]
    monkeypatch.setattr(portfolio, "_BROKER_FUNNELS", [("alpaca", positions_fn, account_fn)])

    result = portfolio.get_portfolio_summary(accounts=[fixture_account(alpaca)])

    assert result["errors"]
    assert result["valuation_status"] == "partial"
    assert result["total_market_value_usd"] is None
    assert result["total_market_value_usd_exact"] is None
    assert result["total_unrealized_pnl_usd"] is None
    assert result["total_unrealized_pnl_usd_exact"] is None
    assert PRIVATE_FAILURE not in json.dumps(result) + caplog.text
    assert "fake-token-avoid-leaking" not in json.dumps(result) + caplog.text
    assert "FORGED_LOG_ENTRY" not in json.dumps(result) + caplog.text


@pytest.mark.parametrize("message,expected", [
    ("FIXTURE_DENIED", "FIXTURE_DENIED"),
    ("FIXTURE_DENIED\n" + PRIVATE_FAILURE, "FIXTURE_UNAVAILABLE"),
    (PRIVATE_FAILURE, "FIXTURE_UNAVAILABLE"),
])
def test_only_complete_caller_owned_codes_are_preserved(message, expected):
    assert safe_exception_code(
        RuntimeError(message), fallback="FIXTURE_UNAVAILABLE", allowed_codes={"FIXTURE_DENIED"},
    ) == expected


def test_exception_formatter_cannot_break_redaction():
    class BrokenFormatter(RuntimeError):
        def __str__(self):
            raise RuntimeError(PRIVATE_FAILURE)
    assert safe_exception_code(BrokenFormatter(), fallback="FIXTURE_UNAVAILABLE") == "FIXTURE_UNAVAILABLE"
    assert safe_exception_code(
        BrokenFormatter(), fallback="FIXTURE_UNAVAILABLE", allowed_codes={"FIXTURE_DENIED"},
    ) == "FIXTURE_UNAVAILABLE"


@pytest.mark.parametrize("module", [alpaca, coinbase, binance])
def test_external_write_guards_still_prevent_client_creation(monkeypatch, module):
    factory = Mock(side_effect=AssertionError("SDK client must not be constructed"))
    monkeypatch.setattr(module, "_get_client", factory)
    broker = module.__name__.rsplit(".", 1)[-1]
    submit = getattr(module, f"submit_{broker}_order")("FIXTUREUSD", "buy", 1, account=fixture_account(module))
    cancel = getattr(module, f"cancel_{broker}_order")("fixture-order", account=fixture_account(module))
    assert submit["blocked"] is True and cancel["blocked"] is True
    factory.assert_not_called()


def test_portfolio_keeps_stable_adapter_codes_and_deduplicates(monkeypatch):
    safe = {"error": "ALPACA_ACCOUNT_UNAVAILABLE", "available": False}
    monkeypatch.setattr(portfolio, "_BROKER_FUNNELS", [
        ("alpaca", Mock(return_value=[safe]), Mock(return_value=safe)),
    ])
    result = portfolio.get_portfolio_summary(accounts=[fixture_account(alpaca)])
    assert len(result["errors"]) == 1
    assert result["errors"][0]["error"] == "ALPACA_ACCOUNT_UNAVAILABLE"


def synthetic_order(symbol):
    return {"orderId": 1, "symbol": symbol, "side": "BUY", "type": "LIMIT",
            "origQty": "1", "executedQty": "1", "price": "10", "status": "FILLED", "time": 1}


@pytest.mark.parametrize("all_failed", [False, True])
def test_binance_default_symbols_do_not_hide_failed_reads(monkeypatch, caplog, all_failed):
    client = Mock()
    def fetch(*, symbol, limit):
        if not all_failed and symbol == "BTCUSDT":
            return [synthetic_order(symbol)]
        raise RuntimeError(PRIVATE_FAILURE)
    client.get_all_orders.side_effect = fetch
    monkeypatch.setattr(binance, "_get_client", Mock(return_value=client))

    result = binance.get_binance_orders(account=fixture_account(binance))

    errors = [row for row in result if "error" in row]
    orders = [row for row in result if "error" not in row]
    assert len(errors) == (4 if all_failed else 3)
    assert all(row["error"] == "BINANCE_ORDERS_UNAVAILABLE" and row["available"] is False for row in errors)
    assert len(orders) == (0 if all_failed else 1)
    if orders:
        assert orders[0]["symbol"] == "BTCUSDT"
    assert client.get_all_orders.call_count == 4
    assert "fake-token-avoid-leaking" not in json.dumps(result) + caplog.text
    assert "FORGED_LOG_ENTRY" not in json.dumps(result) + caplog.text
