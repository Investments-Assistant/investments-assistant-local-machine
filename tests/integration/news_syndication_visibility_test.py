"""Real PostgreSQL copy grouping respects ownership and historical revisions."""

import uuid
from datetime import UTC, datetime
from contextlib import asynccontextmanager
from unittest.mock import patch

from sqlalchemy import select

from src.db.models import User, NewsRevision
from src.news.search import search_news, get_recent_headlines, get_news_evidence_as_of
from src.news.ingestion import ingest_articles, get_article_count

BODY = (
    "The synthetic central bank published its reviewed statement today and reported "
    "that inflation reached 2 percent during the previous reporting period."
)


async def test_syndicated_copies_are_one_evidence_group_without_losing_records(db_session):
    @asynccontextmanager
    async def session_factory():
        yield db_session

    articles = [dict(title="Inflation bulletin " + str(i), summary=BODY,
                     source="Fixture " + str(i), url=f"https://fixture{i}.invalid/news") for i in range(2)]
    with (patch("src.news.ingestion.async_session", session_factory),
          patch("src.news.search.async_session", session_factory)):
        assert await ingest_articles(articles) == 2
        assert await get_article_count() == 2
        for results in (await search_news("inflation"), await get_recent_headlines(),
                        await get_news_evidence_as_of(datetime.now(UTC))):
            assert len(results) == 1
            copies = results[0]["syndication"]["copies"]
            assert {copy["url"] for copy in copies} == {a["url"] for a in articles}
            assert all(copy["available_at"] and copy["content_hash"] for copy in copies)
        assert await ingest_articles(articles) == 0
        assert len(await get_recent_headlines(limit=1)) == 1
        assert len((await get_recent_headlines(limit=1))[0]["syndication"]["copies"]) == 1
        await ingest_articles([dict(title="Brief", source="Fixture", url="https://brief.invalid/news")])
        brief = (await search_news("Brief"))[0]
        assert brief["provenance"]["syndication"]["group_id"] == brief["syndication"]["group_id"]


async def test_copy_groups_never_reveal_private_or_future_copies(db_session):
    @asynccontextmanager
    async def session_factory():
        yield db_session

    users = [User(id=str(uuid.uuid4()), username=uuid.uuid4().hex,
                  password_hash="fixture", is_active=True) for _ in range(2)]
    db_session.add_all(users)
    await db_session.flush()
    public = dict(title="Inflation public", summary=BODY, source="Public", url="https://fixture.invalid/news")
    private = dict(title="Inflation private", summary=BODY, source="Private", url="email://fixture")
    with (patch("src.news.ingestion.async_session", session_factory),
          patch("src.news.search.async_session", session_factory)):
        await ingest_articles([public])
        first = (await db_session.execute(select(NewsRevision))).scalar_one().available_at
        await ingest_articles([private], owner_user_id=users[0].id)
        assert len((await get_recent_headlines())[0]["syndication"]["copies"]) == 1
        assert len((await get_recent_headlines(user_id=users[1].id))[0]["syndication"]["copies"]) == 1
        assert len((await get_recent_headlines(user_id=users[0].id))[0]["syndication"]["copies"]) == 2
        historic = await get_news_evidence_as_of(first, user_id=users[0].id)
        assert len(historic[0]["syndication"]["copies"]) == 1
        await ingest_articles([dict(public, summary=BODY.replace("2 percent", "3 percent"))])
        current = await get_news_evidence_as_of(datetime.now(UTC), user_id=users[0].id)
        assert len(current) == 2
        assert (await get_news_evidence_as_of(first))[0]["summary"] == BODY
        users[0].is_active = False
        await db_session.flush()
        assert len((await get_recent_headlines(user_id=users[0].id))[0]["syndication"]["copies"]) == 1
