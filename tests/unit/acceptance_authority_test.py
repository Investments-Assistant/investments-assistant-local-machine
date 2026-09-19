"""Safety regression cases use actual Settings and never contact a broker."""

from unittest.mock import AsyncMock, patch

import pytest

from src.tools import dispatcher as d
from src.config import Settings


@pytest.mark.asyncio
async def test_model_cannot_approve_its_own_same_session_proposal():
    with d.tool_context("fixture-session", "fixture-user", "recommend"):
        token = d._remember_proposal({"broker": "ibkr", "symbol": "SPYL", "quantity": 6})
        with patch.object(d, "_execute_validated_trade", new_callable=AsyncMock) as submit:
            result = await d._confirm_trade({"confirmation_id": token})
            assert result["reason_code"] == "HUMAN_APPROVAL_REQUIRED"
            submit.assert_not_awaited()
    d._pending_trade_proposals.pop(token, None)


@pytest.mark.parametrize("estimate", [1, 100000, None, float("nan")])
def test_caller_estimate_never_authorizes_excess_notional(estimate):
    settings = Settings(_env_file=None, environment="production", auto_max_trade_usd=500)
    with patch.object(d, "settings", settings):
        ok, reason = d._auto_notional_ok(
            dict(
                quantity=1000, limit_price=100, estimated_notional_usd=estimate, order_type="limit"
            )
        )
    assert not ok
    assert "cap" in reason


@pytest.mark.asyncio
async def test_no_identity_cannot_use_global_broker_credentials():
    with d.tool_context("scheduler", None), patch.object(d, "get_portfolio_summary") as broker:
        result = await d._dispatch_broker_read("get_portfolio_summary", {})
        assert result["blocked"]
        broker.assert_not_called()


@pytest.mark.asyncio
async def test_model_cannot_change_mode():
    with d.tool_context("fixture-session", "fixture-user"):
        assert (await d._set_trading_mode("auto"))["blocked"]


def test_port_and_live_flag_cannot_authorize_external_writes():
    with patch.object(
        d, "settings", Settings(_env_file=None, environment="production", live_trading_enabled=True)
    ):
        assert not d._live_route_allowed("ibkr")
        assert d._route_order("ibkr", "SPYL", "buy", 6, "limit", 100, None)["blocked"]
        assert d._cancel_order({"broker": "ibkr", "order_id": "fixture"})["blocked"]


def test_explicit_database_url_cannot_fall_back_to_application_host(monkeypatch):
    url = "postgresql+asyncpg://fixture@/test_isolated?host=/tmp/fixture-socket"
    monkeypatch.setenv("DATABASE_URL", url)
    settings = Settings(
        _env_file=None, environment="production", postgres_host="must-never-connect.invalid"
    )
    assert settings.database_url == url
