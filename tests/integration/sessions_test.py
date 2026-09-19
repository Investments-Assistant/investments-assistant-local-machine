"""Real PostgreSQL authority lifetime tests with actual production Settings."""

import uuid
from typing import Annotated
from datetime import UTC, datetime, timedelta
from contextlib import asynccontextmanager
from unittest.mock import patch

import httpx
import pytest
from fastapi import Depends, FastAPI

from src.config import Settings
from src.web.auth import Principal, create_session, verify_session, require_authenticated
from src.db.models import User
from src.security.sessions import SessionInactive, revoke, revoke_all, assert_active

pytestmark = pytest.mark.integration


async def fixture_user(session):
    row = User(
        id=str(uuid.uuid4()),
        username="sessions-" + uuid.uuid4().hex,
        password_hash="non-login-fixture",
        is_active=True,
    )
    session.add(row)
    await session.flush()
    return row


def production():
    return Settings(
        _env_file=None,
        environment="production",
        auth_require_login=True,
        auth_username="fixture",
        auth_password_hash="configured",
        auth_session_secret="synthetic-session-key-at-least-32-characters",
    )


async def test_logout_revocation_survives_new_session_and_does_not_cross_users(db_session):
    owner = await fixture_user(db_session)
    other = await fixture_user(db_session)
    now = datetime.now(UTC)
    await assert_active(db_session, owner.id, token="fixture-token", issued_at=now)
    await revoke(
        db_session, user_id=owner.id, token="fixture-token", expires_at=now + timedelta(minutes=30)
    )
    await db_session.flush()
    owner_id, other_id = owner.id, other.id
    db_session.expire_all()  # force persisted reads, no in-memory revocation registry
    with pytest.raises(SessionInactive, match="SESSION_REVOKED"):
        await assert_active(db_session, owner_id, token="fixture-token", issued_at=now)
    await assert_active(db_session, other_id, token="other-token", issued_at=now)


async def test_deactivation_and_all_session_fence(db_session):
    owner = await fixture_user(db_session)
    owner.is_active = False
    await db_session.flush()
    with pytest.raises(SessionInactive, match="PRINCIPAL_INACTIVE"):
        await assert_active(db_session, owner.id)
    await revoke_all(db_session, user_id=owner.id)
    owner.is_active = True
    await db_session.flush()
    with pytest.raises(SessionInactive, match="SESSION_REVOKED"):
        await assert_active(
            db_session,
            owner.id,
            token="old-fixture-token",
            issued_at=datetime.now(UTC) - timedelta(hours=1),
        )
    await assert_active(
        db_session,
        owner.id,
        token="new-fixture-token",
        issued_at=datetime.now(UTC) + timedelta(seconds=1),
    )


async def test_http_rejects_revoked_and_inactive_account(db_session):
    owner = await fixture_user(db_session)

    @asynccontextmanager
    async def factory():
        yield db_session

    app = FastAPI()

    @app.get("/private")
    async def private(principal: Annotated[Principal, Depends(require_authenticated)]):
        return {"user_id": principal.user_id}

    with (
        patch("src.web.auth.config.settings", production()),
        patch("src.db.database.async_session", factory),
    ):
        token = create_session(owner.username, owner.id)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://fixture"
        ) as client:
            client.cookies.set("ia_session", token)
            assert (await client.get("/private")).status_code == 200
            owner.is_active = False
            await db_session.flush()
            assert (await client.get("/private")).status_code == 401
            owner.is_active = True
            await db_session.flush()
            principal = verify_session(token)
            await revoke(db_session, user_id=owner.id, token=token, expires_at=principal.expires_at)
            assert (await client.get("/private")).status_code == 401


async def test_mcp_requires_binding_and_rechecks_account_activity(db_session):
    from src.web.auth import require_mcp_or_browser

    owner = await fixture_user(db_session)

    @asynccontextmanager
    async def factory():
        yield db_session

    app = FastAPI()

    @app.get("/mcp")
    async def scoped(principal: Annotated[Principal, Depends(require_mcp_or_browser)]):
        return {"user_id": principal.user_id}

    settings = production()
    settings.mcp_enabled = True
    settings.mcp_auth_token = "synthetic-mcp-token"
    with (
        patch("src.web.auth.config.settings", settings),
        patch("src.db.database.async_session", factory),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="https://fixture",
            headers={"Authorization": "Bearer synthetic-mcp-token"},
        ) as client:
            assert (await client.get("/mcp")).status_code == 403
            settings.mcp_user_id = owner.id
            assert (await client.get("/mcp")).json() == {"user_id": owner.id}
            owner.is_active = False
            await db_session.flush()
            assert (await client.get("/mcp")).status_code == 401
