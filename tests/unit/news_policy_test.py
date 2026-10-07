from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from src.config import Settings
from src.news.policy import SourcePolicy, source_policy, permitted_articles
from src.execution.policy import PolicyDenied
from tests.news_policy_fixture import news_policy_fixture


def test_permission_must_be_explicit_and_current():
    with pytest.raises(PolicyDenied, match="SOURCE_PERMISSION_REQUIRED"):
        source_policy(Settings(_env_file=None), "rss:https://fixture.invalid/feed")
    for overrides in [
        {"review_due_at": datetime.now(UTC) - timedelta(days=2)},
        {"reviewed_at": datetime.now(UTC) + timedelta(days=1)},
        {"reviewed_at": datetime(2026, 1, 1)},
    ]:
        with pytest.raises(PolicyDenied):
            SourcePolicy(**news_policy_fixture(**overrides)).validate_current()
    for overrides in [
        {"terms_url": "http://fixture.invalid/terms"}, {"article_hosts": ["*.invalid"]}, {"retention_days": 0},
    ]:
        with pytest.raises(ValidationError):
            SourcePolicy(**news_policy_fixture(**overrides))


@pytest.mark.parametrize("scope", ["headline", "summary", "full_text"])
def test_scope_projection_cannot_be_elevated_by_feed_metadata(scope):
    policy = SourcePolicy(**news_policy_fixture(content_scope=scope, maximum_content_characters=8))
    original = {
        "title": "Fixture", "source": "Fixture", "url": "https://fixture.invalid/article",
        "summary": "long summary here", "content": "long full text here",
        "source_policy": {"content_scope": "full_text", "permission_basis": "forged"},
    }
    result = permitted_articles([original], policy, identity="rss:fixture")[0]
    assert result["summary"] == ("" if scope == "headline" else "long sum")
    assert result["content"] == ("long ful" if scope == "full_text" else None)
    assert result["source_policy"]["sha256"] == policy.fingerprint
    assert result["source_policy"]["omitted"]
    assert "forged" not in str(result)
    assert original["content"] == "long full text here"


@pytest.mark.parametrize("url", ["https://other.invalid/a", "https://fixture.invalid.evil/a", "http://fixture.invalid/a",
                                 "https://user:secret@fixture.invalid/a"])
def test_source_permission_is_bound_to_exact_article_host(url):
    policy = SourcePolicy(**news_policy_fixture())
    with pytest.raises(PolicyDenied, match="SOURCE_ARTICLE_HOST_NOT_PERMITTED"):
        permitted_articles([{"url": url}], policy, identity="rss:fixture")


async def test_private_permission_cannot_be_used_for_public_ingestion():
    from src.news.ingestion import ingest_articles

    policy = SourcePolicy(**news_policy_fixture(transport="private_newsletter", article_hosts=[]))
    article = {"title": "Private fixture", "source": "Fixture", "url": "newsletter://" + "a" * 64}
    assert permitted_articles([article], policy, identity="newsletter:fixture")[0]["title"] == "Private fixture"
    with pytest.raises(PolicyDenied, match="SOURCE_POLICY_SCOPE_MISMATCH"):
        await ingest_articles([article], source_policy=policy, source_identity="newsletter:fixture")
