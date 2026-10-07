"""Bounded owner/date-scoped report collections expose omissions."""

import uuid
from datetime import UTC, datetime
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from src.db import database
from src.tools import news, dispatcher, market_data, news_memory
from src.db.models import Trade, SimulationResult
from src.scheduler import reporter
from src.tools.dispatcher import tool_context

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('trade_count,simulation_count', [(0, 0), (2, 10), (1001, 11)])
async def test_report_collection_limits_preserve_ownership_and_expose_coverage(
    db_session, monkeypatch, trade_count, simulation_count,
):
    owner = str(uuid.uuid4())
    stamp = datetime(2026, 1, 15, tzinfo=UTC)
    for i in range(trade_count + 2):
        db_session.add(Trade(user_id=owner if i != trade_count else 'foreign-owner', broker='fixture',
                            symbol='FIXTURE', side='buy', quantity='0.004', order_type='limit', status='pending',
                            mode='simulated',
                            created_at=stamp if i <= trade_count else datetime(2025, 1, 1, tzinfo=UTC)))
    for _ in range(simulation_count):
        db_session.add(SimulationResult(user_id=owner, name='Fixture', strategy={}, initial_capital=100,
                                       final_value=100, total_return_pct=0, period_start='2024-01-01',
                                       period_end='2024-12-31', created_at=stamp))
    await db_session.flush()

    @asynccontextmanager
    async def factory():
        yield db_session

    monkeypatch.setattr(database, 'async_session', factory)
    monkeypatch.setattr(dispatcher, '_load_current_user_accounts', AsyncMock(return_value=([], None)))
    monkeypatch.setattr(market_data, 'get_market_overview', lambda: {})
    monkeypatch.setattr(news, 'search_market_news', lambda *args, **kwargs: {'articles': []})
    monkeypatch.setattr(news_memory, 'search_stored_news', AsyncMock(return_value={'articles': []}))
    with tool_context('coverage-fixture', owner, 'recommend'):
        context = await reporter._collect_report_context('2026-01-01', '2026-01-31')
    assert 'internal_data_error' not in context
    assert len(context['internal_trade_audit']) == min(trade_count, 1000)
    assert len(context['simulations']) == min(simulation_count, 10)
    coverage = context['internal_coverage']
    assert coverage['trade_audit']['has_more'] == (trade_count > 1000)
    assert coverage['simulations']['has_more'] == (simulation_count > 10)
    errors = reporter._collection_errors(context)
    assert any(e['source'] == 'internal_coverage' for e in errors) == (trade_count > 1000 or simulation_count > 10)
    assert all(row['reconciled'] is False for row in context['internal_trade_audit'])
