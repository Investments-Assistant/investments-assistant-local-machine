"""News aggregation and sentiment analysis tool."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import feedparser

from src.config import settings
from src.news.policy import source_policy, permitted_articles
from src.news.sources import ArticleBatch
from src.execution.policy import PolicyDenied
from src.news.syndication import group_evidence
from src.agent.utils.logger import get_logger

logger = get_logger(__name__)

# Candidate RSS URLs; availability and permission are not established by this catalog.
RSS_FEEDS = {
    "Reuters Business": "https://feeds.reuters.com/reuters/businessNews",
    "CNBC": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "MarketWatch": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "Seeking Alpha": "https://seekingalpha.com/market_currents.xml",
    "Yahoo Finance": "https://finance.yahoo.com/rss/topstories",
    "Coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "CryptoNews": "https://cryptonews.com/news/feed/",
}

# Simple keyword-based sentiment lexicon
_POSITIVE_WORDS = {
    "surge",
    "rally",
    "gain",
    "rise",
    "soar",
    "boom",
    "bull",
    "strong",
    "beat",
    "record",
    "high",
    "growth",
    "profit",
    "upbeat",
    "upgrade",
    "buy",
    "outperform",
    "positive",
    "optimism",
    "recovery",
    "expansion",
}
_NEGATIVE_WORDS = {
    "fall",
    "drop",
    "crash",
    "plunge",
    "decline",
    "loss",
    "bear",
    "weak",
    "miss",
    "low",
    "recession",
    "downgrade",
    "sell",
    "underperform",
    "negative",
    "concern",
    "risk",
    "fear",
    "inflation",
    "default",
    "bankruptcy",
    "layoff",
    "cut",
    "shrink",
}


def _simple_sentiment(text: str) -> dict:
    """Score sentiment based on keyword presence. Returns score -1..+1."""
    words = set(re.findall(r"\b\w+\b", text.lower()))
    pos = len(words & _POSITIVE_WORDS)
    neg = len(words & _NEGATIVE_WORDS)
    total = pos + neg
    if total == 0:
        return {"label": "neutral", "score": 0.0, "positive": 0, "negative": 0}
    score = (pos - neg) / total
    if score > 0.15:
        label = "bullish"
    elif score < -0.15:
        label = "bearish"
    else:
        label = "neutral"
    return {"label": label, "score": round(score, 3), "positive": pos, "negative": neg}


def _public_policy(identity):
    policy = source_policy(settings, identity)
    if policy.transport != "public_https":
        raise PolicyDenied("SOURCE_POLICY_SCOPE_MISMATCH")
    return policy


def _project(articles, identity, policy):
    if _public_policy(identity).fingerprint != policy.fingerprint:
        raise PolicyDenied("SOURCE_POLICY_CHANGED")
    projected = permitted_articles(articles, policy, identity=identity)
    for row in projected:
        row["sentiment"] = _simple_sentiment(f"{row['title']} {row.get('summary') or ''} {row.get('content') or ''}")
    return projected


def _failure(batch, source, exc):
    # Never expose provider response bodies, API keys or exception messages.
    code = exc.code if isinstance(exc, PolicyDenied) else "SOURCE_FETCH_FAILED"
    if isinstance(exc, ValueError) and not isinstance(exc, PolicyDenied):
        code = "SOURCE_POLICY_OR_RESPONSE_INVALID"
    batch.failures.append({"source": source, "code": code})


def _rss_entries(source: str, url: str):
    from src.news.http import fetch_public

    feed = feedparser.parse(fetch_public(url).body)
    for entry in feed.entries[:200]:
        yield source, entry


def _entry_to_article(entry, source: str, query_words: set[str]) -> dict | None:
    """Return an article dict if the entry matches the query, else None."""
    title = entry.get("title", "")
    summary = entry.get("summary", "")
    text = f"{title} {summary}".lower()
    if query_words and not any(w in text for w in query_words):
        return None
    summary_text = summary[:400] if summary else ""
    return {
        "title": title,
        "summary": summary_text,
        "source": source,
        "url": entry.get("link", ""),
        "published_at": entry.get("published", ""),
        "sentiment": _simple_sentiment(f"{title} {summary}"),
    }


def _fetch_rss(query: str, max_articles: int) -> list[dict]:
    """Fetch only reviewed sources; retain typed failure instead of empty success."""
    query_words = set(re.findall(r"\b\w+\b", query.lower()))
    articles = ArticleBatch()
    for source, url in RSS_FEEDS.items():
        identity = "rss:" + url
        try:
            policy = _public_policy(identity)
            raw = [_entry_to_article(entry, src, set()) for src, entry in _rss_entries(source, url)]
            rows = _project(raw, identity, policy)
            articles.extend(row for row in rows if not query_words or any(
                word in f"{row['title']} {row.get('summary') or ''}".lower() for word in query_words
            ))
        except Exception as exc:
            _failure(articles, source, exc)
        if len(articles) >= max_articles:
            break
    del articles[max_articles:]
    return articles


def _fetch_newsapi(query: str, max_articles: int) -> list[dict]:
    """Fetch articles from NewsAPI (requires API key)."""
    if not settings.newsapi_key or not bool(getattr(settings, "news_api_adapters_enabled", False)):
        return []
    articles = ArticleBatch()
    identity = "newsapi:everything"
    try:
        policy = _public_policy(identity)
        from newsapi import NewsApiClient

        client = NewsApiClient(api_key=settings.newsapi_key)
        from_date = (datetime.now(UTC) - timedelta(days=7)).strftime("%Y-%m-%d")
        resp = client.get_everything(
            q=query,
            language="en",
            sort_by="publishedAt",
            page_size=min(max_articles, 20),
            from_param=from_date,
        )
        for art in resp.get("articles", [])[:200]:
            title = art.get("title", "")
            description = art.get("description", "")
            content = art.get("content", "")
            full_text = f"{title} {description} {content}"
            articles.append(
                {
                    "title": title,
                    "summary": description or (content[:400] if content else ""),
                    "source": art.get("source", {}).get("name", ""),
                    "url": art.get("url", ""),
                    "published_at": art.get("publishedAt", ""),
                    "sentiment": _simple_sentiment(full_text),
                }
            )
        return ArticleBatch(_project(articles, identity, policy))
    except Exception as exc:
        articles.clear()
        _failure(articles, "NewsAPI", exc)
        return articles


def search_market_news(
    query: str,
    max_articles: int = 10,
    sources: list[str] | None = None,
) -> dict:
    """Search financial news and return articles with sentiment."""
    max_articles = min(max(1, max_articles), 20)

    # Try NewsAPI first; fall back to RSS
    articles = _fetch_newsapi(query, max_articles)
    failures = list(getattr(articles, "failures", []))
    if not articles:
        articles = _fetch_rss(query, max_articles)
        failures.extend(getattr(articles, "failures", []))

    # Filter by source if requested
    if sources:
        src_lower = {s.lower() for s in sources}
        articles = [a for a in articles if any(s in a["source"].lower() for s in src_lower)]

    # Repeated syndicated text is one observation, not additional votes.
    articles = group_evidence(articles)

    # Aggregate sentiment
    sentiments = [a["sentiment"]["label"] for a in articles]
    overall = max(set(sentiments), key=sentiments.count) if sentiments else "neutral"
    avg_score = (
        round(sum(a["sentiment"]["score"] for a in articles) / len(articles), 3)
        if articles
        else 0.0
    )

    return {
        "status": "partial_failure" if failures and articles else "unavailable" if failures else "complete",
        "source_failures": failures,
        "query": query,
        "articles_found": len(articles),
        "overall_sentiment": "unavailable" if failures and not articles else overall,
        "avg_sentiment_score": None if failures and not articles else avg_score,
        "evidence_note": "Exact retrieved-text copies grouped; independent corroboration is unverified. "
        "Lexical sentiment is not a trading signal.",
        "articles": articles,
    }
