"""Preview or explicitly confirm cleanup of abandoned local PDF render files."""

import sys
import json
from pathlib import Path
import argparse
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.operations.report_cleanup import cleanup_temporaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, required=True)
    parser.add_argument("--before", type=datetime.fromisoformat, required=True)
    parser.add_argument("--confirm-sha256")
    parser.add_argument("--limit", type=int, default=10000)
    args = parser.parse_args()
    try:
        result = cleanup_temporaries(
            args.reports_dir, before=args.before, confirm_sha256=args.confirm_sha256, limit=args.limit
        )
    except (OSError, ValueError) as exc:
        result = {"status": "refused", "reason": type(exc).__name__}
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["status"] in {"preview", "complete"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
