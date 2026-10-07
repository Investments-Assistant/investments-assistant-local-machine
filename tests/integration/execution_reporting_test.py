"""Reconciled simulator reporting uses booking intervals and explicit restatement."""

from decimal import Decimal
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.db.models import User
from src.execution.models import ExecutionEvent
from src.execution.policy import PolicyDenied
from src.execution.service import record_fill
from src.scheduler.reporter import _fallback_report, _collection_errors
from src.execution.reporting import collect_execution_period
from src.execution.commissions import record_commission
from tests.integration.execution_test import seed, confirmation
from tests.integration.commissions_test import callback
from tests.integration.simulator_sales_test import sell, owned

pytestmark = pytest.mark.integration


async def period_fixture(session):
    ids, account, buy = await owned(session)
    start = datetime.now(UTC) - timedelta(days=2)
    end = start + timedelta(days=1)
    original = await session.scalar(select(ExecutionEvent).where(
        ExecutionEvent.order_id == buy['order_id'], ExecutionEvent.kind == 'fill',
    ))
    original.observed_at = start - timedelta(days=1)
    fills = []
    for stamp in (start, end):
        sale = await sell(session, ids)
        await confirmation(session, ids, sale)
        await record_fill(session, user_id=ids[0], account_id=ids[1], order_id=sale['order_id'],
                          execution_id='report-fixture', quantity='1', price='120', fee='0.10')
        event = await session.scalar(select(ExecutionEvent).where(
            ExecutionEvent.order_id == sale['order_id'], ExecutionEvent.kind == 'fill',
        ))
        event.observed_at = stamp
        fills.append(event.id)
    await session.flush()
    return ids, account, buy, start, end, fills


async def test_period_evidence_excludes_end_boundary_and_other_users(db_session):
    ids, account, buy, start, end, fills = await period_fixture(db_session)
    await seed(db_session)
    result = await collect_execution_period(db_session, user_id=ids[0], start=start, end=end)
    assert result['status'] == 'partial_failure' and result['portfolio_period_pnl'] is None
    assert len(result['accounts']) == 1
    row = result['accounts'][0]
    assert row['account_id'] == account.id and row['base_currency'] == 'EUR'
    assert row['execution_count'] == 1 and row['executions'][0]['event_id'] == fills[0]
    assert Decimal(row['realized_pnl']) == Decimal('19.90')
    assert Decimal(row['attributed_fees']) == Decimal('0.10')
    assert row['reconciliation_status'] == 'consistent' and row['evidence_sha256']
    text = _fallback_report({'period': {'start': start.date().isoformat(), 'end': end.date().isoformat()},
                             'simulator_execution_period': result})
    assert fills[0] in text and fills[1] not in text
    assert 'Synthetic accounts only' in text and 'booked realized P&L' in text
    assert row['period_performance']['reason'] == 'EXACT_PERIOD_MARKS_UNAVAILABLE'
    assert _collection_errors({'simulator_execution_period': result})[0]['code'] == 'SOURCE_INCOMPLETE'


async def test_late_fees_restate_original_period_without_becoming_period_cash_flow(db_session):
    ids, account, buy, start, end, fills = await period_fixture(db_session)
    before = await collect_execution_period(db_session, user_id=ids[0], start=start, end=end)
    await record_commission(db_session, **callback(ids, buy['order_id'], datetime.now(UTC),
                                                  execution_id='buy', amount='0.20'))
    after = await collect_execution_period(db_session, user_id=ids[0], start=start, end=end)
    row = after['accounts'][0]
    assert Decimal(row['realized_pnl']) == Decimal('19.80')
    assert Decimal(row['attributed_fees']) == Decimal('0.10')
    assert row['period_executions_sha256'] != before['accounts'][0]['period_executions_sha256']
    assert 'Restated' in after['fee_basis'] and 'not fee-payment cash flow' in after['fee_basis']


async def test_discrepant_account_has_no_reported_execution_totals(db_session):
    ids, account, buy, start, end, fills = await period_fixture(db_session)
    account.cash += 1
    await db_session.flush()
    result = await collect_execution_period(db_session, user_id=ids[0], start=start, end=end)
    row = result['accounts'][0]
    assert result['status'] == 'partial_failure' and row['status'] == 'unavailable'
    assert row['realized_pnl'] is None and row['attributed_fees'] is None and row['executions'] == []
    assert _collection_errors({'simulator_execution_period': result})[0]['source'] == 'simulator_execution_period'


async def test_deactivated_owner_cannot_collect_period_evidence(db_session):
    ids, account, buy, start, end, fills = await period_fixture(db_session)
    user = await db_session.get(User, ids[0])
    user.is_active = False
    with pytest.raises(PolicyDenied, match='AUTHENTICATED_ACCOUNT_REQUIRED'):
        await collect_execution_period(db_session, user_id=ids[0], start=start, end=end)



async def test_truncated_details_keep_exact_totals_and_explicit_coverage(db_session, monkeypatch):
    from src.execution import reporting

    ids, account, buy, start, end, fills = await period_fixture(db_session)
    monkeypatch.setattr(reporting, 'MAX_DISPLAY_EXECUTIONS', 1)
    result = await collect_execution_period(db_session, user_id=ids[0], start=start,
                                             end=end + timedelta(seconds=1))
    row = result['accounts'][0]
    assert row['execution_count'] == 2 and len(row['executions']) == 1
    assert row['execution_details_truncated']
    assert Decimal(row['realized_pnl']) == Decimal('39.80')
    assert Decimal(row['attributed_fees']) == Decimal('0.20')


async def test_real_collector_persists_linked_execution_evidence_and_pdf(db_session, monkeypatch, tmp_path):
    import re
    import html
    import json
    from pathlib import Path
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock

    from src.db import database
    from src.agent import clients
    from src.tools import news, dispatcher, market_data, news_memory
    from src.config import Settings
    from src.db.models import Report
    from src.scheduler import reporter
    from src.tools.dispatcher import tool_context

    ids, account, buy, start, end, fills = await period_fixture(db_session)

    from src.execution.models import AccountLedgerEvent
    from src.execution.account_events import record_cash_flow

    receipt = await record_cash_flow(db_session, user_id=ids[0], account_id=ids[1], event_key='report-flow',
        amount_base='250', currency='EUR', effective_at=start, source_reference='synthetic-report', fixture_event=True)
    flow = await db_session.get(AccountLedgerEvent, receipt['event_id'])
    flow.observed_at = start
    await db_session.flush()

    class Factory:
        @asynccontextmanager
        async def __call__(self):
            yield db_session

        begin = __call__

    class Client:
        async def stream_response(self, **kwargs):
            yield {'type': 'final_answer', 'text': '{"status":"abstain","observations":[]}'}
            yield {'type': 'done'}

    monkeypatch.setattr(database, 'async_session', Factory())
    monkeypatch.setattr(dispatcher, '_load_current_user_accounts', AsyncMock(return_value=([], None)))
    monkeypatch.setattr(market_data, 'get_market_overview', lambda: {})
    monkeypatch.setattr(news, 'search_market_news', lambda *args, **kwargs: {'articles': []})
    monkeypatch.setattr(news_memory, 'search_stored_news', AsyncMock(return_value={'articles': []}))
    monkeypatch.setattr(clients, 'create_llm_client', Client)
    monkeypatch.setattr(reporter, 'settings', Settings(_env_file=None, reports_dir=str(tmp_path)))
    day = start.date().isoformat()
    with tool_context('execution-report-fixture', ids[0], 'recommend'):
        result = await reporter.generate_report(day, day)
    assert any(error.get('source') == 'simulator_execution_period' and error['code'] == 'SOURCE_INCOMPLETE'
               for error in result['errors'])
    assert result['report_id'] and Path(result['pdf_path']).read_bytes().startswith(b'%PDF')
    saved = await db_session.get(Report, result['report_id'])
    await db_session.refresh(saved)
    assert saved.user_id == ids[0] and fills[0] in saved.html_content
    evidence = json.loads(html.unescape(re.search(r'<pre>(.*?)</pre>', saved.html_content, re.S)[1]))
    account_evidence = evidence['simulator_execution_period']['accounts'][0]
    assert account_evidence['executions'][0]['event_id'] == fills[0]
    assert account_evidence['execution_count'] == 1
    assert Decimal(account_evidence['realized_pnl']) == Decimal('19.90')
    assert account_evidence['reconciliation_status'] == 'consistent'

    assert Decimal(account_evidence['net_external_flows']) == 250
    assert account_evidence['cash_flows'][0]['event_id'] == flow.id
    assert 'Net synthetic cash flows (EUR): 250' in saved.html_content
    assert 'excluded from trading P' in saved.html_content
