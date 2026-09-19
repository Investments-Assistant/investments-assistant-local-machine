"""Persist turn state and tool evidence before declaring a chat response complete."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from src.db.models import ChatMessage, Conversation
from src.db.database import async_session
from src.chat.evidence import envelope
from src.security.sessions import assert_active


class ChatPersistenceError(RuntimeError):
    pass


async def begin_turn(*, user_id, session_id, user_message):
    if not user_id:
        raise ChatPersistenceError("CHAT_OWNER_REQUIRED")
    turn_id = str(uuid.uuid4())
    async with async_session.begin() as session:
        await assert_active(session, user_id)
        await session.execute(
            insert(Conversation)
            .values(
                id=session_id,
                user_id=user_id,
                title=" ".join(user_message.split())[:80] or "New chat",
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        conversation = await session.scalar(
            select(Conversation)
            .where(Conversation.id == session_id, Conversation.user_id == user_id)
            .with_for_update()
        )
        if conversation is None:
            raise ChatPersistenceError("CONVERSATION_NOT_OWNED")
        now = datetime.now(UTC)
        conversation.updated_at = conversation.last_message_at = now
        session.add(
            ChatMessage(session_id=session_id, user_id=user_id, role="user", content=user_message)
        )
        session.add(
            ChatMessage(
                id=turn_id,
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content="",
                tool_calls=envelope("in_progress", []),
            )
        )
    return turn_id


async def save_turn(*, user_id, session_id, turn_id, state, evidence, content="", omitted_events=0):
    if state not in {"in_progress", "complete", "failed", "interrupted"}:
        raise ValueError("Invalid chat turn state")
    async with async_session.begin() as session:
        if state != "interrupted":
            await assert_active(session, user_id)
        # Consistent conversation-before-message lock order for append, save,
        # owner deletion and retention. Never recreate a removed conversation.
        conversation = await session.scalar(
            select(Conversation)
            .where(Conversation.id == session_id, Conversation.user_id == user_id)
            .with_for_update()
        )
        if conversation is None:
            raise ChatPersistenceError("TURN_NOT_OWNED")
        message = await session.scalar(
            select(ChatMessage)
            .where(
                ChatMessage.id == turn_id,
                ChatMessage.user_id == user_id,
                ChatMessage.session_id == session_id,
                ChatMessage.role == "assistant",
            )
            .with_for_update()
        )
        if message is None:
            raise ChatPersistenceError("TURN_NOT_OWNED")
        current = message.tool_calls or {}
        if current.get("state") != "in_progress":
            raise ChatPersistenceError("TURN_ALREADY_TERMINAL")
        message.content = content
        message.tool_calls = envelope(state, evidence, omitted_events)
        conversation.updated_at = conversation.last_message_at = datetime.now(UTC)
