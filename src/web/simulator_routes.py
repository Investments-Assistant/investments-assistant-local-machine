"""Browser-only synthetic order workflow; never an external account or price feed."""

import asyncio
from decimal import Decimal
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Request, APIRouter, HTTPException
from pydantic import Field, BaseModel, ConfigDict
from sqlalchemy import text, select

from src.web.auth import SESSION_COOKIE, require_csrf, require_authenticated
from src.db.models import User
from src.db.database import async_session
from src.execution.risk import RiskDenied
from src.execution.models import SimulatorOrder, SimulatorAccount, SimulatorInstrument
from src.execution.policy import PolicyDenied, digest
from src.execution.service import halt, approve, propose, record_fill, account_for_user
from src.execution.mandates import MandateSpec, approve_mandate, propose_mandate
from src.execution.reconciliation import reconcile_account

router = APIRouter(prefix="/api/simulator", dependencies=[Depends(require_authenticated)])


class ProposalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    instrument_id: str
    quantity: Decimal = Field(gt=0)
    limit_price: Decimal = Field(gt=0)
    idempotency_key: str = Field(min_length=1, max_length=64)


class ApprovalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nonce: str = Field(min_length=1, max_length=128)
    details_hash: str = Field(min_length=64, max_length=64)


async def browser_identity(request):
    principal = await require_authenticated(request)
    if not principal.user_id or principal.mechanism != "cookie":
        raise HTTPException(403, "An authenticated browser account is required")
    return principal.user_id, digest(request.cookies[SESSION_COOKIE])


def denied(exc):
    return HTTPException(409, detail={"reason_code": exc.code, "environment": "simulator"})


async def risk_checked_command(command, **kwargs):
    """Commit only deliberate risk halts before returning a rejected new-order request."""
    rejection = None
    try:
        async with async_session.begin() as session:
            try:
                result = await command(session, **kwargs)
            except RiskDenied as exc:
                rejection = denied(exc)
    except PolicyDenied as exc:
        raise denied(exc) from exc
    if rejection is not None:
        raise rejection
    return result


@router.post("/fixtures", dependencies=[Depends(require_csrf)])
async def create_fixture(request: Request):
    """An explicit user click creates only a labelled synthetic allocation."""
    user_id, _ = await browser_identity(request)
    async with async_session.begin() as session:
        user = await session.scalar(select(User).where(User.id == user_id, User.is_active.is_(True)))
        if user is None:
            raise HTTPException(401, "Account inactive")
        # Bounded fixture count; lock user to serialize simultaneous setup requests.
        await session.execute(select(User.id).where(User.id == user_id).with_for_update())
        accounts = (
            (await session.execute(select(SimulatorAccount).where(SimulatorAccount.user_id == user_id).limit(10)))
            .scalars()
            .all()
        )
        if len(accounts) >= 10:
            raise HTTPException(409, "Fixture account limit reached")
        now = datetime.now(UTC)
        account = SimulatorAccount(
            user_id=user_id,
            currency="EUR",
            cash=1000,
            reserved=0,
            initial_capital=1000,
            max_order=500,
            loss_limit=50,
            realized_pnl=0,
            halted=False,
            mandate={
                "environment": "simulator",
                "fixture": True,
                "fee_bps": "10",
                "expires_at": (now + timedelta(hours=1)).isoformat(),
                "strategy": "manual-fixture-v1",
            },
        )
        session.add(account)
        await session.flush()
        instrument = SimulatorInstrument(
            account_id=account.id,
            symbol="FIXTURE",
            exchange="SIMULATOR",
            currency="EUR",
            multiplier=1,
            lot=Decimal(".001"),
            tick=Decimal(".01"),
            price=100,
            fx_to_base=1,
            as_of=now,
            protected=False,
            security_type="stock",
        )
        session.add(instrument)
        await session.flush()
        return {
            "account_id": account.id,
            "instrument_id": instrument.id,
            "environment": "simulator",
            "cash": "1000",
            "currency": "EUR",
            "message": "Synthetic fixture only; no bank or broker connection.",
        }


@router.get("/accounts/{account_id}")
async def snapshot(account_id: str, request: Request):
    user_id, _ = await browser_identity(request)
    try:
        async with asyncio.timeout(10), async_session.begin() as session:
            await session.execute(text("SET LOCAL statement_timeout = '5s'"))
            await session.execute(text("SET LOCAL lock_timeout = '2s'"))
            account = await account_for_user(session, account_id, user_id)
            orders = (
                (
                    await session.execute(
                        select(SimulatorOrder)
                        .where(SimulatorOrder.account_id == account_id)
                        .order_by(SimulatorOrder.created_at.desc())
                        .limit(100)
                    )
                )
                .scalars()
                .all()
            )
            return {
                "account_id": account_id,
                "environment": "simulator",
                "currency": account.currency,
                "cash": str(account.cash),
                "reserved": str(account.reserved),
                "halted": account.halted,
                "halt_reason": account.halt_reason,
                "reconciliation": await reconcile_account(session, account),
                "orders": [
                    {
                        "id": o.id,
                        "status": o.status,
                        "quantity": str(o.quantity),
                        "filled": str(o.filled),
                        "fees": str(o.fees),
                    }
                    for o in orders
                ],
            }
    except PolicyDenied as exc:
        raise denied(exc) from exc


@router.post("/accounts/{account_id}/proposals", dependencies=[Depends(require_csrf)])
async def create_proposal(account_id: str, body: ProposalInput, request: Request):
    user_id, session_id = await browser_identity(request)
    return await risk_checked_command(
        propose, user_id=user_id, session_id=session_id, account_id=account_id, **body.model_dump()
    )


@router.post("/accounts/{account_id}/orders/{order_id}/approve", dependencies=[Depends(require_csrf)])
async def approve_proposal(account_id: str, order_id: str, body: ApprovalInput, request: Request):
    user_id, session_id = await browser_identity(request)
    return await risk_checked_command(
        approve,
        user_id=user_id,
        session_id=session_id,
        account_id=account_id,
        order_id=order_id,
        human_event=True,
        **body.model_dump(),
    )


@router.post("/accounts/{account_id}/orders/{order_id}/tick", dependencies=[Depends(require_csrf)])
async def fixture_tick(account_id: str, order_id: str, request: Request):
    """One deterministic fixture fill tick, explicitly separate from approval."""
    user_id, _ = await browser_identity(request)
    try:
        async with async_session.begin() as session:
            account = await account_for_user(session, account_id, user_id)
            if account.mandate.get("fixture") is not True:
                raise PolicyDenied("FIXTURE_REQUIRED")
            order = await session.scalar(
                select(SimulatorOrder).where(SimulatorOrder.id == order_id, SimulatorOrder.account_id == account_id)
            )
            if order is None or order.status not in {"submitted", "partially_filled"}:
                raise PolicyDenied("NO_PENDING_FIXTURE_ORDER")
            instrument = await session.get(SimulatorInstrument, order.instrument_id)
            quantity = order.quantity - order.filled
            fee = quantity * instrument.price * Decimal(account.mandate["fee_bps"]) / 10000
            return await record_fill(
                session,
                user_id=user_id,
                account_id=account_id,
                order_id=order_id,
                execution_id="fixture-tick-1",
                quantity=quantity,
                price=instrument.price,
                fee=fee,
            )
    except PolicyDenied as exc:
        raise denied(exc) from exc


@router.post("/accounts/{account_id}/halt", dependencies=[Depends(require_csrf)])
async def halt_account(account_id: str, request: Request):
    user_id, _ = await browser_identity(request)
    try:
        async with async_session.begin() as session:
            return await halt(session, user_id=user_id, account_id=account_id)
    except PolicyDenied as exc:
        raise denied(exc) from exc


@router.post("/accounts/{account_id}/mandates", dependencies=[Depends(require_csrf)])
async def create_mandate(account_id: str, body: MandateSpec, request: Request):
    user_id, session_id = await browser_identity(request)
    try:
        async with async_session.begin() as session:
            return await propose_mandate(
                session, user_id=user_id, session_id=session_id, account_id=account_id, spec=body
            )
    except PolicyDenied as exc:
        raise denied(exc) from exc


@router.post("/accounts/{account_id}/mandates/{mandate_id}/approve", dependencies=[Depends(require_csrf)])
async def approve_strategy_mandate(account_id: str, mandate_id: str, body: ApprovalInput, request: Request):
    user_id, session_id = await browser_identity(request)
    try:
        async with async_session.begin() as session:
            return await approve_mandate(
                session,
                user_id=user_id,
                session_id=session_id,
                account_id=account_id,
                mandate_id=mandate_id,
                human_event=True,
                **body.model_dump(),
            )
    except PolicyDenied as exc:
        raise denied(exc) from exc
