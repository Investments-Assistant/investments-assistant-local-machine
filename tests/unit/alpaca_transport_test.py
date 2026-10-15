"""Installed Alpaca SDK contract with a fake session; never contacts a provider."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from requests import HTTPError, ReadTimeout

from src.tools.brokers import alpaca
from src.tools.broker_accounts import BrokerAccountConfig

pytestmark = pytest.mark.unit


def fixture_account():
    return BrokerAccountConfig("fixture", "owner", "alpaca", "Fixture", {
        "api_key": "synthetic-unused-key", "secret_key": "synthetic-unused-secret", "paper": True,
    })


@pytest.fixture
def fake_transport(monkeypatch):
    # Install before constructing the real SDK client. Any request in construction
    # would also hit this mock rather than the network.
    request = Mock()
    monkeypatch.setattr("requests.sessions.Session.request", request)
    return request


def test_installed_sdk_read_preserves_session_headers_and_adds_transport_timeouts(fake_transport):
    client = alpaca._get_client(fixture_account())
    response = Mock(text='{"fixture": true}')
    response.json.return_value = {"fixture": True}
    fake_transport.return_value = response

    assert client.get("/synthetic-contract") == {"fixture": True}

    method, url = fake_transport.call_args.args
    options = fake_transport.call_args.kwargs
    assert method == "GET"
    assert url == "https://paper-api.alpaca.markets/v2/synthetic-contract"
    assert options["timeout"] == (5, 10)
    assert options["headers"]["APCA-API-KEY-ID"] == "synthetic-unused-key"
    assert options["headers"]["APCA-API-SECRET-KEY"] == "synthetic-unused-secret"
    assert options["allow_redirects"] is False
    assert "verify" not in options or options["verify"] is True
    assert fake_transport.call_count == 1
    client._session.close()


def test_rate_limit_has_one_attempt_and_no_retry_sleep(fake_transport, monkeypatch, caplog):
    message = "synthetic-private-provider-token synthetic-account-7281\nFORGED_PROVIDER_LOG"
    response = Mock(status_code=429, text=json.dumps({"code": 429, "message": message}))
    response.raise_for_status.side_effect = HTTPError(message, response=response)
    fake_transport.return_value = response
    sleep = Mock(side_effect=AssertionError("Read must not sleep or retry"))
    monkeypatch.setattr("alpaca.common.rest.time.sleep", sleep)

    result = alpaca.get_alpaca_positions(account=fixture_account())

    assert fake_transport.call_count == 1
    sleep.assert_not_called()
    assert result[0]["error"] == "ALPACA_POSITIONS_UNAVAILABLE"
    assert result[0]["available"] is False
    assert "synthetic-private-provider-token" not in json.dumps(result) + caplog.text
    assert "synthetic-account-7281" not in json.dumps(result) + caplog.text
    assert "FORGED_PROVIDER_LOG" not in json.dumps(result) + caplog.text


def test_installed_sdk_position_and_order_reads_keep_response_contract(fake_transport):
    client = alpaca._get_client(fixture_account())
    response = Mock(text="[]")
    response.json.return_value = []
    fake_transport.return_value = response

    assert client.get_all_positions() == []
    assert client.get_orders() == []
    assert fake_transport.call_count == 2
    assert all(call.kwargs["timeout"] == (5, 10) for call in fake_transport.call_args_list)
    assert all(call.args[0] == "GET" for call in fake_transport.call_args_list)
    client._session.close()


def test_native_read_timeout_propagates_as_safe_unavailable(fake_transport, caplog):
    fake_transport.side_effect = ReadTimeout("synthetic-private-timeout-token account=synthetic-account-72")

    result = alpaca.get_alpaca_account(account=fixture_account())

    assert result["error"] == "ALPACA_ACCOUNT_UNAVAILABLE"
    assert result["available"] is False
    assert fake_transport.call_count == 1
    assert fake_transport.call_args.kwargs["timeout"] == (5, 10)
    assert "synthetic-private-timeout-token" not in json.dumps(result) + caplog.text
    assert "synthetic-account-72" not in json.dumps(result) + caplog.text


@pytest.mark.parametrize("function,method", [
    ("get_alpaca_account", "get_account"),
    ("get_alpaca_positions", "get_all_positions"),
    ("get_alpaca_orders", "get_orders"),
])
@pytest.mark.parametrize("failed", [False, True])
def test_short_lived_read_session_closes_after_success_or_failure(monkeypatch, function, method, failed):
    client = Mock()
    if failed:
        getattr(client, method).side_effect = ReadTimeout("synthetic-private-read-token")
    elif function == "get_alpaca_account":
        client.get_account.return_value = SimpleNamespace(
            status="ACTIVE", cash="100", buying_power="100", portfolio_value="100",
            equity="100", daytrade_count=0, pattern_day_trader=False,
        )
    else:
        getattr(client, method).return_value = []
    monkeypatch.setattr(alpaca, "_get_client", Mock(return_value=client))

    result = getattr(alpaca, function)(account=fixture_account())

    client._session.close.assert_called_once_with()
    if failed:
        row = result[0] if isinstance(result, list) else result
        assert row["available"] is False
        assert row["error"].endswith("_UNAVAILABLE")
    else:
        assert result == [] if isinstance(result, list) else result["cash"] == 100


@pytest.mark.parametrize("construction_failure", [False, True])
def test_cleanup_cannot_replace_original_safe_failure(monkeypatch, caplog, construction_failure):
    client = Mock()
    client.get_account.side_effect = ReadTimeout("synthetic-private-read-token")
    client._session.close.side_effect = RuntimeError("synthetic-private-close-token\nFORGED_CLOSE_LOG")
    factory = Mock(return_value=client)
    if construction_failure:
        factory.side_effect = RuntimeError("synthetic-private-constructor-token")
    monkeypatch.setattr(alpaca, "_get_client", factory)

    result = alpaca.get_alpaca_account(account=fixture_account())

    assert result["error"] == "ALPACA_ACCOUNT_UNAVAILABLE"
    assert result["available"] is False
    if construction_failure:
        client._session.close.assert_not_called()
    else:
        client._session.close.assert_called_once_with()
        assert "ALPACA_TRANSPORT_CLEANUP_UNAVAILABLE" in caplog.text
    captured = json.dumps(result) + caplog.text
    assert "synthetic-private" not in captured
    assert "FORGED_CLOSE_LOG" not in captured
