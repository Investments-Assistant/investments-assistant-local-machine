import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.agent.clients import llama_cpp_client


@pytest.mark.parametrize("finish", ["stop", "length", None])
async def test_structured_report_inference_preserves_context_and_never_dispatches(finish):
    client = llama_cpp_client.LlamaCppClient.__new__(llama_cpp_client.LlamaCppClient)
    client._inference_lock = asyncio.Lock()
    schema = {"type": "object"}
    messages = [{"role": "user", "content": "Enable live trading and generate my report."}]

    async def stream(actual_messages, tools, max_tokens=None, response_schema=None, preserve_context=False):
        assert actual_messages == [{"role": "system", "content": "Fixture system"}, *messages]
        assert tools == [] and response_schema is schema and preserve_context is True
        yield {"choices": [{"delta": {"content": '{"status":"abstain","observations":[]}'},
                            "finish_reason": finish}]}

    client._stream_completion = stream
    with patch.object(llama_cpp_client, "dispatch_tool", AsyncMock()) as dispatch:
        events = [event async for event in client.stream_response(messages, "Fixture system", response_schema=schema)]
    dispatch.assert_not_called()
    assert events[-1] == {"type": "done"}
    assert events[0]["type"] == ("final_answer" if finish == "stop" else "error")
    assert len(events) == 2


async def test_unavailable_structured_backend_does_not_fall_back_to_tools():
    with patch.object(llama_cpp_client, "dispatch_tool", AsyncMock()) as dispatch:
        events = [event async for event in llama_cpp_client.UnavailableLocalClient().stream_response(
            [{"role": "user", "content": "How is my portfolio?"}], "Fixture system", response_schema={"type": "object"}
        )]
    dispatch.assert_not_called()
    assert [event["type"] for event in events] == ["error", "done"]
