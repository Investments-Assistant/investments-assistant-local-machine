"""Backup/restore exercise restricted to a positively marked local test database.

Never drops a database or overwrites an existing destination. The resulting test
DB and archive remain for review; repeated runs require a new destination name.
"""

import os
import re
import json
import asyncio
import hashlib
from pathlib import Path
import argparse
from datetime import UTC, datetime
import subprocess

import asyncpg


async def inventory(connection):
    tables = await connection.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
    )
    result = {}
    for record in tables:
        table = record["tablename"]
        if not re.fullmatch(r"[a-z_0-9]+", table):
            raise RuntimeError("Unexpected test table identifier")
        # Persist only digests/counts, never restored user data or credential rows.
        rows = await connection.fetch(f'SELECT row_to_json(t)::text AS record FROM "{table}" t')
        digests = sorted(hashlib.sha256(row["record"].encode()).hexdigest() for row in rows)
        result[table] = {
            "count": len(rows),
            "sha256": hashlib.sha256("\n".join(digests).encode()).hexdigest(),
        }
    return result


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--port", type=int, default=55439)
    parser.add_argument("--bin", type=Path, required=True)
    parser.add_argument("--library-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive-dir", type=Path, default=Path("/tmp"))
    args = parser.parse_args()
    token = os.environ.get("TEST_DATABASE_DISPOSABLE_TOKEN")
    if (
        not token
        or args.source == args.target
        or any(not re.fullmatch(r"test_[a-z0-9_]+", name) for name in (args.source, args.target))
    ):
        raise SystemExit("Distinct test_ database names and explicit marker token are required")
    fixture_root = Path(__file__).resolve().parents[1] / ".qa"

    def fixture_path(path):
        resolved = path.resolve()
        return resolved.is_relative_to(Path("/tmp")) or resolved.is_relative_to(fixture_root)

    if not fixture_path(args.socket) or not args.socket.is_dir():
        raise SystemExit("Only an explicit /tmp or checkout .qa fixture Unix socket is permitted")
    if not fixture_path(args.archive_dir):
        raise SystemExit("Archive directory must be inside /tmp or checkout .qa")
    args.archive_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    source = await asyncpg.connect(database=args.source, host=str(args.socket), port=args.port)
    target = None
    try:
        actual = await source.fetchval("SELECT current_database()")
        marker = await source.fetchval("SELECT token FROM public.ia_disposable_marker")
        if actual != args.source or marker != token:
            raise SystemExit("Disposable source identity verification failed")
        if await source.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", args.target):
            raise SystemExit("Destination already exists; inspect previous run, never overwrite")
        before = await inventory(source)
        archive = args.archive_dir / (args.target + ".dump")
        if archive.exists():
            raise SystemExit("Archive already exists; inspect before retrying")
        # Create privately before pg_dump writes any content.
        descriptor = os.open(archive, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        environment = {
            "PATH": os.environ.get("PATH", ""),
            "LD_LIBRARY_PATH": str(args.library_path),
        }
        subprocess.run(
            [
                str(args.bin / "pg_dump"),
                "-h",
                str(args.socket),
                "-p",
                str(args.port),
                "-d",
                args.source,
                "-Fc",
                "-f",
                str(archive),
            ],
            env=environment,
            check=True,
            timeout=60,
        )
        archive.chmod(0o600)
        await source.execute(f'CREATE DATABASE "{args.target}"')
        subprocess.run(
            [
                str(args.bin / "pg_restore"),
                "-h",
                str(args.socket),
                "-p",
                str(args.port),
                "-d",
                args.target,
                "--exit-on-error",
                "--no-owner",
                "--no-privileges",
                str(archive),
            ],
            env=environment,
            check=True,
            timeout=60,
        )
        target = await asyncpg.connect(database=args.target, host=str(args.socket), port=args.port)
        if await target.fetchval("SELECT token FROM public.ia_disposable_marker") != token:
            raise RuntimeError("Restored marker does not match")
        restored = await inventory(target)
        if before != restored or before != await inventory(source):
            raise RuntimeError("Restore content differs or source changed during the exercise")
        revision = await target.fetchval("SELECT version_num FROM alembic_version")
        result = {
            "status": "PASS",
            "tier": "real-postgresql-disposable-backup-restore",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": args.source,
            "target": args.target,
            "revision": revision,
            "tables": restored,
            "archive": str(archive),
            "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "production_data": False,
            "limitations": [
                "Database only; reports/model/vault-key filesystem recovery is separate."
            ],
        }
        args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "tables": len(restored),
                    "revision": revision,
                    "evidence": str(args.output),
                }
            )
        )
    finally:
        if target:
            await target.close()
        await source.close()


if __name__ == "__main__":
    asyncio.run(main())
