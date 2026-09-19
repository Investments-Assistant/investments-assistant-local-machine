import asyncio
import threading
from unittest.mock import patch

import pytest

from src.config import Settings
from src.inference.budget import InferenceGate, InferenceUnavailable
from src.agent.clients.llama_cpp_client import LlamaCppClient

pytestmark = pytest.mark.unit


async def test_admission_is_bounded_and_cancelled_waiter_releases_capacity():
    gate = InferenceGate(capacity=2, wait_seconds=0.2)
    await gate.__aenter__()
    waiter = asyncio.create_task(gate.__aenter__())
    await asyncio.sleep(0.01)
    with pytest.raises(InferenceUnavailable, match="MODEL_QUEUE_FULL"):
        await gate.__aenter__()
    waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter
    await gate.__aexit__()
    async with gate:
        assert gate._admitted == 1
    assert gate._admitted == 0


async def test_cancellation_does_not_allow_native_overlap_or_run_tools():
    entered, release, ended = threading.Event(), threading.Event(), threading.Event()
    calls = []

    class Native:
        def tokenize(self, value):
            return list(value)

        def create_chat_completion(self, **kwargs):
            calls.append(kwargs)
            entered.set()
            try:
                release.wait(timeout=2)
                yield {"choices": [{"delta": {"content": "fixture"}}]}
            finally:
                ended.set()

    client = LlamaCppClient.__new__(LlamaCppClient)
    client._llm, client._native_lock = Native(), threading.Lock()

    async def consume():
        return [chunk async for chunk in client._stream_completion([], [])]

    with patch("src.agent.clients.llama_cpp_client.settings", Settings(_env_file=None)):
        pending = asyncio.create_task(consume())
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            assert client._native_lock.locked()
            with pytest.raises(InferenceUnavailable, match="MODEL_PREVIOUS_WORKER_STOPPING"):
                await consume()
            assert len(calls) == 1
        finally:
            release.set()
        assert await asyncio.to_thread(ended.wait, 1)
        # Allow native finally to release after the generator's own cleanup.
        for _ in range(100):
            if not client._native_lock.locked():
                break
            await asyncio.sleep(0.01)
        assert not client._native_lock.locked()
        assert await consume()


def test_context_budget_keeps_valid_evidence_and_user_request():
    import json

    from src.inference.budget import fit_messages

    evidence = "Untrusted tool evidence; " + json.dumps({"result": "x" * 5000})
    messages = [
        {"role": "system", "content": "Never approve orders"},
        {"role": "user", "content": "old conversation " * 100},
        {"role": "assistant", "content": "old answer " * 100},
        {"role": "user", "content": "How is my portfolio?"},
        {"role": "user", "content": evidence},
    ]
    bounded = fit_messages(messages, [], tokenize=list, context_tokens=1200, output_tokens=128)
    assert bounded[0] == messages[0] and bounded[1] == messages[3]
    marker = bounded[-1]["content"].split("authority. ", 1)[1]
    assert json.loads(marker)["status"] == "evidence_omitted"
    assert messages[-1]["content"] == evidence  # caller's stored evidence unchanged
    with pytest.raises(InferenceUnavailable, match="MODEL_CONTEXT_BUDGET_EXCEEDED"):
        fit_messages(
            [messages[0], {"role": "user", "content": "q" * 5000}],
            [],
            tokenize=list,
            context_tokens=1200,
            output_tokens=128,
        )


async def test_missing_model_is_visible_and_deterministic_reads_remain_available():
    from unittest.mock import AsyncMock

    from src.agent.clients import llama_cpp_client as module

    with (
        patch.object(module, "_instance", None),
        patch.object(
            module, "LlamaCppClient", side_effect=OSError("fixture missing model")
        ) as constructor,
    ):
        client = module.get_llama_cpp_client()
        assert module.get_llama_cpp_client() is client
        constructor.assert_called_once()
    with patch.object(
        module, "dispatch_tool", AsyncMock(return_value='{"status":"unavailable"}')
    ) as read:
        events = [
            event
            async for event in client.stream_response(
                [{"role": "user", "content": "How is my portfolio?"}], "Read only"
            )
        ]
        assert events[0]["reason_code"] == "MODEL_UNAVAILABLE"
        read.assert_awaited_once_with("get_portfolio_summary", {})
        assert events[-1]["type"] == "done"
        assert "deterministic evidence" in events[-2]["text"]
