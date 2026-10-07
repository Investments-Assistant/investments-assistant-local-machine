import copy
import asyncio

import pytest

from src.scheduler.report_analysis import infer_report_analysis, report_analysis_schema


@pytest.mark.parametrize("recovers", [True, False])
async def test_report_semantic_repair_is_bounded_and_keeps_original_evidence(recovers):
    calls = []
    closed = []

    class Client:
        async def stream_response(self, **kwargs):
            calls.append(copy.deepcopy(kwargs))
            try:
                text = '{"status":"abstain","observations":[]}' if recovers and len(calls) == 2 else '{"profit":999999}'
                yield {"type": "final_answer", "text": text}
                yield {"type": "done"}
            finally:
                closed.append(True)

    analysis, reason, attempts = await infer_report_analysis(
        Client(), prompt="Original scoped evidence", system="NO_TOOL_CALLING", schema=report_analysis_schema({}),
        sources={}, max_tokens=128,
    )
    assert attempts == len(calls) == len(closed) == 2
    assert calls[1]["messages"][0] == calls[0]["messages"][0]
    assert "999999" not in str(calls[1])
    assert calls[0]["response_schema"] == calls[1]["response_schema"]
    assert (analysis is not None) is recovers
    assert reason == (None if recovers else "REPORT_MODEL_OUTPUT_INVALID")


@pytest.mark.parametrize("event,reason", [
    ({"type": "error"}, "MODEL_UNAVAILABLE"),
    ({"type": "tool_call"}, "REPORT_MODEL_CONTRACT_VIOLATION"),
])
async def test_report_dependency_and_contract_errors_stop_without_retry(event, reason):
    calls = []

    class Client:
        async def stream_response(self, **kwargs):
            calls.append(True)
            yield event
            pytest.fail("Stream should have been closed after the failure")

    analysis, actual_reason, attempts = await infer_report_analysis(
        Client(), prompt="Evidence", system="NO_TOOL_CALLING", schema={}, sources={}, max_tokens=128,
    )
    assert analysis is None and actual_reason == reason and attempts == len(calls) == 1


async def test_report_cancel_propagates_without_retry():
    class Client:
        async def stream_response(self, **kwargs):
            raise asyncio.CancelledError
            yield  # pragma: no cover

    with pytest.raises(asyncio.CancelledError):
        await infer_report_analysis(Client(), prompt="Evidence", system="NO_TOOL_CALLING", schema={},
                                    sources={}, max_tokens=128)
