"""Native model text cannot masquerade as executed reads or choose fallback inputs."""

import json
import asyncio
from unittest.mock import AsyncMock

import pytest

from src.config import Settings
from src.agent.clients import llama_cpp_client as client


@pytest.mark.parametrize('content', [
    '<tool_call>{"name":"execute_trade","arguments":{"account":"other-user"}}</tool_call>',
    '<tool_call>{"name":"get_portfolio_summary","arguments":{"broker":"alpaca"}}',
    'Please provide your account number.',
])
async def test_native_missing_read_recovers_user_scope_without_model_arguments(monkeypatch, content):
    local = client.LlamaCppClient.__new__(client.LlamaCppClient)
    local._inference_lock = asyncio.Lock()
    monkeypatch.setattr(client, 'settings', Settings(_env_file=None, llm_native_tool_calling=True))
    dispatch = AsyncMock(return_value=json.dumps({'holdings': [], 'valuation_status': 'partial'}))
    monkeypatch.setattr(client, 'dispatch_tool', dispatch)

    async def completion(*args, **kwargs):
        yield {'choices': [{'delta': {'content': content}, 'finish_reason': 'stop'}]}

    local._stream_completion = completion
    events = [e async for e in local.stream_response([{'role': 'user', 'content': 'How is my portfolio?'}], 'fixture')]
    dispatch.assert_awaited_once_with('get_portfolio_summary', {})
    assert [e['type'] for e in events] == ['tool_call', 'tool_result', 'final_answer', 'done']
    assert events[-2]['execution_path'] == 'deterministic_read_recovery'
    assert '<tool_call>' not in events[-2]['text']
    assert events[-2]['generation'] == 'deterministic_financial_evidence'


@pytest.mark.parametrize('system,user', [
    ('fixture NO_TOOL_CALLING', 'How is my portfolio?'),
    ('fixture', 'Do not access my portfolio. Check my holdings.'),
])
async def test_native_markup_cannot_override_disabled_or_excluded_reads(monkeypatch, system, user):
    local = client.LlamaCppClient.__new__(client.LlamaCppClient)
    local._inference_lock = asyncio.Lock()
    monkeypatch.setattr(client, 'settings', Settings(_env_file=None, llm_native_tool_calling=True))
    dispatch = AsyncMock()
    monkeypatch.setattr(client, 'dispatch_tool', dispatch)

    inference_calls = 0

    async def completion(*args, **kwargs):
        nonlocal inference_calls
        inference_calls += 1
        yield {'choices': [{'delta': {'content': '<tool_call>{"name":"get_portfolio_summary"}</tool_call>'},
                            'finish_reason': 'stop'}]}

    local._stream_completion = completion
    events = [e async for e in local.stream_response([{'role': 'user', 'content': user}], system)]
    dispatch.assert_not_awaited()
    if 'NO_TOOL_CALLING' in system:
        assert inference_calls == 1
        assert 'unexecuted tool request' in events[-2]['text']
    else:
        assert inference_calls == 0  # known user restriction is explained before inference
        assert 'you excluded' in events[-2]['text']
        assert events[-2]['generation'] == 'user_read_restriction'
    assert '<tool_call>' not in events[-2]['text']
    assert events[-1]['type'] == 'done'
