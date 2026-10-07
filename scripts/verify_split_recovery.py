"""Restore split evidence in a new disposable DB; never production or live trading.

Run with PYTHONPATH=$PWD and the explicit acceptance marker. Existing targets are
refused. Reuses verify_restore for all table hashes; earlier vault/model evidence
remains separate because those paths are unchanged by split support.
"""

import os
import re
import sys
import json
import asyncio
from decimal import Decimal
from pathlib import Path
import argparse
from datetime import UTC, datetime
import subprocess

from sqlalchemy import text, delete, select
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.models import User
from src.execution.models import (
    ExecutionEvent,
    SimulatorOrder,
    SimulatorAccount,
    SimulatorPosition,
    ValuationSnapshot,
    AccountLedgerEvent,
    SimulatorInstrument,
)
from src.execution.valuation import capture_valuation, period_performance
from src.execution.account_events import record_split, record_dividend_payment
from src.execution.reconciliation import reconcile_account
from tests.integration.simulator_sales_test import owned


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--with-dividend", action="store_true")
    parser.add_argument("--with-valuations", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if (
        Path.cwd() != root
        or not re.fullmatch("test_[a-z0-9_]+", args.target)
        or args.target == "test_acceptance_expenses"
    ):
        raise SystemExit("Run from checkout with new test_ target")
    if not re.fullmatch("[a-z0-9_-]+", args.prefix):
        raise SystemExit("Simple evidence prefix required")
    if os.environ.get("TEST_DATABASE_DISPOSABLE_TOKEN") != "fixture-acceptance-20260909":
        raise SystemExit("Explicit fixture marker required")
    output = root / "docs/acceptance/evidence"
    evidence = output / (args.prefix + "-split.json")
    database_evidence = output / (args.prefix + "-database.json")
    if evidence.exists() or database_evidence.exists():
        raise SystemExit("Existing evidence; inspect prior run")
    socket = root / ".qa/socket"
    url = f"postgresql+asyncpg://lulu@/test_acceptance_expenses?host={socket}&port=55439"
    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids = None
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
            ids, account, _ = await owned(session)
            opening = None
            if args.with_valuations:
                opening = await capture_valuation(session, user_id=ids[0], account_id=ids[1], snapshot_key="opening")
            receipt = await record_split(
                session,
                user_id=ids[0],
                account_id=ids[1],
                instrument_id=ids[2],
                event_key="restore-split",
                numerator=2,
                denominator=1,
                effective_at=datetime.now(UTC),
                source_reference="synthetic-restoration",
                fixture_event=True,
            )
            dividend = None
            if args.with_dividend:
                dividend = await record_dividend_payment(
                    session,
                    user_id=ids[0],
                    account_id=ids[1],
                    instrument_id=ids[2],
                    allocation_id="manual",
                    event_key="restore-dividend",
                    gross_base="10",
                    withholding_base="2.5",
                    currency="EUR",
                    effective_at=datetime.now(UTC),
                    source_reference="synthetic-restoration",
                    fixture_event=True,
                )
            closing, performance_before = None, None
            if args.with_valuations:
                quote = await session.get(SimulatorInstrument, ids[2])
                quote.price, quote.as_of = Decimal(60), datetime.now(UTC)
                await session.flush()
                closing = await capture_valuation(session, user_id=ids[0], account_id=ids[1], snapshot_key="closing")
                performance_before = await period_performance(
                    session,
                    user_id=ids[0],
                    account_id=ids[1],
                    start=datetime.fromisoformat(opening["as_of"]),
                    end=datetime.fromisoformat(closing["as_of"]),
                )
                if performance_before["status"] != "complete" or Decimal(performance_before["portfolio_pnl"]) != (
                    Decimal("7.5") if args.with_dividend else Decimal(0)
                ):
                    raise RuntimeError("SOURCE_PERIOD_PNL_INVALID")
            # Compare persisted source rows with persisted restored rows, not
            # pre-reload Python numeric scales with PostgreSQL NUMERIC scales.
            await session.flush()
            session.expire_all()
            account = await session.get(SimulatorAccount, ids[1])
            before = await reconcile_account(session, account, _include_execution_evidence=True)
            if before["status"] != "consistent":
                raise RuntimeError("SOURCE_NOT_RECONCILED")
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
                str(root / ".qa/split-recovery"),
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
                account = await session.get(SimulatorAccount, ids[1])
                after = await reconcile_account(session, account, _include_execution_evidence=True)
                position = await session.scalar(select(SimulatorPosition).where(SimulatorPosition.account_id == ids[1]))
                if (
                    after != before
                    or position.quantity != 4
                    or position.cost_basis != 200
                    or account.cash != (Decimal("807.5") if args.with_dividend else 800)
                    or Decimal(after["dividend_gross"]) != (10 if args.with_dividend else 0)
                    or Decimal(after["dividend_withholding"]) != (Decimal("2.5") if args.with_dividend else 0)
                    or not account.halted
                    or account.halt_reason != "CORPORATE_ACTION_REVIEW_REQUIRED"
                ):
                    raise RuntimeError("RESTORED_SPLIT_INVARIANT_FAILED")
                if args.with_valuations:
                    performance_after = await period_performance(
                        session,
                        user_id=ids[0],
                        account_id=ids[1],
                        start=datetime.fromisoformat(opening["as_of"]),
                        end=datetime.fromisoformat(closing["as_of"]),
                    )
                    if performance_after != performance_before:
                        raise RuntimeError("RESTORED_PERIOD_VALUATION_MISMATCH")
                evidence.write_text(
                    json.dumps(
                        dict(
                            status="PASS",
                            revision="0018_job_lease_clock",
                            reconciliation_hash=after["evidence_sha256"],
                            split_receipt=receipt["event_id"],
                            dividend_receipt=dividend["event_id"] if dividend else None,
                            dividend_income_verified=args.with_dividend,
                            exact_period_valuation_verified=args.with_valuations,
                            split_quantity_basis_cash_and_halt_preserved=True,
                            production_data=False,
                            broker_connections=0,
                        ),
                        indent=2,
                    )
                    + "\n"
                )
        finally:
            await restored.dispose()
    finally:
        if ids is not None:
            async with factory.begin() as session:
                orders = select(SimulatorOrder.id).where(SimulatorOrder.account_id == ids[1])
                await session.execute(delete(ExecutionEvent).where(ExecutionEvent.order_id.in_(orders)))
                for model in (
                    ValuationSnapshot,
                    AccountLedgerEvent,
                    SimulatorOrder,
                    SimulatorPosition,
                    SimulatorInstrument,
                ):
                    await session.execute(delete(model).where(model.account_id == ids[1]))
                await session.execute(delete(SimulatorAccount).where(SimulatorAccount.id == ids[1]))
                await session.execute(delete(User).where(User.id == ids[0]))
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
