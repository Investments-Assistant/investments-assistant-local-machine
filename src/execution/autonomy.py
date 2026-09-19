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
    SimulatorPosition,
    SimulatorInstrument,
)
from src.execution.policy import PolicyDenied, digest, positive, preflight, order_details
from src.execution.service import halt, account_for_user
from src.execution.mandates import MandateSpec, immutable_details


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
                select(SimulatorOrder).where(
                    SimulatorOrder.account_id == account_id,
                    SimulatorOrder.approval.is_not(None),
                    SimulatorOrder.created_at >= now.replace(hour=0, minute=0, second=0, microsecond=0),
                )
            )
        )
        .scalars()
        .all()
    )
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
    if instrument is None or now - instrument.as_of > timedelta(seconds=spec.max_quote_age_seconds):
        raise PolicyDenied("STALE_QUOTE")
    # The synthetic feed has a known zero spread. External/unknown spreads never qualify.
    if instrument.exchange != "SIMULATOR":
        raise PolicyDenied("VERIFIED_SPREAD_UNAVAILABLE")
    if Decimal(account.mandate["fee_bps"]) > spec.max_fee_bps:
        raise PolicyDenied("COST_LIMIT")
    positions = (
        (await session.execute(select(SimulatorPosition).where(SimulatorPosition.account_id == account_id)))
        .scalars()
        .all()
    )
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
    equity = account.cash + exposure
    previous = account.mandate.get("risk_observation", {})
    if previous and datetime.fromisoformat(previous["at"]) > now:
        await halt(session, user_id=user_id, account_id=account_id, reason="CLOCK_REGRESSION")
        raise PolicyDenied("CLOCK_REGRESSION")
    day = now.date().isoformat()
    opening = Decimal(previous["day_open_equity"]) if previous.get("day") == day else equity
    high_water = max(Decimal(previous.get("high_water", str(account.initial_capital))), equity)
    risk = dict(
        at=now.isoformat(),
        day=day,
        day_open_equity=str(opening),
        high_water=str(high_water),
        equity=str(equity),
        realized=str(account.realized_pnl),
        unrealized=str(exposure - basis),
        daily_pnl=str(equity - opening),
        drawdown=str(high_water - equity),
        exposure=str(exposure),
        currency=account.currency,
        convention="UTC first observation; fees included in cash/basis; no external flows",
    )
    account.mandate = dict(account.mandate, risk_observation=risk)
    if equity - opening <= -spec.daily_loss_limit or high_water - equity >= spec.drawdown_limit:
        await halt(session, user_id=user_id, account_id=account_id, reason="MARKED_LOSS_LIMIT")
        raise PolicyDenied("MARKED_LOSS_LIMIT")
    from src.execution.risk import enforce_account_risk

    await enforce_account_risk(session, account, now=now)
    if not spec.start_hour <= now.hour < spec.end_hour or now.weekday() not in spec.weekdays:
        raise PolicyDenied("OUTSIDE_PERMITTED_HOURS")
    if len(automatic) >= spec.max_orders_per_day:
        raise PolicyDenied("DAILY_ORDER_FREQUENCY")
    if latest and now - latest.created_at < timedelta(seconds=spec.min_interval_seconds):
        raise PolicyDenied("ORDER_INTERVAL")
    reserve = preflight(account, instrument, spec.quantity_per_order, instrument.price, "buy", now)
    if reserve > spec.max_order:
        raise PolicyDenied("MANDATE_ORDER_CAP")
    pending = (
        (
            await session.execute(
                select(SimulatorOrder).where(
                    SimulatorOrder.account_id == account_id,
                    SimulatorOrder.instrument_id == instrument_id,
                    SimulatorOrder.reserve > 0,
                )
            )
        )
        .scalars()
        .all()
    )
    if selected_value + sum((o.reserve for o in pending), Decimal(0)) + reserve > spec.max_position:
        raise PolicyDenied("POSITION_LIMIT")
    if exposure + account.reserved + reserve > spec.capital_limit:
        raise PolicyDenied("CAPITAL_ALLOCATION")
    order = SimulatorOrder(
        account_id=account_id,
        user_id=user_id,
        session_id="mandate:" + mandate.id,
        idempotency_key=key,
        instrument_id=instrument.id,
        side="buy",
        quantity=spec.quantity_per_order,
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
    return dict(order_id=order.id, status=order.status, environment="simulator")
