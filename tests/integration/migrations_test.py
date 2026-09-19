"""Upgrade the frozen audit schema inside a disposable transactional schema."""

import uuid
from pathlib import Path
import importlib.util

import pytest
from sqlalchemy import text
from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.mark.integration
async def test_reviewed_schema_upgrades_without_assigning_unknown_owner(integration_engine):
    async with integration_engine.connect() as connection:
        transaction = await connection.begin()
        schema = "upgrade_" + uuid.uuid4().hex
        try:
            await connection.execute(text(f"CREATE SCHEMA {schema}"))
            await connection.execute(text(f"SET LOCAL search_path TO {schema}"))

            def upgrade(sync_connection, name):
                path = Path("migrations/versions") / name
                spec = importlib.util.spec_from_file_location(name, path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                with Operations.context(MigrationContext.configure(sync_connection)):
                    module.upgrade()

            await connection.run_sync(upgrade, "0001_reviewed.py")
            await connection.execute(
                text("""INSERT INTO trades
                (id, user_id, broker, symbol, side, quantity, price, order_type, status, mode)
                VALUES ('fixture', NULL, 'ibkr', 'SPYL', 'buy', 0.004, 100, 'limit',
                        'pending', 'simulated')""")
            )
            await connection.run_sync(upgrade, "0002_precision.py")
            await connection.execute(
                text("""INSERT INTO reports
                (id, title, period_start, period_end, html_content)
                VALUES ('legacy-report', 'Fixture', now(), now(), '<p>Historical fixture</p>')""")
            )
            await connection.execute(
                text(
                    """INSERT INTO news_articles
                    (id, title, summary, source, url, sentiment_label, sentiment_score, tags)
                    VALUES ('legacy-mail', 'Private fixture', '', 'Newsletter',
                            'email://fixture/one', 'neutral', 0, '[]'),
                           ('public', 'Public fixture', '', 'Feed',
                            'https://example.org/one', 'neutral', 0, '[]')"""
                )
            )
            for version in [
                "0003_simulator.py",
                "0004_operations.py",
                "0005_sessions.py",
                "0006_news_privacy.py",
                "0007_news_evidence.py",
                "0008_mandates.py",
                "0009_expense_audit.py",
                "0010_report_status.py",
                "0011_retention_index.py",
                "0012_broker_observations.py",
            ]:
                await connection.run_sync(upgrade, version)
            ownership = (
                await connection.execute(text("SELECT id, user_id, visibility FROM news_articles ORDER BY id"))
            ).all()
            assert ownership == [("legacy-mail", None, "quarantined"), ("public", None, "public")]
            result = (
                await connection.execute(
                    text("SELECT user_id, quantity, price FROM trades WHERE id = :id"),
                    {"id": "fixture"},
                )
            ).one()
            assert result.user_id is None
            assert str(result.quantity) == "0.0040000000"
            assert str(result.price) == "100.0000000000"
            columns = (
                (
                    await connection.execute(
                        text("""SELECT column_name FROM information_schema.columns
                WHERE table_schema = :schema AND table_name = 'expense_transactions'"""),
                        {"schema": schema},
                    )
                )
                .scalars()
                .all()
            )
            assert {"account_key", "lifecycle", "category_override"} <= set(columns)
            legacy = (
                await connection.execute(
                    text("SELECT user_id, generation_status, generation_errors FROM reports WHERE id = 'legacy-report'")
                )
            ).one()
            assert legacy.user_id is None
            assert legacy.generation_status == "unverified"
            assert legacy.generation_errors == []
            definition = await connection.scalar(
                text(
                    "SELECT indexdef FROM pg_indexes WHERE schemaname = :schema "
                    "AND indexname = 'ix_expense_raw_retention'"
                ),
                {"schema": schema},
            )
            assert "(user_id, synced_at, id)" in definition and "WHERE" in definition
        finally:
            await transaction.rollback()
