"""Explicit removal of inactive owned chat content while preserving evidence IDs."""

from datetime import UTC, datetime, timedelta

from pydantic import Field, BaseModel, ConfigDict
from sqlalchemy import Text, cast, func, select, update

from src.db.models import User, ChatMessage, Conversation
from src.execution.policy import PolicyDenied, digest

CONVERSATION_LIMIT = 20
MESSAGE_LIMIT = 500


class ChatRetentionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    retain_days: int = Field(ge=1, le=36525, strict=True)
    as_of: datetime

    def cutoff(self, now):
        if self.as_of.tzinfo is None or not now - timedelta(minutes=10) <= self.as_of <= now:
            raise PolicyDenied("RETENTION_PREVIEW_EXPIRED")
        return self.as_of - timedelta(days=self.retain_days)


def hashed(value):
    return func.encode(func.sha256(func.convert_to(cast(value, Text), "UTF8")), "hex")


async def chat_plan(session, *, user_id, policy, now=None, lock=False):
    cutoff = policy.cutoff(now or datetime.now(UTC))
    if not user_id or not await session.scalar(
        select(User.id).where(User.id == user_id, User.is_active.is_(True)).with_for_update(read=True)
    ):
        raise PolicyDenied("PRINCIPAL_INACTIVE")
    owned_messages = select(ChatMessage.id).where(
        ChatMessage.user_id == user_id, ChatMessage.session_id == Conversation.id,
    ).correlate(Conversation)
    unretired = ChatMessage.tool_calls["state"].as_string().is_distinct_from("retired")
    active = ChatMessage.tool_calls["state"].as_string() == "in_progress"
    query = select(
        Conversation.id, Conversation.updated_at, Conversation.last_message_at,
        hashed(Conversation.title).label("title_sha256"),
    ).where(
        Conversation.user_id == user_id, Conversation.updated_at < cutoff,
        owned_messages.where(unretired).exists(), ~owned_messages.where(active).exists(),
    ).order_by(Conversation.updated_at, Conversation.id).limit(CONVERSATION_LIMIT)
    if lock:
        query = query.with_for_update()
    conversations = (await session.execute(query)).all()
    message_query = select(
        ChatMessage.id, ChatMessage.session_id,
        hashed(func.jsonb_build_array(ChatMessage.content, ChatMessage.tool_calls)).label("content_sha256"),
    ).where(
        ChatMessage.user_id == user_id, ChatMessage.session_id.in_([c.id for c in conversations]), unretired,
    ).order_by(ChatMessage.created_at, ChatMessage.id).limit(MESSAGE_LIMIT)
    if lock:
        message_query = message_query.with_for_update()
    messages = (await session.execute(message_query)).all()
    identity = {
        "owner": user_id, "policy": policy.model_dump(mode="json"),
        "conversations": [dict(id=c.id, changed=c.updated_at.isoformat(), title_sha256=c.title_sha256)
                          for c in conversations],
        "messages": [dict(id=m.id, sha256=m.content_sha256) for m in messages],
    }
    return {
        "policy": identity["policy"], "scope": "inactive_chat_content_and_evidence",
        "message_count": len(messages), "conversation_count": len({m.session_id for m in messages}),
        "message_limit": MESSAGE_LIMIT, "conversation_limit": CONVERSATION_LIMIT,
        "may_have_more": len(messages) == MESSAGE_LIMIT or len(conversations) == CONVERSATION_LIMIT,
        "active_turns_excluded": True, "plan_sha256": digest(identity),
        "retained": "Message/conversation IDs, owners, dates and content digests; reports and source ledgers remain",
    }, conversations, messages


async def remove_chat_content(session, *, user_id, policy, expected_plan, now=None):
    now = now or datetime.now(UTC)
    plan, conversations, messages = await chat_plan(session, user_id=user_id, policy=policy, now=now, lock=True)
    if plan["plan_sha256"] != expected_plan:
        raise PolicyDenied("RETENTION_PLAN_CHANGED")
    for message in messages:
        await session.execute(update(ChatMessage).where(
            ChatMessage.id == message.id, ChatMessage.user_id == user_id,
        ).values(content="Chat content removed by its owner.", tool_calls={
            "schema": 1, "state": "retired", "evidence": [], "omitted_events": 0,
            "retention": {
                "content_sha256": message.content_sha256, "plan_sha256": expected_plan,
                "removed_at": now.isoformat(),
            },
            "execution_basis": "Content was removed; this tombstone proves no broker action.",
        }))
    affected = {m.session_id for m in messages}
    for conversation in conversations:
        if conversation.id in affected:
            await session.execute(update(Conversation).where(
                Conversation.id == conversation.id, Conversation.user_id == user_id,
            ).values(
                title="Removed chat content", updated_at=conversation.updated_at,
                last_message_at=conversation.last_message_at,
            ))
    await session.flush()
    return {
        "status": "complete", "removed_messages": len(messages), "affected_conversations": len(affected),
        "may_have_more": plan["may_have_more"], "active_turns_excluded": True,
    }
