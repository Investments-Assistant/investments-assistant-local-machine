"""Verify restored owner-approved removal and re-import suppression on fixtures only."""

import os
import re
import sys
import json
import asyncio
from pathlib import Path
import argparse
import subprocess

from sqlalchemy import text, delete, select
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.models import User, ExpenseTransaction
from src.expenses.models import ExpenseAudit, ExpenseRetirement
from src.expenses.persistence import upsert_transaction
from src.expenses.history_retention import history_plan, purge_history
from tests.integration.expense_retention_test import seed


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--pending-resolution", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if (
        Path.cwd() != root
        or not re.fullmatch("test_[a-z0-9_]+", args.target)
        or args.target == "test_acceptance_expenses"
        or not re.fullmatch("[a-z0-9_-]+", args.prefix)
        or os.environ.get("TEST_DATABASE_DISPOSABLE_TOKEN") != "fixture-acceptance-20260909"
    ):
        raise SystemExit("Checkout, new test target and explicit fixture marker required")
    output = root / "docs/acceptance/evidence"
    evidence = output / (args.prefix + "-retirement.json")
    database_evidence = output / (args.prefix + "-database.json")
    if evidence.exists() or database_evidence.exists():
        raise SystemExit("Evidence already exists; inspect before retry")
    socket = root / ".qa/socket"
    url = f"postgresql+asyncpg://lulu@/test_acceptance_expenses?host={socket}&port=55439"
    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    owners = []
    try:
        async with factory.begin() as session:
            if (
                await session.scalar(text("SELECT current_database()")) != "test_acceptance_expenses"
                or await session.scalar(text("SELECT token FROM public.ia_disposable_marker"))
                != "fixture-acceptance-20260909"
                or await session.scalar(text("SELECT version_num FROM alembic_version")) != "0018_job_lease_clock"
            ):
                raise RuntimeError("DISPOSABLE_IDENTITY_REQUIRED")
            if await session.scalar(text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": args.target}):
                raise SystemExit("Target exists; do not overwrite")
            owners, rows, policy, now = await seed(session)
            if args.pending_resolution:
                rows[0].pending, rows[0].lifecycle = True, "pending"
                rows[0].category, rows[0].subcategory = "health", "pharmacy"
                rows[1].category_override = False
                await session.flush()
            item = {
                column.name: getattr(rows[0], column.name)
                for column in ExpenseTransaction.__table__.columns
                if column.name not in {"id", "user_id", "created_at", "updated_at", "synced_at"}
            }
            removed_ids = [rows[0].id] if args.pending_resolution else [row.id for row in rows[:2]]
            booked_before = None
            if args.pending_resolution:
                from src.expenses.reconciliation import reconcile_pending, reconciliation_plan
                from src.expenses.history_retention import export_row

                pair = dict(user_id=owners[0], pending_id=rows[0].id, booked_id=rows[1].id, as_of=now, now=now)
                plan, _, _, _ = await reconciliation_plan(session, **pair)
                result = await reconcile_pending(session, **pair, expected_plan=plan["plan_sha256"],
                                                 export_sha256=plan["export_sha256"])
                if result["removed_pending"] != 1 or result["booked_amount_changed"]:
                    raise RuntimeError("SOURCE_RESOLUTION_NOT_VERIFIED")
                await session.refresh(rows[1])
                booked_before = export_row(rows[1])
                audit_before = (await session.scalar(select(ExpenseAudit).where(
                    ExpenseAudit.transaction_id == removed_ids[0], ExpenseAudit.action == "pending_reconciled"
                ))).changes
            else:
                plan, _ = await history_plan(session, user_id=owners[0], policy=policy, now=now)
                result = await purge_history(
                    session, user_id=owners[0], policy=policy, expected_plan=plan["plan_sha256"],
                    export_sha256=plan["export_sha256"], now=now,
                )
                if result["removed_transactions"] != 2:
                    raise RuntimeError("SOURCE_PURGE_NOT_VERIFIED")
        subprocess.run(
            [
                sys.executable,
                "scripts/verify_restore.py",
                "--source",
                "test_acceptance_expenses",
                "--target",
                args.target,
                "--socket",
                str(socket),
                "--bin",
                str(root / ".qa/postgres-root/usr/lib/postgresql/16/bin"),
                "--library-path",
                str(root / ".qa/postgres-root/usr/lib/x86_64-linux-gnu"),
                "--archive-dir",
                str(root / ".qa/expense-retirement-recovery"),
                "--output",
                str(database_evidence),
            ],
            check=True,
        )
        restored = create_async_engine(
            url.replace("/test_acceptance_expenses?", f"/{args.target}?"), poolclass=NullPool
        )
        try:
            async with async_sessionmaker(restored)() as session:
                if await session.scalar(text("SELECT current_database()")) != args.target:
                    raise RuntimeError("RESTORE_IDENTITY_MISMATCH")
                if await session.scalar(select(ExpenseTransaction.id).where(ExpenseTransaction.id.in_(removed_ids))):
                    raise RuntimeError("REMOVED_HISTORY_REAPPEARED")
                tombstones = (
                    await session.scalars(select(ExpenseRetirement).where(ExpenseRetirement.user_id == owners[0]))
                ).all()
                if (len(tombstones) != len(removed_ids)
                        or any(row.plan_sha256 != plan["plan_sha256"] for row in tombstones)):
                    raise RuntimeError("RETIREMENT_EVIDENCE_MISMATCH")
                if await upsert_transaction(session, user_id=owners[0], item=item, received_at=now) is not None:
                    raise RuntimeError("RESTORED_IMPORT_NOT_SUPPRESSED")
                if args.pending_resolution:
                    booked_after = await session.get(ExpenseTransaction, booked_before["id"])
                    audit_after = await session.scalar(select(ExpenseAudit).where(
                        ExpenseAudit.transaction_id == removed_ids[0], ExpenseAudit.action == "pending_reconciled"))
                    if (booked_after is None or export_row(booked_after) != booked_before
                            or audit_after is None or audit_after.changes != audit_before):
                        raise RuntimeError("RESTORED_RESOLUTION_EVIDENCE_MISMATCH")
                await session.rollback()
                evidence.write_text(
                    json.dumps(
                        dict(
                            status="PASS",
                            revision="0018_job_lease_clock",
                            removed_rows_absent=True,
                            retirement_hashes_preserved=len(removed_ids),
                            pending_resolution_verified=args.pending_resolution,
                            reimport_suppressed=True,
                            production_data=False,
                            bank_connections=0,
                        ),
                        indent=2,
                    )
                    + "\n"
                )
        finally:
            await restored.dispose()
    finally:
        if owners:
            async with factory.begin() as session:
                for model in (ExpenseTransaction, ExpenseAudit, ExpenseRetirement):
                    await session.execute(delete(model).where(model.user_id.in_(owners)))
                await session.execute(delete(User).where(User.id.in_(owners)))
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
