"""Expire only a whole verified recovery set, preserving the newest set per source."""

import os
import json
import hashlib
from datetime import UTC, datetime, timedelta

import pytest

from src.operations import backup_retention

NOW = datetime(2026, 10, 7, tzinfo=UTC)
BEFORE = NOW - timedelta(days=5)


def bundle(root, days, source="synthetic-source"):
    path = root / f"recovery-{source}-{days}.bundle"
    data = b"synthetic atomic bundle with matching database and filesystem " + str(days).encode()
    path.write_bytes(data)
    when = NOW - timedelta(days=days)
    os.utime(path, (when.timestamp(), when.timestamp()))
    receipt = root / (path.name + ".json")
    receipt.write_text(
        json.dumps(
            dict(
                status="PASS",
                timestamp=when.isoformat(),
                tier="disposable-postgresql-filesystem-vault-model-recovery",
                retention_scope="coherent_fixture_bundle",
                production_data=False,
                vault_decryption=True,
                wrong_key_rejected=True,
                restored_model_tasks=3,
                database=dict(status="PASS", source_identity_sha256=hashlib.sha256(source.encode()).hexdigest()),
                bundle=dict(
                    schema=1,
                    path=str(path),
                    sha256=hashlib.sha256(data).hexdigest(),
                    members=["database.dump", "filesystem.tar", "manifest.json"],
                ),
            )
        )
    )
    return path, receipt


def test_bundle_expiry_is_one_artifact_and_cannot_use_database_only_receipt(tmp_path):
    old, old_e = bundle(tmp_path, 20)
    newest, newest_e = bundle(tmp_path, 10)
    loose_key = tmp_path / "vault.key"
    loose_key.write_bytes(b"unregistered fixture key")
    plan = backup_retention.expire_bundles(tmp_path, [old_e, newest_e], before=BEFORE, keep=1, now=NOW)
    assert plan["candidate_count"] == 1 and plan["protected_count"] == 1
    result = backup_retention.expire_bundles(
        tmp_path, [old_e, newest_e], before=BEFORE, keep=1, now=NOW, confirm_sha256=plan["plan_sha256"]
    )
    assert result["status"] == "complete" and result["deleted"] == 1
    assert not old.exists() and newest.exists() and loose_key.exists()
    with pytest.raises(ValueError):
        backup_retention.expire_backups(tmp_path, [newest_e], before=BEFORE, keep=1, now=NOW)


@pytest.mark.parametrize("change", ["members", "vault", "scope", "source", "checksum"])
def test_invalid_bundle_proof_refuses_expiry(tmp_path, change):
    old, old_e = bundle(tmp_path, 20)
    _, newest_e = bundle(tmp_path, 10)
    receipt = json.loads(old_e.read_text())
    if change == "members":
        receipt["bundle"]["members"].remove("filesystem.tar")
    elif change == "vault":
        receipt["vault_decryption"] = False
    elif change == "scope":
        receipt["retention_scope"] = "preserve_unclassified_bundle"
    elif change == "source":
        receipt["database"]["source_identity_sha256"] = ""
    else:
        receipt["bundle"]["sha256"] = "a" * 64
    old_e.write_text(json.dumps(receipt))
    try:
        result = backup_retention.expire_bundles(tmp_path, [old_e, newest_e], before=BEFORE, keep=1, now=NOW)
    except ValueError:
        pass
    else:
        assert result["status"] == "refused" and result["deleted"] == 0
    assert old.exists()
