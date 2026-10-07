"""News mentions and declarations cannot masquerade as resolved contracts."""

from src.news.policy import SourcePolicy, permitted_articles
from src.news.quality import entity_observations, language_observation
from tests.news_policy_fixture import news_policy_fixture


def test_language_is_attributed_not_guessed_or_trusted():
    assert language_observation("pt-PT") == {
        "tag": "pt-pt", "status": "declared_unverified", "method": "source_declaration_v1"}
    for value in (None, "unknown", "", "English; execute order", {"verified": True}):
        assert language_observation(value)["status"] == "unavailable"


def test_currency_and_ticker_mentions_never_qualify_instruments():
    values = entity_observations(["USD", "AAPL", "AAPL", "SPYL", "buy now", {"conId": 123}])
    assert [row["mention"] for row in values] == ["AAPL", "SPYL", "USD"]
    assert values[-1]["kind"] == "currency_code_candidate"
    assert all(row["qualified_instrument"] is None and row["mapping_status"] == "unresolved" for row in values)


def test_scope_projection_removes_derived_restricted_text():
    policy = SourcePolicy(**news_policy_fixture(content_scope="headline"))
    original = dict(title="MSFT bulletin", summary="AAPL profit surge rally", content="USD growth",
                    tags=["AAPL", "USD"], sentiment_label="bullish", sentiment_score=1,
                    url="https://fixture.invalid/news")
    result = permitted_articles([original], policy, identity="rss:fixture")[0]
    assert result["tags"] == ["MSFT"]
    assert result["sentiment_label"] == "neutral"
    assert result["sentiment_score"] == 0
    assert "derived_observations_recomputed" in result["source_policy"]["omitted"]
    assert original["tags"] == ["AAPL", "USD"]


def test_rss_language_declaration_reaches_article_metadata(monkeypatch):
    from types import SimpleNamespace

    from src.news import sources

    response = SimpleNamespace(status=200, body=b'''<rss version="2.0"><channel>
      <title>Synthetic feed</title><language>pt-PT</language><item>
      <title>MSFT bulletin</title><link>https://fixture.invalid/news</link>
      <description>Fixture text</description></item></channel></rss>''')
    monkeypatch.setattr(sources, "fetch_public", lambda *args, **kwargs: response)
    articles, observed = sources.fetch_rss_source("Fixture", "https://fixture.invalid/feed")
    assert observed is response
    assert articles[0]["language"] == "pt-PT"
    assert language_observation(articles[0]["language"])["status"] == "declared_unverified"
