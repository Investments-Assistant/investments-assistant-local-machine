"""Recompute a saved portfolio replay without network, models or broker adapters."""

import sys
import json
from decimal import Decimal
from pathlib import Path
import argparse
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.research.replay import Bar, Costs  # noqa: E402
from src.research.portfolio import replay_portfolio  # noqa: E402


def reproduce(evidence):
    config = evidence["configuration"]
    numeric = {"open", "close", "volume", "fx_to_base", "split", "dividend"}
    temporal = {"open_at", "close_at", "fx_as_of"}
    series = {
        symbol: [
            Bar(
                **{
                    key: Decimal(value)
                    if key in numeric
                    else datetime.fromisoformat(value)
                    if key in temporal
                    else value
                    for key, value in row.items()
                }
            )
            for row in bars
        ]
        for symbol, bars in evidence["bars"].items()
    }
    default = Costs()
    costs = Costs(
        **{
            key: Decimal(value) if isinstance(getattr(default, key), Decimal) else int(value)
            for key, value in config["costs"].items()
        }
    )
    result = replay_portfolio(
        series,
        capital=Decimal(config["capital"]),
        base_currency=config["base_currency"],
        strategy=config["strategy"],
        params=config["params"],
        costs=costs,
        source=evidence["result"]["source"],
    )
    if result["input_hash"] != evidence["result"]["input_hash"]:
        raise ValueError("Evidence/code/parameters hash mismatch")
    actual = json.loads(json.dumps(result, default=str))
    if actual != evidence["result"]:
        raise ValueError("Replay output differs from recorded evidence")
    return {
        "status": "PASS",
        "input_hash": result["input_hash"],
        "final_value": result["final_value"],
        "network_calls": 0,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args()
    if args.evidence.stat().st_size > 64 * 1024 * 1024:
        raise SystemExit("Evidence exceeds64MiB bounded replay input")
    print(json.dumps(reproduce(json.loads(args.evidence.read_text()))))
