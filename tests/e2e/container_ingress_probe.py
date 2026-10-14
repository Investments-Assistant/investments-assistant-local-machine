"""Exercise real authentication and WebSockets through the pinned Nginx image."""

import ssl
import json
import uuid
import asyncio

import httpx
import websockets
from websockets.exceptions import InvalidStatus


async def main():
    context = ssl.create_default_context(cafile="/app/fixture.crt")
    base = "https://nginx"
    checks = []
    async with httpx.AsyncClient(verify=context, trust_env=False, timeout=10) as client:
        health = await client.get(base + "/api/health")
        health.raise_for_status()
        for path, expected in [("/api/health", 200), ("/static/style.css", 200), ("/static/missing-fixture.css", 404)]:
            response = await client.get(base + path)
            assert response.status_code == expected
            assert response.headers["x-frame-options"] == "DENY"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
            assert "default-src 'self'" in response.headers["content-security-policy"]
        checks.append("Verified TLS, real application and static success/error security headers")
        response = await client.get("http://nginx/api/health?fixture=1")
        assert response.status_code == 301
        assert response.headers["location"] == "https://nginx:8443/api/health?fixture=1"
        checks.append("HTTP redirect retains production published port, path and query")
        response = await client.get(
            base + "/fixture/headers",
            headers={"X-Forwarded-Proto": "http", "X-Real-IP": "203.0.113.7", "X-Forwarded-For": "203.0.113.7"},
        )
        response.raise_for_status()
        observed = response.json()
        assert observed["x-forwarded-proto"] == "https"
        assert observed["x-real-ip"] != "203.0.113.7"
        assert observed["effective_client_ip"] == observed["x-real-ip"]
        assert observed["host"] == "nginx"
        checks.append("Exact trusted proxy overwrites forged scheme/IP and app uses verified peer")
        response = await client.post(
            base + "/api/auth/login",
            json={"username": "container-ingress-fixture", "password": "fixture-browser-password"},
        )
        response.raise_for_status()
        cookie = "; ".join(f"{k}={v}" for k, v in client.cookies.items())
        target = base.replace("https", "wss") + "/ws/chat/" + uuid.uuid4().hex
        async with websockets.connect(
            target, ssl=context, origin=base, proxy=None, additional_headers={"Cookie": cookie}
        ):
            checks.append("Authenticated same-origin WSS accepted through container proxy")
        for origin, credentials in [
            ("https://other.invalid", cookie),
            ("http://nginx", cookie),
            (None, cookie),
            (base, ""),
        ]:
            try:
                async with websockets.connect(
                    target, ssl=context, origin=origin, proxy=None, additional_headers={"Cookie": credentials}
                ):
                    raise AssertionError("Unauthorized WebSocket accepted")
            except InvalidStatus as exc:
                assert exc.response.status_code == 403
        checks.append("Wrong/missing origin, wrong scheme and unauthenticated WSS denied")
    print(json.dumps({"checks": checks, "observed_headers": observed}))


asyncio.run(main())
