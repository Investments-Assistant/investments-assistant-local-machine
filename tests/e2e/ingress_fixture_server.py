"""Actual browser fixture routes behind an isolated loopback Nginx peer."""

from fastapi import Request

from tests.e2e.fixture_server import app, config

config.settings.trust_proxy_headers = True
config.settings.trusted_proxy_ips = "127.0.0.1/32"


@app.get("/fixture/headers")
async def headers(request: Request):
    return {name: request.headers.get(name) for name in (
        "host", "x-forwarded-proto", "x-real-ip", "x-forwarded-for")}
