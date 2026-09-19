"""Durable chat completion, interruption and owner isolation on marked PostgreSQL."""

import json
import uuid
from types import SimpleNamespace
import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db import database
from src.web import chat_routes
from src.chat import persistence
from src.agent import orchestrator as module
from src.config import Settings
from src.db.models import User, ChatMessage, Conversation

pytestmark = pytest.mark.integration


class FixtureClient:
    async def stream_response(self, messages, system, max_tokens=None):
        yield {
            "type": "tool_call",
            "name": "propose_trade",
            "input": {
                "symbol": "SPYL",
                "quantity": "0.004",
                "confirmation_nonce": "synthetic-secret",
            },
        }
        yield {
            "type": "tool_result",
            "name": "propose_trade",
            "result": json.dumps(
                {
                    "status": "proposed",
                    "quantity": "0.004",
                    "currency": "EUR",
                    "broker_order_id": None,
                    "api_key": "synthetic-secret",
                }
            ),
        }
        yield {"type": "final_answer", "text": "A proposal is awaiting independent human approval."}
        yield {"type": "done"}


@pytest_asyncio.fixture
async def chat_fixture(integration_engine, monkeypatch):
    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    owner, other, conversation = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    monkeypatch.setattr(persistence, "async_session", factory)
    monkeypatch.setattr(database, "async_session", factory)
    monkeypatch.setattr(chat_routes, "async_session", factory)
    monkeypatch.setattr(module, "settings", Settings(_env_file=None, environment="production"))
    monkeypatch.setattr(module, "create_llm_client", lambda: FixtureClient())
    monkeypatch.setattr(module, "load_user_broker_accounts", AsyncMock(return_value=[]))
    async with factory.begin() as session:
        for user_id in (owner, other):
            session.add(
                User(id=user_id, username=uuid.uuid4().hex, password_hash="fixture", is_active=True)
            )
    try:
        yield factory, owner, other, conversation
    finally:
        async with factory.begin() as session:
            await session.execute(
                delete(ChatMessage).where(ChatMessage.user_id.in_([owner, other]))
            )
            await session.execute(
                delete(Conversation).where(Conversation.user_id.in_([owner, other]))
            )
            await session.execute(delete(User).where(User.id.in_([owner, other])))


async def stored(factory, owner):
    async with factory() as session:
        return await session.scalar(
            select(ChatMessage).where(ChatMessage.user_id == owner, ChatMessage.role == "assistant")
        )


async def test_completed_turn_saved_before_done_and_restored_with_redacted_evidence(
    chat_fixture, monkeypatch
):
    factory, owner, other, conversation = chat_fixture
    agent = module.InvestmentsAssistantOrchestrator(conversation, owner)
    events = []
    async for event in agent.chat("Propose a synthetic fractional purchase; do not submit."):
        events.append(event)
        if event["type"] in {"final_answer", "done"}:
            assert (await stored(factory, owner)).tool_calls["state"] == "complete"
    assert events[-1]["type"] == "done" and events[-1]["persistence"] == "saved"
    row = await stored(factory, owner)
    data = row.tool_calls
    assert len(data["evidence"]) == 2 and data["state"] == "complete"
    assert "synthetic-secret" not in json.dumps(data)
    assert data["evidence"][1]["payload"]["status"] == "proposed"
    assert data["evidence"][1]["payload"]["quantity"] == "0.004"
    fresh = module.InvestmentsAssistantOrchestrator(conversation, owner)
    await fresh.load_history_from_db()
    assert "Historical evidence" in fresh.history[-1]["content"]
    assert "not proof of broker submission or fills" in fresh.history[-1]["content"]
    monkeypatch.setattr(
        chat_routes, "require_authenticated", AsyncMock(return_value=SimpleNamespace(user_id=owner))
    )
    response = await chat_routes.evidence(row.id, None)
    assert json.loads(response.body)["state"] == "complete"
    monkeypatch.setattr(
        chat_routes, "require_authenticated", AsyncMock(return_value=SimpleNamespace(user_id=other))
    )
    with pytest.raises(HTTPException) as error:
        await chat_routes.evidence(row.id, None)
    assert error.value.status_code == 404
    with pytest.raises(persistence.ChatPersistenceError, match="TURN_NOT_OWNED"):
        await persistence.save_turn(
            user_id=other,
            session_id=conversation,
            turn_id=row.id,
            state="complete",
            evidence=[],
            content="forged",
        )
    with pytest.raises(persistence.ChatPersistenceError, match="TURN_ALREADY_TERMINAL"):
        await persistence.save_turn(
            user_id=owner,
            session_id=conversation,
            turn_id=row.id,
            state="complete",
            evidence=[],
            content="edited",
        )


async def test_cancellation_keeps_received_tool_evidence_and_interrupted_state(chat_fixture):
    factory, owner, _, conversation = chat_fixture
    agent = module.InvestmentsAssistantOrchestrator(conversation, owner)
    received = asyncio.Event()

    class Slow:
        async def stream_response(self, **kwargs):
            yield {
                "type": "tool_result",
                "name": "get_portfolio_summary",
                "result": {"available": False},
            }
            await asyncio.Event().wait()

    agent._client = Slow()

    async def consume():
        async for event in agent.chat("Read scoped evidence"):
            if event["type"] == "tool_result":
                received.set()

    task = asyncio.create_task(consume())
    await asyncio.wait_for(received.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    row = await stored(factory, owner)
    assert row.tool_calls["state"] == "interrupted" and len(row.tool_calls["evidence"]) == 1
    assert not row.content


async def test_final_storage_failure_never_emits_saved_answer_or_done(chat_fixture, monkeypatch):
    factory, owner, _, conversation = chat_fixture
    original = module.save_turn

    async def fail_complete(**kwargs):
        if kwargs["state"] == "complete":
            raise RuntimeError("synthetic storage failure")
        return await original(**kwargs)

    monkeypatch.setattr(module, "save_turn", fail_complete)
    agent = module.InvestmentsAssistantOrchestrator(conversation, owner)
    events = [event async for event in agent.chat("Synthetic request")]
    assert not any(event["type"] in {"final_answer", "done"} for event in events)
    assert events[-1]["code"] == "CHAT_NOT_COMPLETED"
    assert (await stored(factory, owner)).tool_calls["state"] == "interrupted"


async def test_model_error_is_durable_failed_turn(chat_fixture):
    factory, owner, _, conversation = chat_fixture
    agent = module.InvestmentsAssistantOrchestrator(conversation, owner)

    class Failed:
        async def stream_response(self, **kwargs):
            yield {"type": "error", "message": "synthetic model error"}
            yield {"type": "done"}

    agent._client = Failed()
    events = [event async for event in agent.chat("Synthetic request")]
    assert events[-1]["code"] == "MODEL_INCOMPLETE" and events[-1]["persistence"] == "saved"
    assert (await stored(factory, owner)).tool_calls["state"] == "failed"


async def test_next_turn_replaces_cached_content_and_omits_retired_evidence(chat_fixture):
    factory, owner, _, conversation = chat_fixture
    agent = module.InvestmentsAssistantOrchestrator(conversation, owner)
    _ = [event async for event in agent.chat("Private synthetic old request")]
    async with factory.begin() as session:
        rows = list(await session.scalars(select(ChatMessage).where(ChatMessage.session_id == conversation)))
        for row in rows:
            row.content = "Content removed by owner"
            row.tool_calls = {"schema": 1, "state": "retired", "evidence": []}
    assert "Private synthetic old request" in str(agent.history)
    received = []

    class Read:
        async def stream_response(self, messages, **kwargs):
            received.extend(messages)
            yield {"type": "final_answer", "text": "Fresh fixture answer"}
            yield {"type": "done"}

    agent._client = Read()
    events = [event async for event in agent.chat("Fresh request")]
    assert events[-1]["type"] == "done"
    assert received == [{"role": "user", "content": "Fresh request"}]


async def test_history_read_failure_clears_cache_and_never_invokes_model(chat_fixture, monkeypatch):
    factory, owner, _, conversation = chat_fixture
    agent = module.InvestmentsAssistantOrchestrator(conversation, owner)
    agent.history = [{"role": "user", "content": "private stale fixture"}]
    invoked = []

    class Unused:
        async def stream_response(self, **kwargs):
            invoked.append(True)
            yield {"type": "final_answer", "text": "Must not run"}

    def fail_history():
        raise RuntimeError("private storage diagnostic")

    agent._client = Unused()
    # Persistence has its separate bound factory; fail only history/profile reads.
    monkeypatch.setattr(database, "async_session", fail_history)
    events = [event async for event in agent.chat("New fixture request")]
    assert not invoked and agent.history == []
    assert events[-1]["code"] == "CHAT_NOT_COMPLETED"
    assert "private storage diagnostic" not in str(events)
    assert (await stored(factory, owner)).tool_calls["state"] == "interrupted"
