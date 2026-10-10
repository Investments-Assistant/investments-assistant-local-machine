"""Real native inference and authenticated ASGI/PostgreSQL controls in one process.

Synthetic account only, no network listener/providers/brokers. This short benchmark
does not replace Docker, physical sleep, production ingress or 24-hour observation.
"""

import os
import sys
import json
import math
import time
import uuid
import asyncio
from pathlib import Path
import argparse
import resource
from contextlib import suppress

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def run(args):
    from scripts.soak_acceptance import verify_database

    await verify_database(os.environ["TEST_DATABASE_URL"], os.environ["TEST_DATABASE_DISPOSABLE_TOKEN"])
    model = args.model.resolve()
    if not model.is_file() or model.suffix != ".gguf" or not model.is_relative_to(ROOT / "models"):
        raise ValueError("Existing checkout GGUF required; no downloads")
    if args.output.exists():
        raise ValueError("Output already exists; inspect before retry")
    username = "contention-" + uuid.uuid4().hex
    os.environ["BROWSER_FIXTURE_USERS"] = username
    from tests.e2e import fixture_server
    from src.agent.clients import llama_cpp_client

    settings = fixture_server.config.settings
    settings.llm_model_path = str(model)
    settings.llm_n_threads = 4
    settings.llm_n_gpu_layers = 0
    settings.llm_context_size = 4096
    settings.agent_max_tokens = 768
    llama_cpp_client.settings = settings
    started = time.perf_counter()
    client = llama_cpp_client.LlamaCppClient()
    load_seconds = time.perf_counter() - started
    samples, rounds = [], []
    result = dict(tier="same-process native model and real authenticated ASGI/PostgreSQL halt",
                  status="RUNNING", model=model.name, threads=4, output_limit=768,
                  load_seconds=load_seconds, halt_p95_budget_ms=250, minimum_overlap_samples=20,
                  broker_connections=0, external_orders=0, samples=samples, rounds=rounds)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    task = None
    try:
        async with (
            fixture_server.lifespan(fixture_server.app),
            httpx.AsyncClient(transport=httpx.ASGITransport(app=fixture_server.app),
                              base_url="http://127.0.0.1", timeout=5) as http,
        ):
            login = await http.post("/api/auth/login", json={
                "username": username, "password": "fixture-browser-password"})
            login.raise_for_status()
            http.headers["X-CSRF-Token"] = http.cookies["ia_csrf"]
            fixture = await http.post("/api/simulator/fixtures")
            fixture.raise_for_status()
            account = fixture.json()["account_id"]

            async def infer():
                began = time.perf_counter()
                events = [event async for event in client.stream_response(
                    [{"role": "user",
                      "content": "Explain decimal arithmetic and rounding with ten simple examples."}],
                    "NO_TOOL_CALLING. Explain only arithmetic. No tools or financial advice.", max_tokens=768)]
                answers = [e.get("text", "") for e in events if e["type"] == "final_answer"]
                return dict(seconds=time.perf_counter() - began, event_types=[e["type"] for e in events],
                            final_answer_present=any(answers),
                            tool_events=sum(e["type"] in {"tool_call", "tool_result"} for e in events))

            for number in range(3):
                task = asyncio.create_task(infer())
                while not task.done():
                    before = client._native_lock.locked()
                    began = time.perf_counter()
                    response = await http.post(f"/api/simulator/accounts/{account}/halt")
                    elapsed = (time.perf_counter() - began) * 1000
                    after = client._native_lock.locked()
                    response.raise_for_status()
                    if response.json().get("halted") is not True:
                        raise RuntimeError("HALT_NOT_PERSISTED")
                    samples.append(dict(round=number + 1, milliseconds=elapsed,
                                        native_before=before, native_after=after))
                    await asyncio.sleep(0.05)
                rounds.append(await task)
                snapshot = await http.get(f"/api/simulator/accounts/{account}")
                snapshot.raise_for_status()
                if snapshot.json().get("halted") is not True:
                    raise RuntimeError("HALT_STATE_LOST")
                args.output.write_text(json.dumps(result, indent=2) + "\n")
        overlap = sorted(s["milliseconds"] for s in samples if s["native_before"] and s["native_after"])
        p95 = overlap[math.ceil(len(overlap) * .95) - 1] if overlap else None
        result.update(overlap_samples=len(overlap), halt_p95_ms=p95,
                      peak_process_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
                      status="PASS" if len(overlap) >= 20 and p95 <= 250
                      and all(r["final_answer_present"] and r["event_types"][-1] == "done"
                              and "error" not in r["event_types"]
                              and r["tool_events"] == 0 for r in rounds) else "FAIL")
    except BaseException:
        result["status"] = "FAILED_OR_INTERRUPTED"
        raise
    finally:
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        # Await native ownership before closing the model after cancellation.
        while client._native_lock.locked():
            await asyncio.sleep(0.05)
        client._llm.close()
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("status", "overlap_samples", "halt_p95_ms")}))
    return result["status"] == "PASS"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    raise SystemExit(0 if asyncio.run(run(options)) else 1)
