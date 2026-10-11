"""Observe host wall-clock regressions without changing time or OS settings."""

import json
import time
from pathlib import Path
import argparse
from datetime import UTC, datetime


def observe(seconds):
    start = time.monotonic_ns()
    last_wall, last_mono = time.time_ns(), start
    regressions = []
    samples = 0
    while time.monotonic_ns() - start < seconds * 1_000_000_000:
        time.sleep(0.01)
        wall, mono = time.time_ns(), time.monotonic_ns()
        if wall < last_wall:
            regressions.append(
                {
                    "elapsed_seconds": (mono - start) / 1e9,
                    "wall_delta_seconds": (wall - last_wall) / 1e9,
                    "monotonic_delta_seconds": (mono - last_mono) / 1e9,
                }
            )
        samples += 1
        last_wall, last_mono = wall, mono
    return {
        "status": "CLOCK_REGRESSION" if regressions else "NO_REGRESSION_OBSERVED",
        "finished_at": datetime.now(UTC).isoformat(),
        "observed_seconds": (last_mono - start) / 1e9,
        "samples": samples,
        "regressions": regressions,
        "scope": "Bounded observation only; not proof of future stability or wall-clock accuracy",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 3600:
        parser.error("seconds must be between 1 and 3600")
    # Reserve the report before sampling, so an old result cannot be overwritten.
    with args.output.open("x") as report:
        result = observe(args.seconds)
        json.dump(result, report, indent=2)
        report.write("\n")
    print(result["status"])
    return int(bool(result["regressions"]))


if __name__ == "__main__":
    raise SystemExit(main())
