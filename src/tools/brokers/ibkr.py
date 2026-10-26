"""Explicit-account read-only IBKR adapter via the maintained ib_async package.

The worker owns its event loop and always disconnects. TWS Read-Only API remains
required: the native handshake has no read-only wire flag. Live/paper writes
remain unavailable pending independent account and durable broker acceptance.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
import hashlib
import logging
from datetime import UTC, datetime
import threading
from contextlib import suppress, contextmanager

from src.execution.external import disabled_external_write
from src.tools.broker_accounts import BrokerAccountConfig

_connection_lock = threading.Lock()


def _config(account: BrokerAccountConfig | None) -> dict:
    if account is None or not account.id or not account.user_id or account.broker != "ibkr":
        raise ValueError("AUTHENTICATED_ACCOUNT_REQUIRED")
    config = account.config
    if config.get("enabled") is not True or config.get("read_authorized") is not True:
        raise ValueError("IBKR_READ_CONSENT_REQUIRED")
    if not config.get("broker_account_id") or config.get("environment") not in {"paper", "live"}:
        raise ValueError("EXPLICIT_BROKER_ACCOUNT_AND_ENVIRONMENT_REQUIRED")
    if int(config.get("client_id", 0)) <= 0:
        raise ValueError("DEDICATED_NONZERO_CLIENT_ID_REQUIRED")
    return config


def _account_ref(actual: str) -> str:
    return "masked-" + hashlib.sha256(actual.encode()).hexdigest()[:12]


def require_selected_account(ib, actual: str):
    """Broad SDK reads are allowed only for a currently sole managed account.

    Output filtering does not limit the underlying wire request. Once the owned
    session has observed a different scope, a later matching list cannot restore
    its authority. Account identifiers never appear in the denial reason.
    """
    if getattr(ib, "_ia_connection_gap", False) is True:
        raise RuntimeError("IBKR_SESSION_NOT_READY")
    if (
        getattr(ib, "_ia_account_scope_invalid", False) is True
        or getattr(ib, "_ia_selected_account", actual) != actual
        or ib.managedAccounts() != [actual]
    ):
        ib._ia_account_scope_invalid = True
        raise ValueError("IBKR_SOLE_MANAGED_ACCOUNT_REQUIRED")


def _scope_owned_reads(ib, actual):
    # SDK wire/error diagnostics contain account and financial payloads. Silence
    # only this freshly owned instance; never change shared SDK/global loggers.
    private_logger = logging.Logger("investments-assistant.ibkr-private")
    private_logger.addHandler(logging.NullHandler())
    private_logger.propagate = False
    ib._logger = ib.client._logger = ib.wrapper._logger = ib.client.decoder.logger = private_logger
    ib._ia_selected_account = actual
    ib._ia_account_scope_invalid = False
    ib._ia_account_scope_established = False
    ib._ia_connection_gap = False
    # The stock handler silently starts an unfiltered summary request on 1102.
    # This bounded adapter performs only explicit requests, never auto-refreshes.
    ib.errorEvent -= ib._onError
    original_accounts = ib.wrapper.managedAccounts

    def stop_established():
        if ib._ia_account_scope_established:
            # Callback exceptions would expose arguments through Decoder's log.
            try:
                ib.disconnect()
            except Exception:
                # Sticky denial remains; the owner still performs cleanup.
                with suppress(Exception):
                    ib.client.disconnect()

    def managed_accounts(accounts):
        original_accounts(accounts)
        if ib.managedAccounts() != [actual]:
            ib._ia_account_scope_invalid = True
            stop_established()

    ib.wrapper.managedAccounts = managed_accounts

    def connection_health(_req_id, code, _text, _contract):
        if code in {1100, 1101, 1102, 1300}:
            ib._ia_connection_gap = True
            # Block new financial reads/results while the bounded callback owner
            # retains its final partial batch and numeric gap, then closes. A
            # managed-account scope change still disconnects immediately above.

    ib.errorEvent += connection_health

    def guarded_request(original):
        def request(*args, **kwargs):
            require_selected_account(ib, actual)
            return original(*args, **kwargs)
        return request

    for name in ("reqPositions", "reqAllOpenOrders", "reqAccountSummary", "reqExecutions"):
        setattr(ib.client, name, guarded_request(getattr(ib.client, name)))
    original_updates = ib.client.reqAccountUpdates

    def account_updates(subscribe, acctCode):
        # Cleanup must remain possible after authority is lost.
        if subscribe is not False:
            require_selected_account(ib, actual)
            if subscribe is not True or acctCode != actual:
                raise ValueError("IBKR_SOLE_MANAGED_ACCOUNT_REQUIRED")
        return original_updates(subscribe, acctCode)

    ib.client.reqAccountUpdates = account_updates
    return connection_health


async def _connect_selected(ib, config, actual):
    """Metadata handshake, then one selected primary account download only."""
    client_id = int(config["client_id"])
    ib.wrapper.clientId = client_id
    await ib.client.connectAsync(
        config.get("host", "127.0.0.1"), int(config.get("port", 4002)), client_id, timeout=10,
    )
    if ib.client.getAccounts() != [actual]:
        ib._ia_account_scope_invalid = True
    require_selected_account(ib, actual)
    wrapper = ib.wrapper
    original_end = wrapper.accountDownloadEnd
    had_override = "accountDownloadEnd" in vars(wrapper)

    def account_download_end(account):
        if account != actual:
            ib._ia_account_scope_invalid = True
            wrapper._endReq(
                "accountValues", ValueError("IBKR_SOLE_MANAGED_ACCOUNT_REQUIRED"), success=False,
            )
            return
        try:
            original_end(account)
        except Exception:
            ib._ia_account_scope_invalid = True
            wrapper._endReq(
                "accountValues", ValueError("IBKR_SOLE_MANAGED_ACCOUNT_REQUIRED"), success=False,
            )

    wrapper.accountDownloadEnd = account_download_end
    try:
        await ib.reqAccountUpdatesAsync(actual)
    finally:
        if had_override:
            wrapper.accountDownloadEnd = original_end
        else:
            del wrapper.accountDownloadEnd
    require_selected_account(ib, actual)
    if not ib.isConnected():
        raise RuntimeError("IBKR_SESSION_NOT_READY")
    ib._ia_account_scope_established = True
    ib.connectedEvent.emit()


@contextmanager
def _connection(account: BrokerAccountConfig | None):
    config = _config(account)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError("IBKR_SYNC_ADAPTER_REQUIRES_WORKER_THREAD")
    if not _connection_lock.acquire(timeout=10):
        raise RuntimeError("IBKR_CLIENT_BUSY")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    ib = None
    health_handler = None
    try:
        from ib_async import IB

        ib = IB()
        ib.RequestTimeout = 10
        ib.RaiseRequestErrors = True
        actual = config["broker_account_id"]
        health_handler = _scope_owned_reads(ib, actual)
        # IB.connect/connectAsync performs all-account position/execution/Multi
        # warmups before its caller can validate membership. The lower-level
        # metadata handshake and selected download share this one 10s budget.
        ib._run(_connect_selected(ib, config, actual))
        yield ib, actual
    finally:
        try:
            if ib is not None:
                try:
                    ib.disconnect()
                finally:
                    if health_handler is not None:
                        ib.errorEvent -= health_handler
        finally:
            loop.close()
            asyncio.set_event_loop(None)
            _connection_lock.release()


def _error(exc):
    # Provider exception text can contain account IDs or connection credentials.
    allowed = {
        "AUTHENTICATED_ACCOUNT_REQUIRED",
        "IBKR_READ_CONSENT_REQUIRED",
        "EXPLICIT_BROKER_ACCOUNT_AND_ENVIRONMENT_REQUIRED",
        "DEDICATED_NONZERO_CLIENT_ID_REQUIRED",
        "BROKER_ACCOUNT_NOT_MANAGED",
        "IBKR_SOLE_MANAGED_ACCOUNT_REQUIRED",
        "IBKR_CLIENT_BUSY",
        "IBKR_SYNC_ADAPTER_REQUIRES_WORKER_THREAD",
        "INCOMPLETE_CONTRACT",
        "AMBIGUOUS_CONTRACT",
        "CONTRACT_MISMATCH",
        "AMBIGUOUS_CONTRACT_DETAILS",
        "CONTRACT_PRECISION_UNAVAILABLE",
        "IBKR_SESSION_CONFIGURATION_CHANGED",
        "IBKR_SESSION_STOPPING",
        "IBKR_SESSION_NOT_READY",
        "IBKR_READ_QUEUE_FULL",
    }
    code = str(exc) if str(exc) in allowed else "IBKR_READ_UNAVAILABLE"
    return {"broker": "ibkr", "available": False, "error": code}


def summarize_account(values, actual: str) -> dict:
    """Never flatten accounts or currencies. Base-currency facts must be explicit."""
    rows = [value for value in values if value.account == actual]
    by_currency: dict[str, dict] = {}
    base = next((row.value for row in rows if row.tag == "Currency" and len(row.value) == 3), None)
    for row in rows:
        by_currency.setdefault(row.currency or "unspecified", {})[row.tag] = row.value
    metrics = by_currency.get(base, {}) if base else {}
    return {
        "broker": "ibkr",
        "broker_account_ref": _account_ref(actual),
        "currency": base,
        "values_by_currency": by_currency,
        "net_liquidation": metrics.get("NetLiquidation"),
        "cash_balance": metrics.get("CashBalance"),
        "buying_power": metrics.get("BuyingPower"),
        "available_funds": metrics.get("AvailableFunds"),
        "unrealized_pnl": metrics.get("UnrealizedPnL"),
        "realized_pnl": metrics.get("RealizedPnL"),
        "as_of": datetime.now(UTC).isoformat(),
    }


def _read(account, operation):
    _config(account)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError("IBKR_SYNC_ADAPTER_REQUIRES_WORKER_THREAD")
    from src.tools.brokers.ibkr_session import route_read

    def scoped_operation(ib, actual):
        require_selected_account(ib, actual)
        result = operation(ib, actual)
        require_selected_account(ib, actual)
        return result

    handled, result = route_read(account, scoped_operation)
    if handled:
        return result
    with _connection(account) as (ib, actual):
        return scoped_operation(ib, actual)


def get_ibkr_account(account: BrokerAccountConfig | None = None) -> dict:
    try:
        def operation(ib, actual):
            result = summarize_account(ib.accountSummary(account=actual), actual)
            result.update(
                declared_environment=account.config["environment"],
                verified_environment=None,
                environment_verification="operator_configuration_only",
                managed_account_match=True,
                execution_permission="read_only_external_writes_disabled",
            )
            return result
        return _read(account, operation)
    except Exception as exc:
        return _error(exc)


def get_ibkr_positions(account: BrokerAccountConfig | None = None) -> list[dict]:
    try:
        def operation(ib, actual):
            if getattr(ib, "_ia_primary_portfolio_stale", False) is True:
                raise RuntimeError("IBKR_SESSION_NOT_READY")
            return [
                {
                    "symbol": item.contract.symbol,
                    "con_id": item.contract.conId,
                    "security_type": item.contract.secType,
                    "exchange": item.contract.exchange,
                    "primary_exchange": item.contract.primaryExchange,
                    "currency": item.contract.currency,
                    "qty": str(item.position),
                    "avg_cost": str(item.averageCost),
                    "market_price": str(item.marketPrice),
                    "market_value": str(item.marketValue),
                    "unrealized_pnl": str(item.unrealizedPNL),
                    "realized_pnl": str(item.realizedPNL),
                    "broker_account_ref": _account_ref(actual),
                    "as_of": datetime.now(UTC).isoformat(),
                }
                for item in ib.portfolio(account=actual)
                if item.account == actual
            ]
        return _read(account, operation)
    except Exception as exc:
        return [_error(exc)]


def get_ibkr_orders(account: BrokerAccountConfig | None = None) -> list[dict]:
    try:
        def operation(ib, actual):
            # Explicit snapshot request; do not present a fresh client's empty cache as history.
            trades = ib.reqAllOpenOrders()
            return [
                {
                    "order_id": trade.order.orderId,
                    "client_id": trade.order.clientId,
                    "permanent_id": trade.order.permId,
                    "symbol": trade.contract.symbol,
                    "con_id": trade.contract.conId,
                    "currency": trade.contract.currency,
                    "action": trade.order.action,
                    "qty": str(trade.order.totalQuantity),
                    "order_type": trade.order.orderType,
                    "limit_price": str(trade.order.lmtPrice),
                    "status": trade.orderStatus.status,
                    "filled": str(trade.orderStatus.filled),
                    "avg_fill_price": str(trade.orderStatus.avgFillPrice),
                    "scope": "open_order_snapshot_not_execution_history",
                    "ownership": "external_or_unknown",
                }
                for trade in trades
                if trade.order.account == actual
            ]
        return _read(account, operation)
    except Exception as exc:
        return [_error(exc)]


def qualify_stock(ib, *, symbol: str, exchange: str, currency: str) -> dict:
    """Explicit stock contract resolution; a symbol or port never selects a market."""
    from ib_async import Stock

    if not symbol or not exchange or len(currency) != 3:
        raise ValueError("INCOMPLETE_CONTRACT")
    contracts = ib.qualifyContracts(Stock(symbol, exchange, currency))
    if len(contracts) != 1 or not contracts[0].conId:
        raise ValueError("AMBIGUOUS_CONTRACT")
    contract = contracts[0]
    if contract.currency != currency or contract.secType != "STK":
        raise ValueError("CONTRACT_MISMATCH")
    details = ib.reqContractDetails(contract)
    if len(details) != 1:
        raise ValueError("AMBIGUOUS_CONTRACT_DETAILS")
    detail = details[0]
    tick = Decimal(str(detail.minTick))
    lot = Decimal(str(getattr(detail, "minSize", 0)))
    if not tick.is_finite() or not lot.is_finite() or tick <= 0 or lot <= 0:
        raise ValueError("CONTRACT_PRECISION_UNAVAILABLE")
    return {
        "con_id": contract.conId,
        "symbol": contract.symbol,
        "security_type": contract.secType,
        "exchange": exchange,
        "primary_exchange": contract.primaryExchange,
        "currency": currency,
        "tick": str(tick),
        "lot": str(lot),
        "multiplier": contract.multiplier or "1",
    }


def resolve_ibkr_contract(
    symbol: str, exchange: str, currency: str, account: BrokerAccountConfig | None = None
) -> dict:
    try:
        def operation(ib, actual):
            return qualify_stock(ib, symbol=symbol, exchange=exchange, currency=currency)
        return _read(account, operation)
    except Exception as exc:
        return _error(exc)


@disabled_external_write
def submit_ibkr_order(
    symbol,
    side,
    quantity,
    order_type="market",
    limit_price=None,
    stop_price=None,
    asset_type=None,
    option_expiry=None,
    option_strike=None,
    option_right=None,
    account=None,
) -> dict:
    return {"blocked": True, "success": False, "error": "EXTERNAL_EXECUTION_NOT_AUTHORIZED"}


@disabled_external_write
def cancel_ibkr_order(order_id, account=None) -> dict:
    return {"blocked": True, "success": False, "error": "EXTERNAL_CANCELLATION_NOT_AUTHORIZED"}
