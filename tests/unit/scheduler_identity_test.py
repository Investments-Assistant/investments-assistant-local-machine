from unittest.mock import AsyncMock, patch

import pytest

from src.scheduler.jobs import _autonomous_scan

pytestmark = pytest.mark.unit


async def test_degraded_scan_persists_stream_then_reports_job_failure():
    observed = []

    class Conversation:
        async def chat(self, prompt):
            yield {"type": "error", "reason_code": "MODEL_UNAVAILABLE"}
            yield {"type": "final_answer", "text": "Partial deterministic evidence"}
            observed.append("persisted")
            yield {"type": "done"}

    async def run(user_id, name, callback, **kwargs):
        assert user_id == "fixture-owner" and name == "market_scan"
        with pytest.raises(RuntimeError, match="MONITORING_MODEL_UNAVAILABLE"):
            await callback(user_id)
        assert observed == ["persisted"]

    with (
        patch("src.scheduler.jobs.settings.autonomous_scans_enabled", True),
        patch("src.operations.runner.monitoring_users", AsyncMock(return_value=["fixture-owner"])),
        patch("src.operations.runner.run_scoped", run),
        patch(
            "src.agent.orchestrator.get_or_create_session", return_value=Conversation()
        ) as create,
    ):
        await _autonomous_scan()
    assert create.call_args.args[1] == "fixture-owner"
