"""Full-text search over stored news articles using PostgreSQL FTS.

PostgreSQL's `plainto_tsquery` handles natural language queries gracefully:
- Input "Fed interest rates" becomes "Fed & interest & rates"
- Stemming is applied (investing → invest)
- Stop words are ignored

No extra index is needed for small corpora; for >500k articles consider
adding a GIN index on `to_tsvector('english', title || ' ' || summary)`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, and_, func, select

from src.db.models import NewsArticle
from src.db.database import async_session
from src.news.visibility import visible_to


async def search_news(
    query: str,
    days_back: int = 30,
    sources: list[str] | None = None,
    sentiment: str | None = None,
    limit: int = 20,
    *,
    user_id: str | None = None,
) -> list[dict]:
    """Search stored articles using PostgreSQL full-text search.

    Args:
        query:      Natural-language search string, e.g. "ECB interest rate hike".
        days_back:  Only return articles published within this many days.
                    Pass 0 to search all history.
        sources:    Restrict to these source names (case-insensitive).
        sentiment:  Filter by "bullish", "bearish", or "neutral".
        limit:      Maximum results to return (capped at 100).

    Returns:
        List of article dicts ordered by relevance (ts_rank) descending.
    """
    limit = min(max(1, limit), 100)

    # Build the tsvector expression over title + summary + content
    ts_vector = func.to_tsvector(
        "english",
        func.coalesce(NewsArticle.title, "")
        + " "
        + func.coalesce(NewsArticle.summary, "")
        + " "
        + func.coalesce(NewsArticle.content, ""),
    )
    ts_query = func.plainto_tsquery("english", query)
    rank = func.ts_rank(ts_vector, ts_query)

    filters = [visible_to(user_id), ts_vector.op("@@")(ts_query)]

    if days_back > 0:
        since = datetime.now(UTC) - timedelta(days=days_back)
        filters.append(
            or_(
                NewsArticle.published_at >= since,
                and_(
                    NewsArticle.published_at.is_(None),
                    NewsArticle.fetched_at >= since,
                ),
            )
        )

    if sources:
        src_lower = [s.lower() for s in sources]
        filters.append(or_(*(func.lower(NewsArticle.source).contains(s) for s in src_lower)))

    if sentiment and sentiment in ("bullish", "bearish", "neutral"):
        filters.append(NewsArticle.sentiment_label == sentiment)

    stmt = select(NewsArticle).where(and_(*filters)).order_by(rank.desc()).limit(limit)

    async with async_session() as session:
        rows = (await session.execute(stmt)).scalars().all()

    return [
        {
            "title": r.title,
            "summary": r.summary,
            "source": r.source,
            "url": r.url,
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "sentiment": r.sentiment_label,
            "first_seen_at": r.fetched_at.isoformat(),
            "available_at": r.available_at.isoformat() if r.available_at else None,
            "content_hash": r.content_hash,
            "provenance": r.provenance,
            "sentiment_score": r.sentiment_score,
            "tags": r.tags,
        }
        for r in rows
    ]


async def get_recent_headlines(limit: int = 20, *, user_id: str | None = None) -> list[dict]:
    """Return the most recently fetched headlines regardless of query."""
    stmt = (
        select(NewsArticle)
        .where(visible_to(user_id))
        .order_by(NewsArticle.fetched_at.desc(), NewsArticle.published_at.desc())
        .limit(min(max(limit, 1), 100))
    )
    async with async_session() as session:
        rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "title": r.title,
            "source": r.source,
            "url": r.url,
            "published_at": r.published_at.isoformat() if r.published_at else None,
            "sentiment": r.sentiment_label,
            "first_seen_at": r.fetched_at.isoformat(),
            "available_at": r.available_at.isoformat() if r.available_at else None,
            "content_hash": r.content_hash,
            "provenance": r.provenance,
        }
        for r in rows
    ]


async def get_news_evidence_as_of(
    as_of: datetime, *, user_id: str | None = None, limit: int = 100
) -> list[dict]:
    """Latest observed revision per visible URL at a historical decision instant.

    Unknown legacy availability is excluded. Ownership is evaluated now as well,
    so replay never restores a deactivated user's authority.
    """
    from src.db.models import NewsRevision

    if as_of.tzinfo is None:
        raise ValueError("A timezone-aware decision timestamp is required")
    ranked = (
        select(
            NewsRevision.id.label("id"),
            func.row_number()
            .over(
                partition_by=NewsRevision.article_id,
                order_by=(
                    NewsRevision.available_at.desc(),
                    NewsRevision.recorded_at.desc(),
                    NewsRevision.id.desc(),
                ),
            )
            .label("rank"),
        )
        .join(NewsArticle, NewsArticle.id == NewsRevision.article_id)
        .where(
            visible_to(user_id),
            NewsRevision.available_at <= as_of,
        )
        .subquery()
    )
    statement = (
        select(NewsRevision)
        .join(ranked, ranked.c.id == NewsRevision.id)
        .where(ranked.c.rank == 1)
        .order_by(NewsRevision.available_at.desc())
        .limit(min(max(limit, 1), 1000))
    )
    async with async_session() as session:
        rows = (await session.execute(statement)).scalars().all()
    return [
        dict(
            row.evidence,
            revision_id=row.id,
            content_hash=row.content_hash,
            available_at=row.available_at.isoformat(),
        )
        for row in rows
    ]
