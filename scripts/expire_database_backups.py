"""Preview or explicitly confirm expiry of verified local PostgreSQL test archives."""

import sys
import json
from pathlib import Path
import argparse
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.operations.backup_retention import expire_backups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, action="append", required=True)
    parser.add_argument("--before", type=datetime.fromisoformat, required=True)
    parser.add_argument("--keep", type=int, required=True)
    parser.add_argument("--confirm-sha256")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--byte-limit", type=int, default=10 * 1024**3)
    args = parser.parse_args()
    try:
        result = expire_backups(args.archive_dir, args.evidence, before=args.before, keep=args.keep,
                                confirm_sha256=args.confirm_sha256, limit=args.limit, byte_limit=args.byte_limit)
    except Exception as exc:
        result = {"status": "refused", "reason": type(exc).__name__}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] in {"preview", "complete"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
