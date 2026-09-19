"""Real database visibility, deduplication and deactivation regressions."""

import uuid
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import select

from src.db.models import User, NewsArticle
from src.news.search import search_news, get_recent_headlines, get_news_evidence_as_of
from src.news.ingestion import ingest_articles, get_article_count
from src.security.sessions import SessionInactive

pytestmark = pytest.mark.integration


async def test_private_news_cannot_cross_users_or_become_public(db_session):
    users = [
        User(
            id=str(uuid.uuid4()), username=uuid.uuid4().hex, password_hash="fixture", is_active=True
        )
        for _ in range(2)
    ]
    db_session.add_all(users)
    await db_session.flush()

    @asynccontextmanager
    async def session_factory():
        yield db_session

    with (
        patch("src.news.ingestion.async_session", session_factory),
        patch("src.news.search.async_session", session_factory),
    ):
        public = dict(title="Inflation public", source="Fixture", url="https://example.org/public")
        private = dict(
            title="Inflation private", source="Newsletter", url="email://synthetic-mailbox/message"
        )
        assert await ingest_articles([private]) == 0
        assert await ingest_articles([public]) == 1
        for user in users:
            assert await ingest_articles([private], owner_user_id=user.id) == 1
            assert await ingest_articles([private], owner_user_id=user.id) == 0
        db_session.add(
            NewsArticle(
                title="Inflation quarantined",
                source="Newsletter",
                url="email://legacy-fixture",
                visibility="quarantined",
            )
        )
        await db_session.flush()
        for user_id in [None, users[0].id, users[1].id]:
            expected = 1 if user_id is None else 2
            assert len(await search_news("Inflation", days_back=0, user_id=user_id)) == expected
            assert len(await get_recent_headlines(user_id=user_id)) == expected
            assert await get_article_count(user_id=user_id) == expected
        rows = (
            (
                await db_session.execute(
                    select(NewsArticle).where(NewsArticle.visibility == "private")
                )
            )
            .scalars()
            .all()
        )
        assert len({row.url for row in rows}) == 2
        assert all("mailbox" not in row.url and row.url.startswith("newsletter://") for row in rows)
        users[0].is_active = False
        await db_session.flush()
        assert await get_article_count(user_id=users[0].id) == 1
        with pytest.raises(SessionInactive):
            await ingest_articles([private], owner_user_id=users[0].id)


async def test_corrections_preserve_original_evidence_and_never_backdate_availability(db_session):
    from datetime import UTC, datetime

    from src.db.models import NewsRevision

    @asynccontextmanager
    async def session_factory():
        yield db_session

    article = dict(
        title="Inflation initial",
        summary="Initially reported 2 percent",
        source="Fixture",
        url="https://example.org/correction",
        published_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    with patch("src.news.ingestion.async_session", session_factory):
        assert await ingest_articles([article]) == 1
        first = (await db_session.execute(select(NewsArticle))).scalar_one()
        first_seen = first.fetched_at
        initial_hash = first.content_hash
        assert first.available_at.year >= 2026
        assert await ingest_articles([article]) == 0
        corrected = dict(article, summary="Corrected to 3 percent")
        assert await ingest_articles([corrected]) == 1
        await db_session.refresh(first)
        assert first.fetched_at == first_seen
        assert first.content_hash != initial_hash
        revisions = (
            (await db_session.execute(select(NewsRevision).order_by(NewsRevision.recorded_at)))
            .scalars()
            .all()
        )
        assert len(revisions) == 2
        assert revisions[0].evidence["summary"] == article["summary"]
        assert revisions[1].evidence["summary"] == corrected["summary"]
        assert revisions[0].available_at <= revisions[1].available_at

        with patch("src.news.search.async_session", session_factory):
            historical = await get_news_evidence_as_of(revisions[0].available_at)
            assert historical[0]["summary"] == article["summary"]
            current = await get_news_evidence_as_of(revisions[1].available_at)
            assert current[0]["summary"] == corrected["summary"]
            assert await get_news_evidence_as_of(datetime(2020, 1, 1, tzinfo=UTC)) == []
