"""APScheduler background jobs: market data polling and weekly reports."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.config import settings
from src.tools.news import search_market_news
from src.news.ingestion import run_ingestion
from src.news.email_reader import read_and_ingest_newsletters
from src.tools.market_data import get_market_overview
from src.agent.utils.logger import get_logger

logger = get_logger(__name__)

scheduler = AsyncIOScheduler()

# Cache for the latest market snapshot (served to the UI)
_latest_snapshot: dict = {}


def get_latest_snapshot() -> dict:
    return _latest_snapshot


async def _refresh_market_data() -> None:
    """Pull latest market overview + major news. Runs every N minutes."""
    global _latest_snapshot
    logger.info("Scheduled: refreshing market data")
    try:
        # yfinance and the RSS reader are synchronous adapters.  Run them in
        # worker threads so a slow provider cannot stall WebSocket responses.
        overview, btc_news, stock_news = await asyncio.gather(
            asyncio.to_thread(get_market_overview),
            asyncio.to_thread(search_market_news, "Bitcoin crypto market", max_articles=5),
            asyncio.to_thread(search_market_news, "stock market S&P 500", max_articles=5),
        )
        _latest_snapshot = {
            "timestamp": datetime.now(UTC).isoformat(),
            "market_overview": overview,
            "crypto_news": btc_news,
            "stock_news": stock_news,
        }
        logger.debug("Market snapshot refreshed")
    except Exception as exc:
        logger.error("Market data refresh failed: %s", exc)


async def _run_weekly_report() -> None:
    """Generate reports only for explicitly opted-in, active users."""
    from datetime import timedelta

    from src.tools.dispatcher import tool_context
    from src.operations.runner import run_scoped, monitoring_users
    from src.scheduler.reporter import generate_report

    async def report(user_id):
        today = datetime.now(UTC).date()
        with tool_context("scheduled-report", user_id, "recommend"):
            result = await generate_report(str(today - timedelta(days=7)), str(today))
            if result.get("status") != "complete":
                raise RuntimeError("REPORT_PARTIAL_FAILURE")

    for user_id in await monitoring_users():
        await run_scoped(user_id, "weekly_report", report, interval_seconds=86400)


async def _ingest_news() -> None:
    """Fetch and persist articles from all configured sources."""
    logger.info("Scheduled: news ingestion")
    stats = await run_ingestion(days_back=1, user_id=settings.news_service_user_id or None)
    logger.info("News ingestion outcome: %s", stats)


async def _ingest_newsletter() -> None:
    """Check inbox for new newsletters and ingest them (runs Saturday mornings)."""
    logger.info("Scheduled: newsletter email ingestion")
    stats = await read_and_ingest_newsletters(since_days=8)
    logger.info("Newsletter ingestion complete: %s", stats)


async def _autonomous_scan() -> None:
    """Read-only reviews, with explicit user opt-in and durable completion leases."""
    if not settings.autonomous_scans_enabled:
        return
    import uuid

    from src.operations.runner import run_scoped, monitoring_users
    from src.agent.orchestrator import get_or_create_session

    async def scan(user_id):
        session_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "local-monitoring:" + user_id))
        session = get_or_create_session(session_id, user_id)
        prompt = (
            "Review latest stored news, market overview and my portfolio exposure. "
            "Fetch scoped read evidence, identify missing or stale data, and state uncertainty. "
            "This is monitoring only. Do not submit, confirm, cancel, or change trading policy."
        )
        model_failed = False
        async for event in session.chat(prompt):
            model_failed |= event.get("type") == "error"
        # Finish persisting scoped partial evidence before raising the job alert.
        if model_failed:
            raise RuntimeError("MONITORING_MODEL_UNAVAILABLE")

    for user_id in await monitoring_users():
        await run_scoped(
            user_id,
            "market_scan",
            scan,
            interval_seconds=settings.autonomous_scan_interval_minutes * 60,
        )


def setup_scheduler() -> None:
    """Register all scheduled jobs and start the scheduler."""

    # Market data refresh (every N minutes, all day)
    scheduler.add_job(
        _refresh_market_data,
        trigger=IntervalTrigger(minutes=settings.market_data_refresh_minutes),
        id="market_data_refresh",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # Weekly report
    scheduler.add_job(
        _run_weekly_report,
        trigger=CronTrigger(
            day_of_week=settings.weekly_report_day,
            hour=settings.weekly_report_hour,
            minute=settings.weekly_report_minute,
            timezone="UTC",
        ),
        id="weekly_report",
        replace_existing=True,
    )

    # Autonomous review (hourly by default, including global/crypto markets)
    scheduler.add_job(
        _autonomous_scan,
        trigger=IntervalTrigger(minutes=settings.autonomous_scan_interval_minutes),
        id="autonomous_scan",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )

    # News memory ingestion (hourly by default, 24/7)
    scheduler.add_job(
        _ingest_news,
        trigger=IntervalTrigger(minutes=settings.news_ingestion_minutes),
        id="news_ingestion",
        replace_existing=True,
        misfire_grace_time=120,
        max_instances=1,
        coalesce=True,
    )

    # Newsletter email reader (every Saturday at 09:00 UTC = ~10am Lisbon time)
    scheduler.add_job(
        _ingest_newsletter,
        trigger=CronTrigger(
            day_of_week="sat",
            hour=9,
            minute=0,
            timezone="UTC",
        ),
        id="newsletter_ingestion",
        replace_existing=True,
    )

    from src.expenses.runtime import poll_connections

    scheduler.add_job(
        poll_connections,
        trigger=IntervalTrigger(minutes=15),
        id="bank_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )

    from src.execution.monitor import monitor_simulator_risk
    from src.execution.runtime import run_simulator_strategies

    scheduler.add_job(
        monitor_simulator_risk,
        trigger=IntervalTrigger(seconds=60),
        id="simulator_risk_monitor",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )

    scheduler.add_job(
        run_simulator_strategies,
        trigger=IntervalTrigger(seconds=60),
        id="approved_simulator_strategies",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=30,
    )
    scheduler.start()
    logger.info("Scheduler started (%d jobs)", len(scheduler.get_jobs()))


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
