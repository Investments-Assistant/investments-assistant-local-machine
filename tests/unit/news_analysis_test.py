"""Exact source attribution and bounded abstention for model news analysis."""

import json
import asyncio

import pytest

from src.agent.clients import llama_cpp_client as client
from src.agent.clients.news_analysis import prepare_news, validate_assessment

TEXT = "The synthetic company reported revenue growth in its published statement, without offering any market forecast."
RESULTS = {"get_latest_news": json.dumps({"articles": [{"title": "Fixture release", "summary": TEXT,
                                                      "url": "https://fixture.invalid/news"}]})}


def test_quote_and_source_must_both_match_observed_evidence():
    sources, _ = prepare_news(RESULTS)
    identity = next(iter(sources))
    payload = {"status": "supported_extracts", "observations": [{"source_id": identity, "quote": TEXT}],
               "missing_data": []}
    assert validate_assessment(json.dumps(payload), sources).observations[0].quote == TEXT
    for change in ({"source_id": "a" * 64}, {"quote": "Markets will surge tomorrow; buy the synthetic company now."}):
        with pytest.raises(ValueError):
            validate_assessment(json.dumps(payload | {"observations": [payload["observations"][0] | change]}), sources)
    with pytest.raises(ValueError):
        validate_assessment(json.dumps(payload | {"confidence": 1.0}), sources)


async def test_headline_only_abstains_without_model_inference():
    local = client.LlamaCppClient.__new__(client.LlamaCppClient)
    answer = await local._news_assessment(
        {"get_latest_news": '{"articles":[{"title":"Synthetic market observation"}]}'}
    )
    assert '"status": "abstain"' in answer
    assert "INSUFFICIENT_SOURCE_TEXT" in answer
    assert "ongoing market activity" not in answer


async def test_invalid_model_inference_has_bounded_retries_then_abstains():
    local = client.LlamaCppClient.__new__(client.LlamaCppClient)
    local._inference_lock = asyncio.Lock()
    attempts = 0

    async def infer(messages, tools, max_tokens=None, response_schema=None, preserve_context=False):
        nonlocal attempts
        assert preserve_context is True
        attempts += 1
        assert response_schema and tools == []
        allowed_ids = response_schema["$defs"]["Observation"]["properties"]["source_id"]["enum"]
        assert allowed_ids == list(prepare_news(RESULTS)[0])
        yield {"choices": [{"delta": {"content": '"Markets will rise"'}, "finish_reason": "stop"}]}

    local._stream_completion = infer
    answer = await local._news_assessment(RESULTS)
    assert attempts == 2
    assert '"status": "abstain"' in answer and "MODEL_OUTPUT_INVALID" in answer
    assert "Markets will rise" not in answer


async def test_valid_extract_adds_mandatory_limits_even_if_model_omits_them():
    local = client.LlamaCppClient.__new__(client.LlamaCppClient)
    local._inference_lock = asyncio.Lock()
    sources, _ = prepare_news(RESULTS)

    async def infer(messages, tools, max_tokens=None, response_schema=None, preserve_context=False):
        payload = {"status": "supported_extracts", "observations": [{"source_id": next(iter(sources)), "quote": TEXT}],
                   "missing_data": []}
        yield {"choices": [{"delta": {"content": json.dumps(payload)}, "finish_reason": "stop"}]}

    local._stream_completion = infer
    answer = await local._news_assessment(RESULTS)
    assert TEXT in answer
    assert "independent_corroboration" in answer and "price_context" in answer
    assert "not_independent_corroboration_or_trading_signal" in answer


async def test_mixed_market_request_preserves_independent_evidence_and_abstains_on_headline():
    local = client.LlamaCppClient.__new__(client.LlamaCppClient)
    answer = await local._news_response({
        "get_latest_news": '{"articles":[{"title":"Synthetic market observation"}]}',
        "get_market_overview": '{"status":"unavailable","indices":[]}',
    })
    assert "INSUFFICIENT_SOURCE_TEXT" in answer
    assert "get_market_overview" in answer and '"indices": []' in answer


async def test_provider_failure_is_not_evidence_of_absent_market_activity():
    local = client.LlamaCppClient.__new__(client.LlamaCppClient)
    answer = await local._news_assessment({"get_latest_news": '{"status":"unavailable","articles":[]}'})
    assert '"status": "abstain"' in answer and "source_unavailable" in answer


async def test_model_cannot_invent_collection_failure_or_missing_body():
    local = client.LlamaCppClient.__new__(client.LlamaCppClient)
    local._inference_lock = asyncio.Lock()

    async def infer(messages, tools, max_tokens=None, response_schema=None, preserve_context=False):
        payload = {"status": "abstain", "observations": [], "missing_data": ["source_unavailable", "body"]}
        yield {"choices": [{"delta": {"content": json.dumps(payload)}, "finish_reason": "stop"}]}

    local._stream_completion = infer
    answer = await local._news_assessment(RESULTS)
    assert '"status": "abstain"' in answer
    assert "source_unavailable" not in answer
    assert '"body"' not in answer
    assert "publication_time" in answer
    assert "availability_time" in answer
