"""Independent browser preview/confirmation for inactive chat-content retention."""

from typing import Literal
import asyncio
from datetime import UTC, datetime

from fastapi import Depends, Request, APIRouter, HTTPException
from pydantic import Field, BaseModel, ConfigDict
from sqlalchemy import text

from src.web.auth import require_csrf, require_authenticated
from src.db.database import async_session
from src.chat.retention import ChatRetentionPolicy, chat_plan, remove_chat_content
from src.execution.policy import PolicyDenied

router = APIRouter(
    prefix="/api/chat/retention", dependencies=[Depends(require_authenticated), Depends(require_csrf)]
)


class PreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    retain_days: int = Field(ge=1, le=36525, strict=True)


class ApplyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy: ChatRetentionPolicy
    plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirm_chat_content_removal: Literal[True]


async def owner(request):
    principal = await require_authenticated(request)
    if not principal.user_id or principal.mechanism != "cookie":
        raise HTTPException(403, "An authenticated browser account is required")
    return principal.user_id


@router.post("/preview")
async def preview(body: PreviewInput, request: Request):
    user_id = await owner(request)
    policy = ChatRetentionPolicy(retain_days=body.retain_days, as_of=datetime.now(UTC))
    try:
        async with asyncio.timeout(10), async_session.begin() as session:
            await session.execute(text("SET LOCAL statement_timeout = '5s'"))
            plan, _, _ = await chat_plan(session, user_id=user_id, policy=policy)
            return plan
    except PolicyDenied as exc:
        raise HTTPException(409, detail={"reason_code": exc.code}) from None
    except Exception:
        raise HTTPException(503, detail={"reason_code": "CHAT_RETENTION_UNAVAILABLE"}) from None


@router.post("/apply")
async def apply_retention(body: ApplyInput, request: Request):
    user_id = await owner(request)
    try:
        async with asyncio.timeout(10), async_session.begin() as session:
            await session.execute(text("SET LOCAL statement_timeout = '5s'"))
            await session.execute(text("SET LOCAL lock_timeout = '2s'"))
            return await remove_chat_content(
                session, user_id=user_id, policy=body.policy, expected_plan=body.plan_sha256
            )
    except PolicyDenied as exc:
        raise HTTPException(409, detail={"reason_code": exc.code}) from None
    except Exception:
        raise HTTPException(503, detail={"reason_code": "CHAT_RETENTION_UNAVAILABLE"}) from None
