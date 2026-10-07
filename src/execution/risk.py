"""Marked simulator account risk for both manual and autonomous new orders."""

from decimal import Decimal, InvalidOperation
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from src.execution.models import SimulatorOrder, SimulatorPosition, SimulatorInstrument
from src.execution.policy import PolicyDenied, positive
from src.execution.numeric import execution_precision


class RiskDenied(PolicyDenied):
    """Caller must commit the recorded halt, then return the denial to its client."""


@execution_precision
async def enforce_account_risk(session, account, *, now=None):
    """Account lock is held by the caller; no model or external network is involved.

    loss_limit caps both marked loss versus initial synthetic capital and loss
    since the first UTC-day observation, excluding verified synthetic cash flows.
    Missing valuation is a durable halt, never a fabricated zero mark.
    """
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise PolicyDenied("INVALID_RISK_TIME")
    now = now.astimezone(UTC)
    if account.halted:
        raise PolicyDenied("OPERATOR_HALTED")

    async def breach(reason):
        from src.execution.service import halt

        await halt(session, user_id=account.user_id, account_id=account.id, reason=reason)
        raise RiskDenied(reason)

    try:
        initial_capital, loss_limit = positive(account.initial_capital), positive(account.loss_limit)
        cash = Decimal(str(account.cash))
        if not cash.is_finite():
            raise PolicyDenied("INVALID_CASH")
    except (PolicyDenied, InvalidOperation):
        await breach("RISK_BUDGET_UNAVAILABLE")

    uncertain = await session.scalar(
        select(SimulatorOrder.id)
        .where(
            SimulatorOrder.account_id == account.id,
            SimulatorOrder.status == "uncertain",
        )
        .limit(1)
    )
    if uncertain:
        await breach("RECONCILIATION_REQUIRED")
    from src.execution.reconciliation import reconcile_account

    reconciliation = await reconcile_account(session, account)
    account.mandate = dict(
        account.mandate,
        reconciliation={
            key: value for key, value in reconciliation.items() if key not in {"discrepancies", "allocation_inventory"}
        },
    )
    if reconciliation["status"] != "consistent":
        await breach("LEDGER_RECONCILIATION_" + reconciliation["status"].upper())
    rows = (
        await session.execute(
            select(SimulatorPosition, SimulatorInstrument)
            .outerjoin(
                SimulatorInstrument,
                SimulatorInstrument.id == SimulatorPosition.instrument_id,
            )
            .where(SimulatorPosition.account_id == account.id)
            .limit(1001)
        )
    ).all()
    if len(rows) > 1000:
        await breach("RISK_POSITION_CAPACITY")
    exposure, basis = Decimal(0), Decimal(0)
    position_exposure = {}
    for position, instrument in rows:
        if position.quantity == 0:
            continue
        if (
            instrument is None
            or instrument.account_id != account.id
            or instrument.as_of > now
            or now - instrument.as_of > timedelta(seconds=60)
        ):
            await breach("VALUATION_STALE")
        try:
            cost_basis = Decimal(str(position.cost_basis))
            if not cost_basis.is_finite() or cost_basis < 0:
                raise PolicyDenied("INVALID_BASIS")
            if instrument.currency == account.currency and instrument.fx_to_base != 1:
                raise PolicyDenied("INVALID_FX")
            value = (
                positive(position.quantity)
                * positive(instrument.price)
                * positive(instrument.multiplier)
                * positive(instrument.fx_to_base)
            )
        except (PolicyDenied, InvalidOperation):
            await breach("VALUATION_UNAVAILABLE")
        exposure += value
        position_exposure[instrument.id] = value
        basis += cost_basis
    pending = (await session.scalars(select(SimulatorOrder).where(
        SimulatorOrder.account_id == account.id, SimulatorOrder.reserve > 0
    ).limit(1001))).all()
    if len(pending) > 1000:
        await breach("RISK_PENDING_CAPACITY")
    reserved_by_instrument = {}
    for order in pending:
        reserved_by_instrument[order.instrument_id] = (
            reserved_by_instrument.get(order.instrument_id, Decimal(0)) + order.reserve
        )
    equity = cash + exposure
    previous = account.mandate.get("account_risk", {})
    if not isinstance(previous, dict):
        await breach("RISK_BASELINE_UNAVAILABLE")
    day = now.date().isoformat()
    try:
        if previous:
            previous_at = datetime.fromisoformat(previous["at"])
            if previous_at.tzinfo is None:
                raise ValueError("Undated baseline")
            if previous_at > now:
                await breach("CLOCK_REGRESSION")
        opening = Decimal(previous["day_open_equity"]) if previous.get("day") == day else equity
        if not opening.is_finite():
            raise ValueError("Invalid baseline")
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        if isinstance(exc, RiskDenied):
            raise
        await breach("RISK_BASELINE_UNAVAILABLE")
    net_flows = Decimal(reconciliation["net_external_flows"])
    opening_flows = Decimal(previous.get("day_open_net_flows", "0")) if previous.get("day") == day else net_flows
    daily_pnl = equity - opening - (net_flows - opening_flows)
    capital_pnl = equity - initial_capital - net_flows
    account.mandate = dict(
        account.mandate,
        account_risk=dict(
            at=now.isoformat(),
            day=day,
            day_open_equity=str(opening),
            day_open_net_flows=str(opening_flows),
            net_external_flows=str(net_flows),
            equity=str(equity),
            exposure=str(exposure),
            position_exposure={key: str(value) for key, value in sorted(position_exposure.items())},
            reserved_by_instrument={key: str(value) for key, value in sorted(reserved_by_instrument.items())},
            unrealized=str(exposure - basis),
            capital_pnl=str(capital_pnl),
            daily_pnl=str(daily_pnl),
            currency=account.currency,
            convention="Flow-adjusted UTC first observation and initial synthetic capital; fees included",
        ),
    )
    if capital_pnl <= -loss_limit or daily_pnl <= -loss_limit:
        await breach("MARKED_ACCOUNT_LOSS_LIMIT")
    from src.execution.exposure import global_limits

    try:
        position_cap, exposure_cap = global_limits(account)
    except PolicyDenied:
        await breach("GLOBAL_EXPOSURE_LIMITS_UNAVAILABLE")
    for instrument_id in position_exposure.keys() | reserved_by_instrument.keys():
        if position_exposure.get(instrument_id, 0) + reserved_by_instrument.get(instrument_id, 0) > position_cap:
            await breach("GLOBAL_POSITION_CAP")
    if exposure + account.reserved > exposure_cap:
        await breach("GLOBAL_EXPOSURE_CAP")
    return account.mandate["account_risk"]
