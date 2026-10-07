import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import text

from src.operations.report_cleanup import report_directory_lock
from src.operations.report_orphans import cleanup_orphans

pytestmark = pytest.mark.integration
NOW = datetime(2026, 10, 4, tzinfo=UTC)
BEFORE = NOW - timedelta(days=2)


@pytest.fixture
async def reports(db_session):
    # Real PostgreSQL reference collection, privately shadowed table: preserve
    # all existing acceptance rows and drop this temp table on outer rollback.
    await db_session.execute(text("CREATE TEMP TABLE reports (pdf_path text) ON COMMIT DROP"))
    return db_session


def pdf(root, name):
    path = root / name
    path.write_bytes(b"synthetic private PDF")
    os.utime(path, (BEFORE.timestamp() - 1, BEFORE.timestamp() - 1))
    return path


async def reference(session, path):
    await session.execute(text("INSERT INTO reports (pdf_path) VALUES (:path)"), {"path": str(path)})


async def test_exact_orphan_plan_preserves_all_referenced_recent_and_unmanaged_files(reports, tmp_path):
    orphan = pdf(tmp_path, "report_orphan.pdf")
    saved = pdf(tmp_path, "report_saved.pdf")
    temporary = pdf(tmp_path, ".report-incomplete")
    unmanaged = pdf(tmp_path, "unmanaged.pdf")
    recent = pdf(tmp_path, "report_recent.pdf")
    os.utime(recent, (NOW.timestamp(), NOW.timestamp()))
    await reference(reports, str(tmp_path) + "/./" + saved.name)
    plan = await cleanup_orphans(reports, tmp_path, before=BEFORE, now=NOW)
    assert plan["candidate_count"] == 1 and plan["deleted"] == 0
    assert "private" not in str(plan) and orphan.name not in str(plan)
    result = await cleanup_orphans(reports, tmp_path, before=BEFORE, now=NOW,
                                   confirm_sha256=plan["plan_sha256"])
    assert result["status"] == "complete" and result["deleted"] == 1
    assert not orphan.exists()
    assert all(path.exists() for path in (saved, temporary, unmanaged, recent))


@pytest.mark.parametrize("change", ["reference", "file", "symlink", "outside", "file_limit", "reference_limit"])
async def test_changed_or_ambiguous_plan_never_deletes(reports, tmp_path, change):
    orphan = pdf(tmp_path, "report_orphan.pdf")
    plan = await cleanup_orphans(reports, tmp_path, before=BEFORE, now=NOW)
    limit = 10000
    if change == "reference":
        await reference(reports, orphan)
    elif change == "file":
        orphan.write_bytes(b"changed")
        os.utime(orphan, (BEFORE.timestamp() - 1, BEFORE.timestamp() - 1))
    elif change == "symlink":
        (tmp_path / "report_alias.pdf").symlink_to(orphan)
    elif change == "outside":
        await reference(reports, tmp_path.parent / "report_external.pdf")
    elif change == "file_limit":
        pdf(tmp_path, "report_second.pdf")
        limit = 1
    else:
        await reference(reports, orphan)
        await reference(reports, orphan)
        limit = 1
    result = await cleanup_orphans(reports, tmp_path, before=BEFORE, now=NOW, limit=limit,
                                   confirm_sha256=plan["plan_sha256"])
    assert result["status"] == "refused" and result["deleted"] == 0 and orphan.exists()


async def test_active_publication_and_unsafe_clock_exclude_cleanup(reports, tmp_path):
    orphan = pdf(tmp_path, "report_orphan.pdf")
    with report_directory_lock(tmp_path), pytest.raises(BlockingIOError):
        await cleanup_orphans(reports, tmp_path, before=BEFORE, now=NOW)
    with pytest.raises(ValueError):
        await cleanup_orphans(reports, tmp_path, before=NOW, now=NOW)
    os.utime(orphan, (NOW.timestamp() + 10, NOW.timestamp() + 10))
    result = await cleanup_orphans(reports, tmp_path, before=BEFORE, now=NOW)
    assert result["reason"] == "FILE_CLOCK_AHEAD" and orphan.exists()


@pytest.mark.parametrize("failure", ["unlink", "fsync"])
async def test_partial_removal_is_truthful_and_retryable(reports, tmp_path, failure):
    first = pdf(tmp_path, "report_a.pdf")
    second = pdf(tmp_path, "report_b.pdf")
    plan = await cleanup_orphans(reports, tmp_path, before=BEFORE, now=NOW)
    original = os.unlink

    def unlink(name, **kwargs):
        if name == second.name:
            raise OSError("private fixture")
        original(name, **kwargs)

    replacement = {"side_effect": unlink if failure == "unlink" else OSError("private fixture")}
    with patch(f"src.operations.report_orphans.os.{failure}", **replacement):
        result = await cleanup_orphans(reports, tmp_path, before=BEFORE, now=NOW,
                                       confirm_sha256=plan["plan_sha256"])
    assert result["status"] == "partial" and not first.exists()
    assert result["deleted"] == (1 if failure == "unlink" else 2)
    assert "private" not in str(result)
    retry = await cleanup_orphans(reports, tmp_path, before=BEFORE, now=NOW)
    done = await cleanup_orphans(reports, tmp_path, before=BEFORE, now=NOW,
                                 confirm_sha256=retry["plan_sha256"])
    assert done["status"] == "complete" and not second.exists()


async def test_committed_operator_cli_and_reference_write_fence(integration_engine, tmp_path):
    """Exercise the real process against a newly named, marked disposable DB only."""
    import sys
    import json
    import uuid
    import asyncio
    from pathlib import Path

    from sqlalchemy.exc import DBAPIError
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    name = "test_reportorphans_" + uuid.uuid4().hex
    url = integration_engine.url.set(database=name)
    fixture = create_async_engine(url)
    factory = async_sessionmaker(fixture)
    created = False
    try:
        async with integration_engine.connect() as admin:
            await admin.execution_options(isolation_level="AUTOCOMMIT")
            await admin.execute(text(f'CREATE DATABASE "{name}"'))
            created = True
        async with fixture.begin() as connection:
            await connection.execute(text("CREATE TABLE reports (pdf_path text)"))
            await connection.execute(text("CREATE TABLE acceptance_fixture (token text)"))
            await connection.execute(text("INSERT INTO acceptance_fixture VALUES ('orphan-cli-synthetic-only')"))
        orphan = pdf(tmp_path, "report_orphan.pdf")
        saved = pdf(tmp_path, "report_saved.pdf")
        async with factory.begin() as session:
            await reference(session, saved)
        async with factory.begin() as session:
            preview = await cleanup_orphans(session, tmp_path, before=BEFORE, now=NOW)
            assert preview["candidate_count"] == 1
            async with fixture.connect() as competing:
                await competing.execute(text("SET LOCAL lock_timeout = '100ms'"))
                with pytest.raises(DBAPIError):
                    await competing.execute(text("INSERT INTO reports VALUES (:path)"), {"path": str(orphan)})
                await competing.rollback()

        async def command(*args):
            process = await asyncio.create_subprocess_exec(
                sys.executable, "scripts/cleanup_report_orphans.py", "--before", BEFORE.isoformat(), *args,
                cwd=Path(__file__).resolve().parents[2],
                env={**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False),
                     "REPORTS_DIR": str(tmp_path), "ENVIRONMENT": "production"},
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, _ = await asyncio.wait_for(process.communicate(), 20)
            except BaseException:
                process.kill()
                await process.wait()
                raise
            assert process.returncode == 0
            return json.loads(stdout)

        plan = await command()
        assert plan["status"] == "preview" and orphan.exists()
        done = await command("--confirm-sha256", plan["plan_sha256"])
        assert done["status"] == "complete" and done["deleted"] == 1
        assert not orphan.exists() and saved.exists()
    finally:
        await fixture.dispose()
        if created:
            async with integration_engine.connect() as admin:
                await admin.execution_options(isolation_level="AUTOCOMMIT")
                await admin.execute(text(f'DROP DATABASE "{name}"'))
