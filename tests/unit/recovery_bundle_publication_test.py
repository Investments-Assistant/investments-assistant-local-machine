"""Private atomic bundle publication binds both restored archives and fixture proof."""

import io
import os
import json
import hashlib
import tarfile
from datetime import UTC, datetime

import pytest

from src.operations.report_cleanup import report_directory_lock
from src.operations.recovery_bundle import inspect_bundle, publish_fixture_bundle


def recovery_fixture(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    root = tmp_path / "bundles"
    root.mkdir(mode=0o700)
    database = work / "database.dump"
    database.write_bytes(b"synthetic verified database payload")
    content = {
        "vault.key": b"synthetic fixture key",
        "report.pdf": b"fixture pdf",
        "settings.json": b'{"fixture":true}',
        "model.gguf": b"synthetic miniature model bytes",
    }
    manifest = {}
    with tarfile.open(work / "filesystem.tar", "w") as archive:
        for name, data in content.items():
            manifest[name] = dict(size=len(data), sha256=hashlib.sha256(data).hexdigest())
            item = tarfile.TarInfo(name)
            item.size = len(data)
            archive.addfile(item, io.BytesIO(data))
    receipt = dict(
        status="PASS",
        timestamp=datetime.now(UTC).isoformat(),
        tier="disposable-postgresql-filesystem-vault-model-recovery",
        production_data=False,
        vault_decryption=True,
        wrong_key_rejected=True,
        restored_model_tasks=3,
        work_directory=str(work),
        files=manifest,
        database=dict(
            status="PASS",
            archive=str(database),
            archive_sha256=hashlib.sha256(database.read_bytes()).hexdigest(),
            source_identity_sha256="a" * 64,
        ),
    )
    return root, receipt, tmp_path / "receipt.json"


def test_publication_roundtrip_has_complete_matching_artifacts_and_private_receipt(tmp_path):
    root, recovery, output = recovery_fixture(tmp_path)
    result = publish_fixture_bundle(root, recovery, output)
    assert result == json.loads(output.read_text())
    bundle = root / os.path.basename(result["bundle"]["path"])
    assert bundle.stat().st_mode & 0o777 == 0o600
    assert output.stat().st_mode & 0o777 == 0o600
    manifest = inspect_bundle(bundle)
    assert set(manifest["artifacts"]) == {"database.dump", "filesystem.tar"}
    assert manifest["filesystem_members"] == recovery["files"]
    assert manifest["artifacts"]["database.dump"]["sha256"] == recovery["database"]["archive_sha256"]
    assert "synthetic fixture key" not in output.read_text()
    assert result["retention_scope"] == "coherent_fixture_bundle"


@pytest.mark.parametrize("change", ["database", "filesystem", "proof", "symlink", "byte_limit"])
def test_corrupt_or_unverified_source_cannot_publish_receipt(tmp_path, change):
    root, recovery, output = recovery_fixture(tmp_path)
    options = {}
    if change == "database":
        from pathlib import Path

        Path(recovery["database"]["archive"]).write_bytes(b"changed")
    elif change == "filesystem":
        recovery["files"]["vault.key"]["sha256"] = "b" * 64
    elif change == "proof":
        recovery["vault_decryption"] = False
    elif change == "symlink":
        from pathlib import Path

        path = Path(recovery["database"]["archive"])
        path.unlink()
        path.symlink_to(path.parent / "filesystem.tar")
    else:
        options["byte_limit"] = 10
    with pytest.raises((ValueError, OSError)):
        publish_fixture_bundle(root, recovery, output, **options)
    assert not output.exists() and not list(root.iterdir())


def test_active_cleanup_and_unsafe_root_refuse_publication(tmp_path):
    root, recovery, output = recovery_fixture(tmp_path)
    with report_directory_lock(root, exclusive=True), pytest.raises(BlockingIOError):
        publish_fixture_bundle(root, recovery, output)
    root.chmod(0o755)
    with pytest.raises(ValueError, match="private"):
        publish_fixture_bundle(root, recovery, output)
    assert not output.exists()


def test_existing_receipt_is_preserved_and_failure_leaves_only_unregistered_artifact(tmp_path):
    root, recovery, output = recovery_fixture(tmp_path)
    output.write_text("existing operator evidence")
    with pytest.raises(FileExistsError):
        publish_fixture_bundle(root, recovery, output)
    assert output.read_text() == "existing operator evidence"
    assert len(list(root.iterdir())) == 1
    inspect_bundle(next(root.iterdir()))


def test_bundle_tampering_and_member_escape_are_rejected(tmp_path):
    root, recovery, output = recovery_fixture(tmp_path)
    result = publish_fixture_bundle(root, recovery, output)
    with open(result["bundle"]["path"], "r+b") as changed:
        changed.seek(512)
        changed.write(b"tampered")
    with pytest.raises(ValueError):
        inspect_bundle(result["bundle"]["path"])
    malicious = root / "malicious.bundle"
    with tarfile.open(malicious, "w") as archive:
        item = tarfile.TarInfo("../vault.key")
        item.size = 1
        archive.addfile(item, io.BytesIO(b"x"))
    with pytest.raises(ValueError):
        inspect_bundle(malicious)


def test_published_bundle_cli_expiry_removes_only_complete_older_set(tmp_path):
    import sys
    from datetime import timedelta
    import subprocess

    root, recovery, old_receipt = recovery_fixture(tmp_path)
    now = datetime.now(UTC)
    recovery["timestamp"] = (now - timedelta(days=20)).isoformat()
    old = publish_fixture_bundle(root, recovery, old_receipt)
    new_receipt = tmp_path / "new-receipt.json"
    recovery["timestamp"] = (now - timedelta(days=10)).isoformat()
    new = publish_fixture_bundle(root, recovery, new_receipt)
    for result in (old, new):
        when = datetime.fromisoformat(result["timestamp"]).timestamp()
        os.utime(result["bundle"]["path"], (when, when))
    command = [
        sys.executable,
        "scripts/expire_recovery_bundles.py",
        "--archive-dir",
        str(root),
        "--evidence",
        str(old_receipt),
        "--evidence",
        str(new_receipt),
        "--before",
        (now - timedelta(days=5)).isoformat(),
        "--keep",
        "1",
    ]
    plan = json.loads(subprocess.run(command, capture_output=True, text=True, check=True).stdout)
    assert plan["candidate_count"] == 1 and plan["protected_count"] == 1
    applied = json.loads(
        subprocess.run(
            command + ["--confirm-sha256", plan["plan_sha256"]], capture_output=True, text=True, check=True
        ).stdout
    )
    assert applied["status"] == "complete" and applied["deleted"] == 1
    assert not os.path.exists(old["bundle"]["path"])
    inspect_bundle(new["bundle"]["path"])
    assert old_receipt.exists() and new_receipt.exists()
    assert os.path.exists(recovery["database"]["archive"])
