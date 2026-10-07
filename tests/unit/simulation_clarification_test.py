"""Ambiguous simulation instruments must not become fabricated data symbols."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.config import Settings
from src.agent.clients import llama_cpp_client as client


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("prompt", [
    "Backtest it again.",
    "Simulate Apple from 2024-01-01.",
    "Backtest a momentum strategy for SPYL on Xetra from 2024-01-01.",
])
async def test_ambiguous_instrument_requests_clarification_without_simulation(monkeypatch, prompt, native):
    local = client.LlamaCppClient.__new__(client.LlamaCppClient)
    local._inference_lock = asyncio.Lock()
    monkeypatch.setattr(client, "settings", Settings(_env_file=None, llm_native_tool_calling=native))
    dispatch = AsyncMock(return_value='{"status":"unavailable"}')
    monkeypatch.setattr(client, "dispatch_tool", dispatch)
    events = [event async for event in local.stream_response([{"role": "user", "content": prompt}], "fixture")]
    dispatch.assert_not_awaited()
    answer = next(event for event in events if event["type"] == "final_answer")
    assert answer["generation"] == "instrument_clarification"
    assert "symbol" in answer["text"].lower()
    assert events[-1]["type"] == "done"


def test_unavailable_simulation_result_cannot_become_zero_return_success():
    answer = client._format_simulation_result({"status": "unavailable"})
    assert "Simulation complete" not in answer
    assert "0.00" not in answer
    assert "unavailable" in answer.lower()


async def test_ambiguous_simulation_keeps_independent_portfolio_read(monkeypatch):
    local = client.LlamaCppClient.__new__(client.LlamaCppClient)
    local._inference_lock = asyncio.Lock()
    monkeypatch.setattr(client, "settings", Settings(_env_file=None, llm_native_tool_calling=False))
    dispatch = AsyncMock(return_value='{"status":"unavailable","holdings":[]}')
    monkeypatch.setattr(client, "dispatch_tool", dispatch)
    events = [event async for event in local.stream_response([{"role": "user", "content":
        "Show my portfolio. Backtest it again."}], "fixture")]
    dispatch.assert_awaited_once_with("get_portfolio_summary", {})
    assert "Portfolio evidence" in next(event["text"] for event in events if event["type"] == "final_answer")


@pytest.mark.parametrize("value", [{}, [], {"status": "blocked"}, {"final_value": "NaN"}])
def test_missing_or_invalid_calculation_never_reports_success(value):
    assert "unavailable" in client._format_simulation_result(value).lower()


def test_partial_storage_and_source_currency_remain_visible():
    fixture = dict(name="synthetic", symbols=["FIXTURE"], period_start="2025-01-01", period_end="2025-02-01",
                   initial_capital="100", final_value="101", total_return_pct="1", trades_count=1,
                   base_currency="EUR", status="partial_failure")
    answer = client._format_simulation_result(fixture)
    assert "persistence incomplete" in answer and "101.00 EUR" in answer and "$" not in answer
    assert "Simulation complete" not in answer


def test_explicit_provider_symbols_remain_usable():
    result = client._simulation_request([{"role": "user", "content":
        "Backtest momentum for SPYL.DE from 2024-01-01."}])
    assert result["symbols"] == ["SPYL.DE"] and "clarification" not in result
