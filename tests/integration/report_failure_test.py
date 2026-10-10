"""Report failure status survives real PostgreSQL persistence; providers are fixtures."""

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from src.db import database
from src.agent import clients
from src.config import Settings
from src.db.models import User, Report
from src.scheduler import reporter
from src.tools.dispatcher import tool_context
from src.operations.models import OperationalAlert
from src.operations.storage import StorageUnavailable

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("failure", [
    "source", "model_empty", "disk", "persistence", "missing_portfolio", "partial_valuation", "blocked_news",
])
async def test_report_returns_partial_for_each_failed_stage(db_session, monkeypatch, tmp_path, failure):
    owner = str(uuid.uuid4())
    db_session.add(User(id=owner, username="report-" + owner, password_hash="fixture", is_active=True))
    await db_session.flush()

    @asynccontextmanager
    async def factory():
        from src.operations.report_cleanup import report_directory_lock

        # A published PDF must stay protected until its DB reference commits.
        with pytest.raises(BlockingIOError), report_directory_lock(tmp_path, exclusive=True):
            pass
        if failure == "persistence":
            raise RuntimeError("private database fixture diagnostic")
        yield db_session

    class Client:
        async def stream_response(self, **kwargs):
            if failure != "model_empty":
                yield {"type": "final_answer", "text": '{"status":"abstain","observations":[]}' }
            yield {"type": "done"}

    def write_fixture(destination, render, **kwargs):
        if failure == "disk":
            raise StorageUnavailable("DISK_LOW")
        # Real rendering and file ownership are covered by the Chromium tier.

    context = {
        "period": {"start": "2026-09-01", "end": "2026-09-07"},
        "portfolio": {"available": failure != "missing_portfolio",
                      "valuation_status": "partial" if failure == "partial_valuation" else "complete"},
        "stored_news": {"status": "blocked" if failure == "blocked_news" else "complete", "articles": []},
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
    expected_stage = {"source": "collection", "model_empty": "model", "disk": "pdf", "persistence": "persistence",
                      "missing_portfolio": "collection", "partial_valuation": "collection",
                      "blocked_news": "collection"}[
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
        alert = await db_session.scalar(select(OperationalAlert).where(OperationalAlert.user_id == owner))
        assert alert is not None and alert.rule == "report_storage_pressure"
        assert alert.observed_value == "DISK_LOW" and alert.delivery_status == "in_app"
        assert str(tmp_path) not in alert.message
        with tool_context("report-fixture", owner, "recommend"):
            retry = await reporter.generate_report("2026-09-01", "2026-09-07")
        assert retry["status"] == "partial_failure" and retry["report_id"] != result["report_id"]
        await db_session.refresh(alert)
        alerts = list(await db_session.scalars(select(OperationalAlert).where(OperationalAlert.user_id == owner)))
        assert len(alerts) == 1 and alert.occurrences == 2




async def test_real_collector_history_failure_persists_partial_report(db_session, monkeypatch, tmp_path):
    from src.tools import news, portfolio, dispatcher, market_data, news_memory
    from src.tools.broker_accounts import BrokerAccountConfig

    owner = str(uuid.uuid4())
    account = BrokerAccountConfig('history-fixture', owner, 'ibkr', 'Synthetic', {})

    @asynccontextmanager
    async def factory():
        yield db_session

    class Client:
        async def stream_response(self, **kwargs):
            assert 'partial_failure' in kwargs['messages'][0]['content']
            assert 'private-provider-detail' not in kwargs['messages'][0]['content']
            yield {'type': 'final_answer', 'text': '{"status":"abstain","observations":[]}' }
            yield {'type': 'done'}

    monkeypatch.setattr(database, 'async_session', factory)
    monkeypatch.setattr(dispatcher, '_load_current_user_accounts', AsyncMock(return_value=([account], None)))
    monkeypatch.setattr(portfolio, 'get_portfolio_summary', lambda **kwargs: {'positions': []})
    monkeypatch.setattr(portfolio, 'get_trade_history', lambda **kwargs: [{'error': 'private-provider-detail'}])
    monkeypatch.setattr(market_data, 'get_market_overview', lambda: {})
    monkeypatch.setattr(news, 'search_market_news', lambda *args, **kwargs: {'articles': []})
    monkeypatch.setattr(news_memory, 'search_stored_news', AsyncMock(return_value={'articles': []}))
    monkeypatch.setattr(clients, 'create_llm_client', Client)
    monkeypatch.setattr(reporter, 'write_report', lambda *args, **kwargs: None)
    monkeypatch.setattr(reporter, 'settings', Settings(_env_file=None, reports_dir=str(tmp_path)))
    with tool_context('history-report-fixture', owner, 'recommend'):
        result = await reporter.generate_report('2026-01-01', '2026-01-31')
    assert result['status'] == 'partial_failure'
    assert {'stage': 'collection', 'source': 'broker_trade_history', 'code': 'SOURCE_INCOMPLETE'} in result['errors']
    saved = await db_session.get(Report, result['report_id'])
    assert saved.user_id == owner
    assert saved.generation_status == 'partial_failure'
    assert 'private-provider-detail' not in saved.html_content


async def test_oversized_report_evidence_cannot_trigger_unsupported_model_report(db_session, monkeypatch, tmp_path):
    owner = str(uuid.uuid4())
    calls = []
    context = {
        'period': {'start': '2026-01-01', 'end': '2026-01-31'},
        'portfolio': {'positions': [{'symbol': 'FIXTURE', 'account_id': 'synthetic-account',
                                    'quantity_exact': '0.004', 'currency': 'EUR', 'price': '100'}]},
        'market_overview': {}, 'retained_evidence': 'x' * 15000,
    }

    @asynccontextmanager
    async def factory():
        yield db_session

    class Client:
        async def stream_response(self, **kwargs):
            calls.append(kwargs)
            yield {'type': 'final_answer', 'text': 'Portfolio profit was USD 999999.'}
            yield {'type': 'done'}

    monkeypatch.setattr(database, 'async_session', factory)
    monkeypatch.setattr(reporter, '_collect_report_context', AsyncMock(return_value=context))
    monkeypatch.setattr(clients, 'create_llm_client', Client)
    monkeypatch.setattr(reporter, 'write_report', lambda *args, **kwargs: None)
    monkeypatch.setattr(reporter, 'settings', Settings(_env_file=None, reports_dir=str(tmp_path)))
    with tool_context('report-budget-fixture', owner, 'recommend'):
        result = await reporter.generate_report('2026-01-01', '2026-01-31')
    assert not calls
    assert result['status'] == 'partial_failure'
    assert {'stage': 'model', 'code': 'REPORT_EVIDENCE_BUDGET_EXCEEDED'} in result['errors']
    assert '999999' not in result['report_text']
    assert '0.004' in result['report_text'] and 'EUR' in result['report_text']
    saved = await db_session.get(Report, result['report_id'])
    assert saved.user_id == owner and saved.generation_status == 'partial_failure'
    assert context['retained_evidence'] in saved.html_content
    assert result['evidence_sha256'] in saved.html_content


@pytest.mark.parametrize("outcome", ["invalid", "valid", "repair"])
async def test_fitting_evidence_does_not_authorize_model_invented_financial_claims(
    db_session, monkeypatch, tmp_path, outcome,
):
    valid = outcome != "invalid"
    calls = []
    owner = str(uuid.uuid4())
    context = {
        "period": {"start": "2026-01-01", "end": "2026-01-31"},
        "portfolio": {"positions": [{"symbol": "FIXTURE", "account_id": "synthetic-account",
                                    "quantity_exact": "0.004", "currency": "EUR", "price": "100"}]},
        "market_overview": {},
    }

    @asynccontextmanager
    async def factory():
        yield db_session

    class Client:
        async def stream_response(self, **kwargs):
            calls.append(kwargs)
            yield {"type": "final_answer", "text": (
                '{"status":"abstain","observations":[]}'
                if outcome == "valid" or (outcome == "repair" and len(calls) == 2)
                else "Portfolio profit was USD 999999. Six shares were purchased."
            )}
            yield {"type": "done"}

    monkeypatch.setattr(database, "async_session", factory)
    monkeypatch.setattr(reporter, "_collect_report_context", AsyncMock(return_value=context))
    monkeypatch.setattr(clients, "create_llm_client", Client)
    monkeypatch.setattr(reporter, "write_report", lambda *args, **kwargs: None)
    monkeypatch.setattr(reporter, "settings", Settings(_env_file=None, reports_dir=str(tmp_path)))
    with tool_context("report-authority-fixture", owner, "recommend"):
        result = await reporter.generate_report("2026-01-01", "2026-01-31")
    assert result["status"] == ("complete" if valid else "partial_failure")
    if valid:
        assert result["errors"] == []
        assert "abstained" in result["report_text"]
    else:
        assert {"stage": "model", "code": "REPORT_MODEL_OUTPUT_INVALID"} in result["errors"]
    assert "999999" not in result["report_text"] and "Six shares" not in result["report_text"]
    assert "0.004" in result["report_text"] and "EUR" in result["report_text"]
    saved = await db_session.get(Report, result["report_id"])
    assert saved.user_id == owner and saved.generation_errors == result["errors"]
    assert "999999" not in saved.html_content and "Six shares" not in saved.html_content
    expected_attempts = 1 if outcome == "valid" else 2
    assert context["model_attempts"] == len(calls) == expected_attempts
    assert f'&quot;model_attempts&quot;: {expected_attempts}' in saved.html_content
