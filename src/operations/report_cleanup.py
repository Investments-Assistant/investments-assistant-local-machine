"""Explicit operator cleanup of abandoned render temporaries on the local host."""

import os
import json
import stat
import fcntl
import hashlib
from pathlib import Path
from datetime import UTC, datetime, timedelta
from contextlib import contextmanager


@contextmanager
def report_directory_lock(root: Path, *, exclusive: bool = False):
    """Cooperating renderers share a lock; cleanup refuses while any is active."""
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(descriptor, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
        yield descriptor
    finally:
        os.close(descriptor)


def cleanup_temporaries(
    root: Path,
    *,
    before: datetime,
    confirm_sha256: str | None = None,
    limit: int = 10000,
    now: datetime | None = None,
) -> dict:
    """Preview first, then confirm the exact unchanged plan. No finished PDFs.

    Requires the matching writer lock implementation and a private local reports
    directory. Never schedule automatically; the operator chooses the cutoff.
    """
    now = now or datetime.now(UTC)
    if before.tzinfo is None or now.tzinfo is None or before > now - timedelta(days=1):
        raise ValueError("Cutoff must be aware and at least 24 hours old")
    if not 1 <= limit <= 100000:
        raise ValueError("Invalid scan limit")
    with report_directory_lock(root, exclusive=True) as descriptor:
        directory = os.fstat(descriptor)
        candidates = []
        with os.scandir(descriptor) as entries:
            for index, entry in enumerate(entries):
                if index >= limit:
                    return {"status": "partial", "reason": "FILE_LIMIT", "deleted": 0}
                if not entry.name.startswith(".report-"):
                    continue
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISREG(info.st_mode) and info.st_mtime < before.timestamp():
                    candidates.append((entry.name, info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns))
        candidates.sort()
        fingerprint = hashlib.sha256(json.dumps(
            [directory.st_dev, directory.st_ino, before.isoformat(), candidates], separators=(",", ":")
        ).encode()).hexdigest()
        result = {
            "status": "preview",
            "plan_sha256": fingerprint,
            "candidate_count": len(candidates),
            "candidate_bytes": sum(item[3] for item in candidates),
            "deleted": 0,
            "scope": "abandoned_render_temporaries_only",
        }
        if confirm_sha256 is None:
            return result
        if confirm_sha256 != fingerprint:
            return {**result, "status": "refused", "reason": "PLAN_CHANGED"}
        for name, device, inode, size, modified in candidates:
            try:
                info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or (
                    info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
                ) != (device, inode, size, modified):
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
