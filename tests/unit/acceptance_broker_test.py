from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.tools.brokers import ibkr, alpaca, binance, coinbase
from src.tools.broker_accounts import BrokerAccountConfig


def test_account_summary_preserves_currency_and_account_identity():
    def row(account, tag, value, currency):
        return SimpleNamespace(account=account, tag=tag, value=value, currency=currency)

    rows = [
        row("synthetic-a", "Currency", "EUR", ""),
        row("synthetic-a", "CashBalance", "100", "EUR"),
        row("synthetic-a", "CashBalance", "25", "USD"),
        row("synthetic-b", "CashBalance", "99999", "EUR"),
    ]
    result = ibkr.summarize_account(rows, "synthetic-a")
    assert result["cash_balance"] == "100"
    assert result["currency"] == "EUR"
    assert result["values_by_currency"]["USD"]["CashBalance"] == "25"
    assert "synthetic-a" not in str(result)
    assert "99999" not in str(result)


def test_unscoped_or_unapproved_connection_is_rejected_before_sdk_import():
    assert ibkr.get_ibkr_account()["error"] == "AUTHENTICATED_ACCOUNT_REQUIRED"
    fixture = BrokerAccountConfig("fixture", "user", "ibkr", "Synthetic", {"enabled": True})
    assert ibkr.get_ibkr_account(fixture)["error"] == "IBKR_READ_CONSENT_REQUIRED"


@pytest.mark.parametrize(
    "module,submit,cancel",
    [
        (alpaca, "submit_alpaca_order", "cancel_alpaca_order"),
        (ibkr, "submit_ibkr_order", "cancel_ibkr_order"),
        (coinbase, "submit_coinbase_order", "cancel_coinbase_order"),
        (binance, "submit_binance_order", "cancel_binance_order"),
    ],
)
def test_all_retained_adapter_writes_use_closed_external_gate(module, submit, cancel):
    assert getattr(module, submit)("FIXTURE", "buy", 1)["reason_code"] == "EXTERNAL_WRITES_NOT_AUTHORIZED"
    assert getattr(module, cancel)("fixture")["reason_code"] == "EXTERNAL_WRITES_NOT_AUTHORIZED"


def test_spyl_xetra_eur_contract_fixture_is_only_resolution():
    contract = SimpleNamespace(
        conId=123,
        symbol="SPYL",
        secType="STK",
        currency="EUR",
        primaryExchange="IBIS2",
        multiplier="1",
    )
    sdk = MagicMock()
    sdk.qualifyContracts.return_value = [contract]
    sdk.reqContractDetails.return_value = [SimpleNamespace(minTick=0.01, minSize=1)]
    stock = MagicMock()
    with patch.dict("sys.modules", {"ib_insync": SimpleNamespace(Stock=stock)}):
        result = ibkr.qualify_stock(sdk, symbol="SPYL", exchange="IBIS2", currency="EUR")
    stock.assert_called_once_with("SPYL", "IBIS2", "EUR")
    assert result["currency"] == "EUR" and result["con_id"] == 123
    sdk.placeOrder.assert_not_called()


def test_ambiguous_contract_is_rejected():
    sdk = MagicMock()
    sdk.qualifyContracts.return_value = []
    with (
        patch.dict("sys.modules", {"ib_insync": SimpleNamespace(Stock=MagicMock())}),
        pytest.raises(ValueError, match="AMBIGUOUS_CONTRACT"),
    ):
        ibkr.qualify_stock(sdk, symbol="SPYL", exchange="IBIS2", currency="EUR")


def test_failed_connection_disconnects_and_releases_worker_resources():
    sdk = MagicMock()
    sdk.connect.side_effect = TimeoutError("sensitive provider details")
    fixture = BrokerAccountConfig(
        "fixture",
        "user",
        "ibkr",
        "Synthetic",
        {
            "enabled": True,
            "read_authorized": True,
            "broker_account_id": "synthetic",
            "environment": "paper",
            "client_id": 123,
        },
    )
    with patch.dict("sys.modules", {"ib_insync": SimpleNamespace(IB=lambda: sdk)}):
        assert ibkr.get_ibkr_account(fixture)["error"] == "IBKR_READ_UNAVAILABLE"
    sdk.disconnect.assert_called_once()
    assert not ibkr._connection_lock.locked()
    assert sdk.connect.call_args.kwargs["readonly"] is True


@pytest.mark.parametrize("module", [alpaca, binance, coinbase, ibkr])
@pytest.mark.parametrize("invalid", ["missing", "owner", "account", "broker"])
def test_sdk_reads_require_explicit_owned_matching_account(module, invalid, monkeypatch):
    name = module.__name__.rsplit(".", 1)[-1]
    # Even configured global secrets cannot authorize a helper invocation.
    from src.config import settings

    for key in (f"{name}_api_key", f"{name}_secret_key", f"{name}_api_secret"):
        if hasattr(settings, key):
            monkeypatch.setattr(settings, key, "synthetic-global-secret")
    account = BrokerAccountConfig(
        "" if invalid == "account" else "fixture",
        "" if invalid == "owner" else "fixture-user",
        ("binance" if name == "ibkr" else "ibkr") if invalid == "broker" else name,
        "Fixture",
        {
            "enabled": True,
            "read_authorized": True,
            "broker_account_id": "synthetic",
            "environment": "paper",
            "client_id": 123,
        }
        if name == "ibkr"
        else {"api_key": "synthetic", "secret_key": "synthetic", "api_secret": "synthetic"},
    )
    if invalid == "missing":
        account = None
    constructor = MagicMock(side_effect=AssertionError("IBKR SDK must not run"))
    with (
        patch.dict("sys.modules", {"ib_insync": SimpleNamespace(IB=constructor)}),
        patch.object(module, "_connection_lock" if name == "ibkr" else "_get_client") as client,
    ):
        for suffix in ("account", "positions", "orders"):
            result = getattr(module, f"get_{name}_{suffix}")(account=account)
            assert "error" in (result[0] if isinstance(result, list) else result)
            if name == "ibkr":
                assert (result[0] if isinstance(result, list) else result)["error"] == "AUTHENTICATED_ACCOUNT_REQUIRED"
        client.assert_not_called()
        constructor.assert_not_called()
        if name == "ibkr":
            client.acquire.assert_not_called()


@pytest.mark.parametrize("port", [4001, 4002])
def test_ibkr_account_match_does_not_turn_environment_configuration_into_proof(port):
    from contextlib import contextmanager

    fixture = BrokerAccountConfig(
        "fixture",
        "fixture-user",
        "ibkr",
        "Fixture",
        {
            "environment": "paper",
            "port": port,
        },
    )
    sdk = MagicMock()
    sdk.accountSummary.return_value = []

    @contextmanager
    def connected(account):
        assert account is fixture
        yield sdk, "synthetic-managed-account"

    with patch.object(ibkr, "_connection", connected):
        result = ibkr.get_ibkr_account(fixture)
    assert result["managed_account_match"] is True
    assert result["declared_environment"] == "paper" and result["verified_environment"] is None
    assert result["environment_verification"] == "operator_configuration_only"
    assert result["execution_permission"] == "read_only_external_writes_disabled"


@pytest.mark.parametrize("module", [alpaca, binance, coinbase])
def test_explicit_account_reads_retain_selected_credentials(module):
    name = module.__name__.rsplit(".", 1)[-1]
    config = {"api_key": "synthetic", "secret_key": "synthetic", "api_secret": "synthetic"}
    account = BrokerAccountConfig("fixture", "fixture-user", name, "Fixture", config)
    assert module._configured(account)
    assert module._config(account) == config


def test_unscoped_portfolio_helpers_never_dispatch():
    from src.tools import portfolio

    with (
        patch.object(portfolio, "_collect_broker") as collect,
        patch.object(portfolio, "alpaca_tool") as sdk,
    ):
        result = portfolio.get_portfolio_summary()
        assert result["errors"][0]["error"] == "AUTHENTICATED_ACCOUNT_REQUIRED"
        assert result["total_market_value_usd"] is None
        assert portfolio.get_account_info("alpaca")["error"] == "AUTHENTICATED_ACCOUNT_REQUIRED"
        assert portfolio.get_trade_history("alpaca")[0]["error"] == "AUTHENTICATED_ACCOUNT_REQUIRED"
        collect.assert_not_called()
        assert not sdk.mock_calls
