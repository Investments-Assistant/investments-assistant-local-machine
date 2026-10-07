"""Operator preview/confirmation for old unreferenced PDFs in configured storage."""

import sys
import json
import asyncio
from pathlib import Path
import argparse
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import settings
from src.db.database import engine, async_session
from src.operations.report_orphans import cleanup_orphans


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=datetime.fromisoformat, required=True)
    parser.add_argument("--confirm-sha256")
    parser.add_argument("--limit", type=int, default=10000)
    args = parser.parse_args()
    try:
        async with asyncio.timeout(15), async_session() as session, session.begin():
            result = await cleanup_orphans(session, settings.reports_dir, before=args.before,
                                          confirm_sha256=args.confirm_sha256, limit=args.limit)
    except Exception as exc:
        # DB URLs, filesystem paths, titles and driver diagnostics stay private.
        result = {"status": "refused", "reason": type(exc).__name__}
    finally:
        await engine.dispose()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"preview", "complete"} else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
