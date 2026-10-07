"""Restore a retained synthetic decision alongside the full vault/PDF/model fixture.

Uses only the fixed, positively marked acceptance source. Refuses an existing
new target. Requires local test dependencies and the existing model; no download.
"""

import os
import re
import json
import asyncio
from decimal import Decimal
from pathlib import Path
import argparse
from datetime import UTC, datetime
import subprocess

from sqlalchemy import text, delete
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.db.models import User
from src.execution.models import (
    SimulatorAccount,
    SimulatorMandate,
    StrategyDecision,
    AccountLedgerEvent,
    SimulatorInstrument,
)
from src.execution.policy import digest
from src.execution.autonomy import run_tick
from src.execution.account_events import record_cash_flow
from src.execution.reconciliation import reconcile_account
from tests.integration.execution_test import seed
from tests.integration.strategy_sales_test import band


async def main():
    root = Path(__file__).resolve().parents[1]
    if Path.cwd() != root:
        raise SystemExit("Run from this checkout root")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--output-prefix", required=True)
    options = parser.parse_args()
    if os.environ.get("TEST_DATABASE_DISPOSABLE_TOKEN") != "fixture-acceptance-20260909":
        raise SystemExit("Explicit acceptance disposable token required")
    target = options.target
    if not re.fullmatch(r"test_[a-z0-9_]+", target) or target == "test_acceptance_expenses":
        raise SystemExit("A new disposable target name is required")
    if not re.fullmatch(r"[a-z0-9_-]+", options.output_prefix):
        raise SystemExit("Use a simple evidence filename prefix")
    output = root / "docs/acceptance/evidence"
    full_evidence = output / (options.output_prefix + "-full.json")
    decision_evidence = output / (options.output_prefix + "-decision.json")
    if full_evidence.exists() or decision_evidence.exists():
        raise SystemExit("Evidence destination exists; inspect the prior run before retrying")
    url = f"postgresql+asyncpg://lulu@/test_acceptance_expenses?host={root}/.qa/socket&port=55439"
    engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids = None
    try:
        async with factory.begin() as session:
            database = await session.scalar(text("SELECT current_database()"))
            token = await session.scalar(text("SELECT token FROM public.ia_disposable_marker"))
            revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
            if (
                database != "test_acceptance_expenses"
                or token != "fixture-acceptance-20260909"
                or revision != "0018_job_lease_clock"
            ):
                raise SystemExit("Source identity, marker or revision mismatch")
            assert not await session.scalar(text("SELECT 1 FROM pg_database WHERE datname=:name"), {"name": target})
            assert not (root / ".qa" / ("recovery-" + target)).exists()
            ids = await seed(session)
            args = await band(session, ids)
            quote = await session.get(SimulatorInstrument, ids[2])
            now = datetime.now(UTC)
            quote.price, quote.as_of = Decimal("105"), now
            result = await run_tick(session, **args, tick_id="restore-no-trade", now=now)
            decision_id = result["decision_id"]
            decision = await session.get(StrategyDecision, decision_id)
            evidence_hash = decision.evidence_hash
            flow = await record_cash_flow(
                session,
                user_id=ids[0],
                account_id=ids[1],
                event_key="restore-flow",
                amount_base="123.45",
                currency="EUR",
                effective_at=datetime.now(UTC),
                source_reference="synthetic-restore-receipt",
                fixture_event=True,
            )
            flow_id = flow["event_id"]
            flow_event = await session.get(AccountLedgerEvent, flow_id)
            flow_hash, flow_sequence = flow_event.evidence_hash, flow_event.ledger_sequence
        subprocess.run(
            [
                str(root / ".venv/bin/python"),
                "scripts/verify_fixture_recovery.py",
                "--source",
                "test_acceptance_expenses",
                "--target",
                target,
                "--model",
                "models/qwen2.5-1.5b-instruct-q4_k_m.gguf",
                "--output",
                str(full_evidence),
            ],
            check=True,
            env=os.environ.copy(),
        )
        restored_engine = create_async_engine(
            url.replace("/test_acceptance_expenses?", f"/{target}?"), poolclass=NullPool
        )
        try:
            async with async_sessionmaker(restored_engine)() as session:
                assert await session.scalar(text("SELECT current_database()")) == target
                assert await session.scalar(text("SELECT version_num FROM alembic_version")) == "0018_job_lease_clock"
                retained = await session.get(StrategyDecision, decision_id)
                assert retained.evidence_hash == evidence_hash == digest(retained.evidence)
                assert retained.evidence["result"]["status"] == "no_trade"
                assert retained.evidence["result"]["reason"] == "PRICE_INSIDE_BAND"
                assert Decimal(retained.evidence["instrument"]["price"]) == 105
                flow_event = await session.get(AccountLedgerEvent, flow_id)
                assert flow_event.evidence_hash == flow_hash and flow_event.ledger_sequence == flow_sequence
                account = await session.get(SimulatorAccount, ids[1])
                checked = await reconcile_account(session, account)
                assert checked["status"] == "consistent" and Decimal(checked["net_external_flows"]) == Decimal("123.45")
                continuation = await record_cash_flow(
                    session,
                    user_id=ids[0],
                    account_id=ids[1],
                    event_key="restored-continuation",
                    amount_base="1",
                    currency="EUR",
                    effective_at=datetime.now(UTC),
                    source_reference="synthetic-restored-receipt",
                    fixture_event=True,
                )
                later = await session.get(AccountLedgerEvent, continuation["event_id"])
                assert later.ledger_sequence > flow_sequence
                assert (await reconcile_account(session, account))["status"] == "consistent"
                # This proof is rolled back when the read-verification session closes.
            decision_evidence.write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "revision": "0018_job_lease_clock",
                        "decision_evidence_hash": evidence_hash,
                        "no_trade_and_original_quote_preserved": True,
                        "cash_flow_hash_and_reconciliation_preserved": True,
                        "shared_sequence_continuation_verified": True,
                        "scope": "synthetic disposable database restore",
                        "broker_connections": 0,
                    },
                    indent=2,
                )
                + "\n"
            )
        finally:
            await restored_engine.dispose()
    finally:
        if ids is not None:
            async with factory.begin() as session:
                for model in (AccountLedgerEvent, StrategyDecision, SimulatorMandate, SimulatorInstrument):
                    await session.execute(delete(model).where(model.account_id == ids[1]))
                await session.execute(delete(SimulatorAccount).where(SimulatorAccount.id == ids[1]))
                await session.execute(delete(User).where(User.id == ids[0]))
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
