"""Recover marked synthetic DB, vault key, PDF and existing GGUF into new destinations.

Never overwrites a destination or restores production. Only synthetic inactive
records are added to the source; their IDs are removed after the exercise.
"""

import os
import re
import sys
import json
import uuid
import shutil
import asyncio
import hashlib
from pathlib import Path
import tarfile
import argparse
from datetime import UTC, datetime
import subprocess

import asyncpg
from cryptography.fernet import Fernet, InvalidToken

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    token = os.environ.get("TEST_DATABASE_DISPOSABLE_TOKEN")
    if (
        not token
        or args.source == args.target
        or any(not re.fullmatch("test_[a-z0-9_]+", name) for name in (args.source, args.target))
    ):
        raise SystemExit("Distinct explicitly marked test databases required")
    model = args.model.resolve()
    if not model.is_relative_to(ROOT / "models") or not model.is_file() or model.suffix != ".gguf":
        raise SystemExit("Select an existing GGUF in this checkout models directory")
    if shutil.disk_usage(ROOT).free < model.stat().st_size * 3 + 512 * 1024**2:
        raise SystemExit("Insufficient free disk for bounded recovery exercise")
    qa = ROOT / ".qa"
    socket = qa / "socket"
    work = qa / ("recovery-" + args.target)
    source = await asyncpg.connect(
        database=args.source, host=str(socket), port=55439, command_timeout=10
    )
    owner, account = str(uuid.uuid4()), str(uuid.uuid4())
    seeded = False
    try:
        if (
            await source.fetchval("SELECT current_database()") != args.source
            or await source.fetchval("SELECT token FROM public.ia_disposable_marker") != token
        ):
            raise SystemExit("Source disposable identity mismatch")
        if await source.fetchval("SELECT 1 FROM pg_database WHERE datname=$1", args.target):
            raise SystemExit("Destination exists; inspect interrupted operation before retrying")
        work.mkdir(mode=0o700)  # Refuse existing archive/work directory too.
        original, restored = work / "original", work / "restored"
        original.mkdir(mode=0o700)
        key = Fernet.generate_key()
        (original / "vault.key").write_bytes(key)
        (original / "vault.key").chmod(0o600)
        plaintext = json.dumps(
            {"api_key": "synthetic-recovery-only", "secret_key": "synthetic", "paper": True}
        ).encode()
        cipher = Fernet(key).encrypt(plaintext).decode()
        async with source.transaction():
            await source.execute(
                """INSERT INTO users
                (id,username,password_hash,display_name,description,preferences,trading_mode,is_active,created_at,updated_at)
                VALUES($1,$2,'fixture-disabled','Synthetic recovery','',
                       '{}','recommend',false,now(),now())""",
                owner,
                "fixture-recovery-" + owner,
            )
            await source.execute(
                """INSERT INTO broker_accounts
                (id,user_id,broker,display_name,config_encrypted,is_active,created_at,updated_at)
                VALUES($1,$2,'alpaca','Synthetic recovery',$3,false,now(),now())""",
                account,
                owner,
                cipher,
            )
        seeded = True
        from weasyprint import HTML

        HTML(
            string=(
                "<h1>Synthetic recovery report</h1>"
                "<p>No broker connection or real financial data.</p>"
            )
        ).write_pdf(original / "report.pdf")
        (original / "settings.json").write_text(
            json.dumps(
                {
                    "fixture": True,
                    "live_enabled": False,
                    "model": "model.gguf",
                    "vault_key": "vault.key",
                }
            )
        )
        files = {
            "vault.key": original / "vault.key",
            "report.pdf": original / "report.pdf",
            "settings.json": original / "settings.json",
            "model.gguf": model,
        }
        manifest = {
            name: {"sha256": digest(path), "size": path.stat().st_size}
            for name, path in files.items()
        }
        archive = work / "filesystem.tar"
        descriptor = os.open(archive, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with (
            os.fdopen(descriptor, "wb") as output,
            tarfile.open(fileobj=output, mode="w") as backup,
        ):
            for name, path in files.items():
                backup.add(path, arcname=name, recursive=False)
        restored.mkdir(mode=0o700)
        with tarfile.open(archive, "r") as backup:
            members = backup.getmembers()
            if {member.name for member in members} != set(manifest) or len(members) != len(
                manifest
            ):
                raise RuntimeError("Unexpected archive members")
            for member in members:
                if not member.isfile() or member.size != manifest[member.name]["size"]:
                    raise RuntimeError("Unexpected archive type or size")
                destination = restored / member.name
                with backup.extractfile(member) as item, destination.open("xb") as output:
                    shutil.copyfileobj(item, output, length=1024 * 1024)
                destination.chmod(0o600)
                if digest(destination) != manifest[member.name]["sha256"]:
                    raise RuntimeError("Restored file differs")
        db_evidence = work / "database.json"
        command = [
            sys.executable,
            str(ROOT / "scripts/verify_restore.py"),
            "--source",
            args.source,
            "--target",
            args.target,
            "--socket",
            str(socket),
            "--bin",
            str(qa / "postgres-root/usr/lib/postgresql/16/bin"),
            "--library-path",
            str(qa / "postgres-root/usr/lib/x86_64-linux-gnu"),
            "--archive-dir",
            str(work),
            "--output",
            str(db_evidence),
        ]
        with (work / "database.log").open("w") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        target = await asyncpg.connect(
            database=args.target, host=str(socket), port=55439, command_timeout=10
        )
        try:
            restored_cipher = await target.fetchval(
                "SELECT config_encrypted FROM broker_accounts WHERE id=$1 AND user_id=$2",
                account,
                owner,
            )
            restored_key = (restored / "vault.key").read_bytes()
            assert Fernet(restored_key).decrypt(restored_cipher.encode()) == plaintext
            try:
                Fernet(Fernet.generate_key()).decrypt(restored_cipher.encode())
            except InvalidToken:
                pass
            else:
                raise RuntimeError("Wrong key unexpectedly decrypted the fixture")
            assert not await target.fetchval(
                "SELECT is_active FROM broker_accounts WHERE id=$1", account
            )
        finally:
            await target.close()
        benchmark = work / "model.json"
        with (work / "model.log").open("w") as log:
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/benchmark_model.py"),
                    "--model",
                    str(restored / "model.gguf"),
                    "--threads",
                    "4",
                    "--structured",
                    "--output",
                    str(benchmark),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=180,
            )
        measured = json.loads(benchmark.read_text())
        if measured["task_correct"] != 3 or measured["sample_count"] != 3:
            raise RuntimeError("Restored model task verification failed")
        if digest(model) != manifest["model.gguf"]["sha256"]:
            raise RuntimeError("Original model changed during backup")
        result = {
            "status": "PASS",
            "timestamp": datetime.now(UTC).isoformat(),
            "tier": "disposable-postgresql-filesystem-vault-model-recovery",
            "database": json.loads(db_evidence.read_text()),
            "files": manifest,
            "vault_decryption": True,
            "wrong_key_rejected": True,
            "restored_model_tasks": 3,
            "restored_model_p95_seconds": measured["p95_nearest_rank_seconds"],
            "work_directory": str(work),
            "source_fixture_records_removed": True,
            "production_data": False,
            "broker_connections": 0,
            "external_orders": 0,
            "limitations": [
                "Synthetic local recovery; off-host backup and production deployment not tested."
            ],
        }
    finally:
        if seeded:
            async with source.transaction():
                await source.execute(
                    "DELETE FROM broker_accounts WHERE id=$1 AND user_id=$2", account, owner
                )
                await source.execute("DELETE FROM users WHERE id=$1", owner)
        await source.close()
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "evidence": str(args.output), "restored_model_tasks": 3}))


if __name__ == "__main__":
    asyncio.run(main())
