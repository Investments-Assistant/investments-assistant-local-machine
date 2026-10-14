# Engineering soak

The current candidate completed a verified 24-hour observation on 2026-10-14;
see the terminal review below. The runner uses only a marked, migrated,
synthetic PostgreSQL database through the `.qa` socket (or loopback TCP for CI),
loopback HTTP, and an existing local
model. It cannot submit broker orders or fetch provider data.

Before observation, freeze application code and dependency versions. The runner
records their fingerprint and fails if code changes. An interrupted run resumed
with `--resume` archives its previous window and starts a new continuous window;
downtime never counts toward 24 hours. Inspect the checkpoint PID before retrying.

```sh
scripts/start_acceptance_postgres.sh
TEST_DATABASE_URL="postgresql+asyncpg://lulu@/test_soak_acceptance?host=$PWD/.qa/socket&port=55439" \
TEST_DATABASE_DISPOSABLE_TOKEN=fixture-soak-20260909 \
.venv/bin/python scripts/soak_acceptance.py --hours 24 --interval 30 \
  --restart-every 900 --model models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  --output .qa/soak-24h-new
```

The separate `test_soak_acceptance` database must already have disposable marker
`fixture-soak-20260909` and the current migration head `0018_job_lease_clock`. The runner refuses
remote hosts, unapproved socket locations or identities. Raw control samples, checkpoints, and benchmark
JSON stay under the specified ignored directory; retain these before cleaning it.
SIGINT/SIGTERM saves progress and terminates only owned application/model children.

Budgets, fixed before acceptance: halt HTTP p95 <=250 ms, service restart <=15 s,
model benchmark <=180 s, and no unapproved orders or loss of persistent halts.
These support minute-scale practice monitoring, not high-frequency execution.
The 24-hour gate requires actual elapsed observation and intentional restarts.
The local model runs in a separate process to measure CPU contention; the HTTP
fixture uses deterministic model responses. This does not demonstrate production
in-process model readiness, Docker restart, OS sleep/resume, or external-network
recovery. Those remain separate evidence requirements.

Smoke evidence:

- `evidence/soak-smoke-v1.txt`: 108.17 seconds, 36 samples, four restarts,
  halt p95 34.39 ms, local structured model tasks 3/3. Earlier harness revision.
- `evidence/soak-smoke-v2.txt`: 72.22 seconds, 32 samples, three restarts,
  halt p95 43.69 ms, local structured model tasks 3/3. Raw samples and code
  fingerprint saved in `.qa/soak-smoke-v2`. Status is `SMOKE_PASS`, not `PASS_24H`.

The first 24-hour attempt was stopped during setup after a continuity-check defect
was discovered (see below); no 24-hour pass is claimed. Ongoing source changes
invalidate a window; start the full observation only against a stable candidate.

- `evidence/soak-smoke-v3.txt`:90.165seconds,49samples,four restarts, haltHTTPp95
  27.112ms (budget250ms), existing local1.5B structured benchmark PASS. Current
  manual marked-risk and commission code included in fingerprint. Raw checkpoints
  and model result remain in `.qa/soak-smoke-v3`. Still SMOKE_PASS, not PASS_24H.

- `evidence/soak-smoke-guards.txt`: 90.165 seconds, 49 cycles, four restarts,
  halt p95 30.805 ms; existing local model benchmark PASS. Raw data remain in
  `.qa/soak-20260928-guards`. This predates only the CLI exit-status correction.

Database identity, disposable marker, schema revision and control gates are
unconditional checks, including under Python `-O`. The CLI exits zero only for
`SMOKE_PASS` or `PASS_24H`; failed or interrupted observations return nonzero.
Always inspect the saved status: a short successful run is not a 24-hour pass.
CLI regression tests use marked PostgreSQL and real loopback HTTP, including a
deliberately missed restart gate. Their synthetic users and observation artifacts
remain in the disposable database and ignored `.qa/soak-cli-*` directories.


## Verified terminal candidate window — 2026-10-14

The final candidate window reached `PASS_24H` and finished at
`2026-10-14T22:30:11Z`: one continuous window, 86,400.216 monotonic seconds,
3,060 control samples, 93 intentional service restarts, and zero failures.
An independent read-only review and recomputation from raw samples confirm
halt p95 28.275 ms (250 ms budget), maximum 60.897 ms, largest sample gap
30.019 s (60 s budget), and maximum restart 3.118 s (15 s budget).
The current source fingerprint still matches the frozen candidate.

All 24 separate CPU-model runs passed, with 72/72 small structured tasks correct.
Control p95 during the 187 samples overlapping those processes was 33.695 ms.
The existing model checksum is unchanged; no new model was downloaded.
See [terminal review and artifact hashes](evidence/soak-24h-ib-async-final-20261013-review.json)
and [terminal log](evidence/soak-24h-ib-async-final-20261013.txt).

This accepts the documented engineering tier: actual loopback HTTP/PostgreSQL,
deterministic application inference and separate CPU-model contention. Raw samples
do not store individual wall timestamps, so posthoc reconstruction of each clock
pair is unavailable; the runner enforced its wall/monotonic divergence guard on
each cycle and after the loop. There was no broker connection or external order.
Production in-process model readiness and Docker recovery are separately verified
in [CONTAINERS.md](CONTAINERS.md). Physical sleep, remote broker/network recovery,
GPU inference and investment edge are not established by this run.

The 672-sample ACPI thermal series covers the last 11h11m51s, not the whole window.
It reports 67.05–95.05 C, median 75.05 C, p95 87.05 C, passive limit 100 and
throttle reason zero in every sample. The sensor remains unmapped to a component;
this is sustained ACPI telemetry, not verified CPU-package cooling.
The preserved [CSV](evidence/thermal-telemetry-series-20261014.csv) and terminal
review record that limitation. Do not rerun or resume this completed window.

## Scheduled monitoring recovery and consent

Scan and weekly-report discovery filters active exact-boolean opt-in users and
independently due/expired job leases before selecting at most100 rows. Oldest due
work is preferred; non-opted users and recently completed jobs cannot consume the
batch. Each callback rechecks opt-in before acquisition. Discovery/acquisition/
completion use10s async bounds with5s SQL and2s lock timeouts; callbacks retain
120s bounds and180s leases. An interrupted callback leaves its lease for expiry;
a failed dependency records failure without advancing successful evidence. Resume
runs one fresh callback, not one replay for each missed interval. Existing token
and database-clock fencing rejects obsolete completion. Opt-out during an already
running read does not undo that read; it prevents subsequent dispatch.

`monitoring-optout-reproduction.txt` demonstrates the prior post-selection opt-out
bug (1failed,7passed). `monitoring-dispatch-guards.txt`17PASS includes105 excluded
users ahead of eligible work, bounded next batches, independent schedules, invalid
opt-in states, local network-failure and cancellation simulations, and two-day
missed-interval recovery. These use real marked PostgreSQL; they do not claim
physical OS sleep, Docker restart, remote broker reauthentication or24h observation.


## In-app recovered heartbeat gaps

The operations heartbeat runs every60seconds for actively opted-in users, separate
from inference and trading. After an established baseline, a next-due delay greater
than300seconds creates a deduplicated owner-only `monitoring_heartbeat_gap` alert
on recovery. Five minutes is an operational missed-cycle tolerance, not a financial
mandate or a per-user service guarantee. A first observation has no historical
baseline and does not invent an outage. The message does not infer whether the
cause was sleep, a stopped process, load, opt-out or connectivity. The observer
cannot send anything while the host/scheduler is stopped; no external watchdog
or outbound notification is installed.

Observation has a20second cycle and10second per-user bound,5second SQL/2second
lock waits and30second lease. Current active opt-in is held during the short
transaction. Gap alert and checkpoint commit together only under a current
DB-clock/token fence. Missed intervals coalesce into one current observation;
there is no trading, quote refresh, model inference or provider request.

Evidence: `heartbeat-guards.txt`17PASS includes marked PostgreSQL two-hour gap,
concurrent observer deduplication, current opt-in, expired-worker rollback, cycle
failure and cancellation. `suite-heartbeat.txt`955PASS69.74s verifies the full suite.
This is controlled recovery evidence, not physical sleep/Docker/broker validation.

CI soak regression tests create their own randomly marked disposable databases
and apply actual migrations. Metadata-only integration schemas are insufficient
for application startup. Loopback TCP is supported for the CI PostgreSQL service;
remote hosts and query-host overrides outside the isolated socket remain denied.

## Current corrected full window — 2026-10-13

The previous 24-hour run failed at about one hour because the synthetic browser
fixture mandate expired before the harness's stale-quote check. The runner now
extends only its positively marked simulator fixture through the requested
observation plus one hour; application risk policy is unchanged. A 90-second
real HTTP/PostgreSQL smoke passed beyond the stale-quote check (88 cycles, eight
restarts, no failures; `evidence/soak-expiry-regression-20261013.json`).

A fresh detached full run started at `2026-10-13T21:52:36Z`, PID 487287, under
`.qa/soak-24h-expiry-fixed-20261013`. It uses the marked local disposable
`test_acceptance_expenses` database, 30-second sampling, 15-minute service
restarts, and the existing local Qwen 1.5B CPU model. Its launch receipt is
`evidence/soak-24h-expiry-fixed-20261013-launch.json`; inspect its checkpoint and
verify PID before any retry. The detached job does not depend on Codex tokens,
but the host must remain awake and the clock/observation-continuity gates must
hold for the entire 24 hours. No 24-hour credit until terminal `PASS_24H`.

This window was subsequently invalidated when the Yahoo historical-source guard
changed a fingerprinted application file. The runner recorded terminal
`FAILED / CODE_CHANGED_OBSERVATION_INVALIDATED` at 2026-10-13T22:08:47Z; it is
retained as failure evidence and receives no 24-hour credit. Replacement run
PID492940 started at 2026-10-13T22:09:44Z with the new code fingerprint under
`.qa/soak-24h-research-guard-20261013`. Its current status is in
`CHECKPOINT.md`; inspect the live process and checkpoint before any retry.


## Same-process native inference and halt controls

`scripts/benchmark_control_contention.py` measures authenticated real ASGI routes
and PostgreSQL halts while the actual local model generates in the same process
and event loop. It runs three fixed arithmetic prompts without tools, providers
or orders, retaining per-request overlap samples. Native ownership must be held
both before and after a control request for it to count toward the minimum20
overlap samples. The predeclared halt p95 budget remains250ms.

```sh
TEST_DATABASE_URL="postgresql+asyncpg://lulu@/test_soak_acceptance?host=$PWD/.qa/socket&port=55439" \
TEST_DATABASE_DISPOSABLE_TOKEN=fixture-soak-20260909 \
.venv/bin/python scripts/benchmark_control_contention.py \
  --model models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  --output docs/acceptance/evidence/control-contention-new.json
```

Use a new output name; existing evidence is never overwritten. The runner checks
the disposable identity, token and real migration revision before fixture writes.
It opens no HTTP listening port, but runs actual login, CSRF and halt handlers
through ASGI. This measures application processing, not network admission or
Docker/Nginx routing. It does not replace the independent restart, thermal, OS
sleep or24h observation gates, nor evaluate arithmetic-answer quality.

## Updated candidate preflight — 2026-10-13

After CI passed at cd049bf, a 90.165-second preflight passed with the updated
dependencies:51 control samples, halt p95 45.695ms against250ms, and three service
restarts taking1.957/2.005/2.369s against15s. The existing local GGUF benchmark
passed in a separate process. Owned children terminated and no broker connection
or order occurred. This is SMOKE_PASS, not PASS_24H.

Evidence: [preflight](evidence/soak-security-preflight-20261013.json). Concurrent
[clock observation](evidence/clock-soak-preflight-20261013.json) found no backward
steps in100.005s/9827samples. This does not erase earlier under-suite clock failures
or prove future stability. The user was asked whether the laptop can remain
available for a continuous24-hour window. No OS/power setting changed.

## Current candidate window after IBKR client migration — 2026-10-13

The prior PID492940 window was intentionally interrupted at27 cycles/590.7s
before changing the fingerprinted IBKR client dependency. It earned no24-hour
credit. The current candidate passed all719 unit tests and all374 integration
tests against isolated disposable PostgreSQL databases; the latest broker
focused integration subset passed59 tests. Lock, Ruff, compileall and diff
checks also passed. See `evidence/ib-async-migration-20261013.txt`.

A new detached run started at `2026-10-13T22:27:39Z`, PID500853, output
`.qa/soak-24h-ib-async-final-20261013`, against a newly created marked test
database. It uses30-second samples,15-minute fixture restarts and the existing
local Qwen model. At first verification it had4 samples, no failures or
restarts, p95 26.85ms, zero broker connections/orders, and a matching code
fingerprint. This is only an initial RUNNING state. The launch receipt and log
are `evidence/soak-24h-ib-async-final-20261013-launch.json` and
`evidence/soak-24h-ib-async-final-20261013.txt`; inspect PID and checkpoint
before any retry. The host and WSL must remain awake and code/dependency files
must not change for the full24-hour observation.

## Observation continuity repair

The runner previously could count a long scheduling/suspend gap toward its
elapsed target and report PASS_24H without observing that period. A real
PostgreSQL/HTTP regression reproduces this with injected clocks: a service
restart followed by an unobserved day yielded PASS_24H in9.75s. This test is
failure evidence, not actual elapsed observation.

The repaired runner checks continuity at each cycle and once after its loop,
because a gap can cross the deadline. Before starting a fresh window, budgets
are fixed at requested sample interval plus30s for the maximum observation gap,
and250ms for divergence between elapsed wall and monotonic clocks. At the normal
30s cadence, a gap over60s invalidates the run. Clock adjustment or suspend that
violates these budgets produces FAILED with OBSERVATION_GAP or CLOCK_DISCONTINUITY;
it does not authorize an OS change. The extra30s permits bounded control/health
requests and the existing15s service restart budget. This remains minute-scale
engineering observation, not proof of continuous physical hardware availability.

The initial `.qa/soak-24h-security-20261013` attempt is INTERRUPTED and must not be
relabelled or continued across the harness change. Use a fresh output directory
and retain its earlier evidence. No broker/provider or OS setting changed.


## Current candidate observation — first scheduled restart

At `2026-10-13T22:43:20Z`, detached runner PID500853 remained RUNNING at39
cycles /938.2 seconds, one continuous observation window, zero failures, one
scheduled service restart completed in1.600s, and halt-control p95 31.17ms. The
service restarted from PID500855 to PID506404; the harness recorded no broker
connections or external orders. The source fingerprint still matches
`36ee15eb9f882cf8845e54733b0fa434df6b0f514e0b8e053414a0b1cba45a82`. This
earns restart-path evidence only; it is not a24-hour result. Keep the host awake
and preserve all fingerprinted source/dependency files until terminal status.

## 2026-10-14 active 24-hour observation checkpoint

At `2026-10-14T11:08:32Z`, runner PID500853 remained `RUNNING` with one
continuous observation window, 45,552.9 elapsed seconds (12.65h),1,617 cycles,
49 scheduled service restarts, zero failures, and control p95 29.58ms against the
250ms budget. The source fingerprint remains
`36ee15eb9f882cf8845e54733b0fa434df6b0f514e0b8e053414a0b1cba45a82`; the
harness reports zero broker connections and external orders. This is partial
restart/continuity evidence, not `PASS_24H`; continue to keep the host awake and
avoid changing fingerprinted source/dependency files. User clarified they do
not know how to set up an IBKR paper session; no broker connection was attempted.


At `2026-10-14T11:11:02Z`, a follow-up live runner checkpoint recorded45,702.9s
(12.70h),1,622 cycles,49 restarts, zero failures, one window, and control p95
29.50ms. PID500853 was still alive. The original source fingerprint matched;
there were zero broker connections or external orders. The run remains partial.


At `2026-10-14T11:13:32Z`, PID500853 remained RUNNING at45,852.9s (12.74h),
1,627 cycles,49 scheduled restarts, zero failures, one observation window, and
control p95 29.50ms. The code fingerprint still matched; broker connections and
external orders remain zero. The observation is not yet24 hours.


At `2026-10-14T11:14:33Z`, PID500853 remained live at45,912.9s (12.75h),
1,629 cycles,49 restarts, zero failures, one observation window, and control
p95 29.50ms. Code fingerprint unchanged; broker connections/orders remain zero.
The current process has not yet reached the24-hour acceptance window.


At `2026-10-14T11:15:03Z`, the live runner PID500853 remained RUNNING at
45,942.9s (12.76h),1,630 cycles,49 restarts, zero failures, one window, and
control p95 29.50ms. Fingerprint matched; no broker connections or external
orders. The full24-hour requirement remains unfulfilled.
