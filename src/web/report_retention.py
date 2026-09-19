"""Independent owner preview/confirmation; no model or scheduler retention authority."""

from typing import Literal
import asyncio
from datetime import UTC, datetime

from fastapi import Depends, Request, APIRouter, HTTPException
from pydantic import Field, BaseModel, ConfigDict
from sqlalchemy import text

from src.config import settings
from src.web.auth import require_csrf, require_authenticated
from src.db.database import async_session
from src.execution.policy import PolicyDenied
from src.operations.report_retention import (
    ReportRetentionPolicy,
    report_plan,
    finish_retention,
    prepare_retention,
)

router = APIRouter(
    prefix="/api/reports/retention", dependencies=[Depends(require_authenticated), Depends(require_csrf)]
)


class PreviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    retain_days: int = Field(ge=1, le=36525, strict=True)


class ApplyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy: ReportRetentionPolicy
    plan_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirm_report_content_removal: Literal[True]


async def owner(request):
    principal = await require_authenticated(request)
    if not principal.user_id or principal.mechanism != "cookie":
        raise HTTPException(403, "An authenticated browser account is required")
    return principal.user_id


async def limits(session):
    await session.execute(text("SET LOCAL statement_timeout = '5s'"))
    await session.execute(text("SET LOCAL lock_timeout = '2s'"))


@router.post("/preview")
async def preview(body: PreviewInput, request: Request):
    user_id = await owner(request)
    try:
        async with asyncio.timeout(10), async_session.begin() as session:
            await limits(session)
            plan, _ = await report_plan(
                session, user_id=user_id,
                policy=ReportRetentionPolicy(retain_days=body.retain_days, as_of=datetime.now(UTC)),
            )
            return plan
    except PolicyDenied as exc:
        raise HTTPException(409, detail={"reason_code": exc.code}) from None
    except Exception:
        raise HTTPException(503, detail={"reason_code": "REPORT_RETENTION_UNAVAILABLE"}) from None


@router.post("/apply")
async def apply_retention(body: ApplyInput, request: Request):
    user_id = await owner(request)
    try:
        async with asyncio.timeout(10), async_session.begin() as session:
            await limits(session)
            report_ids = await prepare_retention(
                session, user_id=user_id, policy=body.policy, expected_plan=body.plan_sha256,
            )
        # Commit tombstones before unlinking anything. Cancellation or failure
        # leaves durable pending rows, recoverable by a fresh owned preview.
        results = []
        try:
            async with asyncio.timeout(15):
                for report_id in report_ids:
                    async with async_session.begin() as session:
                        await limits(session)
                        result = await finish_retention(
                            session, user_id=user_id, report_id=report_id, root=settings.reports_dir,
                        )
                    results.append(result)
        except Exception as exc:
            results.append({
                "status": "pending",
                "reason_code": exc.code if isinstance(exc, PolicyDenied) else "PDF_CLEANUP_INTERRUPTED",
            })
        completed = sum(result["status"] == "complete" for result in results)
        return {
            "status": "complete" if completed == len(report_ids) else "partial_failure",
            "content_removed": len(report_ids), "pdf_cleanup_complete": completed,
            "pending": len(report_ids) - completed,
            "reason_codes": sorted({r["reason_code"] for r in results if "reason_code" in r}),
            "retained": "ID, owner, dates and digest tombstones; source ledgers and existing chat copies",
        }
    except PolicyDenied as exc:
        raise HTTPException(409, detail={"reason_code": exc.code}) from None
    except Exception:
        raise HTTPException(503, detail={"reason_code": "REPORT_RETENTION_UNAVAILABLE"}) from None
