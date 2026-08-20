"""Async SQLAlchemy engine, session factory, and base class."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.is_development,
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
    """Create tables and apply small additive compatibility migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if conn.dialect.name == "postgresql":
            # SQLAlchemy create_all deliberately does not alter existing
            # tables. These columns/indexes are additive and safe for the
            # already-deployed single-user schema.
            await conn.execute(
                text(
                    "ALTER TABLE chat_messages "
                    "ADD COLUMN IF NOT EXISTS user_id VARCHAR(36)"
                )
            )
            await conn.execute(
                text("ALTER TABLE trades ADD COLUMN IF NOT EXISTS user_id VARCHAR(36)")
            )
            await conn.execute(
                text(
                    "ALTER TABLE trades ADD COLUMN IF NOT EXISTS "
                    "broker_account_id VARCHAR(36)"
                )
            )
            await conn.execute(
                text("ALTER TABLE reports ADD COLUMN IF NOT EXISTS user_id VARCHAR(36)")
            )
            await conn.execute(
                text("ALTER TABLE daily_pnl ADD COLUMN IF NOT EXISTS user_id VARCHAR(36)")
            )
            await conn.execute(
                text(
                    "ALTER TABLE simulation_results "
                    "ADD COLUMN IF NOT EXISTS user_id VARCHAR(36)"
                )
            )
            await conn.execute(
                text("ALTER TABLE daily_pnl DROP CONSTRAINT IF EXISTS daily_pnl_date_key")
            )
            await conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_daily_pnl_user_date "
                    "ON daily_pnl (user_id, date)"
                )
            )
            await conn.execute(
                text(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                    "trading_mode VARCHAR(16) NOT NULL DEFAULT 'recommend'"
                )
            )
            await conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_chat_messages_user_session_created "
                    "ON chat_messages (user_id, session_id, created_at)"
                )
            )

    await _bootstrap_auth_user()
    await _backfill_conversations()


async def _bootstrap_auth_user() -> None:
    """Create the configured env account once, then migrate legacy chat rows."""
    if not settings.auth_username or not settings.auth_password_hash:
        return

    from src.db.models import ChatMessage, DailyPnL, Report, User

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
        # Existing single-user installations have NULL user_id values. Assign
        # those legacy rows only to the bootstrap account, never to later users.
        await session.execute(
            update(ChatMessage)
            .where(ChatMessage.user_id.is_(None))
            .values(user_id=user.id)
        )
        from src.db.models import Trade

        await session.execute(
            update(Trade).where(Trade.user_id.is_(None)).values(user_id=user.id)
        )
        await session.execute(
            update(DailyPnL).where(DailyPnL.user_id.is_(None)).values(user_id=user.id)
        )
        await session.execute(
            update(Report).where(Report.user_id.is_(None)).values(user_id=user.id)
        )
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
