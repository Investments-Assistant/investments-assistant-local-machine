"""Report failure status survives real PostgreSQL persistence; providers are fixtures."""

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from src.db import database
from src.agent import clients
from src.config import Settings
from src.db.models import Report
from src.scheduler import reporter
from src.tools.dispatcher import tool_context
from src.operations.storage import StorageUnavailable

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("failure", ["source", "model_empty", "disk", "persistence"])
async def test_report_returns_partial_for_each_failed_stage(db_session, monkeypatch, tmp_path, failure):
    owner = str(uuid.uuid4())

    @asynccontextmanager
    async def factory():
        if failure == "persistence":
            raise RuntimeError("private database fixture diagnostic")
        yield db_session

    class Client:
        async def stream_response(self, **kwargs):
            if failure != "model_empty":
                yield {"type": "final_answer", "text": "Fixture report with stated data gaps."}
            yield {"type": "done"}

    def write_fixture(destination, render, **kwargs):
        if failure == "disk":
            raise StorageUnavailable("DISK_LOW")
        # Real rendering and file ownership are covered by the Chromium tier.

    context = {
        "period": {"start": "2026-09-01", "end": "2026-09-07"},
        "portfolio": {"available": False, "reason": "No fixture broker"},
        "market_overview": {"error": "MARKET_UNAVAILABLE"} if failure == "source" else {},
    }
    monkeypatch.setattr(
        reporter, "settings", Settings(_env_file=None, environment="production", reports_dir=str(tmp_path))
    )
    monkeypatch.setattr(reporter, "_collect_report_context", AsyncMock(return_value=context))
    monkeypatch.setattr(reporter, "write_report", write_fixture)
    monkeypatch.setattr(clients, "create_llm_client", Client)
    monkeypatch.setattr(database, "async_session", factory)
    with tool_context("report-fixture", owner, "recommend"):
        result = await reporter.generate_report("2026-09-01", "2026-09-07")
    expected_stage = {"source": "collection", "model_empty": "model", "disk": "pdf", "persistence": "persistence"}[
        failure
    ]
    assert result["status"] == "partial_failure" and result["success"] is False
    assert any(error["stage"] == expected_stage for error in result["errors"])
    assert "private database" not in str(result)
    assert result["report_text"]
    if failure == "persistence":
        assert result["report_id"] is None
    else:
        saved = await db_session.get(Report, result["report_id"])
        assert saved.user_id == owner
        assert saved.generation_status == "partial_failure"
        assert saved.generation_errors == result["errors"]
        assert result["evidence_sha256"] in saved.html_content
    if failure == "disk":
        assert result["pdf_path"] is None
        assert {"stage": "pdf", "code": "DISK_LOW"} in result["errors"]
