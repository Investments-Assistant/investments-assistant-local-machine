"""Async SQLAlchemy engine, session factory, and base class."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import func, text, select
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings

engine = create_async_engine(
    settings.database_url,
    # SQL parameters can contain private news, bank records and encrypted credentials.
    echo=False,
    hide_parameters=True,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

async_session: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_all_tables() -> None:
    """Compatibility name: verify the explicit migration, without schema mutation."""
    async with engine.connect() as conn:
        revision = await conn.scalar(text("SELECT version_num FROM alembic_version"))
        if revision != "0012_broker_observations":
            raise RuntimeError("Database migration required: run alembic upgrade head explicitly")


async def _bootstrap_auth_user() -> None:
    """Create the configured env account once, then migrate legacy chat rows."""
    if not settings.auth_username or not settings.auth_password_hash:
        return

    from src.db.models import User

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.username == settings.auth_username)
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                username=settings.auth_username,
                password_hash=settings.auth_password_hash,
                display_name=settings.auth_username,
                trading_mode=settings.trading_mode,
            )
            session.add(user)
            await session.flush()
        elif user.password_hash != settings.auth_password_hash:
            # The environment account is the bootstrap credential source. If
            # its hash is rotated in .env, make the DB login follow the new
            # value while leaving additional CLI-created users untouched.
            user.password_hash = settings.auth_password_hash
        # Unknown-owner historical rows are deliberately left quarantined.
        await session.commit()


def _conversation_title(content: str | None) -> str:
    """Create a readable deterministic title for migrated/first-turn chats."""
    normalized = " ".join((content or "").split())
    if not normalized:
        return "New chat"
    return normalized[:80].rstrip() + ("…" if len(normalized) > 80 else "")


async def _backfill_conversations() -> None:
    """Create conversation metadata for legacy message-only chat history."""
    from src.db.models import ChatMessage, Conversation

    async with async_session() as session:
        grouped = await session.execute(
            select(
                ChatMessage.user_id,
                ChatMessage.session_id,
                func.min(ChatMessage.created_at),
                func.max(ChatMessage.created_at),
            )
            .where(ChatMessage.user_id.is_not(None))
            .group_by(ChatMessage.user_id, ChatMessage.session_id)
        )
        for user_id, session_id, first_at, last_at in grouped.all():
            if not user_id or not session_id:
                continue
            existing = await session.scalar(
                select(Conversation.id).where(
                    Conversation.user_id == user_id,
                    Conversation.id == session_id,
                )
            )
            if existing:
                continue
            first_user_message = await session.scalar(
                select(ChatMessage.content)
                .where(
                    ChatMessage.user_id == user_id,
                    ChatMessage.session_id == session_id,
                    ChatMessage.role == "user",
                )
                .order_by(ChatMessage.created_at.asc())
                .limit(1)
            )
            session.add(
                Conversation(
                    id=session_id,
                    user_id=user_id,
                    title=_conversation_title(first_user_message),
                    created_at=first_at,
                    updated_at=last_at,
                    last_message_at=last_at,
                )
            )
        await session.commit()
