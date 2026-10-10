"""Explicit expiry of restored PostgreSQL archives; no automatic retention policy."""

import os
import json
import stat
import hashlib
from pathlib import Path
from datetime import UTC, datetime, timedelta

from src.operations.report_cleanup import report_directory_lock


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _identity(item):
    return [item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns]


def expire_backups(root, evidence_paths, **options):
    return _expire_archives(root, evidence_paths, retention_scope="standalone_database", **options)


def expire_bundles(root, evidence_paths, **options):
    """Expire one packed, fixture-restored database/filesystem/key set at a time."""
    return _expire_archives(root, evidence_paths, retention_scope="coherent_fixture_bundle", **options)


def _expire_archives(
    root,
    evidence_paths,
    *,
    before,
    keep,
    retention_scope,
    confirm_sha256=None,
    now=None,
    limit=1000,
    byte_limit=10 * 1024**3,
):
    """Use only the matching private local writer and successful restore receipts.

    Protect at least `keep` existing, checksum-verified archives per source identity.
    Unsupported, unregistered and already removed archives are never inferred to
    be expired. Evidence remains after removal. This is not filesystem/key expiry.
    """
    now = now or datetime.now(UTC)
    if before.tzinfo is None or now.tzinfo is None or before > now - timedelta(days=1):
        raise ValueError("Cutoff must be aware and at least 24 hours old")
    if not 1 <= keep <= limit <= 10000 or byte_limit < 1:
        raise ValueError("Invalid retention bounds")
    if not evidence_paths or len(evidence_paths) > limit:
        raise ValueError("Explicit bounded restore evidence required")
    root = Path(os.path.abspath(root))
    with report_directory_lock(root, exclusive=True) as descriptor:
        directory = os.fstat(descriptor)
        if directory.st_uid != os.getuid() or directory.st_mode & 0o022:
            raise ValueError("Backup directory must be owned and not group/world writable")
        with os.scandir(descriptor) as entries:
            for index, _ in enumerate(entries):
                if index >= limit:
                    return {"status": "refused", "reason": "FILE_LIMIT", "deleted": 0}
        records, seen, bytes_read = [], set(), 0
        for evidence_path in evidence_paths:
            fd = os.open(evidence_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > 2 * 1024**2:
                    raise ValueError("Unsafe restore evidence")
                content = stream.read(2 * 1024**2 + 1)
                if len(content) > 2 * 1024**2:
                    raise ValueError("Restore evidence too large")
            receipt = json.loads(content)
            if receipt.get("status") != "PASS" or receipt.get("retention_scope") != retention_scope:
                raise ValueError("Unsupported restore evidence")
            if retention_scope == "coherent_fixture_bundle":
                packed = receipt.get("bundle", {})
                database = receipt.get("database", {})
                if (
                    receipt.get("tier") != "disposable-postgresql-filesystem-vault-model-recovery"
                    or receipt.get("production_data") is not False
                    or receipt.get("vault_decryption") is not True
                    or receipt.get("wrong_key_rejected") is not True
                    or receipt.get("restored_model_tasks") != 3
                    or database.get("status") != "PASS"
                    or packed.get("schema") != 1
                    or packed.get("members") != ["database.dump", "filesystem.tar", "manifest.json"]
                ):
                    raise ValueError("Unsupported coherent recovery proof")
                scope, expected = database.get("source_identity_sha256", ""), packed.get("sha256", "")
                archive_path, suffix = packed.get("path", ""), ".bundle"
            else:
                if receipt.get("tier") != "real-postgresql-disposable-backup-restore":
                    raise ValueError("Unsupported restore evidence")
                scope, expected = receipt.get("source_identity_sha256", ""), receipt.get("archive_sha256", "")
                archive_path, suffix = receipt.get("archive", ""), ".dump"
            if any(len(value) != 64 or any(c not in "0123456789abcdef" for c in value) for value in (scope, expected)):
                raise ValueError("Missing verified archive/source identity")
            verified = datetime.fromisoformat(receipt["timestamp"])
            if verified.tzinfo is None or verified > now:
                raise ValueError("Invalid restore clock")
            path = Path(os.path.abspath(archive_path))
            if path.parent != root or path.suffix != suffix or path.name in seen:
                raise ValueError("Unsafe or duplicate archive reference")
            seen.add(path.name)
            try:
                fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=descriptor)
            except FileNotFoundError:
                continue  # A previous confirmed expiry can leave its receipt.
            with os.fdopen(fd, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_mtime > now.timestamp():
                    raise ValueError("Unsafe archive or future file clock")
                actual = hashlib.sha256()
                while block := stream.read(min(1024**2, byte_limit - bytes_read + 1)):
                    bytes_read += len(block)
                    if bytes_read > byte_limit:
                        return {"status": "refused", "reason": "BYTE_LIMIT", "deleted": 0}
                    actual.update(block)
                after = os.fstat(stream.fileno())
                if _identity(info) != _identity(after) or actual.hexdigest() != expected:
                    return {"status": "refused", "reason": "ARCHIVE_CHANGED", "deleted": 0}
            records.append(
                {
                    "name": path.name,
                    "scope": scope,
                    "verified": verified.isoformat(),
                    "metadata": _identity(info),
                    "receipt": hashlib.sha256(content).hexdigest(),
                }
            )
        protected = set()
        for scope in {item["scope"] for item in records}:
            scoped = sorted(
                (item for item in records if item["scope"] == scope),
                key=lambda item: (datetime.fromisoformat(item["verified"]), item["name"]),
                reverse=True,
            )
            protected.update(item["name"] for item in scoped[:keep])
        candidates = [
            item
            for item in records
            if item["name"] not in protected
            and datetime.fromisoformat(item["verified"]) < before
            and item["metadata"][3] < before.timestamp() * 10**9
        ]
        plan = _hash(
            {
                "retention_scope": retention_scope,
                "directory": [directory.st_dev, directory.st_ino],
                "before": before.isoformat(),
                "keep": keep,
                "records": sorted(records, key=lambda item: item["name"]),
            }
        )
        result = {
            "status": "preview",
            "scope": "verified_coherent_fixture_bundles"
            if retention_scope == "coherent_fixture_bundle"
            else "verified_database_archives_only",
            "plan_sha256": plan,
            "candidate_count": len(candidates),
            "candidate_bytes": sum(item["metadata"][2] for item in candidates),
            "protected_count": len(protected),
            "deleted": 0,
        }
        if confirm_sha256 is None:
            return result
        if confirm_sha256 != plan:
            return {**result, "status": "refused", "reason": "PLAN_CHANGED"}
        for item in candidates:
            try:
                info = os.stat(item["name"], dir_fd=descriptor, follow_symlinks=False)
                if not stat.S_ISREG(info.st_mode) or _identity(info) != item["metadata"]:
                    return {**result, "status": "partial", "reason": "ARCHIVE_CHANGED"}
                os.unlink(item["name"], dir_fd=descriptor)
                result["deleted"] += 1
            except OSError:
                return {**result, "status": "partial", "reason": "EXPIRY_IO_FAILED"}
        try:
            os.fsync(descriptor)
        except OSError:
            return {**result, "status": "partial", "reason": "EXPIRY_SYNC_FAILED"}
        return {**result, "status": "complete"}
