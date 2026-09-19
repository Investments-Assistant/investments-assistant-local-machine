"""Bounded read-only IBKR callback window, separate from order authority.

The caller owns the SDK connection and its worker event loop. Snapshot completion
is not proof of complete execution history or delivery of every late commission.
"""

from datetime import UTC, datetime

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

    def collect(self, ib, execution_filter):
        subscriptions = [
            (ib.execDetailsEvent, self.execution),
            (ib.commissionReportEvent, self.commission),
            (ib.orderStatusEvent, self.order_status),
            (ib.disconnectedEvent, self.disconnected),
        ]
        attached = []
        request_finished = False
        try:
            for event, handler in subscriptions:
                event += handler
                attached.append((event, handler))
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
        finally:
            for event, handler in reversed(attached):
                event -= handler
        return {
            "observations": self.observations,
            "request_finished": request_finished,
            "status": "partial" if self.failures else "observed",
            "failures": sorted(self.failures),
            "coverage": "available_execution_window_and_open_orders_not_complete_history",
            "late_commissions_complete": False,
            "execution_authority": "none",
        }


def collect_ibkr_observations(account):
    """Internal worker function, callable only with explicit scoped read configuration."""
    from src.tools.brokers.ibkr import _connection

    with _connection(account) as (ib, actual):
        from ib_insync import ExecutionFilter

        if not ib.isConnected():
            raise PolicyDenied("BROKER_NOT_CONNECTED")
        return CallbackWindow(actual).collect(ib, ExecutionFilter(acctCode=actual))
