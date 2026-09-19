"""Reproducible query-plan fixture; all synthetic rows are rolled back."""

import os
import json
import uuid
import asyncio
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine


async def main():
    url = make_url(os.environ["TEST_DATABASE_URL"])
    marker = os.environ["TEST_DATABASE_DISPOSABLE_TOKEN"]
    root = Path(__file__).resolve().parents[1]
    if (
        not (url.database or "").startswith("test_")
        or url.host
        or Path(url.query.get("host", "")).resolve() != root / ".qa/socket"
        or str(url.query.get("port")) != "55439"
    ):
        raise SystemExit("Only the explicit private checkout acceptance PostgreSQL fixture is allowed")
    engine = create_async_engine(url)
    result = None
    try:
        async with engine.connect() as connection:
            transaction = await connection.begin()
            try:
                assert await connection.scalar(text("SELECT current_database()")) == url.database
                assert await connection.scalar(text("SELECT token FROM public.ia_disposable_marker")) == marker
                await connection.execute(text("SET LOCAL statement_timeout = '30s'"))
                owner = str(uuid.uuid4())
                await connection.execute(
                    text("""INSERT INTO expense_transactions
                    (id,user_id,provider,external_id,account_name,account_key,lifecycle,category_override,
                     merchant,description,amount,currency,transaction_type,category,subcategory,occurred_at,
                     pending,raw_data,created_at,updated_at,synced_at)
                    SELECT md5(:owner || g::text),:owner,'fixture',g::text,'Fixture','fixture','booked',false,
                     'Fixture','Fixture',1,'EUR','expense','other','other',now()-interval '60 days',false,
                     json_build_object('fixture',true),now(),now(),now()-interval '60 days'
                    FROM generate_series(1,6000) g"""),
                    {"owner": owner},
                )
                await connection.execute(text("ANALYZE expense_transactions"))
                plan = (
                    await connection.scalar(
                        text("""EXPLAIN (ANALYZE, FORMAT JSON)
                    SELECT id,synced_at,encode(sha256(convert_to(raw_data::text,'UTF8')),'hex')
                    FROM expense_transactions WHERE user_id=:owner AND synced_at<now()-interval '30 days'
                    AND raw_data::jsonb <> '{}'::jsonb ORDER BY synced_at,id LIMIT 500"""),
                        {"owner": owner},
                    )
                )[0]

                def indexes(node):
                    own = [node["Index Name"]] if "Index Name" in node else []
                    return own + [item for child in node.get("Plans", []) for item in indexes(child)]

                used = indexes(plan["Plan"])
                assert "ix_expense_raw_retention" in used, used
                assert plan["Plan"]["Actual Rows"] == 500
                result = dict(
                    status="PASS",
                    fixture_rows=6000,
                    selected_rows=500,
                    indexes=used,
                    execution_ms=plan["Execution Time"],
                    production_data=False,
                    transaction="rolled_back",
                )
            finally:
                await transaction.rollback()
            # Refresh fixture statistics after rollback, too.
            await connection.execute(text("ANALYZE expense_transactions"))
            await connection.commit()
    finally:
        await engine.dispose()
    output = root / "docs/acceptance/evidence/retention-index-reproducible.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())
