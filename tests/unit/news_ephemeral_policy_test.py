"""On-demand source permissions precede network and bound returned evidence."""

from types import SimpleNamespace
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

from src.tools import news
from src.config import Settings
from tests.news_policy_fixture import news_policy_fixture

URL = "https://fixture.invalid/feed"
IDENTITY = "rss:" + URL


def configure(monkeypatch, policy=None):
    cfg = Settings(_env_file=None, newsapi_key="", news_source_policies={} if policy is None else {IDENTITY: policy})
    monkeypatch.setattr(news, "settings", cfg)
    monkeypatch.setattr(news, "RSS_FEEDS", {"Fixture": URL})
    return cfg


@pytest.mark.parametrize("policy", [None, news_policy_fixture(
    review_due_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat()),
    news_policy_fixture(transport="private_newsletter", article_hosts=[])])
def test_missing_expired_or_private_policy_never_fetches(monkeypatch, policy):
    configure(monkeypatch, policy)
    fetch = Mock(side_effect=AssertionError("Network forbidden"))
    monkeypatch.setattr(news, "_rss_entries", fetch)
    result = news.search_market_news("rates")
    assert result["status"] == "unavailable"
    assert result["source_failures"] and result["articles"] == []
    fetch.assert_not_called()


def test_headline_permission_cannot_leak_summary_through_filter_or_sentiment(monkeypatch):
    configure(monkeypatch, news_policy_fixture(content_scope="headline"))
    monkeypatch.setattr(news, "_rss_entries", lambda *args: iter([("Fixture", {
        "title": "Bulletin", "summary": "profit surge rally", "link": "https://fixture.invalid/news"})]))
    assert news.search_market_news("profit")["articles"] == []
    result = news.search_market_news("Bulletin")
    assert result["status"] == "complete"
    assert result["articles"][0]["summary"] == ""
    assert result["avg_sentiment_score"] == 0
    assert result["articles"][0]["source_policy"]["policy"]["content_scope"] == "headline"


def test_revoked_policy_during_fetch_discards_response(monkeypatch):
    cfg = configure(monkeypatch, news_policy_fixture())

    def entries(*args):
        cfg.news_source_policies.clear()
        yield "Fixture", {"title": "rates", "link": "https://fixture.invalid/news"}

    monkeypatch.setattr(news, "_rss_entries", entries)
    result = news.search_market_news("rates")
    assert result["status"] == "unavailable"
    assert result["articles"] == []
    assert result["source_failures"][0]["code"] == "SOURCE_PERMISSION_REQUIRED"


def test_provider_exception_is_redacted_and_not_empty_success(monkeypatch):
    configure(monkeypatch, news_policy_fixture())
    monkeypatch.setattr(news, "_rss_entries", Mock(side_effect=RuntimeError("SECRET fixture credential")))
    result = news.search_market_news("rates")
    assert result["status"] == "unavailable"
    assert "SECRET" not in str(result)


def test_api_needs_permission_and_preserves_description_without_content(monkeypatch):
    import newsapi

    cfg = configure(monkeypatch)
    cfg.newsapi_key = "synthetic-only"
    cfg.news_api_adapters_enabled = True
    client = Mock(return_value=SimpleNamespace(get_everything=lambda **kw: {"articles": [{
        "title": "Rates", "description": "Original description", "content": None,
        "url": "https://fixture.invalid/news", "source": {"name": "Fixture"}}]}))
    monkeypatch.setattr(newsapi, "NewsApiClient", client)
    denied = news._fetch_newsapi("rates", 10)
    assert denied.failures[0]["code"] == "SOURCE_PERMISSION_REQUIRED"
    client.assert_not_called()
    cfg.news_source_policies["newsapi:everything"] = news_policy_fixture()
    result = news._fetch_newsapi("rates", 10)
    assert result[0]["summary"] == "Original description"
    assert result[0]["source_policy"]["identity"] == "newsapi:everything"


def test_unpermitted_article_host_never_returns_partial_source_text(monkeypatch):
    configure(monkeypatch, news_policy_fixture())
    monkeypatch.setattr(news, "_rss_entries", lambda *args: iter([("Fixture", {
        "title": "Rates", "summary": "Sensitive source text", "link": "https://unreviewed.invalid/news"})]))
    result = news.search_market_news("rates")
    assert result["status"] == "unavailable"
    assert result["source_failures"][0]["code"] == "SOURCE_ARTICLE_HOST_NOT_PERMITTED"
    assert result["avg_sentiment_score"] is None
    assert "Sensitive" not in str(result)


def test_chat_fallback_does_not_turn_permission_failure_into_no_news(monkeypatch):
    import json

    from src.agent.clients.llama_cpp_client import _format_news_result

    configure(monkeypatch)
    result = news.search_market_news("rates")
    answer = _format_news_result(json.dumps(result))
    assert "unavailable" in answer
    assert "No matching" not in answer and "neutral" not in answer
