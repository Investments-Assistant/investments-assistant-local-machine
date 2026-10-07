import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from src.db.models import NewsArticle
from src.news.policy import SourcePolicy
from src.news.ingestion import ingest_articles
from src.news.visibility import visible_to
from tests.news_policy_fixture import news_policy_fixture

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("state", ["current", "expired", "review_due", "malformed_days", "malformed_time", "no_offset"])
async def test_declared_policy_expiration_is_current_and_invalid_metadata_fails_closed(db_session, state):
    url = "https://fixture.invalid/" + uuid.uuid4().hex
    policy = SourcePolicy(**news_policy_fixture())
    await ingest_articles(
        [{"title": "Fixture evidence", "source": "Fixture", "url": url}], db_session=db_session,
        source_policy=policy, source_identity="rss:fixture",
    )
    row = await db_session.scalar(select(NewsArticle).where(NewsArticle.url == url))
    data = dict(row.provenance["source_policy"]["policy"])
    if state == "expired":
        row.fetched_at = datetime.now(UTC) - timedelta(days=31)
        row.available_at = datetime.now(UTC)  # Corrections cannot renew expired storage.
    elif state == "review_due":
        data["review_due_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    elif state == "malformed_days":
        data["retention_days"] = "not a number"
    elif state == "malformed_time":
        data["review_due_at"] = "not a timestampZ"
    elif state == "no_offset":
        data["review_due_at"] = "2099-01-01T00:00:00"
    row.provenance = {**row.provenance, "source_policy": {**row.provenance["source_policy"], "policy": data}}
    await db_session.flush()
    visible = await db_session.scalar(select(NewsArticle.id).where(NewsArticle.id == row.id, visible_to(None)))
    assert bool(visible) is (state == "current")
