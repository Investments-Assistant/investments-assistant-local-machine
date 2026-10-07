"""Explicit operator-scoped news erasure; source fetches never invoke this module."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import Text, cast, func, select, update

from src.db.models import User, NewsArticle, NewsRevision
from src.news.retention import policy_expired
from src.execution.policy import PolicyDenied, digest

ARTICLE_LIMIT = 20
REVISION_LIMIT = 1000


def hashed(value):
    return func.encode(func.sha256(func.convert_to(cast(value, Text), "UTF8")), "hex")


async def cleanup_plan(session, *, identity, owner_user_id, as_of, now=None, lock=False):
    """Caller explicitly chooses public (None) or exactly one private owner."""
    now = now or datetime.now(UTC)
    if as_of.tzinfo is None or not now - timedelta(minutes=10) <= as_of <= now:
        raise PolicyDenied("RETENTION_PREVIEW_EXPIRED")
    if not isinstance(identity, str) or not 1 <= len(identity) <= 2048:
        raise PolicyDenied("SOURCE_IDENTITY_REQUIRED")
    if owner_user_id is not None:
        principal = select(User.id).where(User.id == owner_user_id, User.is_active.is_(True))
        if lock:
            principal = principal.with_for_update(read=True)
        if not await session.scalar(principal):
            raise PolicyDenied("PRINCIPAL_INACTIVE")
    query = select(
        NewsArticle.id,
        hashed(func.jsonb_build_array(
            NewsArticle.title, NewsArticle.summary, NewsArticle.content, NewsArticle.source,
            NewsArticle.url, NewsArticle.tags, NewsArticle.provenance, NewsArticle.content_hash,
            NewsArticle.fetched_at, NewsArticle.available_at, NewsArticle.published_at,
            NewsArticle.sentiment_label, NewsArticle.sentiment_score,
        )).label("previous_sha256"),
    ).where(
        NewsArticle.user_id.is_not_distinct_from(owner_user_id),
        NewsArticle.visibility == ("private" if owner_user_id is not None else "public"),
        NewsArticle.provenance["source_policy"]["identity"].as_string() == identity,
        NewsArticle.provenance["retention_state"].as_string().is_distinct_from("retired"),
        policy_expired(),
    ).order_by(NewsArticle.fetched_at, NewsArticle.id).limit(ARTICLE_LIMIT)
    if lock:
        query = query.with_for_update()
    articles = (await session.execute(query)).all()
    revisions_query = select(
        NewsRevision.id, NewsRevision.article_id,
        hashed(func.jsonb_build_array(
            NewsRevision.evidence, NewsRevision.content_hash, NewsRevision.available_at, NewsRevision.recorded_at,
        )).label("previous_sha256"),
    ).where(NewsRevision.article_id.in_([a.id for a in articles])).order_by(NewsRevision.id).limit(REVISION_LIMIT + 1)
    if lock:
        revisions_query = revisions_query.with_for_update()
    revisions = (await session.execute(revisions_query)).all()
    if len(revisions) > REVISION_LIMIT:
        raise PolicyDenied("NEWS_RETENTION_REVISION_LIMIT")
    selected = {
        "source": identity, "owner": owner_user_id, "as_of": as_of.isoformat(),
        "articles": [{"id": a.id, "sha256": a.previous_sha256} for a in articles],
        "revisions": [{"id": r.id, "sha256": r.previous_sha256} for r in revisions],
    }
    return {
        "as_of": as_of.isoformat(), "scope": "private_source" if owner_user_id is not None else "public_source",
        "source_identity_sha256": digest(identity), "article_count": len(articles), "revision_count": len(revisions),
        "article_limit": ARTICLE_LIMIT, "revision_limit": REVISION_LIMIT,
        "may_have_more": len(articles) == ARTICLE_LIMIT, "plan_sha256": digest(selected),
        "retained": "IDs, URLs, availability clocks and digests; report/chat/export/backup copies are separate",
    }, articles, revisions


async def remove_expired_content(session, *, identity, owner_user_id, as_of, expected_plan, now=None):
    now = now or datetime.now(UTC)
    plan, articles, revisions = await cleanup_plan(
        session, identity=identity, owner_user_id=owner_user_id, as_of=as_of, now=now, lock=True,
    )
    if plan["plan_sha256"] != expected_plan:
        raise PolicyDenied("RETENTION_PLAN_CHANGED")
    for revision in revisions:
        await session.execute(update(NewsRevision).where(NewsRevision.id == revision.id).values(evidence={
            "retention_state": "retired", "previous_sha256": revision.previous_sha256,
            "plan_sha256": expected_plan, "removed_at": now.isoformat(),
        }))
    for article in articles:
        await session.execute(update(NewsArticle).where(NewsArticle.id == article.id).values(
            title="Expired news content removed", summary="", content=None, source="Retired source",
            tags=[], sentiment_label="unavailable", sentiment_score=0,
            provenance={
                "retention_state": "retired", "previous_sha256": article.previous_sha256,
                "plan_sha256": expected_plan, "removed_at": now.isoformat(),
                "source_identity_sha256": digest(identity),
            },
        ))
    await session.flush()
    return {"status": "complete", "removed_articles": len(articles), "removed_revisions": len(revisions)}
