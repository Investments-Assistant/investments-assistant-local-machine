import uuid
import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text, delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.chat import retention
from src.db.models import User, ChatMessage, Conversation
from src.chat.evidence import message_turn_fields
from src.execution.policy import PolicyDenied

pytestmark = pytest.mark.integration


async def seed(session):
    owners = [str(uuid.uuid4()), str(uuid.uuid4())]
    now = datetime.now(UTC)
    session.add_all([User(id=owner, username=uuid.uuid4().hex, password_hash="fixture") for owner in owners])
    conversations, messages = [], []
    for owner, days, state in [
        (owners[0], 60, "complete"), (owners[0], 60, "in_progress"),
        (owners[0], 1, "complete"), (owners[1], 60, "complete"),
    ]:
        conversation = Conversation(
            id=str(uuid.uuid4()), user_id=owner, title="Private synthetic title",
            updated_at=now - timedelta(days=days), last_message_at=now - timedelta(days=days),
        )
        session.add(conversation)
        conversations.append(conversation)
        for role in ["user", "assistant"]:
            message = ChatMessage(
                id=str(uuid.uuid4()), user_id=owner, session_id=conversation.id,
                role=role, content="Private synthetic message",
                tool_calls={"schema": 1, "state": state, "evidence": [{"secret_fixture": True}]}
                if role == "assistant" else None,
                created_at=now - timedelta(days=days),
            )
            messages.append(message)
            session.add(message)
    await session.flush()
    return owners, conversations, messages, retention.ChatRetentionPolicy(retain_days=30, as_of=now), now


async def test_retention_excludes_active_recent_and_other_owner_and_keeps_evidence_ids(db_session):
    owners, conversations, messages, policy, now = await seed(db_session)
    plan, _, _ = await retention.chat_plan(db_session, user_id=owners[0], policy=policy, now=now)
    assert plan["message_count"] == 2 and plan["conversation_count"] == 1 and plan["active_turns_excluded"]
    assert "Private synthetic" not in str(plan)
    previous_clock = conversations[0].updated_at
    result = await retention.remove_chat_content(
        db_session, user_id=owners[0], policy=policy, expected_plan=plan["plan_sha256"], now=now,
    )
    assert result["removed_messages"] == 2
    for message in messages[:2]:
        await db_session.refresh(message)
        assert "Private synthetic" not in message.content
        assert message.tool_calls["state"] == "retired" and message.tool_calls["evidence"] == []
        assert message.tool_calls["retention"]["content_sha256"]
    assert not message_turn_fields(messages[0])
    assert message_turn_fields(messages[1])["turn"]["evidence_url"].endswith(messages[1].id + "/evidence")
    assert all(message.content == "Private synthetic message" for message in messages[2:])
    await db_session.refresh(conversations[0])
    assert conversations[0].title == "Removed chat content" and conversations[0].updated_at == previous_clock
    assert (await retention.chat_plan(db_session, user_id=owners[0], policy=policy, now=now))[0]["message_count"] == 0


@pytest.mark.parametrize("change", ["content", "active", "owner", "inactive", "expired"])
async def test_changed_or_unauthorized_preview_never_erases_messages(db_session, change):
    owners, conversations, messages, policy, now = await seed(db_session)
    plan, _, _ = await retention.chat_plan(db_session, user_id=owners[0], policy=policy, now=now)
    selected_owner = owners[0]
    if change == "content":
        messages[0].content = "Revised fixture"
    elif change == "active":
        messages[1].tool_calls = {"schema": 1, "state": "in_progress", "evidence": []}
    elif change == "owner":
        selected_owner = owners[1]
    elif change == "inactive":
        (await db_session.get(User, selected_owner)).is_active = False
    elif change == "expired":
        now += timedelta(minutes=11)
    await db_session.flush()
    with pytest.raises(PolicyDenied):
        await retention.remove_chat_content(
            db_session, user_id=selected_owner, policy=policy, expected_plan=plan["plan_sha256"], now=now,
        )
    assert messages[0].content in {"Private synthetic message", "Revised fixture"}
    assert conversations[0].title == "Private synthetic title"


async def test_bounded_batches_make_progress_without_changing_activity_clock(db_session, monkeypatch):
    owners, _, _, policy, now = await seed(db_session)
    monkeypatch.setattr(retention, "MESSAGE_LIMIT", 1)
    for _ in range(2):
        plan, _, _ = await retention.chat_plan(db_session, user_id=owners[0], policy=policy, now=now)
        assert plan["message_count"] == 1 and plan["may_have_more"]
        await retention.remove_chat_content(
            db_session, user_id=owners[0], policy=policy, expected_plan=plan["plan_sha256"], now=now,
        )
    plan, _, _ = await retention.chat_plan(db_session, user_id=owners[0], policy=policy, now=now)
    assert plan["message_count"] == 0
    remaining = list(await db_session.scalars(select(ChatMessage).where(ChatMessage.user_id == owners[0])))
    assert sum(bool(message.tool_calls) and message.tool_calls.get("state") == "retired" for message in remaining) == 2


async def test_new_turn_wins_lock_race_without_retention_erasing_its_history(integration_engine):
    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with factory.begin() as session:
        owners, conversations, _, policy, now = await seed(session)
        plan, _, _ = await retention.chat_plan(session, user_id=owners[0], policy=policy, now=now)
    application = "retention-race-" + uuid.uuid4().hex
    task = None

    async def remove():
        async with factory.begin() as session:
            await session.execute(text("SELECT set_config('application_name', :name, true)"), {"name": application})
            return await retention.remove_chat_content(
                session, user_id=owners[0], policy=policy, expected_plan=plan["plan_sha256"], now=now,
            )

    try:
        async with factory.begin() as writer:
            conversation = await writer.scalar(select(Conversation).where(
                Conversation.id == conversations[0].id,
            ).with_for_update())
            conversation.updated_at = now
            writer.add(ChatMessage(
                user_id=owners[0], session_id=conversation.id, role="assistant", content="",
                tool_calls={"schema": 1, "state": "in_progress", "evidence": []},
            ))
            await writer.flush()
            task = asyncio.create_task(remove())
            async with asyncio.timeout(5):
                while True:
                    async with factory() as observer:
                        waiting = await observer.scalar(text(
                            "SELECT wait_event_type FROM pg_stat_activity WHERE application_name = :name"
                        ), {"name": application})
                    if waiting == "Lock":
                        break
                    assert not task.done(), "Retention must wait for the conversation writer"
                    await asyncio.sleep(0.01)
        with pytest.raises(PolicyDenied, match="RETENTION_PLAN_CHANGED"):
            await asyncio.wait_for(task, 5)
        async with factory() as session:
            rows = list(await session.scalars(select(ChatMessage).where(
                ChatMessage.session_id == conversations[0].id,
            )))
            assert len(rows) == 3
            assert sum(row.content == "Private synthetic message" for row in rows) == 2
            assert not any((row.tool_calls or {}).get("state") == "retired" for row in rows)
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        async with factory.begin() as session:
            await session.execute(delete(ChatMessage).where(ChatMessage.user_id.in_(owners)))
            await session.execute(delete(Conversation).where(Conversation.user_id.in_(owners)))
            await session.execute(delete(User).where(User.id.in_(owners)))
