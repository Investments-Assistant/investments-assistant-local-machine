"""Bound report files and refuse new work when its filesystem is under pressure."""

import os
import shutil
from pathlib import Path
import tempfile

from src.operations.report_cleanup import report_directory_lock


class StorageUnavailable(RuntimeError):
    """A stable, non-sensitive failure code suitable for report results."""


class LimitedWriter:
    def __init__(self, stream, limit: int):
        self.stream = stream
        self.limit = limit
        self.written = 0

    def write(self, data):
        if self.written + len(data) > self.limit:
            raise StorageUnavailable("REPORT_SIZE_LIMIT")
        count = self.stream.write(data)
        self.written += count
        return count


def write_report(destination: str, render, *, minimum_free_bytes: int, maximum_bytes: int):
    """Render privately on the destination filesystem, then publish a complete file.

    Call inside the PDF worker admission slot. The free-space check includes the
    maximum output allowance; unrelated processes can still consume disk space.
    No existing destination is overwritten, including a symlink.
    """
    if minimum_free_bytes < 0 or maximum_bytes <= 0:
        raise ValueError("Invalid storage budget")
    target = Path(destination)
    probe = target.parent
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        free = shutil.disk_usage(probe).free
    except OSError as exc:
        raise StorageUnavailable("STORAGE_UNAVAILABLE") from exc
    if free < minimum_free_bytes + maximum_bytes:
        raise StorageUnavailable("DISK_LOW")
    temporary = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with report_directory_lock(target.parent):
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".report-", delete=False) as stream:
                temporary = Path(stream.name)
                output = LimitedWriter(stream, maximum_bytes)
                render(output)
                if output.written == 0:
                    raise StorageUnavailable("PDF_EMPTY")
                stream.flush()
                os.fsync(stream.fileno())
            # Hard-link creation is atomic and refuses an existing target.
            os.link(temporary, target)
    except OSError as exc:
        raise StorageUnavailable("STORAGE_WRITE_FAILED") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
