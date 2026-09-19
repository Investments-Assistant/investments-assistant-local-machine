"""Real application model/event contract, with explicitly synthetic scoped tools."""

import sys
import json
import time
import asyncio
from pathlib import Path
import argparse
from datetime import UTC, datetime
import resource
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import Settings
from src.agent.clients import llama_cpp_client
from src.agent.prompts import SYSTEM_PROMPT


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = Settings(
        _env_file=None,
        environment="production",
        llm_model_path=str(args.model),
        llm_native_tool_calling=False,
        agent_max_tokens=128,
        llm_n_threads=4,
        llm_n_gpu_layers=0,
        llm_context_size=4096,
    )
    fixtures = {
        "get_portfolio_summary": {
            "fixture": True,
            "account_id": "synthetic-account",
            "holdings": [
                {
                    "symbol": "FIXTURE",
                    "quantity_exact": "0.004",
                    "price": "100",
                    "currency": "EUR",
                    "value_usd": None,
                }
            ],
            "valuation_status": "partial",
            "broker_connected": False,
            "execution_count": 0,
        },
        "get_latest_news": {
            "fixture": True,
            "articles": [
                {
                    "title": "Synthetic market observation",
                    "source": "fixture",
                    "url": "https://example.invalid/synthetic",
                    "available_at": "2026-09-08T00:00:00Z",
                }
            ],
        },
        "get_market_overview": {
            "fixture": True,
            "as_of": "2026-09-08T00:00:00Z",
            "indices": [],
            "status": "unavailable",
        },
    }
    calls = []

    async def fixture_tool(name, inputs):
        calls.append(name)
        if name not in fixtures:
            raise AssertionError("Unexpected tool in synthetic benchmark")
        return json.dumps(fixtures[name])

    with (
        patch.object(llama_cpp_client, "settings", settings),
        patch.object(llama_cpp_client, "dispatch_tool", fixture_tool),
    ):
        start = time.perf_counter()
        client = llama_cpp_client.LlamaCppClient()
        load = time.perf_counter() - start
        observations = []
        try:
            for prompt, required in [
                (
                    "How is my portfolio? Give a brief evidence-based answer.",
                    {"get_portfolio_summary"},
                ),
                (
                    (
                        "Review latest stored news, market overview and my portfolio exposure. "
                        "Give a brief answer."
                    ),
                    {"get_portfolio_summary", "get_latest_news", "get_market_overview"},
                ),
            ]:
                calls.clear()
                start = time.perf_counter()
                events = [
                    event
                    async for event in client.stream_response(
                        [{"role": "user", "content": prompt}],
                        SYSTEM_PROMPT.format(
                            trading_mode="recommend",
                            auto_max_trade_usd=500,
                            auto_daily_loss_limit_usd=50,
                        ),
                        max_tokens=128,
                    )
                ]
                answer = "\n".join(
                    event.get("text", "") for event in events if event["type"] == "final_answer"
                )
                observations.append(
                    {
                        "required_tools": sorted(required),
                        "observed_tools": list(calls),
                        "scope_correct": set(calls) == required,
                        "latency_seconds": time.perf_counter() - start,
                        "final_answer": answer,
                        "event_types": [event["type"] for event in events],
                        "complete_event_contract": bool(answer) and events[-1]["type"] == "done",
                    }
                )
        finally:
            client._llm.close()
    result = {
        "tier": "real-application-model-synthetic-tools",
        "timestamp": datetime.now(UTC).isoformat(),
        "load_seconds": load,
        "model": args.model.name,
        "peak_process_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "observations": observations,
        "broker_connections": 0,
        "external_orders": 0,
        "status": "PASS"
        if all(o["scope_correct"] and o["complete_event_contract"] for o in observations)
        else "FAIL",
        "limitations": [
            "Tools return synthetic evidence; no external freshness, broker, DB or browser claim.",
            "Final text needs factual review; complete events alone do not prove correctness.",
        ],
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "evidence": str(args.output)}))


if __name__ == "__main__":
    asyncio.run(main())
