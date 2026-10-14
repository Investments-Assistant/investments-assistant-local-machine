"""Owned loopback Docker Desktop ingress fixture; no production mounts/providers."""

import json
import time
import uuid
from pathlib import Path
import secrets
import argparse
import ipaddress
import subprocess


def run(args):
    if args.output.exists():
        raise ValueError("Use a new evidence output")
    run_id = "ia-ingress-" + uuid.uuid4().hex[:12]
    work = Path(".qa") / run_id
    work.mkdir(mode=0o700)
    result = dict(
        status="RUNNING",
        run_id=run_id,
        checks=[],
        broker_connections=0,
        external_orders=0,
        limitations=[
            "Synthetic model/provider evidence; real auth/routes",
            "Windows loopback forwarding only, not LAN/firewall or physical client identity",
        ],
    )
    containers = []
    network = None
    args.output.write_text(json.dumps(result, indent=2) + "\n")

    def docker(*parts, check=True, timeout=120):
        completed = subprocess.run([args.docker, *parts], capture_output=True, text=True, timeout=timeout)
        if check and completed.returncode:
            raise RuntimeError(completed.stderr[-3000:])
        return completed

    def copy(source, destination):
        local = str(source.resolve())
        if args.docker.endswith(".exe"):
            local = subprocess.check_output(["wslpath", "-w", local], text=True).strip()
        docker("cp", local, destination)

    def create(*parts):
        identifier = docker("create", "--label", "ia.acceptance=" + run_id, *parts).stdout.strip()
        containers.append(identifier)
        return identifier

    def wait(probe):
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if probe().returncode == 0:
                return
            time.sleep(1)
        raise RuntimeError("Fixture readiness deadline exceeded")

    try:
        # Match Compose's bridge: Docker suppresses published ports on an
        # --internal-only network. This fixture has no provider credentials,
        # scheduler, or real inference; its broker connector explicitly denies.
        network = docker("network", "create", "--label", "ia.acceptance=" + run_id, run_id).stdout.strip()
        info = json.loads(docker("network", "inspect", network).stdout)[0]["IPAM"]["Config"][0]
        subnet = ipaddress.ip_network(info["Subnet"])
        gateway, app_ip, proxy_ip = info["Gateway"], str(subnet[2]), str(subnet[3])
        result["fixture_addresses"] = dict(gateway=gateway, app=app_ip, proxy=proxy_ip)
        password, token = secrets.token_urlsafe(24), uuid.uuid4().hex
        url = f"postgresql+asyncpg://fixture:{password}@db:5432/test_container"
        db = create(
            "--name",
            run_id + "-db",
            "--network",
            network,
            "--ip",
            str(subnet[4]),
            "--network-alias",
            "db",
            "-e",
            "POSTGRES_USER=fixture",
            "-e",
            "POSTGRES_PASSWORD=" + password,
            "-e",
            "POSTGRES_DB=test_container",
            args.postgres,
        )
        docker("start", db)
        wait(
            lambda: docker(
                "exec", db, "pg_isready", "-h", "127.0.0.1", "-U", "fixture", "-d", "test_container", check=False
            )
        )
        observed = docker(
            "exec",
            db,
            "psql",
            "-U",
            "fixture",
            "-d",
            "test_container",
            "-At",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "CREATE TABLE ia_disposable_marker(token text); "
            f"INSERT INTO ia_disposable_marker VALUES ('{token}'); "
            "SELECT current_database(),token FROM ia_disposable_marker;",
        ).stdout
        assert "test_container|" + token in observed
        docker(
            "run", "--rm", "--network", network, "-e", "DATABASE_URL=" + url, args.image, "alembic", "upgrade", "head"
        )
        package = work / "tests"
        (package / "e2e").mkdir(parents=True)
        (package / "__init__.py").touch()
        (package / "e2e/__init__.py").touch()
        (package / "e2e/fixture_server.py").write_text(Path("tests/e2e/fixture_server.py").read_text())
        wrapper = (
            "from fastapi import Request\nfrom tests.e2e.fixture_server import app, config\n"
            "from src.web.routes import _get_client_ip\n"
            "config.settings.trust_proxy_headers = True\n"
            f'config.settings.trusted_proxy_ips = "{proxy_ip}/32"\n'
            f'config.settings.allowed_ips = "{app_ip}/32,{gateway}/32"\n'
            '@app.get("/fixture/headers")\nasync def headers(request: Request):\n'
            "    return {**{k: request.headers.get(k) for k in "
            '("host", "x-real-ip", "x-forwarded-proto", "x-forwarded-for")}, '
            '"effective_client_ip": _get_client_ip(request)}\n'
        )
        (package / "e2e/container_server.py").write_text(wrapper)
        app = create(
            "--name",
            run_id + "-app",
            "--network",
            network,
            "--ip",
            app_ip,
            "--network-alias",
            "app",
            "-e",
            "DATABASE_URL=" + url,
            "-e",
            "TEST_DATABASE_URL=" + url,
            "-e",
            "TEST_DATABASE_DISPOSABLE_TOKEN=" + token,
            "-e",
            "BROWSER_FIXTURE_USERS=container-ingress-fixture",
            args.image,
            "python",
            "-m",
            "uvicorn",
            "tests.e2e.container_server:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--no-proxy-headers",
        )
        copy(package, app + ":/app/tests")
        cert, key = work / "fixture.crt", work / "fixture.key"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=nginx",
                "-addext",
                "subjectAltName=DNS:nginx,IP:127.0.0.1",
                "-keyout",
                str(key),
                "-out",
                str(cert),
            ],
            check=True,
            capture_output=True,
        )
        key.chmod(0o600)
        copy(cert, app + ":/app/fixture.crt")
        docker("start", app)
        wait(
            lambda: docker(
                "exec",
                app,
                "python",
                "-c",
                "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')",
                check=False,
            )
        )
        nginx = create(
            "--name",
            run_id + "-nginx",
            "--network",
            network,
            "--ip",
            proxy_ip,
            "--network-alias",
            "nginx",
            "-p",
            "127.0.0.1::443",
            args.nginx,
        )
        rendered = (
            Path("config/nginx/local.conf")
            .read_text()
            .replace("/etc/nginx/includes/lan-allow.conf", "/etc/nginx/fixture-allow.conf")
            .replace("/etc/nginx/certs/selfsigned.crt", "/etc/nginx/fixture.crt")
            .replace("/etc/nginx/certs/selfsigned.key", "/etc/nginx/fixture.key")
        )
        (work / "default.conf").write_text(rendered)
        (work / "allow.conf").write_text(f"allow {app_ip};\nallow {gateway};\ndeny all;\n")
        for source, target in [
            (work / "default.conf", "/etc/nginx/conf.d/default.conf"),
            (Path("config/nginx/rate-limit.conf"), "/etc/nginx/conf.d/00-rate-limit.conf"),
            (work / "allow.conf", "/etc/nginx/fixture-allow.conf"),
            (cert, "/etc/nginx/fixture.crt"),
            (key, "/etc/nginx/fixture.key"),
        ]:
            copy(source, nginx + ":" + target)
        docker("start", nginx)
        wait(lambda: docker("exec", nginx, "nginx", "-t", check=False))
        probe = docker("exec", app, "python", "-c", Path("tests/e2e/container_ingress_probe.py").read_text())
        result.update(json.loads(probe.stdout))
        # Validate actual Windows loopback publishing, including certificate verification.
        binding = json.loads(docker("inspect", nginx).stdout)[0]["NetworkSettings"]["Ports"]["443/tcp"]
        result["port_bindings"] = binding
        assert len(binding) == 1 and binding[0]["HostIp"] == "127.0.0.1"
        port = binding[0]["HostPort"]
        windows_cert = subprocess.check_output(["wslpath", "-w", str(cert.resolve())], text=True).strip()
        response = subprocess.run(
            [
                args.curl,
                "--silent",
                "--show-error",
                "--fail",
                "--noproxy",
                "*",
                "--cacert",
                windows_cert,
                "--max-time",
                "10",
                "-H",
                "X-Real-IP: 203.0.113.7",
                "-H",
                "X-Forwarded-Proto: http",
                f"https://127.0.0.1:{port}/fixture/headers",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        headers = json.loads(response.stdout)
        assert headers["effective_client_ip"] == headers["x-real-ip"] == gateway
        assert headers["host"] == f"127.0.0.1:{port}" and headers["x-forwarded-proto"] == "https"
        result["windows_forwarding"] = dict(published_address="127.0.0.1", port=port, headers=headers)
        result["checks"].append("Windows loopback TLS verified; actual Docker forwarded source observed")
        denied_code = (
            "import ssl,urllib.request,urllib.error; "
            f"ctx=ssl.create_default_context(cadata={cert.read_text()!r})\n"
            "try:\n urllib.request.urlopen('https://nginx/api/health',context=ctx,timeout=5)\n"
            "except urllib.error.HTTPError as exc:\n assert exc.code == 403\n"
            "else:\n raise AssertionError('Unlisted source accepted')\n"
        )
        denied = create("--name", run_id + "-denied", "--network", network, args.image, "python", "-c", denied_code)
        docker("start", "-a", denied)
        assert json.loads(docker("inspect", denied).stdout)[0]["State"]["ExitCode"] == 0
        result["checks"].append("Separate non-allowlisted container source rejected with HTTPS403")
        result["status"] = "PASS"
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        raise
    finally:
        cleanup = []
        for identifier in reversed(containers):
            try:
                logs = docker("logs", "--tail", "100", identifier, check=False, timeout=10)
                (work / (identifier[:12] + ".log")).write_text(logs.stdout + logs.stderr)
            except subprocess.TimeoutExpired:
                result.setdefault("log_timeouts", []).append(identifier)
            cleanup.append(docker("rm", "-fv", identifier, check=False).returncode)
        if network:
            cleanup.append(docker("network", "rm", network, check=False).returncode)
        result["cleanup_verified"] = all(value == 0 for value in cleanup)
        if result["status"] != "PASS" or not result["cleanup_verified"]:
            result["status"] = "FAIL"
        result["fixture_directory"] = str(work)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    assert result["status"] == "PASS"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker", required=True)
    parser.add_argument("--curl", default="/mnt/c/Windows/System32/curl.exe")
    parser.add_argument("--image", required=True)
    parser.add_argument("--postgres", required=True)
    parser.add_argument("--nginx", required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
