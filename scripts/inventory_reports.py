"""Read-only report file inventory. Run as an operator, never as a model tool."""

import sys
import json
import asyncio
from pathlib import Path
import argparse

from sqlalchemy import text, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings
from src.db.models import Report
from src.db.database import engine, async_session
from src.operations.report_inventory import inventory_reports


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10000)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100000:
        parser.error("limit must be between 1 and 100000")
    try:
        async with asyncio.timeout(15), async_session() as session, session.begin():
            await session.execute(text("SET TRANSACTION READ ONLY"))
            await session.execute(text("SET LOCAL statement_timeout = '5s'"))
            # All owners, including quarantined legacy reports, retain files.
            # Fetch no HTML, titles, account identifiers, or financial evidence.
            references = list(await session.scalars(
                select(Report.pdf_path).where(Report.pdf_path.is_not(None)).order_by(Report.id).limit(args.limit + 1)
            ))
        result = inventory_reports(
            Path(settings.reports_dir), references, reference_limit=args.limit, file_limit=args.limit
        )
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0 if result["status"] == "observed" else 2
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
