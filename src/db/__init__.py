"""Database exports; defer model loading to avoid execution/model import cycles."""

from src.db.database import Base, engine, get_db, async_session

__all__ = [
    "Base",
    "async_session",
    "engine",
    "get_db",
    "ChatMessage",
    "Conversation",
    "Trade",
    "Analysis",
    "Report",
    "DailyPnL",
    "Project",
]


def __getattr__(name):
    if name in __all__:
        from src.db import models

        return getattr(models, name)
    raise AttributeError(name)
