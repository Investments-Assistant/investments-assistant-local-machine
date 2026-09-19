"""Real PostgreSQL source leases/checkpoints; synthetic fetches only."""

import uuid
import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, delete, select, update
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.news import runtime
from src.db.models import User, NewsArticle, NewsRevision
from src.news.http import PublicResponse, PublicFetchError
from src.operations.models import JobLease, OperationalAlert

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def source_fixture(integration_engine, monkeypatch):
    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    owner = str(uuid.uuid4())
    url = "https://fixture.invalid/" + owner
    monkeypatch.setattr(runtime, "async_session", factory)
    from src.config import Settings

    monkeypatch.setattr(
        runtime.config, "settings", Settings(_env_file=None, environment="production")
    )
    async with factory.begin() as session:
        session.add(
            User(id=owner, username=uuid.uuid4().hex, password_hash="fixture", is_active=True)
        )
    try:
        yield factory, owner, url
    finally:
        async with factory.begin() as session:
            ids = select(NewsArticle.id).where(NewsArticle.url == url)
            await session.execute(delete(NewsRevision).where(NewsRevision.article_id.in_(ids)))
            await session.execute(delete(NewsArticle).where(NewsArticle.url == url))
            await session.execute(delete(JobLease).where(JobLease.user_id == owner))
            await session.execute(delete(OperationalAlert).where(OperationalAlert.user_id == owner))
            await session.execute(delete(User).where(User.id == owner))


def article(url):
    return dict(title="Synthetic source evidence", summary="Fixture", source="Synthetic", url=url)


async def make_due(factory, owner):
    async with factory.begin() as session:
        await session.execute(
            update(JobLease)
            .where(JobLease.user_id == owner)
            .values(
                next_due=func.now() - timedelta(seconds=1),
                lease_until=func.now() - timedelta(seconds=1),
            )
        )


async def test_conditional_restart_keeps_evidence_and_source_checkpoint(source_fixture):
    factory, owner, url = source_fixture
    first = AsyncMock(
        return_value=([article(url)], PublicResponse(200, b"fixture", {"etag": '"v1"'}, url))
    )
    assert (await runtime.run_source(owner, url, first))["inserted"] == 1
    first.assert_awaited_once_with({})
    # An independent DB session sees committed article and checkpoint, without process memory.
    async with factory() as session:
        row = await session.scalar(select(NewsArticle).where(NewsArticle.url == url))
        original = row.available_at
        lease = await session.scalar(select(JobLease).where(JobLease.user_id == owner))
        assert lease.checkpoint["etag"] == '"v1"' and lease.last_success
    assert (await runtime.run_source(owner, url, first))["status"] == "leased_or_not_due"
    await make_due(factory, owner)
    cached = AsyncMock(return_value=([], PublicResponse(304, b"", {}, url)))
    assert (await runtime.run_source(owner, url, cached))["status"] == "not_modified"
    cached.assert_awaited_once_with({"If-None-Match": '"v1"'})
    async with factory() as session:
        row = await session.scalar(select(NewsArticle).where(NewsArticle.url == url))
        assert row.available_at == original
        assert (
            await session.scalar(
                select(func.count())
                .select_from(NewsRevision)
                .where(NewsRevision.article_id == row.id)
            )
            == 1
        )


async def test_failure_backoff_preserves_success_and_recovers(source_fixture):
    factory, owner, url = source_fixture
    good = AsyncMock(return_value=([article(url)], PublicResponse(200, b"", {"etag": "v1"}, url)))
    await runtime.run_source(owner, url, good)
    async with factory() as session:
        success = (
            await session.scalar(select(JobLease).where(JobLease.user_id == owner))
        ).last_success
    await make_due(factory, owner)
    fail = AsyncMock(side_effect=PublicFetchError("PUBLIC_HTTP_429", retry_after=900))
    result = await runtime.run_source(owner, url, fail)
    assert result["status"] == "failed" and result["error_code"] == "PUBLIC_HTTP_429"
    assert (await runtime.run_source(owner, url, fail))["status"] == "retry_wait"
    fail.assert_awaited_once()
    async with factory() as session:
        lease = await session.scalar(select(JobLease).where(JobLease.user_id == owner))
        assert lease.last_success == success and lease.checkpoint["etag"] == "v1"
        assert lease.checkpoint["failures"] == 1
        assert lease.next_due - lease.lease_until == timedelta(seconds=900)
        assert (
            await session.scalar(
                select(func.count())
                .select_from(OperationalAlert)
                .where(OperationalAlert.user_id == owner)
            )
            == 1
        )
    await make_due(factory, owner)
    await runtime.run_source(owner, url, good)
    async with factory() as session:
        lease = await session.scalar(select(JobLease).where(JobLease.user_id == owner))
        assert lease.failure_code is None and lease.checkpoint["failures"] == 0


async def test_concurrent_worker_and_stale_fetch_cannot_publish(source_fixture):
    factory, owner, url = source_fixture
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow(headers):
        entered.set()
        await release.wait()
        return [article(url)], PublicResponse(200, b"", {}, url)

    worker = asyncio.create_task(runtime.run_source(owner, url, slow))
    await entered.wait()
    other = AsyncMock()
    try:
        assert (await runtime.run_source(owner, url, other))["status"] == "leased_or_not_due"
        other.assert_not_awaited()
        # Simulate authoritative takeover by another worker after expiry.
        async with factory.begin() as session:
            await session.execute(
                update(JobLease).where(JobLease.user_id == owner).values(token=str(uuid.uuid4()))
            )
    finally:
        release.set()
    assert (await worker)["error_code"] == "STALE_JOB_LEASE"
    async with factory() as session:
        assert not await session.scalar(select(NewsArticle.id).where(NewsArticle.url == url))


async def test_failed_checkpoint_rolls_back_published_evidence(source_fixture, monkeypatch):
    factory, owner, url = source_fixture
    original = runtime.complete

    async def fail_success(*args, **kwargs):
        if kwargs.get("failure_code") is None:
            raise RuntimeError("synthetic checkpoint failure")
        return await original(*args, **kwargs)

    monkeypatch.setattr(runtime, "complete", fail_success)
    fetch = AsyncMock(return_value=([article(url)], PublicResponse(200, b"", {"etag": "v1"}, url)))
    assert (await runtime.run_source(owner, url, fetch))["status"] == "failed"
    async with factory() as session:
        assert not await session.scalar(select(NewsArticle.id).where(NewsArticle.url == url))
        lease = await session.scalar(select(JobLease).where(JobLease.user_id == owner))
        assert lease.last_success is None and "etag" not in lease.checkpoint


async def test_scheduled_sources_isolate_failures_and_reuse_due_state(source_fixture, monkeypatch):
    _, owner, url = source_fixture
    monkeypatch.setattr(runtime, "RSS_FEEDS", {"Good fixture": url, "Bad fixture": url + "/bad"})
    monkeypatch.setattr(runtime, "_SCRAPE_TARGETS", [])
    monkeypatch.setattr(runtime.config.settings, "news_api_adapters_enabled", False)
    calls = []

    def fetch(source, address, *, headers):
        calls.append(address)
        if address.endswith("/bad"):
            raise PublicFetchError("PUBLIC_HTTP_503")
        return [article(url)], PublicResponse(200, b"", {"etag": "v1"}, url)

    monkeypatch.setattr(runtime, "fetch_rss_source", fetch)
    result = await runtime.run_sources(user_id=owner)
    assert result["status"] == "partial_failure" and result["inserted"] == 1, result
    assert len(result["source_failures"]) == 1 and len(calls) == 2
    second = await runtime.run_sources(user_id=owner)
    assert second["sources_not_due"] == 2 and len(calls) == 2
    assert (
        second["status"] == "partial_failure"
        and second["source_failures"][0]["status"] == "retry_wait"
    )
