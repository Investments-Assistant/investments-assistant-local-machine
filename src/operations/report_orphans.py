"""Explicit local operator cleanup; never registered as an application/model tool."""

import os
import stat
from pathlib import Path
from datetime import UTC, datetime, timedelta

from sqlalchemy import text, select

from src.db.models import Report
from src.execution.policy import digest
from src.operations.report_cleanup import report_directory_lock


async def cleanup_orphans(session, root, *, before, confirm_sha256=None, limit=10000, now=None):
    """Require a fresh DB transaction and matching cooperating local writers.

    Directory exclusion spans reference collection and unlink. SHARE table lock
    also fences changes from retention/legacy reference writers until commit.
    The operator CLI is intentionally separate from latency-sensitive services.
    File work is synchronous: cancellation cannot release the DB lock while a
    detached native worker is still deleting files. No names/content are emitted.
    """
    now = now or datetime.now(UTC)
    if before.tzinfo is None or now.tzinfo is None or before > now - timedelta(days=1):
        raise ValueError("Cutoff must be aware and at least 24 hours old")
    if not 1 <= limit <= 100000:
        raise ValueError("Invalid scan limit")
    root = Path(os.path.abspath(root))
    with report_directory_lock(root, exclusive=True) as descriptor:
        await session.execute(text("SET LOCAL statement_timeout = '5s'"))
        await session.execute(text("SET LOCAL lock_timeout = '2s'"))
        await session.execute(text("LOCK TABLE reports IN SHARE MODE"))
        references = list(await session.scalars(
            select(Report.pdf_path).where(Report.pdf_path.is_not(None)).limit(limit + 1)
        ))
        if len(references) > limit:
            return {"status": "refused", "reason": "REFERENCE_LIMIT", "deleted": 0}
        retained = set()
        for reference in references:
            path = Path(os.path.abspath(reference))
            # Fail closed on ambiguous storage layouts, including aliases through
            # another symlinked parent. Operators must reconcile these first.
            if path.parent != root:
                return {"status": "refused", "reason": "REFERENCE_OUTSIDE_ROOT", "deleted": 0}
            retained.add(path.name)
        candidates = []
        with os.scandir(descriptor) as entries:
            for index, entry in enumerate(entries):
                if index >= limit:
                    return {"status": "refused", "reason": "FILE_LIMIT", "deleted": 0}
                info = entry.stat(follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode):
                    return {"status": "refused", "reason": "NON_REGULAR_ENTRY", "deleted": 0}
                if info.st_mtime > now.timestamp():
                    return {"status": "refused", "reason": "FILE_CLOCK_AHEAD", "deleted": 0}
                if (entry.name.startswith("report_") and entry.name.endswith(".pdf")
                        and entry.name not in retained and info.st_mtime < before.timestamp()):
                    candidates.append((entry.name, info.st_dev, info.st_ino, info.st_size,
                                       info.st_mtime_ns, info.st_ctime_ns))
        candidates.sort()
        directory = os.fstat(descriptor)
        plan = digest({"directory": [directory.st_dev, directory.st_ino], "before": before.isoformat(),
                       "references": sorted(retained), "candidates": candidates})
        result = {"status": "preview", "scope": "unreferenced_completed_pdfs",
                  "plan_sha256": plan, "candidate_count": len(candidates),
                  "candidate_bytes": sum(item[3] for item in candidates), "deleted": 0}
        if confirm_sha256 is None:
            return result
        if confirm_sha256 != plan:
            return {**result, "status": "refused", "reason": "PLAN_CHANGED"}
        for name, *metadata in candidates:
            try:
                info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or list((info.st_dev, info.st_ino, info.st_size,
                                                         info.st_mtime_ns, info.st_ctime_ns)) != metadata:
                    return {**result, "status": "partial", "reason": "FILE_CHANGED"}
                os.unlink(name, dir_fd=descriptor)
                result["deleted"] += 1
            except OSError:
                return {**result, "status": "partial", "reason": "CLEANUP_IO_FAILED"}
        try:
            os.fsync(descriptor)
        except OSError:
            return {**result, "status": "partial", "reason": "CLEANUP_SYNC_FAILED"}
        return {**result, "status": "complete"}
