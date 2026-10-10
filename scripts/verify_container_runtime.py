"""Owned isolated Docker runtime/migration/model/restart acceptance, no providers."""

import json
import time
import uuid
import hashlib
from pathlib import Path
import secrets
import argparse
import subprocess


def run(args):
    if args.output.exists() or not args.model.is_file():
        raise ValueError("New output and existing local model required")
    run_id = "ia-runtime-" + uuid.uuid4().hex[:12]
    work = Path(".qa") / run_id
    work.mkdir(mode=0o700)
    containers = []
    network = volume = None
    result = {
        "status": "RUNNING",
        "run_id": run_id,
        "image": args.image,
        "checks": [],
        "broker_connections": 0,
        "external_orders": 0,
        "limitations": [
            "No Nginx/LAN ingress, OS sleep or 24-hour observation",
            "Readiness/model load, not a model answer-quality benchmark",
        ],
    }

    def docker(*arguments, check=True, timeout=180):
        completed = subprocess.run([args.docker, *arguments], capture_output=True, text=True, timeout=timeout)
        if check and completed.returncode:
            raise RuntimeError(completed.stderr[-4000:] or completed.stdout[-4000:])
        return completed

    def wait_for(probe, seconds=120):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            response = probe()
            if response.returncode == 0:
                return response.stdout
            time.sleep(1)
        raise RuntimeError("Owned fixture readiness deadline exceeded")

    db, app = run_id + "-db", run_id + "-app"
    password = secrets.token_urlsafe(24)
    token = uuid.uuid4().hex
    database_url = f"postgresql+asyncpg://fixture:{password}@db:5432/test_container"
    checks = result["checks"]
    result["owned_names"] = {"app": app, "database": db, "network": run_id, "volume": run_id + "-data"}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    try:
        info = json.loads(docker("image", "inspect", args.image).stdout)[0]
        if info["Architecture"] != "amd64" or info["Config"]["User"] != "appuser":
            raise RuntimeError("Unexpected validation image architecture/user")
        result["image_id"] = info["Id"]
        network = docker("network", "create", "--internal", "--label", "ia.acceptance=" + run_id, run_id).stdout.strip()
        volume = docker("volume", "create", "--label", "ia.acceptance=" + run_id, run_id + "-data").stdout.strip()
        db_id = docker(
            "create",
            "--name",
            db,
            "--network",
            network,
            "--network-alias",
            "db",
            "--label",
            "ia.acceptance=" + run_id,
            "-e",
            "POSTGRES_USER=fixture",
            "-e",
            "POSTGRES_PASSWORD=" + password,
            "-e",
            "POSTGRES_DB=test_container",
            "-v",
            volume + ":/var/lib/postgresql/data",
            args.postgres,
        ).stdout.strip()
        containers.append(db_id)
        docker("start", db)
        # The entrypoint's temporary initialization server accepts only Unix sockets.
        # Wait for its final TCP server, otherwise readiness can race its shutdown.
        wait_for(
            lambda: docker(
                "exec",
                db,
                "pg_isready",
                "-h",
                "127.0.0.1",
                "-U",
                "fixture",
                "-d",
                "test_container",
                check=False,
                timeout=10,
            )
        )
        sql = (
            "CREATE TABLE ia_disposable_marker(token text NOT NULL); "
            f"INSERT INTO ia_disposable_marker VALUES ('{token}'); "
            "SELECT current_database(),token FROM ia_disposable_marker;"
        )
        identity = docker(
            "exec", db, "psql", "-U", "fixture", "-d", "test_container", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql
        ).stdout
        if "test_container|" + token not in identity:
            raise RuntimeError("Disposable database identity mismatch")
        checks.append("New isolated database and ownership marker verified")
        migration = docker(
            "run",
            "--rm",
            "--network",
            network,
            "-e",
            "DATABASE_URL=" + database_url,
            args.image,
            "alembic",
            "upgrade",
            "head",
        )
        (work / "migration.log").write_text(migration.stdout + migration.stderr)
        checks.append("Built image explicitly upgrades empty disposable database")
        environment = {
            "DATABASE_URL": database_url,
            "ENVIRONMENT": "production",
            "AUTH_USERNAME": "fixture",
            "AUTH_PASSWORD_HASH": "fixture-unusable",
            "AUTH_SESSION_SECRET": secrets.token_urlsafe(32),
            "AUTH_ALLOW_SIGNUP": "false",
            "ALLOWED_IPS": "127.0.0.1/32",
            "TRUST_PROXY_HEADERS": "false",
            "AUTONOMOUS_SCANS_ENABLED": "false",
            "BANK_SYNC_ENABLED": "false",
            "LIVE_TRADING_ENABLED": "false",
            "LLM_N_GPU_LAYERS": "0",
            "LLM_MODEL_PATH": "/app/models/fixture.gguf",
            "LLM_N_THREADS": "4",
        }
        command = [
            "create",
            "--name",
            app,
            "--network",
            network,
            "--memory",
            "6g",
            "--cpus",
            "4",
            "--label",
            "ia.acceptance=" + run_id,
        ]
        for name, value in environment.items():
            command.extend(["-e", name + "=" + value])
        app_id = docker(*command, args.image).stdout.strip()
        containers.append(app_id)
        model_path = str(args.model.resolve())
        if args.docker.endswith(".exe"):
            model_path = subprocess.check_output(["wslpath", "-w", model_path], text=True).strip()
        docker("cp", model_path, app + ":/app/models/fixture.gguf", timeout=180)
        with args.model.open("rb") as model:
            result["model_sha256"] = hashlib.file_digest(model, "sha256").hexdigest()
        docker("start", app)
        probe_code = (
            "import json,urllib.request; "
            "r=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/ready',timeout=5)); "
            "assert r['checks']=={'database':True,'model':True}; print(json.dumps(r))"
        )

        def probe():
            return docker("exec", app, "python", "-c", probe_code, check=False, timeout=10)

        wait_for(probe)
        checks.append("Production application starts with migrated DB and actual local GGUF loaded")
        state_code = Path("tests/e2e/container_runtime_state.py").read_text()
        docker("exec", app, "python", "-c", state_code, token, "seed")
        docker("exec", app, "python", "-c", state_code, token, "verify")
        for target in (app, db):
            started = time.monotonic()
            docker("restart", "-t", "10", target)
            restarted = time.monotonic()
            wait_for(probe)
            result.setdefault("restart_seconds", {})["app" if target == app else "database"] = round(
                time.monotonic() - started, 3
            )
            result.setdefault("restart_command_seconds", {})["app" if target == app else "database"] = round(
                restarted - started, 3
            )
            docker("exec", app, "python", "-c", state_code, token, "verify")
        checks.append("Persisted operator halt denies proposals after app and database restart")
        identity = docker(
            "exec",
            db,
            "psql",
            "-U",
            "fixture",
            "-d",
            "test_container",
            "-At",
            "-c",
            "SELECT current_database(),token FROM ia_disposable_marker; SELECT version_num FROM alembic_version;",
        ).stdout
        if "test_container|" + token not in identity or "0018_job_lease_clock" not in identity:
            raise RuntimeError("Database marker/schema lost across restart")
        checks.append("Application and database restart recover readiness and preserve marker/schema")
        if max(result["restart_seconds"].values()) > 15:
            raise RuntimeError("Restart exceeds predeclared 15-second budget")
        result["status"] = "PASS"
    except Exception as exc:
        # Error messages from subprocesses may contain synthetic credentials.
        result["error_type"] = type(exc).__name__
        raise
    finally:
        for name in (app, db):
            try:
                logs = docker("logs", "--tail", "200", name, check=False, timeout=15)
                if logs.returncode == 0:
                    (work / ("app.log" if name == app else "db.log")).write_text(logs.stdout + logs.stderr)
            except subprocess.TimeoutExpired:
                result.setdefault("log_capture_timeouts", []).append(name)
        cleanup = []
        for identifier in reversed(containers):
            cleanup.append(docker("rm", "-f", identifier, check=False).returncode)
        if volume:
            cleanup.append(docker("volume", "rm", volume, check=False).returncode)
        if network:
            cleanup.append(docker("network", "rm", network, check=False).returncode)
        result["cleanup_verified"] = all(code == 0 for code in cleanup)
        if result["status"] != "PASS" or not result["cleanup_verified"]:
            result["status"] = "FAIL"
        result["fixture_logs"] = str(work)
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    if result["status"] != "PASS":
        raise RuntimeError("Runtime acceptance or owned resource cleanup failed")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--docker", default="docker")
    parser.add_argument("--image", required=True)
    parser.add_argument("--postgres", required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
