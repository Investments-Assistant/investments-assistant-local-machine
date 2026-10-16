"""Authentication primitives used by the private Pi UI."""

from __future__ import annotations

import hmac
import time
import base64
import hashlib
from unittest.mock import patch

import pytest

from src.web.auth import hash_password, create_session, verify_session, verify_password


@pytest.mark.unit
class TestPasswordHashing:
    def test_hash_round_trip(self):
        encoded = hash_password("a-long-and-private-password")
        assert encoded.startswith("scrypt$v1$")
        assert verify_password("a-long-and-private-password", encoded)
        assert not verify_password("wrong-password", encoded)

    def test_empty_password_rejected(self):
        with pytest.raises(ValueError):
            hash_password("")

    @pytest.mark.parametrize("password", ["a", "ç", "!", " ", " á|€ºª\\\"' ", "ç!" * 1000])
    def test_password_has_no_length_or_composition_policy(self, password):
        encoded = hash_password(password)
        assert verify_password(password, encoded)
        assert not verify_password(password + "x", encoded)

    def test_malformed_hash_rejected(self):
        assert not verify_password("password", "not-a-password-hash")


@pytest.mark.unit
class TestSignedSessions:
    def test_existing_signed_cookie_still_verifies(self):
        issued = time.time_ns() // 1000
        payload = f"legacy-user|alice|{int(time.time()) + 600}|fixture-nonce|{issued}".encode()
        def encode(value):
            return base64.urlsafe_b64encode(value).decode().rstrip("=")
        signature = hmac.new(b"test-session-secret", payload, hashlib.sha256).digest()
        token = encode(payload) + "." + encode(signature)
        with patch("src.web.auth.config.settings") as cfg:
            cfg.auth_session_secret = "test-session-secret"
            cfg.authentication_ready = True
            principal = verify_session(token)
        assert principal.user_id == "legacy-user"
        assert principal.username == "alice"
        assert int(principal.issued_at.timestamp() * 1_000_000) == issued

    def test_session_round_trip_and_tamper_detection(self):
        with patch("src.web.auth.config.settings") as cfg:
            cfg.auth_session_secret = "test-session-secret"
            cfg.auth_username = "admin"
            cfg.auth_password_hash = "configured"
            cfg.auth_session_ttl_minutes = 10
            token = create_session("admin", "user-admin")
            assert verify_session(token).user_id == "user-admin"
            assert verify_session(token + "tampered") is None
            payload, signature = token.split(".")
            for alias in (token + "=", payload + "=." + signature,
                          payload + "!." + signature, payload + "." + signature + "!"):
                assert verify_session(alias) is None

    def test_long_portuguese_username_never_expands_or_breaks_cookie(self):
        with patch("src.web.auth.config.settings") as cfg:
            cfg.auth_session_secret = "test-session-secret"
            cfg.authentication_ready = True
            cfg.auth_session_ttl_minutes = 10
            token = create_session("  João|çã€ºª!\\\"' " * 1000, "user-portuguese")
            principal = verify_session(token)
            assert len(token) < 512
            assert principal is not None
            assert principal.user_id == "user-portuguese"

    def test_unknown_user_rejected(self):
        with patch("src.web.auth.config.settings") as cfg:
            cfg.auth_session_secret = "test-session-secret"
            cfg.auth_username = "admin"
            cfg.auth_password_hash = "configured"
            cfg.auth_session_ttl_minutes = 10
            token = create_session("other", "")
            assert verify_session(token) is None
