"""Deterministic simulator-only mandate execution, independent of language models.

No broker imports or user-provided price/FX inputs. A caller supplies only an
approved mandate identity and a scheduled tick correlation key. Failed checks
raise PolicyDenied; callers must commit recorded risk halts before returning.
"""

from decimal import Decimal
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from src.execution.models import (
    ExecutionEvent,
    SimulatorOrder,
    SimulatorMandate,
    StrategyDecision,
    SimulatorPosition,
    SimulatorInstrument,
)
from src.execution.policy import PolicyDenied, digest, positive, preflight, order_details
from src.execution.numeric import execution_precision
from src.execution.service import halt, account_for_user, require_owned_quantity
from src.execution.mandates import MandateSpec, immutable_details

MAX_MANDATE_ROWS = 10_000


async def require_bounded_evidence(session, account, rows):
    if len(rows) > MAX_MANDATE_ROWS:
        await halt(session, user_id=account.user_id, account_id=account.id, reason="MANDATE_EVIDENCE_CAPACITY")
        raise PolicyDenied("MANDATE_EVIDENCE_CAPACITY")


@execution_precision
async def run_tick(session, *, user_id: str, account_id: str, mandate_id: str, tick_id: str, now=None):
    account = await account_for_user(session, account_id, user_id)
    now = now or datetime.now(UTC)
    if now.tzinfo is None or not tick_id or len(tick_id) > 128:
        raise PolicyDenied("INVALID_TICK")
    now = now.astimezone(UTC)
    mandate = await session.scalar(
        select(SimulatorMandate).where(
            SimulatorMandate.id == mandate_id,
            SimulatorMandate.account_id == account_id,
            SimulatorMandate.user_id == user_id,
        )
    )
    if mandate is None or mandate.status != "approved" or not mandate.approval:
        raise PolicyDenied("APPROVED_MANDATE_REQUIRED")
    if (
        mandate.details_hash != digest(immutable_details(mandate))
        or mandate.approval.get("details_hash") != mandate.details_hash
    ):
        raise PolicyDenied("MANDATE_CHANGED_AFTER_APPROVAL")
    spec = MandateSpec.model_validate(mandate.specification)
    if account.mandate.get("fixture") is not True or account.mandate.get("environment") != "simulator":
        raise PolicyDenied("SIMULATOR_FIXTURE_REQUIRED")
    if now >= spec.expires_at:
        raise PolicyDenied("MANDATE_EXPIRED")
    if account.halted:
        raise PolicyDenied("OPERATOR_HALTED")
    key = digest(dict(mandate=mandate.id, tick=tick_id))
    decision = await session.scalar(
        select(StrategyDecision).where(
            StrategyDecision.account_id == account_id,
            StrategyDecision.tick_key == key,
        )
    )
    if decision is not None:
        if (
            decision.user_id != user_id
            or decision.mandate_id != mandate_id
            or decision.evidence_hash != digest(decision.evidence)
            or decision.evidence.get("mandate_hash") != mandate.details_hash
        ):
            await halt(session, user_id=user_id, account_id=account_id, reason="STRATEGY_EVIDENCE_CONFLICT")
            raise PolicyDenied("STRATEGY_EVIDENCE_CONFLICT")
        result = dict(decision.evidence["result"], decision_id=decision.id, deduplicated=True)
        if result.get("order_id"):
            current = await session.scalar(
                select(SimulatorOrder).where(
                    SimulatorOrder.id == result["order_id"],
                    SimulatorOrder.account_id == account_id,
                    SimulatorOrder.user_id == user_id,
                    SimulatorOrder.idempotency_key == key,
                )
            )
            if current is None:
                await halt(session, user_id=user_id, account_id=account_id, reason="STRATEGY_EVIDENCE_CONFLICT")
                raise PolicyDenied("STRATEGY_EVIDENCE_CONFLICT")
            result["status"] = current.status
        return result
    old = await session.scalar(
        select(SimulatorOrder).where(SimulatorOrder.account_id == account_id, SimulatorOrder.idempotency_key == key)
    )
    if old:
        return dict(order_id=old.id, status=old.status, deduplicated=True, environment="simulator")
    # Uncertain execution requires reconciliation; a fresh key never bypasses it.
    uncertain = await session.scalar(
        select(SimulatorOrder.id)
        .where(SimulatorOrder.account_id == account_id, SimulatorOrder.status == "uncertain")
        .limit(1)
    )
    if uncertain:
        raise PolicyDenied("RECONCILIATION_REQUIRED")
    orders = (
        (
            await session.execute(
                select(SimulatorOrder)
                .where(
                    SimulatorOrder.account_id == account_id,
                    SimulatorOrder.approval.is_not(None),
                    SimulatorOrder.created_at >= now.replace(hour=0, minute=0, second=0, microsecond=0),
                )
                .order_by(SimulatorOrder.created_at, SimulatorOrder.id)
                .limit(MAX_MANDATE_ROWS + 1)
            )
        )
        .scalars()
        .all()
    )
    await require_bounded_evidence(session, account, orders)
    automatic = [o for o in orders if o.approval.get("actor") == "approved_simulator_mandate"]
    latest = await session.scalar(
        select(SimulatorOrder)
        .where(SimulatorOrder.account_id == account_id, SimulatorOrder.session_id.like("mandate:%"))
        .order_by(SimulatorOrder.created_at.desc())
        .limit(1)
    )
    # Fixed deterministic round-robin over the human-approved allowlist.
    instrument_id = spec.instrument_ids[len(automatic) % len(spec.instrument_ids)]
    instrument = await session.get(SimulatorInstrument, instrument_id)
    if (
        instrument is None
        or instrument.as_of > now
        or now - instrument.as_of > timedelta(seconds=spec.max_quote_age_seconds)
    ):
        raise PolicyDenied("STALE_QUOTE")
    # The synthetic feed has a known zero spread. External/unknown spreads never qualify.
    if instrument.exchange != "SIMULATOR":
        raise PolicyDenied("VERIFIED_SPREAD_UNAVAILABLE")
    if Decimal(account.mandate["fee_bps"]) > spec.max_fee_bps:
        raise PolicyDenied("COST_LIMIT")
    positions = (
        (
            await session.execute(
                select(SimulatorPosition)
                .where(SimulatorPosition.account_id == account_id)
                .order_by(SimulatorPosition.id)
                .limit(MAX_MANDATE_ROWS + 1)
            )
        )
        .scalars()
        .all()
    )
    await require_bounded_evidence(session, account, positions)
    exposure = Decimal(0)
    selected_value = Decimal(0)
    basis = Decimal(0)
    for position in positions:
        quote = await session.get(SimulatorInstrument, position.instrument_id)
        if quote is None or quote.as_of > now or now - quote.as_of > timedelta(seconds=spec.max_quote_age_seconds):
            raise PolicyDenied("VALUATION_STALE")
        value = position.quantity * positive(quote.price) * positive(quote.multiplier) * positive(quote.fx_to_base)
        exposure += value
        basis += position.cost_basis
        if position.instrument_id == instrument_id:
            selected_value += value
    from src.execution.reconciliation import reconcile_account

    checked = await reconcile_account(session, account)
    if checked["status"] != "consistent":
        await halt(session, user_id=user_id, account_id=account_id, reason="LEDGER_RECONCILIATION_REQUIRED")
        raise PolicyDenied("LEDGER_RECONCILIATION_REQUIRED")
    net_flows = Decimal(checked["net_external_flows"])
    equity = account.cash + exposure
    previous = account.mandate.get("risk_observation", {})
    if previous and datetime.fromisoformat(previous["at"]) > now:
        await halt(session, user_id=user_id, account_id=account_id, reason="CLOCK_REGRESSION")
        raise PolicyDenied("CLOCK_REGRESSION")
    day = now.date().isoformat()
    opening = Decimal(previous["day_open_equity"]) if previous.get("day") == day else equity
    opening_flows = Decimal(previous.get("day_open_net_flows", "0")) if previous.get("day") == day else net_flows
    prior_flows = Decimal(previous.get("net_external_flows", "0"))
    high_water = (
        max(Decimal(previous.get("high_water", str(account.initial_capital))) - prior_flows, equity - net_flows)
        + net_flows
    )
    daily_pnl = equity - opening - (net_flows - opening_flows)
    risk = dict(
        at=now.isoformat(),
        day=day,
        day_open_equity=str(opening),
        day_open_net_flows=str(opening_flows),
        net_external_flows=str(net_flows),
        high_water=str(high_water),
        equity=str(equity),
        realized=str(account.realized_pnl),
        unrealized=str(exposure - basis),
        daily_pnl=str(daily_pnl),
        drawdown=str(high_water - equity),
        exposure=str(exposure),
        currency=account.currency,
        convention="Flow-adjusted UTC first observation; fees included in cash/basis",
    )
    account.mandate = dict(account.mandate, risk_observation=risk)
    if daily_pnl <= -spec.daily_loss_limit or high_water - equity >= spec.drawdown_limit:
        await halt(session, user_id=user_id, account_id=account_id, reason="MARKED_LOSS_LIMIT")
        raise PolicyDenied("MARKED_LOSS_LIMIT")
    from src.execution.risk import enforce_account_risk

    global_risk = await enforce_account_risk(session, account, now=now)
    if not spec.start_hour <= now.hour < spec.end_hour or now.weekday() not in spec.weekdays:
        raise PolicyDenied("OUTSIDE_PERMITTED_HOURS")
    if len(automatic) >= spec.max_orders_per_day:
        raise PolicyDenied("DAILY_ORDER_FREQUENCY")
    if latest and now - latest.created_at < timedelta(seconds=spec.min_interval_seconds):
        raise PolicyDenied("ORDER_INTERVAL")
    from src.execution.decisions import retain_decision

    async def retain(result, *, quantity=None, side=None):
        return await retain_decision(
            session,
            account=account,
            mandate=mandate,
            tick_key=key,
            instrument=instrument,
            now=now,
            risk=risk,
            result=result,
            quantity=quantity,
            side=side,
        )

    side, quantity = "buy", spec.quantity_per_order
    if spec.strategy == "price_band_fixture":
        from src.execution.reconciliation import reconcile_account

        checked = await reconcile_account(session, account)
        if checked["status"] != "consistent" or checked.get("allocation_inventory") is None:
            raise PolicyDenied("STRATEGY_INVENTORY_UNVERIFIED")
        owned = next(
            (
                row
                for row in checked["allocation_inventory"]
                if row["allocation_id"] == mandate.id and row["instrument_id"] == instrument.id
            ),
            None,
        )
        # Never create another intent while an earlier strategy intent is pending.
        pending_strategy = await session.scalar(
            select(SimulatorOrder.id)
            .where(
                SimulatorOrder.account_id == account_id,
                SimulatorOrder.session_id == "mandate:" + mandate.id,
                SimulatorOrder.status.in_(
                    [
                        "submitted",
                        "acknowledged",
                        "partially_filled",
                        "cancel_requested",
                        "uncertain",
                    ]
                ),
            )
            .limit(1)
        )
        if pending_strategy:
            raise PolicyDenied("STRATEGY_ORDER_PENDING")
        if instrument.price >= spec.sell_above:
            available = Decimal(owned["available_quantity"]) if owned else Decimal(0)
            quantity = min(quantity, available)
            if quantity <= 0:
                return await retain(dict(status="no_trade", reason="NO_STRATEGY_INVENTORY", environment="simulator"))
            side = "sell"
            await require_owned_quantity(session, account, instrument.id, quantity, allocation_id=mandate.id)
        elif instrument.price > spec.buy_below:
            return await retain(dict(status="no_trade", reason="PRICE_INSIDE_BAND", environment="simulator"))
    reserve = preflight(account, instrument, quantity, instrument.price, side, now, mandate_spec=spec)
    from src.execution.exposure import require_order_exposure

    require_order_exposure(account, instrument, side, reserve, global_risk)
    gross_budget = quantity * instrument.price * instrument.multiplier * instrument.fx_to_base
    gross_budget *= 1 + Decimal(account.mandate["fee_bps"]) / 10000
    if gross_budget > spec.max_order:
        raise PolicyDenied("MANDATE_ORDER_CAP")
    pending = (
        (
            await session.execute(
                select(SimulatorOrder)
                .where(
                    SimulatorOrder.account_id == account_id,
                    SimulatorOrder.instrument_id == instrument_id,
                    SimulatorOrder.reserve > 0,
                )
                .order_by(SimulatorOrder.id)
                .limit(MAX_MANDATE_ROWS + 1)
            )
        )
        .scalars()
        .all()
    )
    await require_bounded_evidence(session, account, pending)
    if side == "buy" and selected_value + sum((o.reserve for o in pending), Decimal(0)) + reserve > spec.max_position:
        raise PolicyDenied("POSITION_LIMIT")
    if side == "buy" and exposure + account.reserved + reserve > spec.capital_limit:
        raise PolicyDenied("CAPITAL_ALLOCATION")
    order = SimulatorOrder(
        account_id=account_id,
        user_id=user_id,
        session_id="mandate:" + mandate.id,
        idempotency_key=key,
        instrument_id=instrument.id,
        side=side,
        quantity=quantity,
        limit_price=instrument.price,
        filled=0,
        fees=0,
        reserve=reserve,
        status="submitted",
        nonce_hash=digest(secrets.token_urlsafe(32)),
        details_hash="",
        expires_at=min(spec.expires_at, now + timedelta(seconds=spec.max_quote_age_seconds)),
        created_at=now,
    )
    order.details_hash = digest(order_details(order))
    order.approval = dict(
        actor="approved_simulator_mandate",
        reserved_base=str(reserve),
        mandate_id=mandate.id,
        mandate_hash=mandate.details_hash,
        strategy=spec.strategy,
        version=spec.strategy_version,
        at=now.isoformat(),
        risk=risk,
        environment="simulator",
    )
    account.reserved += reserve
    session.add(order)
    await session.flush()
    session.add(
        ExecutionEvent(
            order_id=order.id,
            event_key="mandate-submission",
            kind="submitted",
            payload=order.approval,
        )
    )
    await session.flush()
    return await retain(
        dict(order_id=order.id, status=order.status, environment="simulator"), quantity=quantity, side=side
    )
