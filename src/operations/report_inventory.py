"""Read-only report storage reconciliation; never authorizes deletion.

The database and filesystem are not an atomic snapshot. Unreferenced files can
belong to an in-flight report or a failed commit. Preserve them for review.
"""

import os
import stat
import hashlib
from pathlib import Path
from datetime import UTC, datetime
from collections.abc import Iterable


def inventory_reports(
    root: Path,
    references: Iterable[str],
    *,
    reference_limit: int = 10000,
    file_limit: int = 10000,
    now: datetime | None = None,
) -> dict:
    """Bound traversal, avoid following links, and emit no private file names."""
    if reference_limit < 1 or file_limit < 1:
        raise ValueError("Inventory limits must be positive")
    now = now or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Inventory clock must be timezone aware")
    root = Path(os.path.abspath(root))
    reasons = set()
    referenced = set()
    reference_count = 0
    for reference_count, value in enumerate(references, 1):
        if reference_count > reference_limit:
            reasons.add("REFERENCE_LIMIT")
            break
        path = Path(os.path.abspath(value))
        if path.parent != root:
            reasons.add("REFERENCE_OUTSIDE_ROOT")
        else:
            referenced.add(path.name)
    files = []
    seen = set()
    total_bytes = 0
    try:
        # Open the directory without following a final symlink. Child metadata
        # is read through this descriptor so a renamed root cannot redirect it.
        descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            with os.scandir(descriptor) as entries:
                for index, entry in enumerate(entries):
                    if index >= file_limit:
                        reasons.add("FILE_LIMIT")
                        break
                    metadata = entry.stat(follow_symlinks=False)
                    if not stat.S_ISREG(metadata.st_mode):
                        reasons.add("NON_REGULAR_ENTRY")
                        continue
                    seen.add(entry.name)
                    total_bytes += metadata.st_size
                    known = entry.name in referenced
                    report_file = entry.name.startswith("report_") and entry.name.endswith(".pdf")
                    temporary = entry.name.startswith(".report-")
                    category = "referenced" if known else "unreferenced" if report_file or temporary else "unmanaged"
                    if category == "unreferenced" and "REFERENCE_LIMIT" in reasons:
                        category = "reference_unknown"
                    files.append({
                        "path_sha256": hashlib.sha256(entry.name.encode()).hexdigest(),
                        "category": category,
                        "bytes": metadata.st_size,
                        "age_seconds": max(0, int(now.timestamp() - metadata.st_mtime)),
                        "temporary": temporary,
                    })
                    if metadata.st_mtime > now.timestamp():
                        reasons.add("FILE_CLOCK_AHEAD")
        finally:
            os.close(descriptor)
    except OSError:
        reasons.add("STORAGE_INVENTORY_UNAVAILABLE")
    complete = not reasons
    return {
        "status": "observed" if complete else "partial",
        "as_of": now.isoformat(),
        "reasons": sorted(reasons),
        "reference_rows_scanned": min(reference_count, reference_limit),
        "regular_files_scanned": len(files),
        "bytes_scanned": total_bytes,
        "missing_reference_count": len(referenced - seen) if complete else None,
        "files": sorted(files, key=lambda item: item["path_sha256"]),
        "deletion_authorized": False,
        "consistency": "non_atomic_observation",
    }
