"""Owner-scoped immutable terminal chat evidence download."""

from fastapi import Depends, Request, APIRouter, HTTPException
from sqlalchemy import select
from fastapi.responses import JSONResponse

from src.web.auth import require_authenticated
from src.db.models import ChatMessage
from src.db.database import async_session

router = APIRouter(prefix="/api/chat/turns", dependencies=[Depends(require_authenticated)])


@router.get("/{turn_id}/evidence")
async def evidence(turn_id: str, request: Request):
    principal = await require_authenticated(request)
    if not principal.user_id:
        raise HTTPException(401, "Authenticated owner required")
    async with async_session() as session:
        message = await session.scalar(
            select(ChatMessage).where(
                ChatMessage.id == turn_id,
                ChatMessage.user_id == principal.user_id,
                ChatMessage.role == "assistant",
            )
        )
        if (
            message is None
            or not isinstance(message.tool_calls, dict)
            or message.tool_calls.get("schema") != 1
        ):
            raise HTTPException(404, "Chat evidence not found")
        return JSONResponse(
            message.tool_calls,
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": 'attachment; filename="chat-evidence.json"',
            },
        )
