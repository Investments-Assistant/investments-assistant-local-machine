"""Transactional simulator commands. Callers own the transaction boundary.

All account changes hold the active principal's shared lock before the account
lock; pending orders reserve budgets before any submission event. There is no
external broker route in this service.
"""

from decimal import ROUND_DOWN, Decimal
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from src.db.models import User
from src.execution.models import (
    ExecutionEvent,
    SimulatorOrder,
    SimulatorAccount,
    SimulatorPosition,
    SimulatorInstrument,
)
from src.execution.policy import PolicyDenied, digest, positive, preflight, order_details
from src.execution.numeric import execution_precision
from src.execution.exposure import require_order_exposure


async def account_for_user(session, account_id: str, user_id: str):
    user = await session.scalar(
        select(User).where(User.id == user_id, User.is_active.is_(True)).with_for_update(read=True)
    )
    if user is None:
        raise PolicyDenied("PRINCIPAL_INACTIVE")
    account = await session.scalar(
        select(SimulatorAccount)
        .where(
            SimulatorAccount.id == account_id,
            SimulatorAccount.user_id == user_id,
        )
        .with_for_update()
    )
    if account is None:
        raise PolicyDenied("ACCOUNT_NOT_OWNED")
    return account


async def require_owned_quantity(session, account, instrument_id, quantity, *, allocation_id="manual"):
    """Called under account_for_user's lock; proposals do not consume inventory."""
    from src.execution.reconciliation import reconcile_account

    result = await reconcile_account(session, account)
    if result["status"] != "consistent" or result.get("allocation_inventory") is None:
        raise PolicyDenied("SALE_INVENTORY_UNVERIFIED")
    available = next((Decimal(row["available_quantity"]) for row in result["allocation_inventory"]
                      if row["allocation_id"] == allocation_id and row["instrument_id"] == instrument_id), Decimal(0))
    if quantity > available:
        raise PolicyDenied("INSUFFICIENT_OWNED_QUANTITY")


@execution_precision
async def propose(
    session,
    *,
    user_id: str,
    session_id: str,
    account_id: str,
    instrument_id: str,
    quantity,
    limit_price,
    idempotency_key: str,
    side: str = "buy",
    now: datetime | None = None,
) -> dict:
    if not session_id or not idempotency_key or len(idempotency_key) > 64:
        raise PolicyDenied("INVALID_CORRELATION")
    account = await account_for_user(session, account_id, user_id)
    now = now or datetime.now(UTC)
    old = await session.scalar(
        select(SimulatorOrder).where(
            SimulatorOrder.account_id == account_id,
            SimulatorOrder.idempotency_key == idempotency_key,
        )
    )
    if old:
        if (
            old.side != side
            or old.instrument_id != instrument_id
            or old.quantity != positive(quantity)
            or old.limit_price != positive(limit_price)
            or old.session_id != session_id
        ):
            raise PolicyDenied("IDEMPOTENCY_CONFLICT")
        return {"order_id": old.id, "status": old.status, "deduplicated": True}
    instrument = await session.scalar(
        select(SimulatorInstrument).where(
            SimulatorInstrument.id == instrument_id, SimulatorInstrument.account_id == account_id
        )
    )
    if instrument is None:
        raise PolicyDenied("UNQUALIFIED_INSTRUMENT")
    quantity, price = positive(quantity), positive(limit_price)
    from src.execution.risk import enforce_account_risk

    risk = await enforce_account_risk(session, account, now=now)
    reserve = preflight(account, instrument, quantity, price, side, now)
    require_order_exposure(account, instrument, side, reserve, risk)
    if side == "sell":
        await require_owned_quantity(session, account, instrument_id, quantity)
    nonce = secrets.token_urlsafe(32)
    order = SimulatorOrder(
        account_id=account_id,
        user_id=user_id,
        session_id=session_id,
        instrument_id=instrument_id,
        side=side,
        quantity=quantity,
        limit_price=price,
        idempotency_key=idempotency_key,
        nonce_hash=digest(nonce),
        details_hash="",
        expires_at=now + timedelta(minutes=5),
        status="proposed",
        reserve=0,
        filled=0,
        fees=0,
    )
    order.details_hash = digest(order_details(order))
    session.add(order)
    await session.flush()
    session.add(
        ExecutionEvent(
            order_id=order.id,
            event_key="proposal",
            kind="proposed",
            payload={"details_hash": order.details_hash, "environment": "simulator"},
        )
    )
    return {
        "order_id": order.id,
        "nonce": nonce,
        "details_hash": order.details_hash,
        "details": order_details(order),
        "status": "proposed",
        "environment": "simulator",
    }


@execution_precision
async def approve(
    session,
    *,
    user_id: str,
    session_id: str,
    account_id: str,
    order_id: str,
    nonce: str,
    details_hash: str,
    human_event: bool,
    now: datetime | None = None,
):
    if human_event is not True:
        raise PolicyDenied("HUMAN_APPROVAL_REQUIRED")
    account = await account_for_user(session, account_id, user_id)
    now = now or datetime.now(UTC)
    order = await session.scalar(
        select(SimulatorOrder)
        .where(
            SimulatorOrder.id == order_id,
            SimulatorOrder.account_id == account_id,
            SimulatorOrder.user_id == user_id,
        )
        .with_for_update()
    )
    if order is None or order.session_id != session_id:
        raise PolicyDenied("PROPOSAL_NOT_OWNED")
    if order.status != "proposed":
        raise PolicyDenied("APPROVAL_ALREADY_CONSUMED")
    if now >= order.expires_at:
        raise PolicyDenied("APPROVAL_EXPIRED")
    if not secrets.compare_digest(order.nonce_hash, digest(nonce)):
        raise PolicyDenied("INVALID_NONCE")
    if not (
        secrets.compare_digest(order.details_hash, details_hash)
        and secrets.compare_digest(order.details_hash, digest(order_details(order)))
    ):
        raise PolicyDenied("ORDER_CHANGED_AFTER_PROPOSAL")
    instrument = await session.get(SimulatorInstrument, order.instrument_id)
    from src.execution.risk import enforce_account_risk

    risk = await enforce_account_risk(session, account, now=now)
    reserve = preflight(account, instrument, order.quantity, order.limit_price, order.side, now)
    require_order_exposure(account, instrument, order.side, reserve, risk)
    if order.side == "sell":
        await require_owned_quantity(session, account, order.instrument_id, order.quantity)
    account.reserved += reserve
    order.reserve = reserve
    order.status = "submitted"
    order.approval = {
        "actor": "authenticated_browser",
        "at": now.isoformat(),
        "details_hash": order.details_hash,
        "environment": "simulator",
        "reserved_base": str(reserve),
    }
    session.add(ExecutionEvent(order_id=order.id, event_key="approval", kind="submitted", payload=order.approval))
    await session.flush()
    return {"order_id": order.id, "status": order.status, "environment": "simulator"}


@execution_precision
async def record_fill(
    session,
    *,
    user_id: str,
    account_id: str,
    order_id: str,
    execution_id: str,
    quantity,
    price,
    fee=0,
):
    """Simulator feed callback; duplicate execution IDs must carry identical data.

    Fills can arrive after cancel acknowledgments. A discrepant fill is recorded
    and halts the account; broker reality must not disappear due to local policy.
    """
    account = await account_for_user(session, account_id, user_id)
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
    quantity, price = positive(quantity), positive(price)
    fee = Decimal(str(fee))
    if not fee.is_finite() or fee < 0:
        raise PolicyDenied("INVALID_FEE")
    if fee:
        fee = positive(fee)
    payload = {
        "quantity": str(quantity.normalize()),
        "price": str(price.normalize()),
        "fee": str(fee.normalize()),
    }
    event_key = "fill:" + execution_id
    if not execution_id or len(event_key) > 128:
        raise PolicyDenied("INVALID_EXECUTION_ID")
    old = await session.scalar(
        select(ExecutionEvent).where(ExecutionEvent.order_id == order_id, ExecutionEvent.event_key == event_key)
    )
    if old:
        if any(old.payload.get(key) != value for key, value in payload.items()):
            raise PolicyDenied("CONFLICTING_DUPLICATE_EXECUTION")
        accounting_status = old.payload.get("accounting_status")
        if accounting_status is None and order.side == "sell":
            # Legacy callbacks predate the retained settlement outcome. Do not
            # infer settlement from an execution's terminal state alone.
            from src.execution.reconciliation import reconcile_account

            checked = await reconcile_account(session, account)
            accounting_status = "applied" if checked["status"] == "consistent" else "reconciliation_required"
        return {
            "status": "reconciliation_required" if accounting_status == "reconciliation_required" else order.status,
            "deduplicated": True,
        }
    if order.filled + quantity > order.quantity:
        raise PolicyDenied("OVERFILL_RECONCILIATION_REQUIRED")
    instrument = await session.get(SimulatorInstrument, order.instrument_id)
    from src.execution.commissions import latest_commission

    commission = await latest_commission(session, order_id, execution_id)
    applied_fee = Decimal(commission.payload["fee_base"]) if commission else fee
    principal = positive(quantity * price * instrument.multiplier * instrument.fx_to_base)
    cost = principal + applied_fee
    before_ledger = None
    if order.side == "sell":
        from src.execution.reconciliation import reconcile_account

        before, before_ledger = await reconcile_account(
            session, account, _include_ledger=True, _pending_fees_for_fill=True,
        )
        pending_only = before.get("unknown_reasons") == ["COMMISSION_AWAITING_EXECUTION"]
        if before["status"] != "consistent" and not (pending_only and before["discrepancy_count"] == 0):
            before_ledger = None
    payload.update(
        principal_base=str(principal),
        applied_fee_base=str(applied_fee),
        base_currency=account.currency,
        source_currency=instrument.currency,
        multiplier=str(instrument.multiplier),
        fx_to_base=str(instrument.fx_to_base),
        fx_as_of=instrument.as_of.isoformat(),
        valuation_basis="simulator fixture quote at callback",
    )
    # Keep rounding dust reserved until the final fill; never let PostgreSQL
    # silently round a higher-precision intermediate balance.
    release = min(order.reserve, order.reserve * quantity / (order.quantity - order.filled)).quantize(
        Decimal("0.0000000001"), rounding=ROUND_DOWN
    )
    payload["released_reserve_base"] = str(release)
    consumed = cost if order.side == "buy" else applied_fee
    price_breach = price > order.limit_price if order.side == "buy" else price < order.limit_price
    if order.status in {"cancelled", "rejected"} or consumed > release or price_breach:
        account.halted = True
        account.halt_reason = "FILL_RECONCILIATION_DISCREPANCY"
    account.reserved -= release
    order.reserve -= release
    if order.side == "buy":
        account.cash -= cost
        position = await session.scalar(
            select(SimulatorPosition).where(
                SimulatorPosition.account_id == account_id,
                SimulatorPosition.instrument_id == order.instrument_id,
            )
        )
        if position is None:
            position = SimulatorPosition(
                account_id=account_id, instrument_id=order.instrument_id, quantity=0, cost_basis=0,
            )
            session.add(position)
        position.quantity += quantity
        position.cost_basis += cost
    order.filled += quantity
    order.fees += applied_fee
    order.status = "filled" if order.filled == order.quantity else "partially_filled"
    fill_event = ExecutionEvent(order_id=order_id, event_key=event_key, kind="fill", payload=payload)
    session.add(fill_event)
    await session.flush()
    if order.side == "sell":
        _, after_ledger = await reconcile_account(
            session, account, _include_ledger=True, _pending_fees_for_fill=True,
        )
        if before_ledger is None or after_ledger is None:
            account.halted, account.halt_reason = True, "FILL_RECONCILIATION_DISCREPANCY"
            fill_event.payload = dict(payload, accounting_status="reconciliation_required")
            await session.flush()
            return {"order_id": order_id, "status": "reconciliation_required", "filled": str(order.filled)}
        account.cash += after_ledger.cash - before_ledger.cash
        account.realized_pnl += after_ledger.realized_pnl - before_ledger.realized_pnl
        position = await session.scalar(select(SimulatorPosition).where(
            SimulatorPosition.account_id == account_id, SimulatorPosition.instrument_id == order.instrument_id,
        ))
        # Materialized positions aggregate allocations; replay retains ownership.
        # Apply only the verified instrument delta, including mandate-owned sales.
        for field in ("quantity", "cost_basis"):
            previous = sum((getattr(balance, field) for (_, instrument_id), balance
                            in before_ledger.positions.items() if instrument_id == order.instrument_id), Decimal(0))
            current = sum((getattr(balance, field) for (_, instrument_id), balance
                           in after_ledger.positions.items() if instrument_id == order.instrument_id), Decimal(0))
            setattr(position, field, getattr(position, field) + current - previous)
        await session.flush()
    fill_event.payload = dict(payload, accounting_status="applied")
    await session.flush()
    return {"order_id": order_id, "status": order.status, "filled": str(order.filled)}


@execution_precision
async def transition(session, *, user_id: str, account_id: str, order_id: str, status: str, event_key: str):
    """Feed lifecycle transitions; uncertain submission never releases budget."""
    if status not in {"acknowledged", "uncertain", "cancel_requested", "cancelled", "rejected"}:
        raise PolicyDenied("UNSUPPORTED_TRANSITION")
    account = await account_for_user(session, account_id, user_id)
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
    old = await session.scalar(
        select(ExecutionEvent).where(ExecutionEvent.order_id == order_id, ExecutionEvent.event_key == event_key)
    )
    if old:
        if old.kind != status:
            raise PolicyDenied("CONFLICTING_DUPLICATE_EVENT")
        return {"status": order.status, "deduplicated": True}
    # Late acknowledgements cannot regress a partial/full fill or cancellation.
    if order.status not in {"filled", "cancelled", "rejected"}:
        if status in {"cancelled", "rejected"}:
            account.reserved -= order.reserve
            order.reserve = 0
        if status != "acknowledged" or order.status in {"submitted", "uncertain"}:
            order.status = status
    session.add(
        ExecutionEvent(
            order_id=order_id,
            event_key=event_key,
            kind=status,
            payload={"effective_status": order.status},
        )
    )
    await session.flush()
    return {"order_id": order_id, "status": order.status}


async def halt(session, *, user_id: str, account_id: str, reason="OPERATOR_HALT"):
    account = await account_for_user(session, account_id, user_id)
    account.halted = True
    account.halt_reason = reason
    from src.operations.alerts import emit

    await emit(
        session,
        user_id=user_id,
        account_id=account_id,
        rule="strategy_halted",
        observed_value=reason,
        threshold="operator review before new orders",
        message="Simulator stopped new orders. Existing orders and positions require separate review.",
        evidence_at=datetime.now(UTC),
        severity="warning",
    )
    await session.flush()
    return {"halted": True, "pending_orders_cancelled": False, "positions_liquidated": False}
