"""Durable revocation. Cookie signatures alone never prove current authority."""

import hashlib
from datetime import UTC, datetime
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import String, DateTime, or_, func, select
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import insert

from src.db.database import Base


class SessionRevocation(Base):
    __tablename__ = "session_revocations"
    # A hash only; never persist reusable browser cookies.
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SessionInactive(Exception):
    pass


_cookie_context: ContextVar[str | None] = ContextVar("authority_cookie", default=None)


@contextmanager
def cookie_authority(token):
    context = _cookie_context.set(token)
    try:
        yield
    finally:
        _cookie_context.reset(context)


def fingerprint(token):
    return hashlib.sha256(token.encode()).hexdigest()


async def assert_active(session, user_id, *, token=None, issued_at=None):
    from src.db.models import User

    if not user_id or not await session.scalar(
        select(User.id).where(User.id == user_id, User.is_active.is_(True))
    ):
        raise SessionInactive("PRINCIPAL_INACTIVE")
    if token:
        rows = (
            (
                await session.execute(
                    select(SessionRevocation).where(
                        SessionRevocation.user_id == user_id,
                        or_(
                            SessionRevocation.token_hash == fingerprint(token),
                            SessionRevocation.token_hash == fingerprint("all:" + user_id),
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            if (
                row.token_hash == fingerprint(token)
                or issued_at is None
                or issued_at <= row.revoked_at
            ):
                raise SessionInactive("SESSION_REVOKED")


async def revoke(session, *, user_id, token, expires_at):
    await session.execute(
        insert(SessionRevocation)
        .values(
            token_hash=fingerprint(token),
            user_id=user_id,
            expires_at=expires_at,
            revoked_at=func.clock_timestamp(),
        )
        .on_conflict_do_nothing(index_elements=["token_hash"])
    )


async def revoke_all(session, *, user_id):
    # Operator-controlled timestamp fence survives restart and user reactivation.
    key = fingerprint("all:" + user_id)
    statement = (
        insert(SessionRevocation)
        .values(
            token_hash=key,
            user_id=user_id,
            expires_at=datetime(9999, 1, 1, tzinfo=UTC),
            revoked_at=func.clock_timestamp(),
        )
        .on_conflict_do_update(
            index_elements=["token_hash"], set_={"revoked_at": func.clock_timestamp()}
        )
    )
    await session.execute(statement)


async def check_tool_authority(user_id):
    from src.web.auth import verify_session
    from src.db.database import async_session

    token = _cookie_context.get()
    principal = verify_session(token) if token else None
    if token and (principal is None or principal.user_id != user_id):
        raise SessionInactive("SESSION_EXPIRED")
    async with async_session() as session:
        await assert_active(
            session, user_id, token=token, issued_at=principal.issued_at if principal else None
        )
