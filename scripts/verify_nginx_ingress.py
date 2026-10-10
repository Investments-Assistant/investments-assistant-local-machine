"""Real loopback TLS/Nginx/WebSocket and marked PostgreSQL fixture validation."""

import os
import ssl
import sys
import json
import uuid
import socket
import asyncio
from pathlib import Path
import argparse
import subprocess

import httpx
import websockets
from websockets.exceptions import InvalidStatus

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


async def run(args):
    from scripts.soak_acceptance import terminate, verify_database

    await verify_database(os.environ["TEST_DATABASE_URL"], os.environ["TEST_DATABASE_DISPOSABLE_TOKEN"])
    if not args.nginx.is_file() or args.output.exists():
        raise ValueError("Existing nginx executable and new output path required")
    work = ROOT / ".qa" / ("nginx-ingress-" + uuid.uuid4().hex)
    work.mkdir(mode=0o700)
    http_port, tls_port, app_port = port(), port(), port()
    if len({http_port, tls_port, app_port}) != 3:
        raise RuntimeError("Fixture ports collided; no services started")
    cert, key = work / "fixture.crt", work / "fixture.key"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                    "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1",
                    "-keyout", str(key), "-out", str(cert)], check=True, capture_output=True)
    key.chmod(0o600)
    allow = work / "allow.conf"
    allow.write_text("allow 127.0.0.1;\ndeny all;\n")
    original = (ROOT / "config/nginx/local.conf").read_text()
    rendered = (original.replace("listen 80;", f"listen 127.0.0.1:{http_port};")
                .replace("listen 443 ssl;", f"listen 127.0.0.1:{tls_port} ssl;")
                .replace("$host:8443", f"$host:{tls_port}")
                .replace("/etc/nginx/includes/lan-allow.conf", str(allow))
                .replace("/etc/nginx/certs/selfsigned.crt", str(cert))
                .replace("/etc/nginx/certs/selfsigned.key", str(key))
                .replace("http://app:8000", f"http://127.0.0.1:{app_port}"))
    conf = work / "nginx.conf"
    conf.write_text(f"daemon off;\npid {work}/nginx.pid;\nerror_log {work}/nginx-error.log;\n"
                    "events { worker_connections 128; }\nhttp {\naccess_log off;\n"
                    f"client_body_temp_path {work}/body;\nproxy_temp_path {work}/proxy;\n"
                    f"fastcgi_temp_path {work}/fastcgi;\nuwsgi_temp_path {work}/uwsgi;\n"
                    f"scgi_temp_path {work}/scgi;\n"
                    + (ROOT / "config/nginx/rate-limit.conf").read_text() + rendered + "\n}\n")
    subprocess.run([str(args.nginx.resolve()), "-t", "-p", str(work), "-c", str(conf)],
                   check=True, capture_output=True)
    checks = []
    result = dict(status="RUNNING", tier="actual loopback nginx TLS and application routes/PostgreSQL",
                  fixture_directory=str(work.relative_to(ROOT)), checks=checks,
                  broker_connections=0, external_orders=0,
                  limitations=["Fixture listener ports, TLS certificate and exact proxy peer substituted.",
                               "No Docker/WSL forwarding, LAN firewall or external account proof."])
    app = proxy = None
    username = "ingress-" + uuid.uuid4().hex
    context = ssl.create_default_context(cafile=str(cert))
    try:
        with (work / "app.log").open("w") as log:
            app = subprocess.Popen([sys.executable, "-m", "uvicorn", "tests.e2e.ingress_fixture_server:app",
                                    "--host", "127.0.0.1", "--port", str(app_port),
                                    "--no-proxy-headers", "--no-access-log"], cwd=ROOT,
                                   env={**os.environ, "BROWSER_FIXTURE_USERS": username},
                                   stdout=log, stderr=subprocess.STDOUT)
        async with httpx.AsyncClient(trust_env=False, timeout=5) as probe:
            async with asyncio.timeout(15):
                while True:
                    if app.poll() is not None:
                        raise RuntimeError("Fixture application exited")
                    try:
                        if (await probe.get(f"http://127.0.0.1:{app_port}/api/health")).status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    await asyncio.sleep(.1)
        with (work / "proxy.log").open("w") as log:
            proxy = subprocess.Popen([str(args.nginx.resolve()), "-p", str(work), "-c", str(conf)],
                                     stdout=log, stderr=subprocess.STDOUT)
        base = f"https://127.0.0.1:{tls_port}"
        async with httpx.AsyncClient(verify=context, trust_env=False, timeout=5) as client:
            async with asyncio.timeout(10):
                while True:
                    if proxy.poll() is not None:
                        raise RuntimeError("Nginx fixture exited")
                    try:
                        response = await client.get(base + "/api/health")
                        if response.status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    await asyncio.sleep(.1)
            checks.append("TLS certificate verified; actual upstream health")
            if response.headers.get("x-frame-options") != "DENY" or response.headers.get(
                    "x-content-type-options") != "nosniff":
                raise RuntimeError("SECURITY_HEADERS_MISSING")
            checks.append("Security headers retained on proxied responses")
            for path, status in [("/static/style.css", 200), ("/static/missing-ingress-fixture.css", 404)]:
                static = await client.get(base + path)
                if (static.status_code != status or static.headers.get("x-frame-options") != "DENY"
                        or static.headers.get("x-content-type-options") != "nosniff"
                        or static.headers.get("referrer-policy") != "strict-origin-when-cross-origin"
                        or "default-src 'self'" not in static.headers.get("content-security-policy", "")):
                    raise RuntimeError("STATIC_SECURITY_HEADERS_MISSING")
                if status == 200 and "max-age=3600" not in static.headers.get("cache-control", ""):
                    raise RuntimeError("STATIC_CACHE_POLICY_MISSING")
            checks.append("Static success/error responses retain security headers and successful cache budget")
            response = await client.get(f"http://127.0.0.1:{http_port}/api/health?fixture=1")
            if response.status_code != 301 or response.headers["location"] != base + "/api/health?fixture=1":
                raise RuntimeError("HTTPS_REDIRECT_MISMATCH")
            checks.append("HTTP redirect preserves requested path/query and published TLS port")
            response = await client.get(base + "/fixture/headers", headers={
                "X-Forwarded-Proto": "http", "X-Real-IP": "203.0.113.7", "X-Forwarded-For": "203.0.113.7"})
            response.raise_for_status()
            headers = response.json()
            if (headers["host"] != f"127.0.0.1:{tls_port}" or headers["x-forwarded-proto"] != "https"
                    or headers["x-real-ip"] != "127.0.0.1"):
                raise RuntimeError("FORWARDED_IDENTITY_MISMATCH")
            checks.append("Host retains public port; Nginx overwrites spoofed scheme and real IP")
            login = await client.post(base + "/api/auth/login", json={
                "username": username, "password": "fixture-browser-password"})
            login.raise_for_status()
            cookie = "; ".join(f"{k}={v}" for k, v in client.cookies.items())
            target = f"wss://127.0.0.1:{tls_port}/ws/chat/" + uuid.uuid4().hex
            async with websockets.connect(target, ssl=context, origin=base, proxy=None,
                                          additional_headers={"Cookie": cookie, "X-Forwarded-Proto": "http"}):
                checks.append("Authenticated same-origin WSS accepted despite spoofed incoming scheme")
            for origin, credentials in [("https://other.invalid", cookie),
                                        (f"http://127.0.0.1:{tls_port}", cookie), (None, cookie), (base, "")]:
                try:
                    async with websockets.connect(target, ssl=context, origin=origin, proxy=None,
                                                  additional_headers={"Cookie": credentials}):
                        raise RuntimeError("UNAUTHORIZED_WEBSOCKET_ACCEPTED")
                except InvalidStatus as exc:
                    if exc.response.status_code != 403:
                        raise
            checks.append("Cross-origin, wrong-scheme, missing-origin and unauthenticated WSS rejected")
        async with httpx.AsyncClient(transport=httpx.AsyncHTTPTransport(
                local_address="127.0.0.2", verify=context), trust_env=False, timeout=5) as denied:
            if (await denied.get(base + "/api/health")).status_code != 403:
                raise RuntimeError("NGINX_SOURCE_ALLOWLIST_BYPASSED")
            checks.append("Non-allowlisted loopback source denied by Nginx HTTPS access rules")
        result["status"] = "PASS"
    finally:
        terminate(proxy)
        terminate(app)
        if result["status"] != "PASS":
            result["status"] = "FAIL"
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--nginx", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(run(parser.parse_args()))
