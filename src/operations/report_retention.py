"""Owner-confirmed report erasure with durable tombstones and retryable PDF removal."""

import os
import stat
from pathlib import Path
from datetime import UTC, datetime, timedelta

from pydantic import Field, BaseModel, ConfigDict
from sqlalchemy import Text, cast, func, select, update

from src.db.models import User, Report
from src.execution.policy import PolicyDenied, digest
from src.operations.workloads import WorkPool
from src.operations.report_cleanup import report_directory_lock

BATCH_SIZE = 20
retention_work = WorkPool(1, "REPORT_RETENTION")


class ReportRetentionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    retain_days: int = Field(ge=1, le=36525, strict=True)
    as_of: datetime

    def cutoff(self, now):
        if self.as_of.tzinfo is None or not now - timedelta(minutes=10) <= self.as_of <= now:
            raise PolicyDenied("RETENTION_PREVIEW_EXPIRED")
        return self.as_of - timedelta(days=self.retain_days)


async def active_owner(session, user_id):
    if not user_id or not await session.scalar(
        select(User.id).where(User.id == user_id, User.is_active.is_(True)).with_for_update(read=True)
    ):
        raise PolicyDenied("PRINCIPAL_INACTIVE")


async def report_plan(session, *, user_id, policy, now=None, lock=False):
    cutoff = policy.cutoff(now or datetime.now(UTC))
    await active_owner(session, user_id)
    content = func.jsonb_build_array(
        Report.title, Report.html_content, Report.pdf_path, Report.generation_status,
        Report.generation_errors, Report.total_pnl_usd, Report.period_start, Report.period_end,
    )
    query = select(
        Report.id,
        Report.generation_status,
        func.encode(func.sha256(func.convert_to(cast(content, Text), "UTF8")), "hex").label("content_sha256"),
    ).where(
        Report.user_id == user_id, Report.created_at < cutoff, Report.generation_status != "retired"
    ).order_by(Report.created_at, Report.id).limit(BATCH_SIZE)
    if lock:
        query = query.with_for_update()
    rows = (await session.execute(query)).all()
    identity = {
        "owner": user_id, "policy": policy.model_dump(mode="json"), "scope": "report_content_and_pdf",
        "rows": [{"id": row.id, "sha256": row.content_sha256} for row in rows],
    }
    return {
        "policy": identity["policy"], "scope": identity["scope"], "count": len(rows),
        "batch_limit": BATCH_SIZE, "may_have_more": len(rows) == BATCH_SIZE, "plan_sha256": digest(identity),
        "retained": "Report ID, owner, dates and content digest tombstone; source ledgers and chat copies remain",
    }, rows


async def prepare_retention(session, *, user_id, policy, expected_plan, now=None):
    """Commit this phase before file work; an interrupted request remains retryable."""
    now = now or datetime.now(UTC)
    plan, rows = await report_plan(session, user_id=user_id, policy=policy, lock=True, now=now)
    if plan["plan_sha256"] != expected_plan:
        raise PolicyDenied("RETENTION_PLAN_CHANGED")
    for row in rows:
        if row.generation_status == "retention_pending":
            continue
        await session.execute(update(Report).where(Report.id == row.id, Report.user_id == user_id).values(
            title="Removed report", html_content="<p>Report content removed by its owner.</p>",
            total_pnl_usd=None, generation_status="retention_pending",
            generation_errors=[{
                "stage": "retention", "code": "PDF_REMOVAL_PENDING", "content_sha256": row.content_sha256,
                "plan_sha256": expected_plan, "requested_at": now.isoformat(),
            }],
        ))
    await session.flush()
    return [row.id for row in rows]


def remove_pdf(root, source, references):
    """Only a directly contained regular report PDF; no recursive or symlink deletion."""
    root = Path(os.path.abspath(root))
    path = Path(os.path.abspath(source))
    if path.parent != root or not path.name.startswith("report_") or path.suffix != ".pdf":
        raise PolicyDenied("REPORT_PATH_UNSAFE")
    with report_directory_lock(root, exclusive=True) as descriptor:
        for reference in references:
            if Path(reference).resolve() == path:
                raise PolicyDenied("REPORT_PDF_SHARED")
        try:
            info = os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
        except FileNotFoundError:
            os.fsync(descriptor)
            return "already_absent"
        if not stat.S_ISREG(info.st_mode):
            raise PolicyDenied("REPORT_PATH_UNSAFE")
        os.unlink(path.name, dir_fd=descriptor)
        os.fsync(descriptor)
        return "removed"


async def finish_retention(session, *, user_id, report_id, root):
    """A committed tombstone authorizes this file attempt, even across request interruption.

    File unlink and DB commit are not atomic. A crash after unlink leaves a
    pending tombstone; retry accepts absence and completes the retained record.
    """
    await active_owner(session, user_id)
    row = await session.scalar(select(Report).where(
        Report.id == report_id, Report.user_id == user_id,
    ).with_for_update())
    if row is None or row.generation_status not in {"retention_pending", "retired"}:
        raise PolicyDenied("REPORT_RETENTION_NOT_AUTHORIZED")
    if row.generation_status == "retired":
        return {"status": "complete", "pdf": "already_retired"}
    if row.pdf_path:
        references = list(await session.scalars(select(Report.pdf_path).where(
            Report.pdf_path.is_not(None), Report.id != row.id,
        ).limit(10001)))
        if len(references) > 10000:
            return {"status": "pending", "reason_code": "REPORT_REFERENCE_LIMIT"}
        try:
            outcome = await retention_work.arun(remove_pdf, root, row.pdf_path, references, timeout=5)
        except Exception as exc:
            return {
                "status": "pending",
                "reason_code": exc.code if isinstance(exc, PolicyDenied) else "PDF_REMOVAL_FAILED",
            }
    else:
        outcome = "not_present"
    row.pdf_path = None
    row.generation_status = "retired"
    row.generation_errors = [dict(item, code="CONTENT_REMOVED") for item in row.generation_errors]
    await session.flush()
    return {"status": "complete", "pdf": outcome}
