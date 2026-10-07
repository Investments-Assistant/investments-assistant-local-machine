"""Synthetic permission declarations, never claims about a real publisher."""

from datetime import UTC, datetime, timedelta


def news_policy_fixture(**overrides):
    now = datetime.now(UTC)
    return {
        "policy_id": "fixture-only-v1", "permission_basis": "operator_reviewed_permission",
        "terms_url": "https://fixture.invalid/terms", "reviewed_at": (now - timedelta(days=1)).isoformat(),
        "review_due_at": (now + timedelta(days=30)).isoformat(), "article_hosts": ["fixture.invalid"],
        "content_scope": "summary", "retention_days": 30, **overrides,
    }
