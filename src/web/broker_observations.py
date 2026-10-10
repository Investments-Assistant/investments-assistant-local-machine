"""Browser-owned local callback evidence and explicit broker read refresh."""

from typing import Literal
import asyncio

from fastapi import Query, Depends, Request, APIRouter, HTTPException
from pydantic import Field, BaseModel, ConfigDict, field_validator
from sqlalchemy import text

from src.web.auth import require_csrf, require_authenticated
from src.db.database import async_session
from src.execution.policy import PolicyDenied
from src.operations.workloads import WorkloadBusy
from src.execution.broker_monitor import refresh_observations
from src.execution.broker_observations import read_observations
from src.execution.broker_capture_control import capture_control

router = APIRouter(prefix="/api/broker-accounts", dependencies=[Depends(require_authenticated)])


class RefreshInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_broker_read: Literal[True]


class CaptureInput(RefreshInput):
    duration_seconds: int = Field(default=60, strict=True, ge=1, le=480)

    @field_validator("confirm_broker_read", mode="before")
    @classmethod
    def explicit_boolean(cls, value):
        if value is not True:
            raise ValueError("Explicit true confirmation required")
        return value


async def owner(request):
    principal = await require_authenticated(request)
    if not principal.user_id or principal.mechanism != "cookie":
        raise HTTPException(403, "An authenticated browser account is required")
    return principal.user_id


@router.post("/{account_id}/observations/capture", dependencies=[Depends(require_csrf)], status_code=202)
async def start_capture(account_id: str, body: CaptureInput, request: Request):
    user_id = await owner(request)
    try:
        return await capture_control.start(user_id=user_id, account_id=account_id,
                                           duration_seconds=body.duration_seconds)
    except PolicyDenied as exc:
        raise HTTPException(409, detail={"reason_code": exc.code}) from None
    except Exception:
        raise HTTPException(503, detail={"reason_code": "BROKER_CAPTURE_UNAVAILABLE"}) from None


@router.get("/{account_id}/observations/capture")
async def capture_status(account_id: str, request: Request):
    return capture_control.status(user_id=await owner(request), account_id=account_id)


@router.delete("/{account_id}/observations/capture", dependencies=[Depends(require_csrf)], status_code=202)
async def stop_capture(account_id: str, request: Request):
    try:
        return await capture_control.stop(user_id=await owner(request), account_id=account_id)
    except PolicyDenied as exc:
        raise HTTPException(409, detail={"reason_code": exc.code}) from None


@router.get("/{account_id}/observations")
async def observations(
    account_id: str, request: Request, limit: int = Query(1000, ge=1, le=1000), cursor: str | None = None
):
    user_id = await owner(request)
    try:
        async with asyncio.timeout(10), async_session.begin() as session:
            await session.execute(text("SET LOCAL statement_timeout = '5s'"))
            await session.execute(text("SET LOCAL lock_timeout = '2s'"))
            return await read_observations(session, user_id=user_id, account_id=account_id, limit=limit, cursor=cursor)
    except PolicyDenied as exc:
        raise HTTPException(409, detail={"reason_code": exc.code}) from None
    except Exception:
        raise HTTPException(503, detail={"reason_code": "BROKER_EVIDENCE_UNAVAILABLE"}) from None


@router.post("/{account_id}/observations/refresh", dependencies=[Depends(require_csrf)])
async def refresh(account_id: str, body: RefreshInput, request: Request):
    user_id = await owner(request)
    try:
        return await refresh_observations(user_id=user_id, account_id=account_id)
    except PolicyDenied as exc:
        raise HTTPException(409, detail={"reason_code": exc.code}) from None
    except WorkloadBusy:
        raise HTTPException(503, detail={"reason_code": "BROKER_OBSERVATION_BUSY"}) from None
    except TimeoutError:
        raise HTTPException(504, detail={"reason_code": "BROKER_OBSERVATION_TIMEOUT"}) from None
    except Exception:
        raise HTTPException(503, detail={"reason_code": "BROKER_OBSERVATION_UNAVAILABLE"}) from None
