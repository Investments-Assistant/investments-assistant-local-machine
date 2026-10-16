"""Actual PostgreSQL registration/login with unrestricted nonempty credentials."""

import uuid
import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db import database
from src.web import auth, routes
from src.config import Settings
from src.db.models import User

pytestmark = pytest.mark.integration


def application(monkeypatch, factory):
    settings = Settings(
        _env_file=None, environment="production", auth_require_login=True,
        auth_cookie_secure=True, auth_allow_signup=True, auth_username="fixture",
        auth_password_hash="configured-non-login-fixture",
        auth_session_secret="synthetic-credential-session-key-at-least-32-characters",
        allowed_ips="127.0.0.1/32", trust_proxy_headers=False,
    )
    monkeypatch.setattr(routes, "settings", settings)
    monkeypatch.setattr(auth.config, "settings", settings)
    monkeypatch.setattr(routes, "async_session", factory)
    monkeypatch.setattr(database, "async_session", factory)
    auth._failed_logins.clear()
    auth._registration_attempts.clear()
    app = FastAPI()
    app.include_router(routes.router)
    return app


@pytest.mark.parametrize("username,password", [
    ("ç", "!"),
    (" João|áàâãçéêíóôõú€ºª!#$%&/()=?»«\\\"' ", "ç"),
    (" ", " "),
    ("  João|çã€ºª!\\\"' " * 1000, "a"),
    ("long-password", "çá| €!" * 2000),
])
async def test_registration_logout_and_login_preserve_exact_values(
    db_session, monkeypatch, username, password,
):
    @asynccontextmanager
    async def factory():
        yield db_session

    factory.begin = factory
    app = application(monkeypatch, factory)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://127.0.0.1",
    ) as client:
        registered = await client.post("/api/auth/register", json={
            "username": username, "password": password, "password_confirmation": password,
        })
        assert registered.status_code == 201, registered.text
        assert registered.json()["username"] == username
        original_token = client.cookies[auth.SESSION_COOKIE]
        assert len(original_token) < 512
        assert (await client.get("/api/auth/me")).json()["username"] == username
        csrf = client.cookies[auth.CSRF_COOKIE]
        assert (await client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})).status_code == 200
        client.cookies.set(auth.SESSION_COOKIE, original_token)
        assert (await client.get("/api/auth/me")).status_code == 401
        client.cookies.set(auth.SESSION_COOKIE, original_token + "=")
        assert (await client.get("/api/auth/me")).status_code == 401
        client.cookies.clear()
        login = await client.post("/api/auth/login", json={"username": username, "password": password})
        assert login.status_code == 200
        assert (await client.get("/api/auth/me")).json()["username"] == username
        assert (await client.post("/api/auth/login", json={
            "username": username, "password": password + "x",
        })).status_code == 401
        assert (await client.post("/api/auth/login", json={
            "username": username + "x", "password": password,
        })).status_code == 401


@pytest.mark.parametrize("username,password", [("", "a"), ("a", ""), (None, "a"), (12, "a"), ("a", False)])
async def test_credentials_require_strings_and_nonempty_values(db_session, monkeypatch, username, password):
    @asynccontextmanager
    async def factory():
        yield db_session

    app = application(monkeypatch, factory)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://127.0.0.1",
    ) as client:
        payload = {"username": username, "password": password, "password_confirmation": password}
        assert (await client.post("/api/auth/register", json=payload)).status_code == 400
        assert (await client.post("/api/auth/login", json=payload)).status_code == 401


async def test_concurrent_duplicate_registration_creates_only_one_identity(integration_engine, monkeypatch):
    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    app = application(monkeypatch, factory)
    username = "  duplicate|ç€-" + uuid.uuid4().hex + " "
    payload = {"username": username, "password": "ç", "password_confirmation": "ç"}
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="https://127.0.0.1",
        ) as client:
            results = await asyncio.gather(*(
                client.post("/api/auth/register", json=payload) for _ in range(2)
            ))
            assert sorted(response.status_code for response in results) == [201, 409]
            assert (await client.post("/api/auth/login", json=payload)).status_code == 200
            assert (await client.get("/api/auth/me")).json()["username"] == username
    finally:
        async with factory.begin() as session:
            await session.execute(delete(User).where(User.username_matches(username)))


@pytest.mark.parametrize("changed_field", ["password_hash", "username", "is_active"])
async def test_login_rechecks_identity_after_password_worker(db_session, monkeypatch, changed_field):
    username = "worker-race-" + uuid.uuid4().hex
    user = User(username=username, password_hash=auth.hash_password("a"), is_active=True)
    db_session.add(user)
    await db_session.flush()

    @asynccontextmanager
    async def factory():
        yield db_session

    app = application(monkeypatch, factory)

    async def raced_verification(_function, *_args, **_kwargs):
        replacements = {"password_hash": auth.hash_password("b"),
                        "username": username + "renamed", "is_active": False}
        setattr(user, changed_field, replacements[changed_field])
        await db_session.flush()
        return True

    monkeypatch.setattr(auth.credential_work, "arun", raced_verification)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://127.0.0.1",
    ) as client:
        response = await client.post("/api/auth/login", json={"username": username, "password": "a"})
        assert response.status_code == 401
        assert auth.SESSION_COOKIE not in response.cookies
