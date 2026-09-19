import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.operations.storage import write_report
from src.operations.report_cleanup import cleanup_temporaries, report_directory_lock

NOW = datetime(2026, 9, 17, tzinfo=UTC)
CUTOFF = NOW - timedelta(days=2)


def old_file(root, name):
    target = root / name
    target.write_bytes(b"fixture")
    os.utime(target, (CUTOFF.timestamp() - 1, CUTOFF.timestamp() - 1))
    return target


def test_preview_confirm_preserves_finished_recent_and_nonregular_files(tmp_path):
    abandoned = old_file(tmp_path, ".report-abandoned")
    finished = old_file(tmp_path, "report_saved.pdf")
    link = tmp_path / ".report-link"
    link.symlink_to(finished)
    (tmp_path / ".report-directory").mkdir()
    recent = tmp_path / ".report-current"
    recent.write_bytes(b"active")
    plan = cleanup_temporaries(tmp_path, before=CUTOFF, now=NOW)
    assert plan["candidate_count"] == 1
    assert abandoned.exists()
    result = cleanup_temporaries(tmp_path, before=CUTOFF, now=NOW, confirm_sha256=plan["plan_sha256"])
    assert result["deleted"] == 1
    assert result["status"] == "complete"
    assert not abandoned.exists()
    assert finished.exists() and recent.exists() and link.is_symlink()


def test_changed_plan_and_scan_limit_delete_nothing(tmp_path):
    first = old_file(tmp_path, ".report-first")
    plan = cleanup_temporaries(tmp_path, before=CUTOFF, now=NOW)
    second = old_file(tmp_path, ".report-second")
    changed = cleanup_temporaries(tmp_path, before=CUTOFF, now=NOW, confirm_sha256=plan["plan_sha256"])
    assert changed["reason"] == "PLAN_CHANGED"
    partial = cleanup_temporaries(tmp_path, before=CUTOFF, now=NOW, limit=1, confirm_sha256=plan["plan_sha256"])
    assert partial["reason"] == "FILE_LIMIT" and partial["deleted"] == 0
    assert first.exists() and second.exists()


def test_active_renderer_prevents_cleanup_and_cleanup_prevents_renderer(tmp_path):
    old_file(tmp_path, ".report-old")

    def render(output):
        with pytest.raises(BlockingIOError):
            cleanup_temporaries(tmp_path, before=CUTOFF, now=NOW)
        output.write(b"rendered")

    write_report(str(tmp_path / "report_new.pdf"), render, minimum_free_bytes=0, maximum_bytes=100)
    with report_directory_lock(tmp_path, exclusive=True), pytest.raises(RuntimeError, match="STORAGE_WRITE_FAILED"):
        write_report(str(tmp_path / "report_other.pdf"), render, minimum_free_bytes=0, maximum_bytes=100)
    assert not (tmp_path / "report_other.pdf").exists()


def test_reject_recent_cutoff_and_symlink_root(tmp_path):
    with pytest.raises(ValueError):
        cleanup_temporaries(tmp_path, before=NOW, now=NOW)
    directory = tmp_path / "real"
    directory.mkdir()
    link = tmp_path / "link"
    link.symlink_to(directory, target_is_directory=True)
    with pytest.raises(OSError):
        cleanup_temporaries(link, before=CUTOFF, now=NOW)


def test_partial_io_failure_reports_completed_removals(tmp_path):
    first = old_file(tmp_path, ".report-a")
    second = old_file(tmp_path, ".report-b")
    plan = cleanup_temporaries(tmp_path, before=CUTOFF, now=NOW)
    original = os.unlink

    def unlink(name, **kwargs):
        if name == second.name:
            raise OSError("fixture")
        return original(name, **kwargs)

    with patch("src.operations.report_cleanup.os.unlink", side_effect=unlink):
        result = cleanup_temporaries(tmp_path, before=CUTOFF, now=NOW, confirm_sha256=plan["plan_sha256"])
    assert result["status"] == "partial" and result["deleted"] == 1
    assert result["reason"] == "CLEANUP_IO_FAILED"
    assert not first.exists() and second.exists()


def test_sync_failure_does_not_claim_durable_cleanup(tmp_path):
    old_file(tmp_path, ".report-a")
    plan = cleanup_temporaries(tmp_path, before=CUTOFF, now=NOW)
    with patch("src.operations.report_cleanup.os.fsync", side_effect=OSError("fixture")):
        result = cleanup_temporaries(tmp_path, before=CUTOFF, now=NOW, confirm_sha256=plan["plan_sha256"])
    assert result["status"] == "partial" and result["deleted"] == 1
    assert result["reason"] == "CLEANUP_SYNC_FAILED"
