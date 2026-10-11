"""Production cookie policy preserves session secrecy and double-submit CSRF."""

from types import SimpleNamespace
from http.cookies import SimpleCookie

import pytest
from fastapi import HTTPException

from src.web import auth, routes
from src.config import Settings


def test_csrf_cookie_is_readable_but_never_a_session_credential(monkeypatch):
    settings = Settings(
        _env_file=None,
        environment="production",
        auth_require_login=True,
        auth_cookie_secure=True,
        auth_username="fixture",
        auth_password_hash=auth.hash_password("synthetic-cookie-fixture-password"),
        auth_session_secret="synthetic-cookie-security-fixture",
    )
    monkeypatch.setattr(routes, "settings", settings)
    monkeypatch.setattr(auth.config, "settings", settings)
    user = SimpleNamespace(id="fixture-user", username="fixture", display_name="Fixture")
    response = routes._authenticated_response(user)
    cookies = SimpleCookie()
    for header in response.headers.getlist("set-cookie"):
        cookies.load(header)
    session, csrf = cookies[auth.SESSION_COOKIE], cookies[auth.CSRF_COOKIE]
    assert session["httponly"]
    assert not csrf["httponly"]  # Browser copies this value into X-CSRF-Token.
    assert session["secure"] and csrf["secure"]
    assert session["samesite"] == csrf["samesite"] == "strict"
    assert auth.verify_session(session.value).user_id == user.id
    assert auth.verify_session(csrf.value) is None
    for headers in ({}, {"X-CSRF-Token": "wrong"}):
        with pytest.raises(HTTPException) as caught:
            auth.require_csrf(SimpleNamespace(cookies={auth.CSRF_COOKIE: csrf.value}, headers=headers))
        assert caught.value.status_code == 403
    auth.require_csrf(SimpleNamespace(cookies={auth.CSRF_COOKIE: csrf.value}, headers={"X-CSRF-Token": csrf.value}))
