"""Versioned simulator commission observations, independent of callback ordering."""

import re
from decimal import Decimal, InvalidOperation
from datetime import UTC, datetime

from sqlalchemy import select

from src.execution.models import ExecutionEvent, SimulatorOrder, SimulatorPosition
from src.execution.policy import PolicyDenied, digest, positive


async def latest_commission(session, order_id, execution_id):
    return await session.scalar(
        select(ExecutionEvent)
        .where(
            ExecutionEvent.order_id == order_id,
            ExecutionEvent.kind == "commission",
            ExecutionEvent.payload["execution_id"].as_string() == execution_id,
        )
        .order_by(ExecutionEvent.payload["revision"].as_integer().desc())
        .limit(1)
    )


def commission_amount(value):
    try:
        amount = Decimal(str(value))
        if amount == 0:
            return Decimal(0)
        return positive(amount)
    except (InvalidOperation, TypeError, ValueError):
        raise PolicyDenied("INVALID_COMMISSION") from None


async def record_commission(
    session,
    *,
    user_id,
    account_id,
    order_id,
    execution_id,
    revision,
    amount,
    currency,
    fx_to_base,
    fx_as_of,
    now=None,
):
    """Record an absolute commission revision, never a repeated incremental charge.

    Trusted simulator feed only. External SDK callbacks are not wired to this
    function. Before-fill observations persist and are consumed by record_fill.
    Higher revisions supersede lower ones; conflicting same revisions fail closed.
    """
    from src.execution.service import account_for_user

    now = now or datetime.now(UTC)
    if (
        not isinstance(execution_id, str)
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,123}", execution_id)
        or type(revision) is not int
        or not 0 <= revision <= 1_000_000_000
    ):
        raise PolicyDenied("INVALID_COMMISSION_ID")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        raise PolicyDenied("INVALID_COMMISSION_CURRENCY")
    if not isinstance(fx_as_of, datetime) or fx_as_of.tzinfo is None or fx_as_of > now:
        raise PolicyDenied("INVALID_COMMISSION_FX_TIME")
    amount, fx = commission_amount(amount), positive(fx_to_base)
    base_amount = commission_amount(amount * fx)
    account = await account_for_user(session, account_id, user_id)
    if currency == account.currency and fx != 1:
        raise PolicyDenied("INVALID_FX")
    order = await session.scalar(
        select(SimulatorOrder)
        .where(
            SimulatorOrder.id == order_id,
            SimulatorOrder.account_id == account_id,
        )
        .with_for_update()
    )
    if order is None or order.status == "proposed":
        raise PolicyDenied("ORDER_NOT_SUBMITTED")
    payload = dict(
        execution_id=execution_id,
        revision=revision,
        amount=str(amount.normalize()),
        currency=currency,
        fx_to_base=str(fx.normalize()),
        fx_as_of=fx_as_of.astimezone(UTC).isoformat(),
        base_currency=account.currency,
        fee_base=str(base_amount.normalize()),
    )
    key = f"commission:{digest(execution_id)}:{revision}"
    old = await session.scalar(
        select(ExecutionEvent).where(
            ExecutionEvent.order_id == order_id,
            ExecutionEvent.event_key == key,
        )
    )
    if old:
        if old.payload != payload:
            raise PolicyDenied("CONFLICTING_DUPLICATE_COMMISSION")
        return {"status": "deduplicated", "environment": "simulator"}
    latest = await latest_commission(session, order_id, execution_id)
    fill = await session.scalar(
        select(ExecutionEvent).where(
            ExecutionEvent.order_id == order_id,
            ExecutionEvent.event_key == "fill:" + execution_id,
            ExecutionEvent.kind == "fill",
        )
    )
    state = "awaiting_fill" if fill is None else "applied"
    if latest and latest.payload["revision"] > revision:
        state = "older_revision_recorded"
    elif fill is not None:
        previous = Decimal(latest.payload["fee_base"] if latest else fill.payload["fee"])
        delta = base_amount - previous
        position = await session.scalar(
            select(SimulatorPosition).where(
                SimulatorPosition.account_id == account_id,
                SimulatorPosition.instrument_id == order.instrument_id,
            )
        )
        if position is None:
            raise PolicyDenied("COMMISSION_POSITION_RECONCILIATION_REQUIRED")
        account.cash -= delta
        order.fees += delta
        position.cost_basis += delta
        # Preserve observed costs even if they exceed reserved capital. Stop new orders.
        fills = (
            await session.scalars(
                select(ExecutionEvent).where(
                    ExecutionEvent.order_id == order_id,
                    ExecutionEvent.kind == "fill",
                )
            )
        ).all()
        reservation = (order.approval or {}).get("reserved_base")
        if reservation is None or any("principal_base" not in event.payload for event in fills):
            account.halted, account.halt_reason = True, "COMMISSION_RECONCILIATION_REQUIRED"
        elif account.cash < account.reserved or sum(
            Decimal(event.payload["principal_base"]) for event in fills
        ) + order.fees + order.reserve > Decimal(reservation):
            account.halted, account.halt_reason = True, "COMMISSION_BUDGET_EXCEEDED"
    session.add(ExecutionEvent(order_id=order_id, event_key=key, kind="commission", payload=payload))
    await session.flush()
    return {"status": state, "environment": "simulator", "fee_base": str(base_amount), "halted": account.halted}
