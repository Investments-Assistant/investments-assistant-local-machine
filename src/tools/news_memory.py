"""Agent-facing wrapper for the news memory system.

The agent calls `search_stored_news` to query the persistent article DB
and `get_recent_headlines` to see what just came in.
"""

from __future__ import annotations

from src.news.search import search_news, get_recent_headlines
from src.news.ingestion import run_ingestion, get_article_count


async def search_stored_news(
    query: str,
    days_back: int = 30,
    sources: list[str] | None = None,
    sentiment: str | None = None,
    limit: int = 20,
) -> dict:
    """Search the persistent news memory using full-text search.

    Args:
        query:      What to search for, e.g. "ECB rate hike Portugal".
        days_back:  How far back to look (0 = all history).
        sources:    Restrict to specific sources, e.g. ["The Guardian", "Reuters"].
        sentiment:  Filter by sentiment: "bullish", "bearish", or "neutral".
        limit:      Max articles to return (1–100).
    """
    from src.tools.dispatcher import _tool_user_id

    user_id = _tool_user_id.get()
    articles = await search_news(
        user_id=user_id,
        query=query,
        days_back=days_back,
        sources=sources,
        sentiment=sentiment,
        limit=limit,
    )
    total = await get_article_count(user_id=user_id)
    return {
        "query": query,
        "results_found": len(articles),
        "total_articles_in_memory": total,
        "filters": {
            "days_back": days_back,
            "sources": sources,
            "sentiment": sentiment,
        },
        "articles": articles,
    }


async def get_latest_news(limit: int = 20) -> dict:
    """Return the most recently ingested headlines from all sources."""
    from src.tools.dispatcher import _tool_user_id

    user_id = _tool_user_id.get()
    articles = await get_recent_headlines(limit=limit, user_id=user_id)
    total = await get_article_count(user_id=user_id)
    return {
        "total_articles_in_memory": total,
        "articles": articles,
    }


async def trigger_news_ingestion() -> dict:
    """Manually trigger a news ingestion cycle (normally runs on a schedule)."""
    from src.tools.dispatcher import _tool_user_id

    return await run_ingestion(days_back=1, user_id=_tool_user_id.get())
