"""Owned local HTTP/PostgreSQL engineering soak. No broker/provider connections.

Run against a migrated, positively marked disposable database. A short run is
SMOKE_PASS, never a 24-hour pass. Restart gaps and real observation time are kept.
Optional existing-GGUF benchmarks run in a separate CPU-only process, which proves
host contention only, not production in-process model readiness.
"""

import os
import re
import sys
import json
import math
import time
import uuid
import signal
import socket
import asyncio
import hashlib
from pathlib import Path
import argparse
from datetime import UTC, datetime
from threading import Event
import subprocess

import httpx
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]
STOP = Event()


def code_fingerprint():
    digest = hashlib.sha256()
    files = list((ROOT / "src").rglob("*.py")) + list((ROOT / "src/web/static").glob("*"))
    files += [
        ROOT / "tests/e2e/fixture_server.py",
        Path(__file__),
        ROOT / "scripts/benchmark_model.py",
        ROOT / "poetry.lock",
        ROOT / "pyproject.toml",
    ]
    for path in sorted(set(files)):
        if path.is_file():
            digest.update(str(path.relative_to(ROOT)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def save(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


async def verify_database(url, marker):
    parsed = make_url(url)
    if parsed.drivername != "postgresql+asyncpg" or not re.fullmatch(
        r"test_[a-z0-9_]+", parsed.database or ""
    ):
        raise ValueError("Explicit disposable PostgreSQL database required")
    host = Path(parsed.query.get("host", "")).resolve()
    if not host.is_relative_to(ROOT / ".qa"):
        raise ValueError("Soak accepts only the isolated .qa Unix socket")
    engine = create_async_engine(
        url, poolclass=NullPool, connect_args={"timeout": 5, "command_timeout": 5}
    )
    try:
        async with engine.connect() as connection:
            assert await connection.scalar(text("SELECT current_database()")) == parsed.database
            assert await connection.scalar(text("SELECT token FROM ia_disposable_marker")) == marker
            assert (
                await connection.scalar(text("SELECT version_num FROM alembic_version"))
                == "0012_broker_observations"
            )
    finally:
        await engine.dispose()


def terminate(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def start_server(state, output, env):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    log = (output / "service.log").open("a")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "tests.e2e.fixture_server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    log.close()
    base = f"http://127.0.0.1:{port}"
    client = httpx.Client(base_url=base, timeout=5, trust_env=False)
    try:
        startup_deadline = time.monotonic() + 15
        for _ in range(100):
            if time.monotonic() >= startup_deadline:
                raise RuntimeError("FIXTURE_STARTUP_BUDGET")
            if process.poll() is not None:
                raise RuntimeError("FIXTURE_SERVICE_EXITED")
            try:
                if client.get("/api/health", timeout=1).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            if STOP.wait(0.1):
                raise RuntimeError("INTERRUPTED")
        else:
            raise RuntimeError("FIXTURE_SERVICE_START_TIMEOUT")
        response = client.post(
            "/api/auth/login",
            json={"username": state["user"], "password": "fixture-browser-password"},
        )
        response.raise_for_status()
        client.headers["X-CSRF-Token"] = client.cookies["ia_csrf"]
        return process, client, base
    except BaseException:
        client.close()
        terminate(process)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hours", type=float, default=24)
    parser.add_argument("--interval", type=float, default=30)
    parser.add_argument("--restart-every", type=float, default=900)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not 0 < args.hours <= 72 or not 1 <= args.interval <= 300 or args.restart_every < 5:
        raise SystemExit("Invalid bounded soak duration/interval/restart cadence")
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / ".qa"):
        raise SystemExit("Output must be under ignored .qa")
    url, marker = (
        os.environ.get("TEST_DATABASE_URL"),
        os.environ.get("TEST_DATABASE_DISPOSABLE_TOKEN"),
    )
    if not url or not marker:
        raise SystemExit("Explicit test database and disposable marker required")
    asyncio.run(verify_database(url, marker))
    if args.model and (not args.model.is_file() or args.model.suffix != ".gguf"):
        raise SystemExit("Only an existing local GGUF is accepted; no downloads")
    checkpoint = output / "checkpoint.json"
    fingerprint = hashlib.sha256(url.encode()).hexdigest()
    if checkpoint.exists():
        if not args.resume:
            raise SystemExit(
                "Output exists; inspect live PID and explicitly --resume only after it stopped"
            )
        state = json.loads(checkpoint.read_text())
        if state["database_fingerprint"] != fingerprint:
            raise SystemExit("Resume database mismatch")
        old_pid = state.get("runner_pid")
        if (
            old_pid
            and Path(f"/proc/{old_pid}/cmdline").exists()
            and b"soak_acceptance.py" in Path(f"/proc/{old_pid}/cmdline").read_bytes()
        ):
            raise SystemExit("Prior soak is still running; do not duplicate it")
        state.setdefault("history", []).append(
            {
                key: state.get(key)
                for key in (
                    "status",
                    "cycles",
                    "restarts",
                    "current_window_seconds",
                    "control_p95_ms",
                    "failures",
                    "code_sha256",
                )
            }
        )
        state.update(cycles=0, restarts=0, failures=[], latency_ms=[], model_runs=[])
        state["observation_windows"] += 1
        state["continuity"] = "interrupted; this run starts a new continuous observation window"
    else:
        output.mkdir(parents=True, exist_ok=False)
        state = dict(
            user="soak-" + uuid.uuid4().hex[:16],
            database_fingerprint=fingerprint,
            observation_windows=1,
            continuity="continuous",
            cycles=0,
            restarts=0,
            failures=[],
            latency_ms=[],
            model_runs=[],
            broker_connections=0,
            external_orders=0,
            tier="real HTTP/PostgreSQL; synthetic app model; optional separate CPU model",
        )
    state.update(
        code_sha256=code_fingerprint(),
        runner_pid=os.getpid(),
        status="RUNNING",
        current_window_started_at=datetime.now(UTC).isoformat(),
        target_hours=args.hours,
        control_p95_budget_ms=250,
    )
    save(checkpoint, state)
    env = dict(os.environ, BROWSER_FIXTURE_USERS=state["user"] + "," + state["user"] + "-other")
    process = client = model_process = None
    began = last_restart = time.monotonic()
    next_model = began
    model_started = None
    latencies = []
    deadline = began + args.hours * 3600
    try:
        process, client, base = start_server(state, output, env)
        if "halt_account" not in state:
            state["halt_account"] = client.post("/api/simulator/fixtures").json()["account_id"]
            stale = client.post("/api/simulator/fixtures").json()
            state["stale_account"], state["stale_instrument"] = (
                stale["account_id"],
                stale["instrument_id"],
            )
        while time.monotonic() < deadline and not STOP.is_set():
            cycle = time.monotonic()
            if code_fingerprint() != state["code_sha256"]:
                raise RuntimeError("CODE_CHANGED_OBSERVATION_INVALIDATED")
            # A slow local model process contends for CPU/RAM while deterministic controls run.
            if args.model and model_process is None and cycle >= next_model:
                model_output = (
                    output / f"model-{len(state['model_runs']):04d}-{uuid.uuid4().hex[:8]}.json"
                )
                log = (output / "model.log").open("a")
                model_process = subprocess.Popen(
                    [
                        sys.executable,
                        "scripts/benchmark_model.py",
                        "--model",
                        str(args.model.resolve()),
                        "--threads",
                        "4",
                        "--structured",
                        "--output",
                        str(model_output),
                    ],
                    cwd=ROOT,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                log.close()
                state["model_runs"].append(dict(path=model_output.name, status="RUNNING"))
                model_started = cycle
                next_model = cycle + 3600
            started = time.perf_counter()
            halted = client.post(f"/api/simulator/accounts/{state['halt_account']}/halt")
            elapsed = (time.perf_counter() - started) * 1000
            halted.raise_for_status()
            assert halted.json()["halted"] is True
            latencies.append(elapsed)
            with (output / "latency-samples.jsonl").open("a") as samples:
                samples.write(
                    json.dumps(
                        dict(
                            window=state["observation_windows"],
                            elapsed_seconds=cycle - began,
                            latency_ms=elapsed,
                            model_process_active=model_process is not None
                            and model_process.poll() is None,
                        )
                    )
                    + "\n"
                )
            snapshot = client.get(f"/api/simulator/accounts/{state['halt_account']}")
            snapshot.raise_for_status()
            assert snapshot.json()["halted"] and snapshot.json()["orders"] == []
            ready = client.get("/api/ready")
            ready_payload = ready.json().get("detail", ready.json())
            assert ready_payload["checks"]["database"] is True
            if cycle - began > 65:
                rejected = client.post(
                    f"/api/simulator/accounts/{state['stale_account']}/proposals",
                    json=dict(
                        instrument_id=state["stale_instrument"],
                        quantity="1",
                        limit_price="100",
                        idempotency_key="stale-soak-probe",
                    ),
                )
                assert (
                    rejected.status_code == 409
                    and rejected.json()["detail"]["reason_code"] == "STALE_QUOTE"
                )
            if cycle - last_restart >= args.restart_every:
                restart_started = time.monotonic()
                terminate(process)
                try:
                    client.get("/api/health")
                except httpx.TransportError:
                    state["restarts"] += 1
                else:
                    raise RuntimeError("STOPPED_SERVICE_STILL_REACHABLE")
                client.close()
                process, client, base = start_server(state, output, env)
                restart_seconds = time.monotonic() - restart_started
                state.setdefault("restart_seconds", []).append(restart_seconds)
                if restart_seconds > 15:
                    raise RuntimeError("RESTART_BUDGET_EXCEEDED")
                last_restart = time.monotonic()
            if model_process and cycle - model_started > 180:
                raise RuntimeError("LOCAL_MODEL_BENCHMARK_TIMEOUT")
            if model_process and model_process.poll() is not None:
                if model_process.returncode:
                    raise RuntimeError("LOCAL_MODEL_BENCHMARK_FAILED")
                model_data = json.loads((output / state["model_runs"][-1]["path"]).read_text())
                if (
                    model_data["sample_count"] < 3
                    or model_data["task_correct"] != model_data["sample_count"]
                ):
                    raise RuntimeError("LOCAL_MODEL_TASK_GATE_FAILED")
                state["model_runs"][-1]["status"] = "PASS"
                model_process = None
            state["cycles"] += 1
            state.update(
                current_window_seconds=time.monotonic() - began,
                last_observed_at=datetime.now(UTC).isoformat(),
                service_pid=process.pid,
                control_p95_ms=sorted(latencies)[max(0, math.ceil(0.95 * len(latencies)) - 1)],
                latency_samples=len(latencies),
                latency_ms=latencies[-1000:],
            )
            save(checkpoint, state)
            if state["cycles"] % 10 == 1:
                print(
                    json.dumps(
                        {
                            key: state[key]
                            for key in (
                                "status",
                                "cycles",
                                "current_window_seconds",
                                "control_p95_ms",
                                "restarts",
                            )
                        }
                    ),
                    flush=True,
                )
            STOP.wait(
                max(
                    0,
                    min(
                        (min(args.interval, 1) if model_process else args.interval)
                        - (time.monotonic() - cycle),
                        deadline - time.monotonic(),
                    ),
                )
            )
        if STOP.is_set():
            state["status"] = "INTERRUPTED"
        elif state["control_p95_ms"] > 250 or not state["restarts"]:
            state["status"] = "FAILED_BUDGET_OR_RESTART_GATE"
        else:
            state["status"] = "PASS_24H" if time.monotonic() - began >= 86400 else "SMOKE_PASS"
    except Exception as exc:
        state["status"] = "FAILED"
        state["failures"].append(
            dict(
                at=datetime.now(UTC).isoformat(),
                code=str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__,
            )
        )
        raise
    finally:
        if model_process and model_process.poll() is None:
            state["model_runs"][-1]["status"] = "INTERRUPTED"
            if state["status"] in {"PASS_24H", "SMOKE_PASS"}:
                state["status"] = "INCOMPLETE_MODEL_OBSERVATION"
        terminate(model_process)
        terminate(process)
        if client:
            client.close()
        state.update(
            current_window_seconds=time.monotonic() - began,
            finished_at=datetime.now(UTC).isoformat(),
            runner_pid=None,
            service_pid=None,
        )
        save(checkpoint, state)
        print(
            json.dumps(
                {
                    key: state[key]
                    for key in (
                        "status",
                        "cycles",
                        "current_window_seconds",
                        "restarts",
                        "failures",
                    )
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda *_: STOP.set())
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    main()
