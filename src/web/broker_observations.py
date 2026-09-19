"""Browser-owned local callback evidence and explicit broker read refresh."""

from typing import Literal
import asyncio

from fastapi import Query, Depends, Request, APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from src.web.auth import require_csrf, require_authenticated
from src.db.database import async_session
from src.execution.policy import PolicyDenied
from src.operations.workloads import WorkloadBusy
from src.execution.broker_monitor import refresh_observations
from src.execution.broker_observations import read_observations

router = APIRouter(prefix="/api/broker-accounts", dependencies=[Depends(require_authenticated)])


class RefreshInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_broker_read: Literal[True]


async def owner(request):
    principal = await require_authenticated(request)
    if not principal.user_id or principal.mechanism != "cookie":
        raise HTTPException(403, "An authenticated browser account is required")
    return principal.user_id


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
