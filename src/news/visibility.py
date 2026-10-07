"""Server-side news ownership, including deactivation and legacy quarantine."""

from sqlalchemy import or_, and_, exists, select

from src.db.models import User, NewsArticle
from src.news.retention import policy_eligible


def visible_to(user_id: str | None):
    public = and_(NewsArticle.visibility == "public", NewsArticle.user_id.is_(None))
    if not user_id:
        return and_(public, policy_eligible())
    active = exists(select(User.id).where(User.id == user_id, User.is_active.is_(True)))
    return and_(policy_eligible(), or_(
        public, and_(NewsArticle.visibility == "private", NewsArticle.user_id == user_id, active)
    ))
