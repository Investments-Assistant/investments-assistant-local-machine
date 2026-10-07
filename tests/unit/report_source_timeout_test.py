"""Timed-out report reads remain bounded and cannot consume rendering capacity."""

import asyncio
from threading import Event
from contextvars import ContextVar

import pytest

from src.scheduler import reporter
from src.operations.workloads import WorkPool


async def test_report_timeout_retains_source_slot_and_principal(monkeypatch):
    pool = WorkPool(1, 'REPORT_SOURCE_FIXTURE')
    monkeypatch.setattr(reporter, '_report_source_work', pool)
    monkeypatch.setattr(reporter, '_REPORT_SOURCE_TIMEOUT', 0.05)
    principal = ContextVar('fixture_report_principal', default=None)
    token = principal.set('synthetic-owner')
    release = Event()
    seen = []

    def blocked():
        seen.append(principal.get())
        assert release.wait(5)
        return {'status': 'complete'}

    try:
        result = await reporter._read_report_source(blocked)
        assert result == {'status': 'unavailable', 'error': 'REPORT_SOURCE_TIMEOUT'}
        assert seen == ['synthetic-owner']
        assert await reporter._read_report_source(lambda: pytest.fail('Native slot still held')) == {
            'status': 'unavailable', 'error': 'REPORT_SOURCE_BUSY',
        }
        assert reporter._collection_errors({'portfolio': result})
    finally:
        release.set()
        principal.reset(token)
    for _ in range(100):
        await asyncio.sleep(0.01)
        result = await reporter._read_report_source(lambda: {'status': 'complete'})
        if result.get('status') == 'complete':
            break
    else:
        pytest.fail('Completed worker did not release admission slot')
