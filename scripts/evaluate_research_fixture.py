"""Reproduce a fixed, chronological synthetic research comparison. No data fetches."""

import sys
import json
import math
from decimal import Decimal
import hashlib
from pathlib import Path
import argparse
from datetime import UTC, datetime, timedelta
from dataclasses import asdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.research.replay import Bar, Costs, NewsEvidence, replay, canonical_hash


def fixture(count):
    bars, news = [], []
    day = datetime(2025, 1, 2, 9, tzinfo=UTC)
    for i in range(count):
        while day.weekday() > 4:
            day += timedelta(days=1)
        # The data is explicitly synthetic, with deterministic gaps and cycles.
        price = Decimal(str(round(100 + 0.025 * i + 7 * math.sin(i / 9), 4)))
        close = price * Decimal(str(round(1 + 0.002 * math.sin(i / 3), 6)))
        bars.append(
            Bar(
                "FIXTURE",
                day,
                day + timedelta(hours=8),
                price,
                close,
                Decimal(100000),
                "EUR",
                Decimal(1),
                day,
            )
        )
        if i % 5 == 0:
            news.append(
                NewsEvidence(
                    canonical_hash({"fixture_article": i}),
                    "FIXTURE",
                    day,
                    day + timedelta(days=1),
                    Decimal(1 if i % 10 == 0 else -1),
                    "synthetic-news",
                    "synthetic-score-v1-not-an-LLM",
                )
            )
        day += timedelta(days=1)
    return bars, news


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--plan", type=Path, default=Path("docs/acceptance/research-fixture-plan.json")
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan_bytes = args.plan.read_bytes()
    plan = json.loads(plan_bytes)
    if args.output.exists():
        raise SystemExit("Preserve the existing result; choose a new evidence file for a rerun")
    costs = Costs(**{key: Decimal(value) for key, value in plan["costs"].items()})
    bars, news = fixture(sum(plan["split_sessions"].values()))
    results, offset = {}, 0
    for split in ("train", "validation", "test"):
        count = plan["split_sessions"][split]
        sample = bars[offset : offset + count]
        offset += count
        # Each independent split starts with cash; no holdings/selection leak
        # from train into holdout. Parameters are fixed by the predeclared plan.
        results[split] = {
            strategy: replay(
                sample,
                capital=Decimal(plan["capital"]),
                base_currency=plan["base_currency"],
                strategy=strategy,
                costs=costs,
                lookback=plan["lookback_sessions"],
                news=news if strategy == "momentum_news" else [],
                source_version="synthetic-price-series-v1",
                fixture=True,
            )
            for strategy in plan["strategies"]
        }
    holdout = results["test"]
    criteria = plan["illustrative_economic_criteria"]
    assessment = {}
    for strategy in ("momentum", "momentum_news"):
        result = holdout[strategy]
        assessment[strategy] = {
            "net_excess_vs_buy_hold_pct": result["total_return_pct"]
            - holdout["buy_and_hold"]["total_return_pct"],
            "sample_sufficient": result["exit_sample_size"] >= criteria["minimum_closed_trades"],
            "drawdown_within_fixture_limit": abs(result["max_drawdown_pct"])
            <= criteria["maximum_drawdown_pct"],
            "operational_rejections": len(result["rejected"]),
        }
    output = {
        "experiment": plan["experiment"],
        "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "engine_sha256": hashlib.sha256(Path("src/research/replay.py").read_bytes()).hexdigest(),
        "data_sha256": canonical_hash([asdict(bar) for bar in bars]),
        "plan": plan,
        "results": results,
        "holdout_assessment": assessment,
        "news_assistance_delta_net_return_pct": holdout["momentum_news"]["total_return_pct"]
        - holdout["momentum"]["total_return_pct"],
        "strategy_decision": "INSUFFICIENT EVIDENCE",
        "live_decision": "NO-GO",
        "limitations": [
            "Synthetic prices and scores cannot demonstrate investment edge.",
            (
                "One instrument; survivor/delisting coverage and actual "
                "exchange calendar not established."
            ),
            "Daily bars cannot evaluate immediate-news execution or intraday spread/latency.",
            (
                "252-session volatility/zero-risk-free Sharpe; small exit samples "
                "and no confidence guarantee."
            ),
            (
                "Fixture criteria are unapproved for real deployment. "
                "Forward observation remains required."
            ),
        ],
        "broker_connections": 0,
        "external_orders": 0,
    }
    with args.output.open("x") as destination:
        destination.write(json.dumps(output, default=str, indent=2) + "\n")
    print(
        json.dumps(
            {
                "strategy_decision": output["strategy_decision"],
                "live_decision": "NO-GO",
                "evidence": str(args.output),
                "plan_sha256": output["plan_sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
