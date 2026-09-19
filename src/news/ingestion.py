"""Ingestion pipeline: fetch from all sources and persist to PostgreSQL.

URL upserts append immutable revisions only when observed content changes.
Publication timestamps never substitute for locally observed availability.
"""

from __future__ import annotations

import json
from typing import Any
import hashlib
from contextlib import asynccontextmanager

from sqlalchemy import or_, cast, func, select
from sqlalchemy.dialects.postgresql import (
    JSONB,
    insert as pg_insert,
)

from src.db.models import NewsArticle, NewsRevision
from src.db.database import async_session
from src.news.visibility import visible_to
from src.security.sessions import assert_active
from src.agent.utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def _article_session(existing):
    if existing is not None:
        yield existing
    else:
        async with async_session() as session:
            yield session


async def ingest_articles(articles: list[dict[str, Any]], *, owner_user_id: str | None = None, db_session=None) -> int:
    """Persist *articles* to the DB. Returns the count of newly inserted rows.

    Returns newly inserted or corrected articles; exact repeated content is skipped.
    """
    if not articles:
        return 0

    rows = [
        {
            "content_hash": hashlib.sha256(
                json.dumps(
                    {k: a.get(k) for k in ("title", "summary", "content", "published_at")},
                    sort_keys=True,
                    default=str,
                    ensure_ascii=False,
                ).encode()
            ).hexdigest(),
            "available_at": func.clock_timestamp(),
            "provenance": {
                "language": a.get("language", "unknown"),
                "license": a.get("license", "unverified"),
                "retention": a.get("retention", "operator_review_required"),
                "entities": a.get("tags", []),
            },
            "title": a["title"],
            "summary": a.get("summary", ""),
            "content": a.get("content"),
            "source": a["source"],
            "url": ("newsletter://" + hashlib.sha256((owner_user_id + "\0" + a["url"]).encode()).hexdigest())
            if owner_user_id
            else a["url"],
            "user_id": owner_user_id,
            "visibility": "private" if owner_user_id else "public",
            "published_at": a.get("published_at"),
            "sentiment_label": a.get("sentiment_label", "neutral"),
            "sentiment_score": a.get("sentiment_score", 0.0),
            "tags": a.get("tags", []),
        }
        for a in articles
        if a.get("url") and (owner_user_id or a["url"].startswith("https://"))
    ]

    if not rows:
        return 0

    async with _article_session(db_session) as session:
        if owner_user_id:
            await assert_active(session, owner_user_id)
        # Collapse exact repeated URLs within a batch before PostgreSQL upsert.
        rows = list({row["url"]: row for row in rows}.values())
        insert = pg_insert(NewsArticle).values(rows)
        mutable = (
            "title",
            "summary",
            "content",
            "published_at",
            "sentiment_label",
            "sentiment_score",
            "tags",
            "content_hash",
            "available_at",
            "provenance",
            "source",
        )
        statement = (
            insert.on_conflict_do_update(
                index_elements=["url"],
                set_={key: getattr(insert.excluded, key) for key in mutable},
                where=or_(
                    NewsArticle.content_hash.is_distinct_from(insert.excluded.content_hash),
                    cast(NewsArticle.provenance, JSONB).is_distinct_from(cast(insert.excluded.provenance, JSONB)),
                    NewsArticle.source.is_distinct_from(insert.excluded.source),
                    NewsArticle.sentiment_label.is_distinct_from(insert.excluded.sentiment_label),
                    NewsArticle.sentiment_score.is_distinct_from(insert.excluded.sentiment_score),
                )
                & (NewsArticle.visibility == insert.excluded.visibility)
                & (NewsArticle.user_id.is_not_distinct_from(insert.excluded.user_id)),
            )
            .returning(NewsArticle)
            .execution_options(populate_existing=True)
        )
        changed = (await session.execute(statement)).scalars().all()
        for article in changed:
            session.add(
                NewsRevision(
                    article_id=article.id,
                    content_hash=article.content_hash,
                    available_at=article.available_at,
                    evidence={
                        key: (value.isoformat() if hasattr(value, "isoformat") else value)
                        for key in (
                            "title",
                            "summary",
                            "content",
                            "source",
                            "url",
                            "published_at",
                            "provenance",
                            "sentiment_label",
                            "sentiment_score",
                        )
                        for value in [getattr(article, key)]
                    },
                )
            )
        if db_session is None:
            await session.commit()
        return len(changed)


async def run_ingestion(days_back: int = 1, *, user_id: str | None = None) -> dict[str, Any]:
    """Run durable ingestion only for an explicitly selected active principal."""
    from src.news.runtime import run_sources

    return await run_sources(user_id=user_id, days_back=days_back)


async def get_article_count(*, user_id: str | None = None) -> int:
    """Count only articles visible to the current principal, entirely in SQL."""
    async with async_session() as session:
        return await session.scalar(select(func.count()).select_from(NewsArticle).where(visible_to(user_id))) or 0
