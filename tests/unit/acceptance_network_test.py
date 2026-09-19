from unittest.mock import AsyncMock, patch

import pytest
from fastapi import WebSocket

from src.config import Settings
from src.web.auth import websocket_origin_allowed


def socket(scheme, origin, *, peer="127.0.0.1", forwarded=None):
    headers = [(b"host", b"localhost:8443"), (b"origin", origin.encode())]
    if forwarded:
        headers.append((b"x-forwarded-proto", forwarded.encode()))
    return WebSocket(
        {
            "type": "websocket",
            "path": "/ws/chat/fixture",
            "scheme": scheme,
            "headers": headers,
            "query_string": b"",
            "client": (peer, 1234),
            "server": ("localhost", 8443),
        },
        receive=AsyncMock(),
        send=AsyncMock(),
    )


@pytest.mark.parametrize(
    ("scheme", "origin"),
    [
        ("ws", "http://localhost:8443"),
        ("wss", "https://localhost:8443"),
    ],
)
def test_same_origin_uses_actual_connection_scheme(scheme, origin):
    with patch(
        "src.web.auth.config.settings",
        Settings(_env_file=None, environment="production", trust_proxy_headers=False),
    ):
        assert websocket_origin_allowed(socket(scheme, origin))
        assert not websocket_origin_allowed(socket(scheme, "https://attacker.invalid"))


def test_untrusted_peer_cannot_forge_forwarded_scheme():
    settings = Settings(
        _env_file=None,
        environment="production",
        trust_proxy_headers=True,
        trusted_proxy_ips="127.0.0.1/32",
    )
    with patch("src.web.auth.config.settings", settings):
        assert not websocket_origin_allowed(
            socket("ws", "https://localhost:8443", peer="192.168.1.25", forwarded="https")
        )
        assert websocket_origin_allowed(socket("ws", "https://localhost:8443", forwarded="https"))


def test_compose_proxy_identity_preserves_https_origin_without_trusting_other_peers():
    settings = Settings(
        _env_file=None,
        environment="production",
        trust_proxy_headers=True,
        trusted_proxy_ips="172.30.80.3/32",
    )
    with patch("src.web.auth.config.settings", settings):
        assert websocket_origin_allowed(
            socket("ws", "https://localhost:8443", peer="172.30.80.3", forwarded="https")
        )
        assert not websocket_origin_allowed(
            socket("ws", "https://localhost:8443", peer="172.30.80.4", forwarded="https")
        )
        assert not websocket_origin_allowed(
            socket("ws", "https://attacker.invalid:8443", peer="172.30.80.3", forwarded="https")
        )
