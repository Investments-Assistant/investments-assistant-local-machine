# Engineering soak

The observation gate remains pending. The runner uses only a marked, migrated,
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

No 24-hour observation has been launched or claimed. Ongoing source changes would
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
