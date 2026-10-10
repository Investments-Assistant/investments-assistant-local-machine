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


def test_scheduler_registers_bounded_coalesced_heartbeat_observation():
    from src.scheduler import jobs

    with patch.object(jobs, "scheduler") as scheduler:
        jobs.setup_scheduler()
    registered = {call.kwargs["id"]: call for call in scheduler.add_job.call_args_list}
    call = registered["operations_heartbeat"]
    assert call.kwargs["coalesce"] is True
    assert call.kwargs["max_instances"] == 1
    assert call.kwargs["misfire_grace_time"] == 30
    assert call.args[0].__name__ == "monitor_heartbeat"
