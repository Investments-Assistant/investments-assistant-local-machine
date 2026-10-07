"""Independent browser preview/confirmation for expense raw-payload retention."""

from typing import Literal
import asyncio
from datetime import UTC, datetime

from fastapi import Depends, Request, APIRouter, HTTPException
from pydantic import Field, BaseModel, ConfigDict
from sqlalchemy import text

from src.web.auth import require_csrf, require_authenticated
from src.db.database import async_session
from src.execution.policy import PolicyDenied
from src.expenses.retention import RawRetentionPolicy, raw_payload_plan, remove_raw_payloads

router = APIRouter(
    prefix="/api/expenses/retention", dependencies=[Depends(require_authenticated), Depends(require_csrf)]
)


class PreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    retain_days: int = Field(ge=1, le=36525, strict=True)


class ApplyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy: RawRetentionPolicy
    plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirm_raw_payload_removal: Literal[True]


async def owner(request):
    principal = await require_authenticated(request)
    if not principal.user_id or principal.mechanism != "cookie":
        raise HTTPException(403, "An authenticated browser account is required")
    return principal.user_id


@router.post("/preview")
async def preview(body: PreviewInput, request: Request):
    user_id = await owner(request)
    policy = RawRetentionPolicy(retain_days=body.retain_days, as_of=datetime.now(UTC))
    try:
        async with asyncio.timeout(10), async_session.begin() as session:
            await session.execute(text("SET LOCAL statement_timeout = '5s'"))
            plan, _ = await raw_payload_plan(session, user_id=user_id, policy=policy)
            return plan
    except PolicyDenied as exc:
        raise HTTPException(409, detail={"reason_code": exc.code}) from None


@router.post("/apply")
async def apply_retention(body: ApplyInput, request: Request):
    user_id = await owner(request)
    try:
        async with asyncio.timeout(10), async_session.begin() as session:
            await session.execute(text("SET LOCAL statement_timeout = '5s'"))
            await session.execute(text("SET LOCAL lock_timeout = '2s'"))
            return await remove_raw_payloads(
                session, user_id=user_id, policy=body.policy, expected_plan=body.plan_sha256
            )
    except PolicyDenied as exc:
        raise HTTPException(409, detail={"reason_code": exc.code}) from None


class HistoryApplyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy: RawRetentionPolicy
    plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    export_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirm_history_removal: Literal[True]
    confirm_export_saved: Literal[True]


@router.post("/history/preview")
async def preview_history(body: PreviewInput, request: Request):
    from src.expenses.history_retention import history_plan

    user_id = await owner(request)
    policy = RawRetentionPolicy(retain_days=body.retain_days, as_of=datetime.now(UTC))
    try:
        async with asyncio.timeout(10), async_session.begin() as session:
            await session.execute(text("SET LOCAL statement_timeout = '5s'"))
            await session.execute(text("SET LOCAL lock_timeout = '2s'"))
            plan, exported = await history_plan(session, user_id=user_id, policy=policy)
            from fastapi.responses import JSONResponse

            return JSONResponse(dict(plan=plan, export=exported), headers={"Cache-Control": "no-store"})
    except PolicyDenied as exc:
        raise HTTPException(409, detail={"reason_code": exc.code}) from None


@router.post("/history/apply")
async def apply_history(body: HistoryApplyInput, request: Request):
    from src.expenses.history_retention import purge_history

    user_id = await owner(request)
    try:
        async with asyncio.timeout(10), async_session.begin() as session:
            await session.execute(text("SET LOCAL statement_timeout = '5s'"))
            await session.execute(text("SET LOCAL lock_timeout = '2s'"))
            result = await purge_history(
                session,
                user_id=user_id,
                policy=body.policy,
                expected_plan=body.plan_sha256,
                export_sha256=body.export_sha256,
            )
        from src.web.routes import _publish_expense_event

        await _publish_expense_event(user_id, {"kind": "history_retired"})
        return result
    except PolicyDenied as exc:
        raise HTTPException(409, detail={"reason_code": exc.code}) from None
