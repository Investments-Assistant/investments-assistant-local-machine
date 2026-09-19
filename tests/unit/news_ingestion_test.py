"""Unit tests for src/news/ingestion.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.news.ingestion import run_ingestion, ingest_articles, get_article_count


def _make_article(url: str = "https://example.com/1") -> dict:
    return {
        "title": "Test headline",
        "summary": "Test summary",
        "content": None,
        "source": "Reuters",
        "url": url,
        "published_at": None,
        "sentiment_label": "neutral",
        "sentiment_score": 0.0,
        "tags": [],
    }


# ---------------------------------------------------------------------------
# ingest_articles
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIngestArticles:
    async def test_empty_list_returns_zero(self, mock_async_session_factory):
        result = await ingest_articles([])
        assert result == 0

    async def test_articles_without_url_are_skipped(self, mock_async_session_factory):
        articles = [_make_article(url="")]
        result = await ingest_articles(articles)
        assert result == 0

    async def test_valid_articles_inserted(self, mock_async_session_factory):
        # Arrange
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = [MagicMock(), MagicMock()]
        mock_async_session_factory.return_value.execute = AsyncMock(
            return_value=mock_execute_result
        )

        articles = [_make_article("https://a.com/1"), _make_article("https://a.com/2")]

        # Act
        result = await ingest_articles(articles)

        # Assert
        assert result == 2

    async def test_session_commit_called(self, mock_async_session_factory):
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = [MagicMock()]
        session = mock_async_session_factory.return_value
        session.execute = AsyncMock(return_value=mock_execute_result)
        session.commit = AsyncMock()

        await ingest_articles([_make_article()])

        session.commit.assert_called_once()


# ---------------------------------------------------------------------------
# run_ingestion
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunIngestion:
    async def test_missing_identity_never_fetches(self):
        result = await run_ingestion()
        assert result["status"] == "blocked"
        assert result["error_code"] == "NEWS_PRINCIPAL_REQUIRED"

    async def test_selected_identity_and_interval_are_preserved(self):
        expected = {"status": "complete", "fetched": 3, "inserted": 2}
        with patch("src.news.runtime.run_sources", AsyncMock(return_value=expected)) as run:
            assert await run_ingestion(days_back=7, user_id="fixture") == expected
        run.assert_awaited_once_with(user_id="fixture", days_back=7)


# ---------------------------------------------------------------------------
# get_article_count
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetArticleCount:
    async def test_returns_row_count(self, mock_async_session_factory):
        mock_async_session_factory.return_value.scalar = AsyncMock(return_value=42)

        count = await get_article_count()
        assert count == 42


@pytest.mark.unit
async def test_unavailable_sources_are_not_reported_as_successful_empty_feed():
    failed = {"status": "partial_failure", "source_failures": [{"error_code": "PUBLIC_HTTP_503"}]}
    with patch("src.news.runtime.run_sources", AsyncMock(return_value=failed)):
        result = await run_ingestion(user_id="fixture")
    assert result["status"] == "partial_failure" and result["source_failures"]
