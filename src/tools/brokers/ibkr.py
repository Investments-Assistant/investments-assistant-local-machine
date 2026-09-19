"""Explicit-account read-only IBKR adapter via ib_insync.

The worker owns its event loop and always disconnects. Live/paper writes remain
unavailable pending independent external-account and durable broker acceptance.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
import hashlib
from datetime import UTC, datetime
import threading
from contextlib import contextmanager

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
    try:
        from ib_insync import IB

        ib = IB()
        ib.RequestTimeout = 10
        ib.RaiseRequestErrors = True
        actual = config["broker_account_id"]
        ib.connect(
            host=config.get("host", "127.0.0.1"),
            port=int(config.get("port", 4002)),
            clientId=int(config["client_id"]),
            account=actual,
            timeout=10,
            readonly=True,
            raiseSyncErrors=True,
        )
        if actual not in ib.managedAccounts():
            raise ValueError("BROKER_ACCOUNT_NOT_MANAGED")
        yield ib, actual
    finally:
        try:
            if ib is not None:
                ib.disconnect()
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
        "IBKR_CLIENT_BUSY",
        "IBKR_SYNC_ADAPTER_REQUIRES_WORKER_THREAD",
        "INCOMPLETE_CONTRACT",
        "AMBIGUOUS_CONTRACT",
        "CONTRACT_MISMATCH",
        "AMBIGUOUS_CONTRACT_DETAILS",
        "CONTRACT_PRECISION_UNAVAILABLE",
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


def get_ibkr_account(account: BrokerAccountConfig | None = None) -> dict:
    try:
        with _connection(account) as (ib, actual):
            result = summarize_account(ib.accountSummary(account=actual), actual)
            result.update(
                declared_environment=account.config["environment"],
                verified_environment=None,
                environment_verification="operator_configuration_only",
                managed_account_match=True,
                execution_permission="read_only_external_writes_disabled",
            )
            return result
    except Exception as exc:
        return _error(exc)


def get_ibkr_positions(account: BrokerAccountConfig | None = None) -> list[dict]:
    try:
        with _connection(account) as (ib, actual):
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
    except Exception as exc:
        return [_error(exc)]


def get_ibkr_orders(account: BrokerAccountConfig | None = None) -> list[dict]:
    try:
        with _connection(account) as (ib, actual):
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
    except Exception as exc:
        return [_error(exc)]


def qualify_stock(ib, *, symbol: str, exchange: str, currency: str) -> dict:
    """Explicit stock contract resolution; a symbol or port never selects a market."""
    from ib_insync import Stock

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
        with _connection(account) as (ib, _):
            return qualify_stock(ib, symbol=symbol, exchange=exchange, currency=currency)
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
