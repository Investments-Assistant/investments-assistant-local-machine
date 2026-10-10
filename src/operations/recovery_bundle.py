"""Package an already verified disposable recovery set into one expirable artifact."""

import io
import os
import json
import stat
import uuid
import hashlib
from pathlib import Path
import tarfile
from contextlib import ExitStack, suppress

from src.operations.report_cleanup import report_directory_lock

MEMBERS = ["database.dump", "filesystem.tar", "manifest.json"]
FILES = {"vault.key", "report.pdf", "settings.json", "model.gguf"}


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _digest(stream):
    value = hashlib.sha256()
    while block := stream.read(1024**2):
        value.update(block)
    return value.hexdigest()


def _regular(stack, path):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    stream = stack.enter_context(os.fdopen(descriptor, "rb"))
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Recovery member must be a regular file")
    return stream, info


def inspect_bundle(path, *, byte_limit=10 * 1024**3):
    """Stream-verify one uncompressed bundle without extracting or loading a key/model."""
    with ExitStack() as stack:
        stream, before = _regular(stack, path)
        if before.st_size > byte_limit or byte_limit < 1:
            raise ValueError("Bundle byte limit exceeded")
        artifacts = {}
        manifest = None
        total = 0
        with tarfile.open(fileobj=stream, mode="r:") as archive:
            for index, item in enumerate(archive):
                if index >= 3 or item.name != MEMBERS[index] or not item.isfile():
                    raise ValueError("Unexpected bundle member")
                total += item.size
                if item.size < 0 or total > byte_limit:
                    raise ValueError("Bundle member byte limit exceeded")
                with archive.extractfile(item) as content:
                    if item.name == "manifest.json":
                        if item.size > 1024**2:
                            raise ValueError("Bundle manifest too large")
                        manifest = json.load(content)
                    else:
                        artifacts[item.name] = dict(size=item.size, sha256=_digest(content))
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema") != 1
            or manifest.get("fixture") is not True
            or manifest.get("artifacts") != artifacts
            or set(artifacts) != set(MEMBERS[:2])
            or _identity(before) != _identity(os.fstat(stream.fileno()))
        ):
            raise ValueError("Incomplete or changed bundle")
        return manifest


def publish_fixture_bundle(root, recovery, receipt_path, *, byte_limit=10 * 1024**3):
    """Publish atomically, retaining unknown files and never overwriting a receipt.

    Cooperating expiry is excluded until the verified bundle and receipt are durable.
    A publication failure can leave an unregistered bundle; it is never auto-expired.
    This packages synthetic recovery artifacts only, not production backups.
    """
    database = recovery.get("database", {})
    files = recovery.get("files", {})
    if (
        recovery.get("status") != "PASS"
        or recovery.get("tier") != "disposable-postgresql-filesystem-vault-model-recovery"
        or recovery.get("production_data") is not False
        or recovery.get("vault_decryption") is not True
        or recovery.get("wrong_key_rejected") is not True
        or recovery.get("restored_model_tasks") != 3
        or database.get("status") != "PASS"
        or set(files) != FILES
    ):
        raise ValueError("Complete successful fixture recovery evidence required")
    scope = database.get("source_identity_sha256", "")
    if len(scope) != 64 or any(char not in "0123456789abcdef" for char in scope):
        raise ValueError("Source recovery identity required")
    root = Path(os.path.abspath(root))
    work = Path(os.path.abspath(recovery["work_directory"]))
    dump = Path(os.path.abspath(database["archive"]))
    if dump.parent != work or dump.suffix != ".dump":
        raise ValueError("Database archive is not part of the recovery work directory")
    with report_directory_lock(root) as directory, ExitStack() as stack:
        info = os.fstat(directory)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError("Bundle root must be private and owned")
        source_streams = {}
        artifacts = {}
        for name, path in (("database.dump", dump), ("filesystem.tar", work / "filesystem.tar")):
            stream, before = _regular(stack, path)
            if before.st_size > byte_limit:
                raise ValueError("Recovery byte limit exceeded")
            source_streams[name] = stream, before
            artifacts[name] = dict(size=before.st_size, sha256=_digest(stream))
            stream.seek(0)
        if sum(item["size"] for item in artifacts.values()) > byte_limit - 10240:
            raise ValueError("Recovery byte limit exceeded")
        if artifacts["database.dump"]["sha256"] != database.get("archive_sha256"):
            raise ValueError("Database archive changed since restore")
        filesystem = source_streams["filesystem.tar"][0]
        observed = {}
        with tarfile.open(fileobj=filesystem, mode="r:") as archive:
            for index, member in enumerate(archive):
                if index >= 4 or member.name not in FILES or member.name in observed or not member.isfile():
                    raise ValueError("Unexpected filesystem recovery member")
                if member.size != files[member.name]["size"] or member.size < 0 or member.size > byte_limit:
                    raise ValueError("Filesystem member size changed")
                with archive.extractfile(member) as content:
                    observed[member.name] = dict(size=member.size, sha256=_digest(content))
        if observed != files:
            raise ValueError("Filesystem recovery content changed")
        filesystem.seek(0)
        manifest = dict(
            schema=1, fixture=True, source_identity_sha256=scope, artifacts=artifacts, filesystem_members=files
        )
        manifest_bytes = json.dumps(manifest, sort_keys=True).encode()
        name = "recovery-" + uuid.uuid4().hex + ".bundle"
        temporary = "." + name + ".tmp"
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=directory)
        try:
            with os.fdopen(fd, "wb") as output:
                with tarfile.open(fileobj=output, mode="w") as archive:
                    for member_name, (stream, before) in source_streams.items():
                        item = tarfile.TarInfo(member_name)
                        item.size, item.mode = before.st_size, 0o600
                        archive.addfile(item, stream)
                        if _identity(before) != _identity(os.fstat(stream.fileno())):
                            raise ValueError("Recovery member changed while packing")
                    item = tarfile.TarInfo("manifest.json")
                    item.size, item.mode = len(manifest_bytes), 0o600
                    archive.addfile(item, io.BytesIO(manifest_bytes))
                output.flush()
                os.fsync(output.fileno())
            if inspect_bundle(root / temporary, byte_limit=byte_limit) != manifest:
                raise ValueError("Packed recovery verification failed")
            # Link gives no-replace publication, even under a name collision.
            os.link(temporary, name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            os.unlink(temporary, dir_fd=directory)
            os.fsync(directory)
            with (root / name).open("rb") as packed:
                checksum = _digest(packed)
            result = {
                **recovery,
                "retention_scope": "coherent_fixture_bundle",
                "bundle": dict(schema=1, path=str(root / name), sha256=checksum, members=MEMBERS),
            }
            # A failed receipt write leaves an unregistered protected artifact.
            receipt_fd = os.open(receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(receipt_fd, "w") as receipt:
                json.dump(result, receipt, indent=2)
                receipt.write("\n")
                receipt.flush()
                os.fsync(receipt.fileno())
            parent_fd = os.open(Path(receipt_path).parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
            return result
        finally:
            with suppress(FileNotFoundError):
                os.unlink(temporary, dir_fd=directory)
