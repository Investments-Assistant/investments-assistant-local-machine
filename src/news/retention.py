"""Current storage-policy eligibility, independent of historical research time."""

from datetime import timedelta

from sqlalchemy import Integer, DateTime, or_, and_, case, cast, func

from src.db.models import NewsArticle


def valid_policy_time(value):
    # PostgreSQL16 soft input validation prevents malformed metadata from aborting
    # every search. Require an explicit offset instead of a session-local date.
    valid = and_(
        value.op("~")(r"(Z|[+-][0-9]{2}:[0-9]{2})$"),
        func.pg_input_is_valid(value, "timestamp with time zone"),
    )
    return case((valid, cast(value, DateTime(timezone=True))), else_=None)


def policy_deadlines():
    policy = NewsArticle.provenance["source_policy"]["policy"]
    raw_days = policy["retention_days"].as_string()
    days = case((raw_days.op("~")(r"^[0-9]{1,5}$"), cast(raw_days, Integer)), else_=None)
    reviewed = valid_policy_time(policy["reviewed_at"].as_string())
    due = valid_policy_time(policy["review_due_at"].as_string())
    return days, reviewed, due, NewsArticle.fetched_at + days * timedelta(days=1)


def policy_expired():
    """Only valid elapsed policies authorize an expired-content cleanup preview."""
    days, reviewed, due, retention_due = policy_deadlines()
    return and_(
        days >= 1, days <= 36525, due > reviewed,
        or_(due <= func.clock_timestamp(), retention_due <= func.clock_timestamp()),
    )


def policy_eligible():
    """Current eligibility; historical research cannot rewind storage constraints."""
    days, reviewed, due, retention_due = policy_deadlines()
    now = func.clock_timestamp()
    declared = NewsArticle.provenance["source_policy"]
    return and_(
        NewsArticle.provenance["retention_state"].as_string().is_distinct_from("retired"),
        or_(declared.is_(None), and_(days >= 1, days <= 36525, reviewed <= now, due > now, retention_due > now)),
    )
