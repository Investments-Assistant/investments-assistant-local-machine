# Final-host deployment and acceptance handoff

## Owner decision — 22 October 2026

The application will run on a different computer. Stop this laptop's 24-hour
observation, CPU-temperature tooling and clock-repair work. Carry those checks to
the actual final host as **DEFERRED — pending final-host validation**, not PASS.
The pending laptop Portable ZIP download/setup request is cancelled. Preserve all
historical interrupted, failed and completed observations with their source scope.

The owner explicitly keeps research and external Paper gates open. L04/L15 still
need their outstanding lifecycle, provenance, reconciliation and authority evidence;
L14 still needs time-aware news/model, representativeness and agreed forward
evidence beyond the completed private price-only pilot.
Portable offline Paper implementation can continue within checkout authority, but
offline tests cannot establish actual connectivity, execution authority or economic
results. External SDK writes remain closed and live trading stays OFF. This handoff
does not complete the Goal or make all remaining work final-host-only.

## Establish the target before selecting commands

Record the final computer's OS, architecture, CPU/core count, physical and available
RAM, disk capacity, Docker/Compose availability, local clock behaviour and mapped
CPU temperature/throttling sources. GPU capability needs its own runtime/build
evidence. The final host is unknown; do not assume Windows, WSL, Linux, a Pi, an
existing sensor tool, a network address or certificate trust.

Current portable source is published as08cdba5, migration0020; [image146d8bac](evidence/ibkr-read-scope-image-20261026.json)
reconciles all187context/184copied files to that commit. It is an amd64 build and
isolated smoke result, with prior actualGGUF/startup/restart proof reused only for
unchanged surfaces. [Exact currentCI/Sonar40259671081](evidence/account-scope-ci-20261026.json)
passes allfourjobs,961unit/459PG/1424overlappingcombined and24browser/8TLS-WSS.
None of this proves
final-host compatibility or hardware acceptance.

The owner-approved [local private backup/rehearsal/update](evidence/private-upgrade-result-20261026.json)
now verifies this laptop's operator database at0020 while preserving its prior
data, sequences and matching settings/keys. Encrypted0019backup, separately
protected recovery key and private rehearsal copy remain local. This is not an
off-host backup, migration to the final computer, or permission to transfer/start
anything there. Retain the protected material; never use the rehearsal copy as
the normal app database or copy the ignored tree blindly.

Retain the chosen source revision, dirty application diff if any, dependency lock
hash, migration head, build-input hashes, image ID/architecture and GGUF licence,
hash and runtime profile. Reconcile the actual deployed bytes with that candidate.
The published e154a0a proof covers 860 unit/392 PostgreSQL cases, configured CI/Sonar
and an amd64 image for its recorded inputs; its migration0019 and CPU4/context4096/
GPU0 measurements are historical provenance, not the required future schema or a
universal hardware profile. Resolve the checked-out head with `alembic heads`;
inspect the corresponding startup and acceptance guards before migration.

Use already-permitted software/model artifacts when available. Installation,
downloads, driver/service, firewall, power or clock changes require their own
concrete scope and applicable approval. `scripts/setup.sh` modifies OS/VPN/firewall
state and is not generic final-host bootstrap. `scripts/start_acceptance_postgres.sh`
hardcodes extracted x86_64 PostgreSQL16 paths and old fixture locations/port; it is
not a portable final-host preparation command.

## Deploy only to the reviewed target

Prepare private final-host secrets and an existing permitted GGUF with the locked
toolchain. Keep authentication enabled, production checks on, live trading OFF,
broker read flags OFF unless a separately approved scoped action requires them,
and both Yahoo permissions OFF unless each has its own rights review. A global
broker credential variable is not an account-selection or read authorization.
Never put credentials, reusable cookies, account identifiers or secret values in
the handoff/evidence. Do not blindly copy this laptop's `.env`, private database,
keys, raw PostgreSQL directory, model binaries or ignored `.qa` tree.

Default Compose ingress is loopback. Review actual port/subnet conflicts, TLS
hostname/SANs, certificate trust and effective proxy identity on the target. LAN
or remote exposure, DNS and firewall setup remain separate decisions. Existing
laptop loopback/Windows-forwarding results cannot establish final-host ingress.

The following is conditional on an **explicitly approved new empty database**, a
reviewed configuration/model and available compatible Docker/Compose. Run from
the checkout root only after target preparation; these examples grant no deployment
permission:

```sh
make local-build
docker compose up -d postgres
# Wait until this new PostgreSQL service is healthy.
docker compose run --rm --no-deps app alembic heads
docker compose run --rm --no-deps app alembic upgrade head
docker compose run --rm --no-deps app alembic current
docker compose run --rm --no-deps app python scripts/create_user.py
make local-up
make local-wait
make local-ready
```

`create_user.py` prompts for the login ID/password; a nonempty `--username` is
optional. `make local-deploy` does not perform migrations. Startup checks the
required revision and must not be used to initialize/upgrade an unknown database.
For existing application data, first follow the [runbook](RUNBOOK.md): separately
authorized encrypted backup, restore to a new disposable target, verify schema,
ownership, counts, encrypted records and compatible keys, then review the actual
migration and rollback. Preserve original data/keys and never stamp an unknown
schema or automatically migrate an existing production volume.

## Validate the actual final-host profile

After the candidate is reviewed and frozen, retain final-host model load and
structured-answer results, representative in-process inference/control contention,
real database/model readiness, application/database restart halt persistence,
TLS/loopback login/CSRF/WebSocket behaviour and a disposable backup/restore check.
Use new output names and separately owned synthetic fixtures; source-dependent
historical passes can be reused only where the relevant bytes and scope still
match. Record limitations separately from failures and unavailable results.

For an already-permitted local GGUF and a compatible Python/runtime environment,
the direct benchmark command shape is:

```sh
poetry run python scripts/benchmark_model.py \
  --model "$APPROVED_EXISTING_GGUF" --threads "$REVIEWED_CPU_THREADS" \
  --structured --repetitions 3 --output "$NEW_MODEL_EVIDENCE_JSON"
```

Select supported thread counts from the checked-out CLI; record the actual context,
CPU/GPU mode, hash and native-library build. Current benchmark code is CPU-only and
imports POSIX `resource`. The soak currently fixes CPU4/context4096/GPU0; the current
container runtime verifier requires amd64 and fixes4CPU/6GiB. Check compatibility
before invoking them. A needed platform/profile adaptation requires code review
and affected verification; do not claim ARM/GPU/native-Windows acceptance or tune
budgets after seeing results.

Use a component-mapped CPU package/core source appropriate to the final host. Keep
raw labels, units, timestamps/time zone, load/effective clocks and available thermal
throttling fields through baseline, representative sustained load and recovery.
Report missing fields. A GPU reading, unmapped ACPI zone or temperature screenshot
does not establish CPU cooling. Sensor software/privileged access is not preapproved.
Clock observation is read-only; no laptop clock experiment or OS change is carried
forward as an automatic fix. A short stable probe cannot prove future stability.

## Prepare a fresh disposable continuous observation

Provision a new PostgreSQL16 test fixture appropriate to the final platform: new
owned cluster/resources, a new `test_[a-z0-9_]+` database, fresh random token in
`public.ia_disposable_marker` and explicit migrations to the reviewed checked-out
head. Verify actual database name, marker, revision and exact local transport before
fixture writes. The current runner accepts loopback TCP or an absolute Unix-socket
directory below this checkout's `.qa`; it rejects remote hosts. Its fixed revision
guard must agree with the reviewed migration head before launch.

Do not resume old clusters or copy old launcher/auditor/observer scripts: those
helpers are bound to historical source, boot IDs, PIDs, paths and run identities.
Prepare a new reviewed launch/terminal-audit plan with final-host boot/process
identity, unique owned paths, a new output below `.qa`, recorded source/model hashes
and exactly one runner/verifier. Capture launch receipt, log and tool/process exit
result durably so interruption cannot be mistaken for success. Preserve existing
fixtures; there is no blanket cleanup permission.

Only after those prerequisites and applicable execution authority, the command
shape is:

```sh
TEST_DATABASE_URL="$FINAL_HOST_DISPOSABLE_URL" \
TEST_DATABASE_DISPOSABLE_TOKEN="$FINAL_HOST_RANDOM_MARKER" \
poetry run python scripts/soak_acceptance.py \
  --hours 24 --interval 30 --restart-every 900 \
  --model "$APPROVED_EXISTING_GGUF" --output "$NEW_UNIQUE_QA_DIRECTORY"
```

All variables are newly reviewed final-host values, not old usernames, database
names, markers or ports. Never add `--resume` to continue a historical observation.
Keep source/dependencies unchanged for the full window. A suspend, reboot, source
change, observation gap or clock discontinuity invalidates continuity; preserve
the failed/partial evidence and require a new window rather than lowering guards.

Predeclared gates remain:86400 continuous observed seconds,30-second normal sampling,
maximum60-second observation gap, maximum250ms wall/monotonic divergence, halt HTTP
p95≤250ms, each restart≤15s and each model benchmark≤180s. Required full-window
model evidence remains24 runs/72 actual fixed-task answers, with zero unapproved
orders and persistent halts. Do not substitute this synthetic HTTP/PostgreSQL plus
separate CPU-model tier for production in-process inference, physical sleep,
external broker recovery, Paper lifecycle or economic research acceptance.

## Independent terminal review and retention

Before accepting the window, a new bound independent audit must verify exit0 and
terminal `PASS_24H`, one continuous window of at least86400 seconds, zero failures,
matching source/model/profile, cleared owned child fields and no duplicate live
runner. Recompute p95/sample count/gaps and restart limits from retained raw data;
independently parse all required model answers, not only recorded PASS booleans.
Exit0 alone can mean `SMOKE_PASS`; missing, interrupted or stale RUNNING records
are not acceptance. Clock checks rely on the fingerprinted runner where raw paired
timestamps are unavailable; retain that limitation.

Retain checkpoints, samples, model JSONs, logs, launch/exit/audit receipts, source
and image provenance with an explicit bounded path allowlist, per-file hashes and
byte-for-byte archive roundtrip verification. Exclude private data/secrets/PG dumps
and preserve originals. Review owned database/cluster identity, marker, active
clients and retained evidence before separately scoped cleanup; never signal or
drop an old/private instance by PID, port or name alone. Acceptance remains pending
until actual final-host evidence passes and the Goal's other open gates are resolved.
