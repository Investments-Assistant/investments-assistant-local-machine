# Host and model evidence

Measured 2026-09-08. No model downloads, cloud calls, GPU builds, OS power changes,
firewall changes, or production deployment were performed.

The host exposes WSL2 x86_64, Ubuntu24.04 and an i7-11850H (8 cores/16 logical CPUs).
WSL sees about31GiB RAM; Windows CIM reports68,408,107,008 bytes physical RAM
(about63.7GiB). This is not a16GiB Pi. Approximately883GiB filesystem space was
available at baseline. Hardware evidence is in `evidence/host-windows-hardware.txt`.

NVML identifies an RTX3050Ti Laptop GPU with4096MiB VRAM; its sampled temperature
was65C/power14.69W (`host-gpu.txt`). These are observations, not a thermal soak.
The installed llama-cpp-python0.3.20 library reports GPU offload unsupported
(`model-build-capabilities.txt`), so every model result below is CPU-only. Windows
reports Intel integrated graphics too; CIM AdapterRAM is not used as authoritative
VRAM capacity. CPU temperature, fan behavior and sustained throttling are unknown.

Read-only `powercfg /query ... STANDBYIDLE` reports zero automatic sleep timeout for
both AC/DC on the active Balanced plan. Lid-close, hibernation, manual sleep, battery
exhaustion and actual suspend/resume behavior remain unverified. No power setting
was changed. Windows time-service status reports no leap warning, stratum5 and a
successful sync; raw evidence is `host-clock.txt`. This is not a continuous clock
accuracy guarantee. App logs use local time; evidence timestamps explicitly use UTC.

## Direct inference baseline

Reproduce with `scripts/benchmark_model.py --model <existing.gguf> --threads 4
--structured --repetitions 3 --output <new-evidence.json>`. Context4096/batch128,
GPU layers0, temperature0/seed42,96 output tokens. Only three fixed synthetic tasks
are repeated; there are no broker/tool calls. Counts and native llama.cpp prompt/
decode timing counters are retained in the JSON. File hashes identify tested GGUFs.

| Profile | Strict JSON/task success | Median | p95 nearest rank | Peak process RSS |
|---|---:|---:|---:|---:|
| 1.5B Q4 CPU4, raw text | 0/3 (Markdown fences) |1.68s|2.51s|1875MiB|
| 1.5B Q4 CPU4, JSON mode |9/9|2.69s|7.23s|1972MiB|
| 3B Q8 CPU4, JSON mode |9/9|4.06s|7.25s|3792MiB|

The failed raw contract is preserved; no fence-stripping was used to make it pass.
Structured output remains necessary wherever a typed model answer is consumed.
Different filesystem cache/grammar warmup states mean model load times are not a
controlled cold-start comparison. These tiny samples do not establish general
model quality or a production p95. The existing7B model was not benchmarked; no
quality need justifies its additional resource cost from this narrow comparison.

## Application path and candidate budgets

`scripts/benchmark_workflows.py` runs the actual client/event contract with synthetic
scoped tools. Baseline portfolio/scanner latencies85.42s/27.12s exposed overhead and
incomplete scope coverage in the final narrative. Compact safety instructions and
explicit CPU4 prefill threads reduced them to13.33s/7.52s, with all expected read
tools and complete final_answer/done events. The first answer used the deterministic
portfolio fallback; it must not be counted as successful model synthesis. Scanner
output retained fractional holdings, original EUR and unavailable USD/market data.

Initial candidate: retain1.5B Q4, CPU4 prefill/decode, context4096, batch128, no GPU.
It is a measured initial profile, not final host acceptance. Proposed engineering
budgets after this baseline: queue admission at most4; queue wait15s; individual
inference120s; interactive factual task p95<=30s on a larger fixed evaluation set;
operator halt p95<=250ms and independent of model inference. These fit human/hourly
monitoring, not high-frequency trading. Actual concurrent halt/load and sustained
latency acceptance measurements remain pending; do not label these budgets passed.

Admission and cancellation controls are in `inference/budget.py` and the model client.
A16-chunk buffer bounds queued output. Cancellation signals the worker; its native
lock remains held until native evaluation exits. A second request fails closed
while a cancelled native call finishes. The worker has no tools or credentials.
Tokenized envelopes include instructions/schemas/history/evidence plus output and
256 framing tokens; oversized evidence becomes complete structured omission JSON.
Unfittable instructions/latest requests fail closed instead of arbitrary truncation.
This conservative estimate does not claim exact chat-template token accounting.

Missing models expose degraded deterministic reads, with an explicit error and no
cloud fallback. Readiness checks actual model-loaded state and migration revision.
HTTP, in-app alerts and simulator halt controls remain independent of inference.
The degraded model-load behavior has focused tests; full target-stack outage and
24-hour observation remain pending. Docker Desktop Linux daemon was unavailable,
so container restart/TLS/host-source-address validation remains a separate gate.
