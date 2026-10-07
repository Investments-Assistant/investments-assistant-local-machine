"""Native inference budgeting preserves event evidence and valid context JSON."""

import json
import asyncio
from unittest.mock import AsyncMock

from src.config import Settings
from src.agent.clients import llama_cpp_client as client


async def test_oversized_native_result_preserves_event_and_returns_structured_context(monkeypatch):
    local = client.LlamaCppClient.__new__(client.LlamaCppClient)
    local._inference_lock = asyncio.Lock()
    payload = {"articles": [{"title": "Fixture", "summary": "é" * 4000}], "status": "complete"}
    serialized = json.dumps(payload, ensure_ascii=False)
    dispatch = AsyncMock(return_value=serialized)
    monkeypatch.setattr(client, "dispatch_tool", dispatch)
    monkeypatch.setattr(client, "settings", Settings(_env_file=None, llm_native_tool_calling=True,
                        agent_max_tokens=128, agent_max_tool_rounds=2, agent_max_tool_result_chars=1000))
    calls = 0

    async def completion(messages, tools, max_tokens=None, response_schema=None, preserve_context=False):
        nonlocal calls
        if response_schema:
            yield {"choices": [{"delta": {"content": json.dumps({
                "status": "abstain", "observations": [], "missing_data": ["price_context"]
            })}, "finish_reason": "stop"}]}
            return
        calls += 1
        if calls == 1:
            yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "fixture-budget",
                   "function": {"name": "get_latest_news", "arguments": "{}"}}]},
                   "finish_reason": "tool_calls"}]}
        else:
            evidence = json.loads(next(m["content"] for m in reversed(messages) if m["role"] == "tool"))
            assert evidence["status"] == "evidence_budget_exceeded"
            assert evidence["original_characters"] == len(serialized)
            assert "articles" not in evidence
            yield {"choices": [{"delta": {"content": "Narrow the news request to fit the evidence budget."},
                                "finish_reason": "stop"}]}

    local._stream_completion = completion
    events = [event async for event in local.stream_response(
        [{"role": "user", "content": "Show latest stored news."}], "fixture")]
    result = next(event for event in events if event["type"] == "tool_result")
    assert result["result"] == serialized
    assert json.loads(result["result"]) == payload
    dispatch.assert_awaited_once_with("get_latest_news", {})
    assert calls == 2 and events[-1]["type"] == "done"
