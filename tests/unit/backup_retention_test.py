import os
import json
import hashlib
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from src.operations.report_cleanup import report_directory_lock
from src.operations.backup_retention import expire_backups

NOW = datetime(2026, 10, 5, tzinfo=UTC)
BEFORE = NOW - timedelta(days=5)


def archive(root, days, scope="source", name=None):
    name = name or f"{scope}_{days}"
    path = root / (name + ".dump")
    content = b"synthetic archive " + name.encode()
    path.write_bytes(content)
    when = NOW - timedelta(days=days)
    os.utime(path, (when.timestamp(), when.timestamp()))
    evidence = root / (name + ".json")
    evidence.write_text(json.dumps({
        "status": "PASS", "tier": "real-postgresql-disposable-backup-restore",
        "retention_scope": "standalone_database",
        "timestamp": when.isoformat(), "archive": str(path),
        "archive_sha256": hashlib.sha256(content).hexdigest(),
        "source_identity_sha256": hashlib.sha256(scope.encode()).hexdigest(),
    }))
    return path, evidence


def expiry(root, evidence, **kwargs):
    return expire_backups(root, evidence, before=BEFORE, keep=1, now=NOW, **kwargs)


def test_expiry_preserves_newest_per_source_unregistered_files_and_evidence(tmp_path):
    old, old_e = archive(tmp_path, 20)
    new, new_e = archive(tmp_path, 10)
    other, other_e = archive(tmp_path, 30, "other-source")
    unknown = tmp_path / "unregistered.dump"
    unknown.write_bytes(b"unknown ownership")
    evidence = [old_e, new_e, other_e]
    plan = expiry(tmp_path, evidence)
    assert plan["candidate_count"] == 1 and plan["protected_count"] == 2
    assert old.name not in str(plan) and "source" not in str(plan)
    result = expiry(tmp_path, evidence, confirm_sha256=plan["plan_sha256"])
    assert result["deleted"] == 1 and result["status"] == "complete"
    assert not old.exists() and all(p.exists() for p in [new, other, unknown, *evidence])
    assert expiry(tmp_path, evidence)["candidate_count"] == 0


@pytest.mark.parametrize("change", ["corrupt", "replaced", "missing_protected", "scope", "new_receipt"])
def test_changed_plan_never_expires_remaining_backups(tmp_path, change):
    old, old_e = archive(tmp_path, 20)
    new, new_e = archive(tmp_path, 10)
    evidence = [old_e, new_e]
    plan = expiry(tmp_path, evidence)
    if change == "corrupt":
        old.write_bytes(b"corrupt")
        os.utime(old, (BEFORE.timestamp() - 1, BEFORE.timestamp() - 1))
    elif change == "replaced":
        content = old.read_bytes()
        old.unlink()
        old.write_bytes(content)
        os.utime(old, (BEFORE.timestamp() - 1, BEFORE.timestamp() - 1))
    elif change == "missing_protected":
        new.unlink()
    elif change == "scope":
        receipt = json.loads(old_e.read_text())
        receipt["source_identity_sha256"] = "0" * 64
        old_e.write_text(json.dumps(receipt))
    else:
        _, extra = archive(tmp_path, 1)
        evidence.append(extra)
    result = expiry(tmp_path, evidence, confirm_sha256=plan["plan_sha256"])
    assert result["status"] == "refused" and result["deleted"] == 0 and old.exists()


def test_bounds_active_writer_symlinks_and_invalid_receipts_fail_closed(tmp_path):
    old, old_e = archive(tmp_path, 20)
    _, new_e = archive(tmp_path, 10)
    evidence = [old_e, new_e]
    with report_directory_lock(tmp_path), pytest.raises(BlockingIOError):
        expiry(tmp_path, evidence)
    assert expiry(tmp_path, evidence, byte_limit=1)["reason"] == "BYTE_LIMIT"
    assert expiry(tmp_path, evidence, limit=2)["reason"] == "FILE_LIMIT"
    with pytest.raises(ValueError):
        expire_backups(tmp_path, evidence, before=BEFORE, keep=0, now=NOW)
    old.unlink()
    old.symlink_to(new_e)
    with pytest.raises(OSError):
        expiry(tmp_path, evidence)
    old.unlink()
    receipt = json.loads(old_e.read_text())
    del receipt["source_identity_sha256"]
    old_e.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        expiry(tmp_path, evidence)


@pytest.mark.parametrize("operation", ["unlink", "fsync"])
def test_partial_expiry_retains_newest_and_reports_actual_removal(tmp_path, operation):
    old, old_e = archive(tmp_path, 30)
    middle, middle_e = archive(tmp_path, 20)
    newest, newest_e = archive(tmp_path, 10)
    evidence = [old_e, middle_e, newest_e]
    plan = expiry(tmp_path, evidence)
    original = os.unlink

    def unlink(name, **kwargs):
        if name == middle.name:
            raise OSError("private fixture")
        original(name, **kwargs)

    with patch(f"src.operations.backup_retention.os.{operation}",
               side_effect=unlink if operation == "unlink" else OSError("private fixture")):
        result = expiry(tmp_path, evidence, confirm_sha256=plan["plan_sha256"])
    assert result["status"] == "partial" and newest.exists()
    assert result["deleted"] == (1 if operation == "unlink" else 2)
    assert not old.exists() and "private" not in str(result)


def test_operator_cli_preview_and_confirmation(tmp_path):
    import sys
    import subprocess

    old, old_e = archive(tmp_path, 30)
    new, new_e = archive(tmp_path, 10)
    command = [sys.executable, "scripts/expire_database_backups.py", "--archive-dir", str(tmp_path),
               "--before", BEFORE.isoformat(), "--keep", "1", "--evidence", str(old_e), "--evidence", str(new_e)]
    preview = subprocess.run(command, capture_output=True, text=True, check=True)
    plan = json.loads(preview.stdout)
    confirmed = subprocess.run(command + ["--confirm-sha256", plan["plan_sha256"]],
                               capture_output=True, text=True, check=True)
    assert json.loads(confirmed.stdout)["status"] == "complete"
    assert not old.exists() and new.exists()


def test_bundle_or_unclassified_archive_cannot_be_expired(tmp_path):
    old, old_e = archive(tmp_path, 30)
    newest, newest_e = archive(tmp_path, 10)
    receipt = json.loads(old_e.read_text())
    receipt["retention_scope"] = "preserve_unclassified_bundle"
    old_e.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="Unsupported restore evidence"):
        expiry(tmp_path, [old_e, newest_e])
    assert old.exists() and newest.exists()
