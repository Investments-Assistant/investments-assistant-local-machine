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

## Scope workflow evaluation v2 (2026-09-23)

Actual existing1.5B Q4 CPU4, context4096,128 output tokens, synthetic tools:
`evidence/workflow-scope-v2-cpu.json`. Five fixed cases (portfolio, scanner,
exclusion, exclusion follow-up, Portuguese portfolio) all used the expected
read scopes and completed final_answer/done. Load1.70s, peak RSS1987.3MiB;
individual latencies11.99/6.48/2.52/0.84/2.58s. One observation per case is not
production p95 or sustained-load acceptance. Native-tool comparison remains pending.

The harness PASS is explicitly limited to scope/events. Manual review FAILS
financial-answer quality (`evidence/workflow-scope-v2-review.json`): Portuguese
answer invented EUR4.00 for0.004 units atEUR100, whose quantity×price isEUR0.400;
no supplied multiplier/FX/total supportedEUR4.00. The English portfolio answer
used deterministic fallback, not successful model synthesis. News-only prose also
inferred more than the synthetic headline established. These findings block broader
L06/model-quality acceptance despite correctly enforced read exclusions.

Next repair: deterministic exact portfolio facts and explicit missing inputs must
bound financial answers; model prose cannot establish valuation. Retain this
unfavorable result and rerun fixed cases after correction. No threshold tuning,
model download, provider/broker connection or live action was performed.

Financial boundary rerun: `workflow-financial-facts-cpu.json`, same five cases,
existing model/profile.5/5 scope/event checks pass. Portfolio/scanner/Portuguese
answers identify deterministic_financial_evidence and preserve exact0.004/EUR100,
missing market value and missing USD total. `workflow-financial-facts-review.json`
parses and verifies those actual answers. Sub-millisecond financial-path timings
reflect skipped inference, not accelerated model synthesis. Load1.33s/peak1979.25MiB.
News-only model output still infers market activity/changes from a synthetic title;
broader model-quality acceptance remains FAIL/pending. No favorable-edge claim.

## Resumed real-model comparisons (2026-09-24)

Existing1.5B Q4 CPU4/context4096/output128, synthetic tools only.
Default headline and substantive runs each pass5/5 scope/event checks:
workflow-news-abstention-cpu.json and workflow-news-substantive-cpu.json.
Headline abstention removes prior unsupported market prose. Substantive evidence
also produces abstention; no useful causal analysis or investment edge established.
Parsed review is workflow-news-review.json. Portfolio/scanner generation remains
deterministic source facts, so its latency cannot measure inference improvement.

Native comparison workflow-native-headline-cpu.json FAILS4/5 scope checks:
portfolio/scanner/news-only responses emit tool-call markup without executing
required tools; Portuguese portfolio asks for account/broker without reading.
Only excluded-portfolio follow-up has the expected empty scope. Native case times
18.22/20.43/13.49/1.82/7.37s, load1.02s, peak1995.49MiB. Keep native tools off
for this measured profile. Five cases cannot establish general quality or p95.
No external broker/provider calls, model downloads or orders occurred.

Substantive output also invented source_unavailable. Collection metadata now comes
from observed tool results; regression coverage verifies model assertions cannot
introduce missing body/source failure. Broader useful interpretation remains open.

Native recovery rerun: workflow-native-recovery-cpu.json passes5/5 scope/event
checks after application repair. Four cases explicitly record deterministic_read_recovery;
this proves scoped fallback behavior, not working native tool generation. Parsed
portfolio answers preserve0.004/EUR100 and unavailable totals; headline news
abstains; excluded follow-up performs no read. Timings26.04/27.82/17.50/2.16/9.85s,
load1.17s, peak1995.67MiB. Measurements overlapped local unit verification and are
not isolated latency or p95 claims. Keep the deterministic default; native adds
latency without proven benefit on this profile. Original failed benchmark retained.

## Report structured inference (2026-09-26)

`benchmark_reports.py` runs the actual report pipeline with the existing1.5B CPU
GGUF (SHA256 in evidence), synthetic account/news inputs and explicit PDF/storage
sinks. No downloads, broker connections, provider calls or orders. Command:

```sh
.venv/bin/python scripts/benchmark_reports.py --model models/qwen2.5-1.5b-instruct-q4_k_m.gguf --output docs/acceptance/evidence/report-model-schema-cpu.json
```

Prompt-only report output failed schema validation in all3 cases; reports remained
truthful partial failures with deterministic financial facts (`report-model-cpu.json`).
Schema-constrained local inference passed substantive-news and source-injection
cases in16.94s/21.85s; the empty-source case still failed semantic validation
(`report-model-schema-cpu.json`, overall FAIL). Empty-source schema was then
restricted to abstention/zero extracts and the affected case rerun:

```sh
.venv/bin/python scripts/benchmark_reports.py --model models/qwen2.5-1.5b-instruct-q4_k_m.gguf --case no_news --output docs/acceptance/evidence/report-model-empty-source-cpu.json
```

That case PASS8.11s, explicit abstention. Reuse the unaffected source cases; no
claim of an all-three fresh run. Structured inference bypasses tool routing and
prose repair, preserves all context or errors, and rejects truncated completion.
Output budget512, context4096, CPU4threads, no GPU; these are benchmark settings,
not evidence that the full production output budget or workload meets an SLA.
One injection-case extract quoted the injected instruction itself, labelled as an
unverified source quotation. No instruction execution occurred, but useful source
selection/analytical quality remains a separate unresolved requirement. These tiny
samples prove neither p95 latency, independent corroboration nor investment edge.


## Read follow-up benchmark (2026-10-06)
Existing1.5BQ4 CPU4/context4096/output128, synthetic tools only; no downloads.
`workflow-followup-cpu-20261006.json` passes8/8scope/eventcases, including refresh of
portfolio evidence, holdings+news, and refreshed news preserving portfolio exclusion.
Load6.30s, peak1976.18MiB. Financial answers retain0.004/EUR100 and unknown totals;
headline-only news abstains. Seven paths bypass inference for deterministic evidence
or abstention; their~1–9ms timings do not demonstrate model acceleration. The excluded
portfolio follow-up uses inference17.55s and returns a generic refusal rather than
explaining the explicit user restriction; this remains a conversational-quality gap.
No broader analysis, ambiguity, p95 or financial-edge claim.0brokerconnections/orders.

The above excluded-followup quality defect is fixed in
workflow-exclusion-answer-cpu-20261006.json (8/8 scope/event/content checks PASS).
Existing1.5BQ4 CPU profile loaded in1.418s, peak1955.61MiB; excludedfollowup0.0001s
now returns the precise user restriction and read-preference option. That latency
comes from bypassing unnecessary inference, not faster model generation. Wider
portfolio interpretation and useful source selection still need quality evidence.

## Combined scanner and source-selection quality (2026-10-07)
The predeclared benchmark now checks factual source selection, not just valid JSON
or completed events. The first scanner run safely abstained but failed usefulness
in both cases (workflow-scanner-quality-cpu-20261007.json). Bounded exact candidate
sentences now exclude recognized direct instructions before tool-free inference;
quote enums, source attribution, mandatory limitations and bounded retries remain.
No classifier is treated as an authority boundary or proof arbitrary text is safe.

workflow-scanner-candidates-cpu-20261007.json passes both default-mode cases:
combined scanner10.976s and scoped news with portfolio excluded9.133s. The source
revenue statement is selected, the injected order command is absent, and exact
financial facts, independent scopes and missing evidence stay visible. Existing
1.5BQ4, CPU4/context4096/output512; load1.020s, peak2012.73MiB. No model download.
workflow-scanner-native-cpu-20261007.json passes the same scanner content checks in
38.508s, using deterministic read recovery after native selection did not supply
all required reads. Load0.950s, peak2022.70MiB. This supports retaining the existing
default deterministic read routing; native mode has no measured advantage here.
These tiny samples are not p95, production-output768 acceptance or a full soak.

The report injection case initially failed (report-source-quality-cpu-20261007.json).
The first candidate report had a nominal PASS but manual review found an injected
Enable live sentence among its observations: that result is invalid for quality.
The benchmark now checks every selected quote against the directive filter, and
the candidate filter includes mode/limit commands. The final
report-source-candidates-final-cpu-20261007.json passes13.654s with only the factory
closure statement and its no-forecast/no-price limitation. Load0.982s, peak2032.47MiB.
Report prompts now receive candidate excerpts and the period; financial source
context stays in deterministic rendering/persisted evidence. Existing report
collection/context size limits remain enforced. PDF/storage are sinks in this
model tier; browser/PostgreSQL verification is separately required. No external
broker connection/order occurred, and no return or investment-edge claim follows.


## Repeated production output-budget checks (2026-10-09)

The unchanged workflow-scope-v6 harness ran all9fixedcases three times with the
existing1.5BQ4, CPU4/context4096/outputlimit768, default routing, substantive
synthetic news and source injection. Plan and30s per-task budget were recorded
before the runs in `evidence/workflow-production-budget-20261009-plan.json`.
All27scope/event/answer checks passed; final answers are identical across runs.
Manual source/financial review and model SHA256 are in the corresponding
`-review.json`; rawanswers/logs/exitcodes are preserved for runs1,2,3.

Model-assisted case nearest-rank p95 (maximum of3): scanner11.044s, explicit
portfolio exclusion9.470s, holdings+news9.510s, refreshed excluded-portfolio
news9.741s. The other5cases use deterministic financial/restriction responses;
their sub4ms times are not model inference performance. Modelload0.906–1.498s;
peakprocessRSS2017.195MiB. All measured cases meet the existing30s task budget.

This supports retaining the measured CPU/default-routing profile at the normal
768-token output limit, not a claim each task generated768tokens. Three samples
per case are not production tail-latency confidence. There was no concurrent
load, thermal/OS/Docker observation, network/provider data, browser/database
workflow, external broker connection or order in this model tier. The24h and
fulltargetstack observation requirements remain pending.


## Same-process control responsiveness under native inference (2026-10-09)

`control-contention-20261009.json` and its `-review.json` record three real local
CPU4/output768 generations in the same process/event loop as authenticated
ASGI/PostgreSQL halt handlers.1044requests overlap native ownership before/after
the entire request. Halt p95=27.921ms, maximum94.336ms, against the unchanged250ms
budget. Persisted halt state survived every inference round. Native tasks took
26.846/22.155/26.024s and completed final_answer/done with no tool events.
Load1.715s; peakRSS2018.191MiB. Runner and relevant source/model hashes are saved.

This closes the previous same-process contention evidence gap for this short
synthetic fixture. It does not establish network admission, Docker/Nginx routing,
physical cooling/sleep, arbitrary blocking dependencies or24h stability. The
arithmetic text is only a load fixture; no answer-quality claim follows.
