"""Explicit-principal source leases, conditional RSS and durable retry checkpoints."""

import asyncio
import hashlib

from sqlalchemy import func, select

from src import config
from src.news.http import PublicFetchError
from src.db.database import async_session
from src.news.sources import (
    RSS_FEEDS,
    _SCRAPE_TARGETS,
    _GUARDIAN_SECTIONS,
    source_work,
    fetch_scraped,
    fetch_guardian,
    fetch_rss_source,
)
from src.news.ingestion import ingest_articles
from src.operations.jobs import acquire, complete
from src.execution.policy import PolicyDenied
from src.operations.alerts import emit
from src.operations.models import JobLease
from src.security.sessions import assert_active


def validator(value):
    return (
        value
        if isinstance(value, str)
        and len(value) <= 512
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
        else None
    )


def source_key(identity):
    return "news:" + hashlib.sha256(identity.encode()).hexdigest()[:40]


async def run_source(user_id, identity, fetch, *, interval_seconds=3600):
    """Fetch outside DB transactions; persist evidence and fenced checkpoint together."""
    name = source_key(identity)
    async with async_session.begin() as session:
        lease = await acquire(session, user_id=user_id, name=name, lease_seconds=180)
        if lease is None:
            prior = await session.scalar(
                select(JobLease).where(JobLease.user_id == user_id, JobLease.name == name)
            )
            return {
                "status": "retry_wait" if prior and prior.failure_code else "leased_or_not_due",
                "error_code": prior.failure_code if prior else None,
                "fetched": 0,
                "inserted": 0,
            }
        row = await session.get(JobLease, lease[0])
        previous = dict(row.checkpoint or {})
    headers = {}
    for field, header in (("etag", "If-None-Match"), ("last_modified", "If-Modified-Since")):
        if validator(previous.get(field)):
            headers[header] = previous[field]
    try:
        async with asyncio.timeout(120):
            articles, response = await fetch(headers)
        failures = getattr(articles, "failures", [])
        if failures:
            raise PublicFetchError(
                "SOURCE_BATCH_INCOMPLETE",
                retry_after=max(
                    (failure.get("retry_after") or 0 for failure in failures), default=0
                ),
            )
        status = response.status if response else 200
        if status == 304 and (not previous.get("validated_at") or not headers):
            raise PublicFetchError("UNEXPECTED_NOT_MODIFIED")
        async with async_session.begin() as session:
            row = await session.scalar(
                select(JobLease).where(JobLease.id == lease[0]).with_for_update()
            )
            now = await session.scalar(select(func.clock_timestamp()))
            if row.token != lease[1] or row.lease_until <= now:
                raise PolicyDenied("STALE_JOB_LEASE")
            await assert_active(session, user_id)
            inserted = await ingest_articles(articles, db_session=session)
            metadata = response.headers if response else {}
            checkpoint = {
                "schema": 1,
                "validated_at": now.isoformat(),
                "failures": 0,
                "fetched": len(articles),
                "inserted": inserted,
                "etag": validator(metadata.get("etag"))
                or (previous.get("etag") if status == 304 else None),
                "last_modified": validator(metadata.get("last-modified"))
                or (previous.get("last_modified") if status == 304 else None),
            }
            await complete(
                session,
                lease_id=lease[0],
                token=lease[1],
                checkpoint=checkpoint,
                interval_seconds=interval_seconds,
            )
        return {
            "status": "not_modified" if status == 304 else "complete",
            "fetched": len(articles),
            "inserted": inserted,
        }
    except asyncio.CancelledError:
        # Leave the lease to expire. Native fetch capacity remains held until worker exit.
        raise
    except Exception as exc:
        code = str(exc) if isinstance(exc, (PublicFetchError, PolicyDenied)) else type(exc).__name__
        # Only bounded internal codes reach audit; never raw provider exception payloads.
        if not code.replace("_", "").isalnum() or len(code) > 64:
            code = "NEWS_SOURCE_FAILED"
        async with async_session.begin() as session:
            row = await session.scalar(
                select(JobLease).where(JobLease.id == lease[0]).with_for_update()
            )
            now = await session.scalar(select(func.clock_timestamp()))
            if row.token != lease[1] or row.lease_until <= now:
                return {
                    "status": "failed",
                    "error_code": "STALE_JOB_LEASE",
                    "fetched": 0,
                    "inserted": 0,
                }
            failures = min(int(previous.get("failures", 0)) + 1, 10)
            # Retry metadata changes; last successful content validators and success time do not.
            row.checkpoint = {**previous, "failures": failures}
            await complete(
                session,
                lease_id=lease[0],
                token=lease[1],
                checkpoint={},
                interval_seconds=min(
                    86400, max(300 * 2 ** (failures - 1), getattr(exc, "retry_after", None) or 0)
                ),
                failure_code=code,
            )
            await emit(
                session,
                user_id=user_id,
                rule="source_failure:" + name,
                observed_value=code,
                threshold="successful source retrieval",
                message="A configured news source needs attention.",
                evidence_at=now,
            )
        return {"status": "failed", "error_code": code, "fetched": 0, "inserted": 0}


async def run_sources(*, user_id, days_back=1):
    if not user_id:
        return {
            "status": "blocked",
            "error_code": "NEWS_PRINCIPAL_REQUIRED",
            "fetched": 0,
            "inserted": 0,
        }
    if not 1 <= days_back <= 30:
        raise ValueError("days_back must be between 1 and 30")
    interval = config.settings.news_ingestion_minutes * 60
    # Never infer an admin owner or credentials. Public articles remain public;
    # only the operational lease/alert belongs to the explicitly selected principal.
    async with async_session() as session:
        await assert_active(session, user_id)
    results = []
    feeds = list(RSS_FEEDS.items())
    for offset in range(0, len(feeds), 2):

        async def rss(source, url):
            async def fetch(headers):
                return await source_work.arun(
                    fetch_rss_source, source, url, headers=headers, timeout=25
                )

            return await run_source(user_id, "rss:" + url, fetch, interval_seconds=interval)

        results.extend(
            await asyncio.gather(*(rss(source, url) for source, url in feeds[offset : offset + 2]))
        )
    adapters = [
        ("scrape:" + target[1], lambda selected=target: fetch_scraped(targets=[selected]))
        for target in _SCRAPE_TARGETS
    ]
    if config.settings.news_api_adapters_enabled and config.settings.guardian_api_key:
        adapters.extend(
            (
                "guardian:" + section,
                lambda selected=section: fetch_guardian(days_back=days_back, sections=[selected]),
            )
            for section in _GUARDIAN_SECTIONS
        )
    for name, callback in adapters:

        async def batch(headers, function=callback):
            return await function(), None

        results.append(await run_source(user_id, name, batch, interval_seconds=interval))
    failures = [result for result in results if result["status"] in {"failed", "retry_wait"}]
    return {
        "status": "partial_failure" if failures else "complete",
        "fetched": sum(result["fetched"] for result in results),
        "inserted": sum(result["inserted"] for result in results),
        "source_failures": failures,
        "sources_not_due": sum(
            result["status"] in {"leased_or_not_due", "retry_wait"} for result in results
        ),
    }
