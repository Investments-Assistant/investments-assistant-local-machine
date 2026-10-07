import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.news import cleanup
from src.db.models import User, NewsArticle, NewsRevision
from src.news.policy import SourcePolicy
from src.news.ingestion import ingest_articles
from src.news.visibility import visible_to
from src.execution.policy import PolicyDenied
from tests.news_policy_fixture import news_policy_fixture

pytestmark = pytest.mark.integration


async def seed(session):
    owner = str(uuid.uuid4())
    session.add(User(id=owner, username=uuid.uuid4().hex, password_hash="fixture"))
    await session.flush()
    policy = SourcePolicy(**news_policy_fixture())
    source = "rss:fixture-" + uuid.uuid4().hex
    articles = []
    for suffix, days, identity in [("expired", 31, source), ("recent", 1, source), ("other", 31, source + "-other")]:
        url = "https://fixture.invalid/" + uuid.uuid4().hex
        data = {"title": "Private fixture text " + suffix, "source": "Fixture", "url": url, "summary": "first version"}
        await ingest_articles([data], db_session=session, source_policy=policy, source_identity=identity)
        await ingest_articles([dict(data, summary="second version")], db_session=session,
                              source_policy=policy, source_identity=identity)
        row = await session.scalar(select(NewsArticle).where(NewsArticle.url == url))
        row.fetched_at = datetime.now(UTC) - timedelta(days=days)
        articles.append(row)
    await session.flush()
    return owner, source, policy, articles, datetime.now(UTC)


async def test_cleanup_removes_all_revision_text_preserves_ids_and_prevents_resurrection(db_session):
    _, source, policy, articles, now = await seed(db_session)
    args = dict(identity=source, owner_user_id=None, as_of=now, now=now)
    plan, _, _ = await cleanup.cleanup_plan(db_session, **args)
    assert plan["article_count"] == 1 and plan["revision_count"] == 2
    assert "Private fixture" not in str(plan) and "https://" not in str(plan)
    row = articles[0]
    retained = row.id, row.url, row.content_hash, row.fetched_at, row.available_at
    result = await cleanup.remove_expired_content(db_session, **args, expected_plan=plan["plan_sha256"])
    assert result == {"status": "complete", "removed_articles": 1, "removed_revisions": 2}
    await db_session.refresh(row)
    assert (row.id, row.url, row.content_hash, row.fetched_at, row.available_at) == retained
    assert row.content is None and row.summary == "" and row.provenance["retention_state"] == "retired"
    revisions = list(await db_session.scalars(select(NewsRevision).where(NewsRevision.article_id == row.id)))
    assert len(revisions) == 2 and all(r.evidence["retention_state"] == "retired" for r in revisions)
    assert "version" not in json.dumps([r.evidence for r in revisions])
    assert all(r.content_hash and r.available_at for r in revisions)
    assert all(article.summary == "second version" for article in articles[1:])
    assert await db_session.scalar(select(NewsArticle.id).where(NewsArticle.id == row.id, visible_to(None))) is None
    assert await ingest_articles(
        [{"title": "Attempted resurrection", "url": row.url, "source": "Fixture", "summary": "new text"}],
        db_session=db_session, source_policy=policy, source_identity=source,
    ) == 0
    await db_session.refresh(row)
    assert row.title == "Expired news content removed"
    assert (await cleanup.cleanup_plan(db_session, **args))[0]["article_count"] == 0


@pytest.mark.parametrize("change", ["body", "revision", "owner", "expiry"])
async def test_changed_preview_refuses_cleanup(db_session, change):
    owner, source, _, articles, now = await seed(db_session)
    args = dict(identity=source, owner_user_id=None, as_of=now, now=now)
    plan, _, _ = await cleanup.cleanup_plan(db_session, **args)
    if change == "body":
        articles[0].summary = "Changed fixture"
    elif change == "revision":
        revision = await db_session.scalar(select(NewsRevision).where(NewsRevision.article_id == articles[0].id))
        revision.evidence = {"changed": True}
    elif change == "owner":
        args["owner_user_id"] = owner
    else:
        args["now"] += timedelta(minutes=11)
    await db_session.flush()
    with pytest.raises(PolicyDenied):
        await cleanup.remove_expired_content(db_session, **args, expected_plan=plan["plan_sha256"])
    assert articles[0].title.startswith("Private fixture")


async def test_revision_capacity_refuses_partial_article_erasure(db_session, monkeypatch):
    _, source, _, articles, now = await seed(db_session)
    monkeypatch.setattr(cleanup, "REVISION_LIMIT", 1)
    with pytest.raises(PolicyDenied, match="NEWS_RETENTION_REVISION_LIMIT"):
        await cleanup.cleanup_plan(db_session, identity=source, owner_user_id=None, as_of=now, now=now)
    assert articles[0].summary == "second version"


async def test_private_cleanup_is_bound_to_one_active_owner(db_session):
    owner, _, _, _, now = await seed(db_session)
    other = str(uuid.uuid4())
    db_session.add(User(id=other, username=uuid.uuid4().hex, password_hash="fixture"))
    await db_session.flush()
    policy = SourcePolicy(**news_policy_fixture(transport="private_newsletter", article_hosts=[]))
    identity = "newsletter:" + uuid.uuid4().hex
    rows = []
    for selected in [owner, other]:
        await ingest_articles(
            [{"title": "Private mailbox fixture", "source": "Fixture", "url": "newsletter://" + "a" * 64}],
            db_session=db_session, source_policy=policy, source_identity=identity, owner_user_id=selected,
        )
        row = await db_session.scalar(select(NewsArticle).where(NewsArticle.user_id == selected))
        row.fetched_at = now - timedelta(days=31)
        rows.append(row)
    await db_session.flush()
    args = dict(identity=identity, owner_user_id=owner, as_of=now, now=now)
    plan, _, _ = await cleanup.cleanup_plan(db_session, **args)
    assert plan["article_count"] == 1 and plan["scope"] == "private_source"
    await cleanup.remove_expired_content(db_session, **args, expected_plan=plan["plan_sha256"])
    await db_session.refresh(rows[0])
    await db_session.refresh(rows[1])
    assert rows[0].provenance["retention_state"] == "retired"
    assert rows[1].title == "Private mailbox fixture"
    (await db_session.get(User, other)).is_active = False
    await db_session.flush()
    with pytest.raises(PolicyDenied, match="PRINCIPAL_INACTIVE"):
        await cleanup.cleanup_plan(db_session, identity=identity, owner_user_id=other, as_of=now, now=now)


async def test_operator_command_previews_then_commits_confirmed_cleanup(integration_engine, monkeypatch, capsys):
    from scripts import cleanup_news

    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    monkeypatch.setattr(cleanup_news, "async_session", factory)
    monkeypatch.setattr(cleanup_news, "engine", integration_engine)
    async with factory.begin() as session:
        owner, source, _, articles, _ = await seed(session)
        ids = [article.id for article in articles]
    try:
        command = ["cleanup_news.py", "--public", "--source-identity", source]
        monkeypatch.setattr("sys.argv", command)
        assert await cleanup_news.main() == 0
        plan = json.loads(capsys.readouterr().out)
        assert plan["status"] == "preview" and plan["article_count"] == 1
        async with factory() as session:
            assert (await session.get(NewsArticle, ids[0])).summary == "second version"
        monkeypatch.setattr("sys.argv", command + [
            "--as-of", plan["as_of"], "--confirm-sha256", plan["plan_sha256"],
        ])
        assert await cleanup_news.main() == 0
        assert json.loads(capsys.readouterr().out)["removed_revisions"] == 2
        async with factory() as session:
            assert (await session.get(NewsArticle, ids[0])).provenance["retention_state"] == "retired"
            revisions = list(await session.scalars(select(NewsRevision).where(NewsRevision.article_id == ids[0])))
            assert all(revision.evidence["retention_state"] == "retired" for revision in revisions)
    finally:
        async with factory.begin() as session:
            await session.execute(delete(NewsRevision).where(NewsRevision.article_id.in_(ids)))
            await session.execute(delete(NewsArticle).where(NewsArticle.id.in_(ids)))
            await session.execute(delete(User).where(User.id == owner))
