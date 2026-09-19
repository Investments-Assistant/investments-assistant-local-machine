# Engineering soak

The observation gate remains pending. The runner uses only a marked, migrated,
synthetic PostgreSQL database under `.qa`, loopback HTTP, and an existing local
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
`fixture-soak-20260909` and migration head `0011_retention_index`. The runner refuses
other locations or identities. Raw control samples, checkpoints, and benchmark
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
