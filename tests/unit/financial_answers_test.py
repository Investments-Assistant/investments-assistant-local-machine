"""Financial chat facts retain exact source values and never infer missing totals."""

import json
import asyncio
from unittest.mock import AsyncMock

from src.config import Settings
from src.agent.clients import llama_cpp_client as client
from src.finance.answers import portfolio_facts, financial_answer

FIXTURE = {"holdings": [{"symbol": "FIXTURE", "quantity_exact": "0.004", "price": "100",
                        "currency": "EUR", "value_usd": None}], "valuation_status": "partial"}


def test_fractional_source_facts_never_invent_portfolio_value():
    facts = portfolio_facts(json.dumps(FIXTURE))
    position = facts["positions"][0]
    assert position["quantity"] == "0.004" and position["source_price"] == "100"
    assert position["source_currency"] == "EUR"
    assert position["source_market_value"] is None
    assert facts["reported_total_market_value_usd"] is None
    assert position["as_of"] is None


def test_high_precision_and_unavailable_currency_are_preserved():
    facts = portfolio_facts('{"positions":[{"qty":0.004000000001,"market_price":100.000000001}]}')
    assert facts["positions"][0]["quantity"] == "0.004000000001"
    assert facts["positions"][0]["source_price"] is None
    assert portfolio_facts('{"status":"blocked"}')["status"] == "unavailable"
    assert portfolio_facts('not JSON')["status"] == "unavailable"


def test_multiscope_output_retains_news_and_markets_with_safe_structured_omission():
    answer = financial_answer({"get_portfolio_summary": json.dumps(FIXTURE),
                               "get_latest_news": '{"articles":[{"title":"Synthetic news"}]}',
                               "get_market_overview": '{"status":"unavailable"}'})
    assert "Synthetic news" in answer and "get_market_overview" in answer
    assert "No totals" in answer
    oversized = financial_answer({"get_portfolio_summary": json.dumps(FIXTURE),
                                  "get_latest_news": json.dumps({"text": "x" * 5000})})
    assert "evidence_budget_exceeded" in oversized
    for part in oversized.split("```json\n")[1:]:
        json.loads(part.split("\n```")[0])


async def test_default_financial_workflow_has_no_unchecked_model_arithmetic(monkeypatch):
    local = client.LlamaCppClient.__new__(client.LlamaCppClient)
    local._inference_lock = asyncio.Lock()
    monkeypatch.setattr(client, "settings", Settings(_env_file=None, llm_native_tool_calling=False))
    monkeypatch.setattr(client, "dispatch_tool", AsyncMock(return_value=json.dumps(FIXTURE)))

    async def forbidden_model(*args, **kwargs):
        raise AssertionError("Financial source amounts must not depend on model arithmetic")
        yield  # pragma: no cover

    local._stream_completion = forbidden_model
    events = [event async for event in local.stream_response(
        [{"role": "user", "content": "Como está a minha carteira?"}], "fixture")]
    answer = next(event for event in events if event["type"] == "final_answer")
    assert answer["generation"] == "deterministic_financial_evidence"
    assert '"quantity": "0.004"' in answer["text"]
    assert '"source_market_value": null' in answer["text"]
    assert "4,00" not in answer["text"]


async def test_native_model_valuation_is_replaced_by_exact_source_facts(monkeypatch):
    local = client.LlamaCppClient.__new__(client.LlamaCppClient)
    local._inference_lock = asyncio.Lock()
    monkeypatch.setattr(client, "settings", Settings(_env_file=None, llm_native_tool_calling=True,
                                                    agent_max_tool_rounds=2, agent_max_tokens=128))
    dispatch = AsyncMock(return_value=json.dumps(FIXTURE))
    monkeypatch.setattr(client, "dispatch_tool", dispatch)
    calls = 0

    async def completion(messages, tools, max_tokens=None):
        nonlocal calls
        calls += 1
        assert "get_portfolio_summary" in {tool["function"]["name"] for tool in tools}
        if calls == 1:
            yield {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "fixture-portfolio",
                   "function": {"name": "get_portfolio_summary", "arguments": "{}"}}]},
                   "finish_reason": "tool_calls"}]}
        else:
            yield {"choices": [{"delta": {"content": "A sua carteira vale EUR 4.00."}, "finish_reason": "stop"}]}

    local._stream_completion = completion
    events = [event async for event in local.stream_response(
        [{"role": "user", "content": "Como está a minha carteira?"}], "fixture")]
    answer = next(event for event in events if event["type"] == "final_answer")
    assert answer["generation"] == "deterministic_financial_evidence"
    assert "EUR 4.00" not in answer["text"]
    assert '"quantity": "0.004"' in answer["text"]
    dispatch.assert_awaited_once_with("get_portfolio_summary", {})
