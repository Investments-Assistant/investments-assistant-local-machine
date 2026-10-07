"""Independent browser review of an explicitly selected pending/booked pair."""

from typing import Literal
import asyncio
from datetime import UTC, datetime

from fastapi import Depends, Request, APIRouter, HTTPException
from pydantic import Field, BaseModel, ConfigDict, AwareDatetime
from sqlalchemy import text
from fastapi.responses import JSONResponse

from src.web.auth import require_csrf, require_authenticated
from src.db.database import async_session
from src.execution.policy import PolicyDenied
from src.expenses.reconciliation import reconcile_pending, reconciliation_plan

router = APIRouter(prefix="/api/expenses/reconciliation", dependencies=[
    Depends(require_authenticated), Depends(require_csrf)])


class PairInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pending_id: str = Field(min_length=36, max_length=36)
    booked_id: str = Field(min_length=36, max_length=36)


class ApplyInput(PairInput):
    as_of: AwareDatetime
    plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    export_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirm_same_transaction: Literal[True]
    confirm_export_saved: Literal[True]


async def owner(request):
    principal = await require_authenticated(request)
    if not principal.user_id or principal.mechanism != "cookie":
        raise HTTPException(403, "An authenticated browser account is required")
    return principal.user_id


@router.post("/preview")
async def preview(body: PairInput, request: Request):
    user_id = await owner(request)
    try:
        async with asyncio.timeout(10), async_session.begin() as session:
            await session.execute(text("SET LOCAL statement_timeout = '5s'"))
            await session.execute(text("SET LOCAL lock_timeout = '2s'"))
            plan, exported, _, _ = await reconciliation_plan(session, user_id=user_id,
                pending_id=body.pending_id, booked_id=body.booked_id, as_of=datetime.now(UTC))
            return JSONResponse(dict(plan=plan, export=exported), headers={"Cache-Control": "no-store"})
    except PolicyDenied as exc:
        raise HTTPException(409, detail={"reason_code": exc.code}) from None


@router.post("/apply")
async def apply_pair(body: ApplyInput, request: Request):
    user_id = await owner(request)
    try:
        async with asyncio.timeout(10), async_session.begin() as session:
            await session.execute(text("SET LOCAL statement_timeout = '5s'"))
            await session.execute(text("SET LOCAL lock_timeout = '2s'"))
            result = await reconcile_pending(session, user_id=user_id, pending_id=body.pending_id,
                booked_id=body.booked_id, as_of=body.as_of, expected_plan=body.plan_sha256,
                export_sha256=body.export_sha256)
        from src.web.routes import _publish_expense_event

        await _publish_expense_event(user_id, {"kind": "pending_reconciled"})
        return result
    except PolicyDenied as exc:
        raise HTTPException(409, detail={"reason_code": exc.code}) from None
