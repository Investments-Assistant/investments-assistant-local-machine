"""Operator-only preview/confirmation of one expired news source's retained text."""

import sys
import json
import asyncio
from pathlib import Path
import argparse
from datetime import UTC, datetime

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db.database import engine, async_session
from src.news.cleanup import cleanup_plan, remove_expired_content
from src.execution.policy import PolicyDenied


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-identity", required=True)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--public", action="store_true")
    scope.add_argument("--private-owner")
    parser.add_argument("--as-of", type=datetime.fromisoformat)
    parser.add_argument("--confirm-sha256")
    args = parser.parse_args()
    if args.confirm_sha256 and not args.as_of:
        parser.error("confirmation requires the preview's exact --as-of timestamp")
    try:
        async with asyncio.timeout(15), async_session.begin() as session:
            if not args.confirm_sha256:
                await session.execute(text("SET TRANSACTION READ ONLY"))
            await session.execute(text("SET LOCAL statement_timeout = '5s'"))
            await session.execute(text("SET LOCAL lock_timeout = '2s'"))
            arguments = {
                "identity": args.source_identity, "owner_user_id": args.private_owner,
                "as_of": args.as_of or datetime.now(UTC),
            }
            if args.confirm_sha256:
                result = await remove_expired_content(session, **arguments, expected_plan=args.confirm_sha256)
            else:
                result, _, _ = await cleanup_plan(session, **arguments)
                result["status"] = "preview"
        # Report completion only after commit; no raw text, URLs or account IDs.
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "reason_code": exc.code if isinstance(exc, PolicyDenied)
                          else "NEWS_CLEANUP_UNAVAILABLE"}))
        return 2
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
