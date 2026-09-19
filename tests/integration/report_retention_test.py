import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.db.models import User, Report
from src.execution.policy import PolicyDenied
from src.operations.report_retention import (
    ReportRetentionPolicy,
    report_plan,
    finish_retention,
    prepare_retention,
)

pytestmark = pytest.mark.integration


async def seed(session, root):
    now = datetime.now(UTC)
    owners = [str(uuid.uuid4()), str(uuid.uuid4())]
    session.add_all([User(id=owner, username=uuid.uuid4().hex, password_hash="fixture") for owner in owners])
    rows = []
    for owner, days in [(owners[0], 60), (owners[0], 1), (owners[1], 60)]:
        path = root / f"report_{uuid.uuid4().hex}.pdf"
        path.write_bytes(b"synthetic private report")
        row = Report(
            user_id=owner, title="Private fixture title", html_content="private fixture HTML",
            pdf_path=str(path), generation_status="complete", generation_errors=[], total_pnl_usd=10,
            period_start=now - timedelta(days=days), period_end=now - timedelta(days=days - 1),
            created_at=now - timedelta(days=days),
        )
        session.add(row)
        rows.append(row)
    await session.flush()
    return owners, rows, ReportRetentionPolicy(retain_days=30, as_of=now), now


async def test_owned_retention_keeps_tombstone_and_other_reports(db_session, tmp_path):
    owners, rows, policy, now = await seed(db_session, tmp_path)
    plan, _ = await report_plan(db_session, user_id=owners[0], policy=policy, now=now)
    assert plan["count"] == 1 and "private fixture" not in str(plan)
    ids = await prepare_retention(
        db_session, user_id=owners[0], policy=policy, expected_plan=plan["plan_sha256"], now=now,
    )
    assert ids == [rows[0].id]
    await db_session.refresh(rows[0])
    assert rows[0].generation_status == "retention_pending" and rows[0].total_pnl_usd is None
    assert "private fixture" not in rows[0].html_content
    result = await finish_retention(db_session, user_id=owners[0], report_id=rows[0].id, root=tmp_path)
    assert result == {"status": "complete", "pdf": "removed"}
    assert rows[0].generation_status == "retired" and rows[0].pdf_path is None
    assert rows[0].generation_errors[0]["content_sha256"]
    assert rows[1].html_content == rows[2].html_content == "private fixture HTML"
    plan, _ = await report_plan(db_session, user_id=owners[0], policy=policy, now=now)
    assert plan["count"] == 0


async def test_owner_hash_expiry_and_deactivation_reject_erasure(db_session, tmp_path):
    owners, rows, policy, now = await seed(db_session, tmp_path)
    plan, _ = await report_plan(db_session, user_id=owners[0], policy=policy, now=now)
    with pytest.raises(PolicyDenied, match="RETENTION_PLAN_CHANGED"):
        await prepare_retention(
            db_session, user_id=owners[1], policy=policy, expected_plan=plan["plan_sha256"], now=now,
        )
    rows[0].html_content = "changed content"
    await db_session.flush()
    with pytest.raises(PolicyDenied, match="RETENTION_PLAN_CHANGED"):
        await prepare_retention(
            db_session, user_id=owners[0], policy=policy, expected_plan=plan["plan_sha256"], now=now,
        )
    with pytest.raises(PolicyDenied, match="RETENTION_PREVIEW_EXPIRED"):
        await report_plan(db_session, user_id=owners[0], policy=policy, now=now + timedelta(minutes=11))
    principal = await db_session.get(User, owners[0])
    principal.is_active = False
    await db_session.flush()
    with pytest.raises(PolicyDenied, match="PRINCIPAL_INACTIVE"):
        await report_plan(db_session, user_id=owners[0], policy=policy, now=now)


@pytest.mark.parametrize("failure", ["unlink", "missing", "shared", "alias", "symlink"])
async def test_partial_file_cleanup_is_retryable_and_preserves_shared_files(db_session, tmp_path, failure):
    from pathlib import Path

    owners, rows, policy, now = await seed(db_session, tmp_path)
    source = Path(rows[0].pdf_path)
    if failure == "missing":
        source.unlink()
    elif failure in {"shared", "alias"}:
        rows[2].pdf_path = str(source) if failure == "shared" else str(tmp_path) + "/./" + source.name
    elif failure == "symlink":
        source.unlink()
        source.symlink_to(rows[2].pdf_path)
    await db_session.flush()
    plan, _ = await report_plan(db_session, user_id=owners[0], policy=policy, now=now)
    await prepare_retention(db_session, user_id=owners[0], policy=policy, expected_plan=plan["plan_sha256"], now=now)
    if failure == "unlink":
        with patch("src.operations.report_retention.os.unlink", side_effect=OSError("private fixture details")):
            result = await finish_retention(db_session, user_id=owners[0], report_id=rows[0].id, root=tmp_path)
        assert result == {"status": "pending", "reason_code": "PDF_REMOVAL_FAILED"}
        assert source.exists()
        result = await finish_retention(db_session, user_id=owners[0], report_id=rows[0].id, root=tmp_path)
        assert result["status"] == "complete"
    else:
        result = await finish_retention(db_session, user_id=owners[0], report_id=rows[0].id, root=tmp_path)
        assert result["status"] == ("complete" if failure == "missing" else "pending")
        if failure != "missing":
            assert source.exists()
    assert "private fixture details" not in str(result)


async def test_committed_tombstone_recovers_after_interrupted_file_completion(integration_engine, tmp_path):
    from pathlib import Path

    factory = async_sessionmaker(integration_engine, expire_on_commit=False)
    async with factory.begin() as session:
        owners, rows, policy, now = await seed(session, tmp_path)
    try:
        async with factory.begin() as session:
            plan, _ = await report_plan(session, user_id=owners[0], policy=policy, now=now)
            await prepare_retention(
                session, user_id=owners[0], policy=policy, expected_plan=plan["plan_sha256"], now=now,
            )
        # A separate process/transaction can observe only the committed tombstone.
        async with factory.begin() as session:
            pending = await session.get(Report, rows[0].id)
            assert pending.generation_status == "retention_pending"
            assert "private fixture" not in pending.html_content
            original_hash = pending.generation_errors[0]["content_sha256"]
            Path(pending.pdf_path).unlink()  # Simulated crash after unlink, before DB completion.
        async with factory.begin() as session:
            plan, _ = await report_plan(session, user_id=owners[0], policy=policy, now=now)
            await prepare_retention(
                session, user_id=owners[0], policy=policy, expected_plan=plan["plan_sha256"], now=now,
            )
        async with factory.begin() as session:
            result = await finish_retention(session, user_id=owners[0], report_id=rows[0].id, root=tmp_path)
            assert result == {"status": "complete", "pdf": "already_absent"}
        async with factory.begin() as session:
            saved = await session.get(Report, rows[0].id)
            assert saved.generation_status == "retired" and saved.pdf_path is None
            assert saved.generation_errors[0]["content_sha256"] == original_hash
    finally:
        async with factory.begin() as session:
            await session.execute(delete(Report).where(Report.user_id.in_(owners)))
            await session.execute(delete(User).where(User.id.in_(owners)))
