"""Bounded read-only IBKR callback window, separate from order authority.

The caller owns the SDK connection and its worker event loop. Snapshot completion
is not proof of complete execution history or delivery of every late commission.
"""

from datetime import UTC, datetime
import threading
from contextlib import contextmanager

from src.execution.policy import PolicyDenied
from src.execution.broker_observations import OBSERVATION


class CallbackWindow:
    def __init__(self, actual_account, *, capacity=1000):
        if type(capacity) is not int or not 1 <= capacity <= 1000:
            raise ValueError("Invalid callback capacity")
        self.actual_account = actual_account
        self.capacity = capacity
        self.observations = []
        self.failures = set()
        self._owner_thread = None
        self._attached = []

    def append(self, fields):
        if fields["actual_account"] != self.actual_account:
            return
        if len(self.observations) >= self.capacity:
            self.failures.add("BROKER_CALLBACK_CAPACITY")
            return
        try:
            self.observations.append(OBSERVATION.validate_python(fields))
        except ValueError:
            self.failures.add("INVALID_BROKER_CALLBACK")

    def execution(self, trade, fill):
        try:
            execution, contract = fill.execution, fill.contract
            self.append(
                dict(
                    kind="execution",
                    actual_account=execution.acctNumber,
                    event_id=execution.execId,
                    observed_at=datetime.now(UTC),
                    con_id=contract.conId,
                    currency=contract.currency,
                    security_type=getattr(contract, "secType", None),
                    multiplier=getattr(contract, "multiplier", None)
                    or ("1" if getattr(contract, "secType", None) == "STK" else None),
                    client_id=execution.clientId,
                    order_id=execution.orderId,
                    permanent_id=execution.permId,
                    side=execution.side,
                    quantity=str(execution.shares),
                    price=str(execution.price),
                    executed_at=execution.time,
                )
            )
        except (AttributeError, TypeError, ValueError):
            self.failures.add("INVALID_BROKER_CALLBACK")

    def commission(self, trade, fill, report):
        try:
            if report.execId != fill.execution.execId:
                self.failures.add("COMMISSION_EXECUTION_MISMATCH")
                return
            self.append(
                dict(
                    kind="commission",
                    actual_account=fill.execution.acctNumber,
                    event_id=report.execId,
                    observed_at=datetime.now(UTC),
                    amount=str(report.commission),
                    currency=report.currency,
                )
            )
        except (AttributeError, TypeError, ValueError):
            self.failures.add("INVALID_BROKER_CALLBACK")

    def order_status(self, trade):
        try:
            order, status = trade.order, trade.orderStatus
            self.append(
                dict(
                    kind="order_status",
                    actual_account=order.account,
                    event_id=f"{order.clientId}:{order.orderId}:{order.permId}",
                    observed_at=datetime.now(UTC),
                    client_id=order.clientId,
                    order_id=order.orderId,
                    permanent_id=order.permId,
                    status=status.status,
                    filled=str(status.filled),
                    remaining=str(status.remaining),
                )
            )
        except (AttributeError, TypeError, ValueError):
            self.failures.add("INVALID_BROKER_CALLBACK")

    def disconnected(self):
        self.failures.add("BROKER_DISCONNECTED_DURING_SNAPSHOT")

    def connection_message(self, request_id, code, message, contract=None):
        # TWS-to-server loss/restoration can leave the local API socket open.
        # Even a "data maintained" restoration cannot erase this capture's gap.
        # Never persist provider text, account identifiers or contract payloads.
        if type(code) is int and code in {1100, 1101, 1102, 1300}:
            self.failures.add("BROKER_UPSTREAM_CONNECTION_CHANGED")

    @contextmanager
    def subscribed(self, ib):
        """Keep callbacks attached; all capture/drain work belongs to this SDK thread."""
        if self._owner_thread is not None:
            raise RuntimeError("BROKER_CALLBACK_ALREADY_SUBSCRIBED")
        self._owner_thread = threading.get_ident()
        subscriptions = [
            (ib.execDetailsEvent, self.execution),
            (ib.commissionReportEvent, self.commission),
            (ib.orderStatusEvent, self.order_status),
            (ib.disconnectedEvent, self.disconnected),
            (ib.errorEvent, self.connection_message),
        ]
        try:
            for event, handler in subscriptions:
                event += handler
                self._attached.append((event, handler))
            yield self
        finally:
            self.stop_capture()
            self._owner_thread = None

    def _require_owner(self):
        if self._owner_thread != threading.get_ident():
            raise RuntimeError("BROKER_CALLBACK_OWNER_REQUIRED")

    def stop_capture(self):
        """Detach on the owner before a final drain; cleanup is idempotent."""
        self._require_owner()
        while self._attached:
            event, handler = self._attached.pop()
            event -= handler

    def drain(self, *, final=False):
        """Return detached immutable observations; overflow remains a permanent gap."""
        self._require_owner()
        if final:
            self.stop_capture()
        observations, self.observations = self.observations, []
        return {"observations": observations, "failures": sorted(self.failures),
                "status": "partial" if self.failures else "observed",
                "capture_active": bool(self._attached), "execution_authority": "none"}

    def request_snapshot(self, ib, execution_filter):
        """Initial requests within an existing callback subscription; never reconnect."""
        self._require_owner()
        request_finished = False
        try:
            # reqAllOpenOrders does not bind or grant ownership of another client's orders.
            for trade in ib.reqAllOpenOrders():
                self.order_status(trade)
            for fill in ib.reqExecutions(execution_filter):
                self.execution(None, fill)
                report = fill.commissionReport
                # SDK's default empty report is missing evidence, not a zero fee.
                if report.execId:
                    self.commission(None, fill, report)
            from src.tools.brokers.ibkr_balances import collect_balances

            self.append(collect_balances(ib, self.actual_account))
            request_finished = True
        except Exception:
            # Preserve already-delivered facts but never publish snapshot success.
            self.failures.add("BROKER_SNAPSHOT_REQUEST_FAILED")
        return request_finished

    def collect(self, ib, execution_filter):
        with self.subscribed(ib):
            request_finished = self.request_snapshot(ib, execution_filter)
            result = self.drain(final=True)
        return result | {
            "request_finished": request_finished,
            "coverage": "available_execution_window_and_open_orders_not_complete_history",
            "late_commissions_complete": False,
        }


def collect_ibkr_observations(account):
    """Explicit bounded snapshot on a worker-owned SDK session; no automatic stream."""
    from src.tools.brokers.ibkr_session import ReadSessionWorker, route_read

    def collect(ib, actual):
        from ib_insync import ExecutionFilter

        if not ib.isConnected():
            raise PolicyDenied("BROKER_NOT_CONNECTED")
        return CallbackWindow(actual).collect(ib, ExecutionFilter(acctCode=actual))

    handled, result = route_read(account, collect)
    if handled:
        return result
    worker = ReadSessionWorker(account)
    try:
        worker.start()
        return worker.call(collect, timeout=30)
    finally:
        if not worker.close(timeout=10):
            # Native work cannot be killed; its connection remains owned/locked.
            raise RuntimeError("IBKR_SESSION_CLEANUP_PENDING")
