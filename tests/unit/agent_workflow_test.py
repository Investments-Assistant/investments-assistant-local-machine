"""Tests for deterministic workflows used by the CPU-safe local agent path."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.clients import llama_cpp_client
from src.agent.clients.llama_cpp_client import (
    _format_market_overview_result,
    _format_news_result,
    _format_simulation_result,
    _looks_like_intermediate_response,
    _prefetch_request,
    _report_request,
    _simulation_request,
)


@pytest.mark.unit
def test_report_request_defaults_to_the_last_seven_days(monkeypatch):
    class FrozenDate(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 8, 13, tzinfo=UTC)

    monkeypatch.setattr("src.agent.clients.llama_cpp_client.datetime", FrozenDate)
    result = _report_request(
        [{"role": "user", "content": "Generate my weekly investment report for the past 7 days."}]
    )
    assert result == {"period_start": "2026-08-06", "period_end": "2026-08-13"}


@pytest.mark.unit
def test_report_request_preserves_explicit_period():
    result = _report_request(
        [{"role": "user", "content": "Create a report from 2026-01-01 to 2026-01-31."}]
    )
    assert result == {"period_start": "2026-01-01", "period_end": "2026-01-31"}


@pytest.mark.unit
def test_simulation_request_parses_quick_prompt():
    result = _simulation_request(
        [
            {
                "role": "user",
                "content": "Run a buy-and-hold simulation on AAPL, MSFT, NVDA from 2022-01-01.",
            }
        ]
    )
    assert result is not None
    assert result["symbols"] == ["AAPL", "MSFT", "NVDA"]
    assert result["strategy"] == {"type": "buy_and_hold"}
    assert result["period_start"] == "2022-01-01"


@pytest.mark.unit
def test_simulation_result_is_actionable_and_safe():
    text = _format_simulation_result(
        {
            "name": "test",
            "symbols": ["AAPL"],
            "period_start": "2024-01-01",
            "period_end": "2024-12-31",
            "initial_capital": 10_000,
            "final_value": 11_000,
            "total_return_pct": 10.0,
            "sharpe_ratio": 1.2,
            "max_drawdown_pct": -8.0,
            "trades_count": 2,
        }
    )
    assert "Fake starting capital" in text
    assert "does not place orders" in text


@pytest.mark.unit
def test_news_prefetch_extracts_topic_and_uses_market_news_tool():
    result = _prefetch_request(
        [
            {
                "role": "user",
                "content": "Search for news about Federal Reserve and analyse sentiment.",
            }
        ]
    )
    assert result == (
        "search_market_news",
        {"query": "Federal Reserve", "max_articles": 10},
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "I will analyze the news and sentiment and provide a summary.",
        "Please wait for my analysis.",
        "Let me check the latest data.",
    ],
)
def test_intermediate_model_messages_are_not_final_answers(text):
    assert _looks_like_intermediate_response(text)


@pytest.mark.unit
def test_news_fallback_is_a_completed_answer():
    answer = _format_news_result(
        json.dumps(
            {
                "query": "Federal Reserve",
                "articles_found": 1,
                "overall_sentiment": "neutral",
                "avg_sentiment_score": 0.0,
                "articles": [
                    {
                        "title": "Fed holds rates steady",
                        "source": "Example News",
                        "published_at": "2026-08-13",
                        "summary": "The central bank kept its policy unchanged.",
                        "sentiment": {"label": "neutral", "score": 0.0},
                    }
                ],
            }
        )
    )
    assert "News analysis: Federal Reserve" in answer
    assert "Fed holds rates steady" in answer
    assert "Please wait" not in answer


@pytest.mark.unit
def test_market_fallback_includes_every_snapshot_asset():
    answer = _format_market_overview_result(
        json.dumps(
            {
                "timestamp": "2026-08-13T02:38:56+00:00",
                "markets": {
                    "S&P 500": {"price": 7748.5, "change_pct": 0.26},
                    "NASDAQ 100": {"price": 29742.604, "change_pct": 0.74},
                    "Dow Jones": {"price": 53770.27, "change_pct": -0.04},
                    "Russell 2000": {"price": 3045.483, "change_pct": 0.61},
                    "VIX (Fear Index)": {"price": 14.55, "change_pct": -4.78},
                    "10Y Treasury Yield": {"price": 4.682, "change_pct": -0.04},
                    "2Y Treasury Yield": {"price": 3.707, "change_pct": -0.62},
                    "Gold": {"price": 4465.6, "change_pct": -0.04},
                    "Crude Oil (WTI)": {"price": 82.17, "change_pct": -1.32},
                    "Bitcoin": {"price": 119_000.0, "change_pct": 0.2},
                    "Ethereum": {"price": 4_300.0, "change_pct": 0.1},
                    "Dollar Index": {"price": 98.2, "change_pct": -0.1},
                },
            }
        )
    )
    assert "Bitcoin" in answer
    assert "Ethereum" in answer
    assert "Dollar Index" in answer
    assert answer.count("|") >= 39


@pytest.mark.unit
async def test_length_truncation_uses_complete_market_fallback():
    client = llama_cpp_client.LlamaCppClient.__new__(llama_cpp_client.LlamaCppClient)
    client._inference_lock = asyncio.Lock()

    async def fake_stream(_messages, _tools, max_tokens=None):
        yield {
            "choices": [
                {
                    "delta": {"content": "The market overview ends at Bitcoin"},
                    "finish_reason": "length",
                }
            ]
        }

    client._stream_completion = fake_stream
    cfg = MagicMock(
        llm_native_tool_calling=False,
        trading_mode="recommend",
        agent_max_tokens=64,
        agent_max_tool_rounds=2,
        agent_max_tool_result_chars=5_000,
    )
    tool_result = json.dumps(
        {
            "timestamp": "2026-08-13T02:38:56+00:00",
            "markets": {
                "Bitcoin": {"price": 119_000.0, "change_pct": 0.2},
                "Ethereum": {"price": 4_300.0, "change_pct": 0.1},
                "Dollar Index": {"price": 98.2, "change_pct": -0.1},
            },
        }
    )
    with (
        patch.object(llama_cpp_client, "settings", cfg),
        patch.object(llama_cpp_client, "dispatch_tool", new=AsyncMock(return_value=tool_result)),
    ):
        events = [
            event
            async for event in client.stream_response(
                [{"role": "user", "content": "Give me a full market overview right now."}],
                "You are a test assistant.",
            )
        ]

    assert events[-1]["type"] == "done"
    answer = events[-2]["text"]
    assert answer.startswith("# Market overview")
    assert "Ethereum" in answer
    assert "Dollar Index" in answer
    assert "ends at Bitcoin" not in answer


@pytest.mark.unit
async def test_stream_response_repairs_progress_only_output_before_emitting_final():
    client = llama_cpp_client.LlamaCppClient.__new__(llama_cpp_client.LlamaCppClient)
    client._inference_lock = asyncio.Lock()
    calls = 0

    async def fake_stream(_messages, _tools, max_tokens=None):
        nonlocal calls
        calls += 1
        text = (
            "I will analyze the news and sentiment and provide a summary."
            if calls == 1
            else "## Final answer\nThe evidence is neutral."
        )
        yield {"choices": [{"delta": {"content": text}, "finish_reason": "stop"}]}

    client._stream_completion = fake_stream
    cfg = MagicMock(
        llm_native_tool_calling=False,
        trading_mode="recommend",
        agent_max_tokens=64,
        agent_max_tool_rounds=2,
        agent_max_tool_result_chars=5_000,
    )
    with patch.object(llama_cpp_client, "settings", cfg):
        events = [
            event
            async for event in client.stream_response(
                [{"role": "user", "content": "What is diversification?"}],
                "You are a test assistant.",
            )
        ]

    assert calls == 2
    assert [event["type"] for event in events] == ["final_answer", "done"]
    assert events[0]["text"] == "## Final answer\nThe evidence is neutral."


@pytest.mark.unit
async def test_tool_progress_text_is_buffered_until_the_final_turn():
    client = llama_cpp_client.LlamaCppClient.__new__(llama_cpp_client.LlamaCppClient)
    client._inference_lock = asyncio.Lock()
    calls = 0

    async def fake_stream(_messages, _tools, max_tokens=None):
        nonlocal calls
        calls += 1
        if calls == 1:
            yield {"choices": [{"delta": {"content": "I will analyze this now."}}]}
            yield {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call-1",
                                    "function": {
                                        "name": "search_market_news",
                                        "arguments": '{"query":"Federal Reserve"}',
                                    },
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            }
        else:
            yield {
                "choices": [
                    {
                        "delta": {"content": "## Final answer\nNeutral sentiment."},
                        "finish_reason": "stop",
                    }
                ]
            }

    client._stream_completion = fake_stream
    cfg = MagicMock(
        llm_native_tool_calling=True,
        trading_mode="recommend",
        agent_max_tokens=64,
        agent_max_tool_rounds=2,
        agent_max_tool_result_chars=5_000,
    )
    tool_result = json.dumps(
        {
            "query": "Federal Reserve",
            "articles_found": 0,
            "overall_sentiment": "neutral",
            "avg_sentiment_score": 0.0,
            "articles": [],
        }
    )
    with (
        patch.object(llama_cpp_client, "settings", cfg),
        patch.object(llama_cpp_client, "dispatch_tool", new=AsyncMock(return_value=tool_result)),
    ):
        events = [
            event
            async for event in client.stream_response(
                [{"role": "user", "content": "Search for news about the Federal Reserve."}],
                "You are a test assistant.",
            )
        ]

    assert [event["type"] for event in events] == [
        "tool_call",
        "tool_result",
        "final_answer",
        "done",
    ]
    assert all("I will analyze" not in event.get("text", "") for event in events)
    assert events[2]["text"] == "## Final answer\nNeutral sentiment."
