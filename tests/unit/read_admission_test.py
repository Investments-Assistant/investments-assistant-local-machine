"""Read admission remains occupied after caller cancellation or timeout."""

import json
from types import SimpleNamespace
import asyncio
from threading import Event
from unittest.mock import AsyncMock
from concurrent.futures import ThreadPoolExecutor

import pytest

from src.web import routes
from src.tools import dispatcher
from src.operations.workloads import WorkPool

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def isolated_authority_lookup(monkeypatch):
    # Exercise production admission without accessing a real session/database.
    monkeypatch.setattr("src.security.sessions.check_tool_authority", AsyncMock())


async def test_cancelled_market_read_rejects_excess_work(monkeypatch):
    pool = WorkPool(1, "MARKET_READ")
    monkeypatch.setattr(dispatcher, "market_read_work", pool, raising=False)
    entered, release = Event(), Event()
    calls = []

    def blocked(inp):
        calls.append(inp)
        entered.set()
        assert release.wait(5)
        return {"value": 1}

    monkeypatch.setitem(dispatcher._SYNC_DISPATCH, "get_stock_data", blocked)
    first = asyncio.create_task(dispatcher.dispatch_tool("get_stock_data", {"symbol": "fixture"}))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        result = json.loads(await asyncio.wait_for(dispatcher.dispatch_tool("get_stock_data", {}), .2))
        assert result["error"] == "MARKET_READ_BUSY"
        assert result["available"] is False
        assert len(calls) == 1
    finally:
        release.set()
        await asyncio.gather(first, return_exceptions=True)


async def test_read_timeout_keeps_capacity_and_owner_context(monkeypatch):
    pool = WorkPool(1, "BROKER_QUERY")
    monkeypatch.setattr(dispatcher, "broker_query_work", pool, raising=False)
    monkeypatch.setattr(dispatcher, "_READ_TIMEOUT_SECONDS", .03, raising=False)
    monkeypatch.setattr(dispatcher, "_resolve_single_account", AsyncMock(return_value=(object(), None)))
    entered, release = Event(), Event()
    owners = []

    def blocked(**kwargs):
        owners.append(dispatcher._tool_user_id.get())
        entered.set()
        assert release.wait(5)
        return {"available": True}

    monkeypatch.setattr(dispatcher, "get_account_info", blocked)
    try:
        with dispatcher.tool_context("fixture-session", "fixture-owner"):
            result = json.loads(await asyncio.wait_for(
                dispatcher.dispatch_tool("get_account_info", {"broker": "ibkr"}), .2,
            ))
            assert result["error"] == "TOOL_TIMEOUT"
            assert result["available"] is False
            result = json.loads(await dispatcher.dispatch_tool("get_account_info", {"broker": "ibkr"}))
        assert result["error"] == "BROKER_QUERY_BUSY"
        assert owners == ["fixture-owner"]
    finally:
        release.set()


async def test_portfolio_http_shares_broker_read_capacity(monkeypatch):
    pool = WorkPool(1, "BROKER_QUERY")
    monkeypatch.setattr(dispatcher, "broker_query_work", pool, raising=False)
    monkeypatch.setattr(routes, "broker_query_work", pool, raising=False)
    monkeypatch.setattr(
        routes, "require_authenticated", AsyncMock(return_value=SimpleNamespace(user_id="fixture-owner")),
    )
    monkeypatch.setattr(routes, "ensure_broker_vault", lambda: None)
    monkeypatch.setattr(routes, "load_user_broker_accounts", AsyncMock(return_value=[]))
    entered, release = Event(), Event()

    def blocked(inp):
        entered.set()
        assert release.wait(5)

    first = asyncio.create_task(pool.arun(blocked, {}))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        with pytest.raises(routes.HTTPException) as failure:
            await routes.portfolio_snapshot(SimpleNamespace())
        assert failure.value.status_code == 503
        assert failure.value.detail == "BROKER_QUERY_BUSY"
    finally:
        release.set()
        await first


async def test_dispatch_error_does_not_disclose_provider_exception(monkeypatch, caplog):
    secret = "fixture-token-123 https://example.test/?token=fixture-token-123\naccount=fixture-account-789"
    monkeypatch.setattr(dispatcher, "_dispatch", AsyncMock(side_effect=RuntimeError(secret)))
    result = await dispatcher.dispatch_tool("get_stock_data", {})
    assert "fixture-token-123" not in result + caplog.text
    assert "fixture-account-789" not in result + caplog.text
    assert json.loads(result)["error"] == "TOOL_UNAVAILABLE"


async def test_vault_error_does_not_disclose_account_or_secret(monkeypatch, caplog):
    monkeypatch.setattr(dispatcher, "load_user_broker_accounts", AsyncMock(
        side_effect=dispatcher.BrokerVaultUnavailable("fixture-secret-123 account=fixture-account-789"),
    ))
    with dispatcher.tool_context("fixture-session", "fixture-owner"):
        result = await dispatcher._dispatch_broker_read("get_portfolio_summary", {})
    assert result["error"] == "BROKER_VAULT_UNAVAILABLE"
    assert "fixture-secret-123" not in json.dumps(result) + caplog.text
    assert "fixture-account-789" not in json.dumps(result) + caplog.text


async def test_dedicated_read_workers_do_not_wait_for_shared_executor():
    release, entered = Event(), Event()
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1)
    loop.set_default_executor(executor)
    pool = WorkPool(1, "READ_FIXTURE", dedicated=True)

    def occupy_shared_worker():
        entered.set()
        assert release.wait(5)

    blocked = loop.run_in_executor(None, occupy_shared_worker)
    try:
        while not entered.is_set():
            await asyncio.sleep(.001)
        assert await asyncio.wait_for(pool.arun(lambda: "read completed"), .2) == "read completed"
    finally:
        release.set()
        await blocked
        pool._executor.shutdown(wait=True)


async def test_scheduled_market_refresh_shares_admission(monkeypatch):
    from src.scheduler import jobs

    pool = WorkPool(1, "MARKET_READ")
    monkeypatch.setattr(jobs, "market_read_work", pool)
    monkeypatch.setattr(jobs, "get_market_overview", lambda: pytest.fail("Rejected read must not run"))
    monkeypatch.setattr(jobs, "search_market_news", lambda *a, **k: pytest.fail("Rejected read must not run"))
    previous = {"timestamp": "fixture-previous"}
    monkeypatch.setattr(jobs, "_latest_snapshot", previous)
    entered, release = Event(), Event()

    def block():
        entered.set()
        assert release.wait(5)

    first = asyncio.create_task(pool.arun(block))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        await jobs._refresh_market_data()
        assert jobs.get_latest_snapshot() == previous
    finally:
        release.set()
        await first


@pytest.mark.parametrize("revocation", ["session", "owner", "account", "config"])
async def test_portfolio_does_not_publish_after_mid_read_revocation(monkeypatch, revocation):
    from src.tools.broker_accounts import BrokerAccountConfig

    principal = SimpleNamespace(user_id="fixture-owner")
    account = BrokerAccountConfig("fixture-id", "fixture-owner", "alpaca", "fixture", {})
    auth = AsyncMock(
        side_effect=[principal, routes.HTTPException(status_code=401)] if revocation == "session" else None,
    )
    if revocation != "session":
        auth.return_value = principal
    if revocation == "owner":
        auth.side_effect = [principal, SimpleNamespace(user_id="different-owner")]
    monkeypatch.setattr(routes, "require_authenticated", auth)
    monkeypatch.setattr(routes, "ensure_broker_vault", lambda: None)
    accounts = AsyncMock(side_effect=[[account], []] if revocation == "account" else None)
    if revocation != "account":
        accounts.return_value = [account]
    if revocation == "config":
        changed = BrokerAccountConfig(
            account.id, account.user_id, account.broker, account.display_name, {"paper": False},
        )
        accounts.side_effect = [[account], [changed]]
    monkeypatch.setattr(routes, "load_user_broker_accounts", accounts)
    entered, release = Event(), Event()

    def private_read(**kwargs):
        entered.set()
        assert release.wait(5)
        return {"positions": [], "accounts": [], "errors": []}

    monkeypatch.setattr(routes, "get_portfolio_summary", private_read)
    task = asyncio.create_task(routes.portfolio_snapshot(SimpleNamespace()))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        release.set()  # The mocked revocation is observed after native work returns.
        with pytest.raises(routes.HTTPException) as denied:
            await task
        assert denied.value.status_code == (401 if revocation in {"session", "owner"} else 503)
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
