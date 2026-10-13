"""Soak authorization checks must remain active under optimized Python."""

import os
import sys
import asyncio

import pytest
from sqlalchemy import text
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def soak_database(integration_engine, monkeypatch):
    """The real app requires migrations, not metadata-only integration tables."""
    import uuid

    name = "test_soak_cli_" + uuid.uuid4().hex
    token = "soak-cli-" + uuid.uuid4().hex
    url = integration_engine.url.set(database=name)
    rendered = url.render_as_string(hide_password=False)
    async with integration_engine.connect() as admin:
        await admin.execution_options(isolation_level="AUTOCOMMIT")
        await admin.execute(text(f'CREATE DATABASE "{name}"'))
    fixture = create_async_engine(url)
    try:
        async with fixture.begin() as conn:
            await conn.execute(text("CREATE TABLE ia_disposable_marker(token text NOT NULL)"))
            await conn.execute(text("INSERT INTO ia_disposable_marker VALUES (:token)"), {"token": token})
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "alembic", "upgrade", "head",
            env={**os.environ, "DATABASE_URL": rendered},
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), 30)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        assert process.returncode == 0, stderr.decode()
        monkeypatch.setenv("TEST_DATABASE_URL", rendered)
        monkeypatch.setenv("TEST_DATABASE_DISPOSABLE_TOKEN", token)
        yield
    finally:
        await fixture.dispose()
        async with integration_engine.connect() as admin:
            await admin.execution_options(isolation_level="AUTOCOMMIT")
            await admin.execute(text(f'DROP DATABASE "{name}"'))


@pytest.mark.parametrize("optimized", [False, True])
async def test_soak_rejects_wrong_disposable_marker_even_when_optimized(soak_database, optimized):
    code = """import asyncio, os
from scripts.soak_acceptance import verify_database
asyncio.run(verify_database(os.environ["TEST_DATABASE_URL"], "wrong-marker-fixture"))
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        *(["-O"] if optimized else []),
        "-c",
        code,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=os.environ.copy(),
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=20)
    assert process.returncode != 0, "Unverified database was accepted"
    assert b"DISPOSABLE_MARKER_MISMATCH" in stderr


async def test_optimized_soak_accepts_the_verified_disposable_database(soak_database):
    code = """import asyncio, os
from scripts.soak_acceptance import verify_database
asyncio.run(verify_database(os.environ["TEST_DATABASE_URL"], os.environ["TEST_DATABASE_DISPOSABLE_TOKEN"]))
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-O",
        "-c",
        code,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=os.environ.copy(),
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=20)
    assert process.returncode == 0, stderr.decode()


@pytest.mark.parametrize(
    "restart_seconds, expected_status, expected_exit",
    [
        (60, "FAILED_BUDGET_OR_RESTART_GATE", 1),
        (5, "SMOKE_PASS", 0),
    ],
)
async def test_soak_cli_exit_matches_observed_acceptance(
    soak_database, restart_seconds, expected_status, expected_exit
):
    import json
    import uuid
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    output = root / ".qa" / ("soak-cli-" + uuid.uuid4().hex)
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "scripts/soak_acceptance.py",
        "--hours",
        "0.003",
        "--interval",
        "1",
        "--restart-every",
        str(restart_seconds),
        "--output",
        str(output),
        cwd=root,
        env=os.environ.copy(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=40)
    finally:
        if process.returncode is None:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=20)
    assert (output / "checkpoint.json").exists(), (stdout.decode(), stderr.decode())
    state = json.loads((output / "checkpoint.json").read_text())
    assert state["status"] == expected_status, (stdout.decode(), stderr.decode())
    assert state["runner_pid"] is None
    assert state["service_pid"] is None
    assert process.returncode == expected_exit, "CLI result contradicts persisted acceptance status"


async def test_soak_cannot_count_an_unobserved_day_as_a_pass(soak_database):
    """A suspended runner can wake after its deadline without another loop body."""
    import json
    import uuid
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    output = root / ".qa" / ("soak-gap-" + uuid.uuid4().hex)
    code = r'''
import json, sys
from pathlib import Path
from scripts import soak_acceptance as soak
output = Path(sys.argv[1])
original_mono, original_wall = soak.time.monotonic, soak.time.time
original_wait = soak.STOP.wait
offset = [0.0]
soak.time.monotonic = lambda: original_mono() + offset[0]
soak.time.time = lambda: original_wall() + offset[0]
def wait(seconds):
    checkpoint = output / "checkpoint.json"
    if seconds >= 0.5 and checkpoint.exists():
        cycles = json.loads(checkpoint.read_text())["cycles"]
        # First complete an actual service restart, then miss an entire day.
        offset[0] += 10 if cycles == 1 else 86401
    return original_wait(min(seconds, 0.01))
soak.STOP.wait = wait
sys.argv = ["soak_acceptance", "--hours", "24", "--interval", "1",
            "--restart-every", "5", "--output", str(output)]
raise SystemExit(soak.main())
'''
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", code, str(output), cwd=root,
        env=os.environ.copy(), stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), 40)
    finally:
        if process.returncode is None:
            process.terminate()
            await asyncio.wait_for(process.wait(), 20)
    state = json.loads((output / "checkpoint.json").read_text())
    assert state["status"] == "FAILED", (stdout.decode(), stderr.decode(), state)
    assert state["failures"][-1]["code"] == "OBSERVATION_GAP"
    assert state["runner_pid"] is None and state["service_pid"] is None
    assert process.returncode != 0
