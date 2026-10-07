# Operator runbook (work in progress)

## Migration and rollback

Startup verifies `alembic_version`; it no longer creates/alters tables, rotates
bootstrap credentials, or assigns unknown-owner records. No migration was run
against the application database in this task.

For a **new empty isolated database**, explicitly set DATABASE_URL to that
instance, then run `.venv/bin/alembic upgrade head`. Create users through the
existing `scripts/create_user.py` command. Review `--help` before supplying inputs;
never put a production password into evidence or shell history.

For an existing reviewed installation: stop writes only with deployment approval,
take an encrypted pg_dump backup, restore to a disposable database, compare all
schema columns/indexes against `migrations/reviewed_schema.json`, then stamp that
verified baseline with `alembic stamp 0001_reviewed` and upgrade the disposable
copy first. Never blindly stamp an unknown schema. Unknown-owner records remain
NULL; unknown expense accounts retain `legacy-unassigned` for explicit mapping.
Numeric conversion preserves available stored digits; it cannot recover precision
already lost by historical floating point storage. Roll back with a verified
backup and compatible code; automatic precision-reducing downgrades are refused.
Production upgrade remains approval-gated.

## Isolated local PostgreSQL used for validation

PostgreSQL 16 packages are extracted under `/tmp/ia-postgres-root` without system
installation. Cluster: `/tmp/ia-acceptance-pgdata`; Unix socket directory:
`/tmp/ia-acceptance-pgsocket` (mode 0700), port namespace 55439; no TCP listener.
Only synthetic test data is permitted in this instance. Fixtures require both an
explicit TEST_DATABASE_URL and matching `public.ia_disposable_marker` token,
verify `current_database()`, and roll back each test without dropping tables.

```
TEST_DATABASE_URL='postgresql+asyncpg://lulu@/test_acceptance_20260908?host=/tmp/ia-acceptance-pgsocket&port=55439' \
TEST_DATABASE_DISPOSABLE_TOKEN=fixture-acceptance-20260908 \
.venv/bin/python -m pytest tests/integration -q
```

The OS user in this example is local to the observed host. Recreate a fresh marked
database after schema changes; `create_all` never upgrades existing test tables.
Sandboxed AnyIO thread wakeups hung; the same fully mocked endpoint passed outside
the sandbox. Run approved tests outside that sandbox when necessary.

Shutdown the **test cluster only**:

```
LD_LIBRARY_PATH=/tmp/ia-postgres-root/usr/lib/x86_64-linux-gnu \
/tmp/ia-postgres-root/usr/lib/postgresql/16/bin/pg_ctl \
-D /tmp/ia-acceptance-pgdata -m fast -w stop
```

## Deployment and incidents

The inherited ARM64/Pi automatic deployment is replaced with a manual x86_64 CPU
image validation workflow. It does not install on a host. Production deployment,
firewall/power changes and external notifications remain unapproved. A halted
application does not cancel an existing broker order. Stop-new-trading,
cancellation of owned orders, and liquidation require separate powers; none may
silently sell protected long-term allocations. Sleeping/offline laptops cannot
send their own missed-heartbeat alert. An external watchdog requires separate
privacy/setup approval.

## Verified disposable backup/restore

`scripts/verify_restore.py` refuses a non-test name, unmarked source, remote socket,
existing target or existing archive. It never drops/replaces a database. Example
already executed successfully (do not blindly repeat this target):

```
TEST_DATABASE_DISPOSABLE_TOKEN=fixture-acceptance-20260908 .venv/bin/python scripts/verify_restore.py \
  --source test_acceptance_browser --target test_restore_20260908_a \
  --socket /tmp/ia-acceptance-pgsocket \
  --bin /tmp/ia-postgres-root/usr/lib/postgresql/16/bin \
  --library-path /tmp/ia-postgres-root/usr/lib/x86_64-linux-gnu \
  --output docs/acceptance/evidence/restore-database.json
```

23 table digests/counts and revision0005_sessions matched. The source was checked
unchanged during this exercise. Archive `/tmp/test_restore_20260908_a.dump` is0600.
A production backup additionally needs separately protected vault/session keys,
report files and a compatible code/config snapshot; database restoration alone
cannot decrypt credentials or restore report PDFs. Production backups/migrations/
restore remain approval-gated; no production data was used here.

Cookie format changed with0005_sessions; existing browsers must sign in again.
Logout revocation is durable and does not store reusable cookies. The operator may
call `security.sessions.revoke_all` for a specific local user in an approved admin
transaction. Deactivate first for immediate account denial; a revocation fence
prevents old cookies becoming valid again after reactivation. MCP now needs an
explicit MCP_USER_ID bound to an active account in addition to its separate token.

## Private newsletters and observed news history

Current migration head is `0007_news_evidence`. Apply explicit migrations only after
reviewing the target and backup; startup does not mutate schemas. The disposable
upgrade and full regression suite are recorded in `evidence/suite-news-evidence.txt`.
Set `NEWSLETTER_OWNER_USER_ID` only to the deliberately selected active application
user before enabling the configured mailbox reader. No owner means blocked ingestion.
The reader leaves the mailbox unread and stores opaque, owner-specific references.
Legacy email rows remain quarantined with unknown ownership; do not assign them to
an administrator simply to make them visible. A separate reviewed retention/ownership
operation is required. Unknown legacy availability excludes these records from
historical replay. Current corrections retain their actual observed availability and
prior evidence; `get_news_evidence_as_of` never selects a future revision.

## Resumable disposable acceptance infrastructure

Temporary directories were reset between resumed sessions. Current fixture state is
under git-ignored `.qa/`, permissions0700, and is never production data. PostgreSQL16
Ubuntu packages are extracted into `.qa/postgres-root` without installing an OS
service. `scripts/start_acceptance_postgres.sh` starts only this cluster; it uses a
private Unix socket and disables TCP listeners. Test databases must still pass the
existing name/current-database/disposable-marker checks before fixture mutations.

```sh
scripts/start_acceptance_postgres.sh
export TEST_DATABASE_URL="postgresql+asyncpg://lulu@/test_acceptance_expenses?host=$PWD/.qa/socket&port=55439"
export TEST_DATABASE_DISPOSABLE_TOKEN=fixture-acceptance-20260909
.venv/bin/pytest tests/unit tests/integration
# Separate browser database: test_browser_expenses, same marker and socket.
PLAYWRIGHT_BROWSERS_PATH="$PWD/.qa/playwright" \
TEST_DATABASE_URL="postgresql+asyncpg://lulu@/test_browser_expenses?host=$PWD/.qa/socket&port=55439" \
.venv/bin/python scripts/verify_browser.py
LD_LIBRARY_PATH="$PWD/.qa/postgres-root/usr/lib/x86_64-linux-gnu" \
.qa/postgres-root/usr/lib/postgresql/16/bin/pg_ctl -D "$PWD/.qa/pgdata" -m fast -w stop
```

Current schema head is `0011_retention_index`. Category edits are browser-authenticated
and audited without transaction histories. Displayed-page export is explicit JSON; full-period export is bounded NDJSON and
requires its completion trailer. Neither is a bank connection. Retention decisions
remain pending.

## Compose ingress, proxy identity and bounded logs

Default `LOCAL_BIND_ADDRESS=127.0.0.1` publishes only loopback ports 8080/8443.
Restricted LAN operation is a separate opt-in: choose the actual private interface
address, generate the matching Nginx allow-list and verify effective host firewall
and Docker/WSL source addresses before starting or redeploying. No firewall changes
or existing production deployment are authorized by this acceptance task.

Compose allocates Nginx `LOCAL_PROXY_IP=172.30.80.3` in
`LOCAL_DOCKER_SUBNET=172.30.80.0/24`; the application trusts only that exact peer.
Choose a nonconflicting private subnet/address pair if the host already uses this
range. Uvicorn header rewriting is disabled so application validation sees the
actual peer. Nginx overwrites origin-related proxy headers and retains the public
Host port. The current unit fixtures verify HTTPS WS origin checks from the exact
peer and rejection from other peers; actual Docker/WSL forwarding remains pending.

Offline Compose validation (no daemon or real env-file resolution):

```sh
.venv/bin/python scripts/verify_compose_config.py --docker docker \
  --output docs/acceptance/evidence/compose-local-ingress.json
# On this WSL host, the available client is:
# --docker '/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe'
```

The verifier uses `.qa/compose-validation.env` containing synthetic interpolation
values. It checks default/explicit bind addresses, no app/database port publication,
exact proxy/subnet consistency and 10 MiB × 3 stdout/stderr rotation per service.
It does not prove firewall behavior, runtime ingress, image build or deployment.
The Docker image now contains `alembic.ini` and `migrations/`; schema upgrades remain
explicit operator actions following the backup/upgrade procedure, never startup
mutation or permission to migrate production.

## Full synthetic recovery exercise

```sh
TEST_DATABASE_DISPOSABLE_TOKEN=fixture-acceptance-20260909 \
.venv/bin/python scripts/verify_fixture_recovery.py \
  --source test_browser_expenses --target test_recovery_20260909_v1 \
  --model models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  --output docs/acceptance/evidence/full-fixture-recovery.json
```

This exact run completed; **do not reuse its destination**. Inspect any interrupted
operation, database and `.qa/recovery-<target>` before choosing a new test destination.
The script requires a matching disposable marker and test-prefixed names, refuses
existing destinations, and uses only the checkout's private `.qa` PostgreSQL socket.
It creates inactive synthetic user/broker records, renders a fixture PDF, archives
that PDF/configuration/generated vault key and the explicitly selected existing
GGUF, then restores into a new directory/database. It verifies table counts/digests,
all file hashes, correct-key decryption and wrong-key rejection. The restored GGUF
must load and pass three structured synthetic tasks. Only its newly seeded source
records are removed; original source/model content is preserved. Restored artifacts
remain private under ignored `.qa` for inspection, with0600 files/0700 directories.

Observed result: **26 tables restored at0009_expense_audit**, vault decryption and
wrong-key rejection pass, restored1.5B model3/3 tasks, p95 2.654s. Evidence is in
`evidence/full-fixture-recovery.json` and `.txt`. This is synthetic local recovery,
not production/off-host disaster recovery or a production deployment. Real vault
keys must be backed up separately and privately with the matching database; losing
them makes encrypted credentials unrecoverable. Model license/checksum validation
and normal operator permissions still apply to any real deployment.

## Report disk admission and output budget

`STORAGE_MINIMUM_FREE_BYTES=1073741824` preserves a default1GiB free-space floor
plus `REPORT_MAXIMUM_BYTES=16777216` output allowance before each PDF render.
These are operational resource budgets, not financial mandates. The check runs
inside the existing single PDF worker slot. Output is capped while written to a
private0600 temporary file on the report filesystem; only complete nonempty output
is published, without replacing any existing destination. Normal failures remove
the temporary file. Typed PDF partial failures include DISK_LOW, REPORT_SIZE_LIMIT,
PDF_EMPTY and STORAGE_WRITE_FAILED. Existing report text/evidence can still persist.

The preflight cannot reserve space against other processes, cap renderer memory,
or make PostgreSQL writable on a full disk. Native cancellation retains the worker
slot; a hard crash or timed-out render may leave an orphan for reviewed cleanup.
There is no automatic data deletion or production retention policy.

Validation: storage-budget-first.txt (five targeted tests) and
browser-storage-budget.txt (real Chromium/PDF/owned download PASS).

## Report completion migration

Migration0010 adds generation_status and bounded stage-error metadata to reports.
Historical rows keep their ownership and become unverified. New source/model/PDF
failures persist as partial_failure; failed persistence returns no report ID.
The report list displays these states; PDF generation does not imply data coverage.
Run the normal reviewed backup and explicit Alembic upgrade workflow. The verified
full recovery archive at0009 is historical; do not reuse or overwrite that target.

## Independent simulator risk monitoring

An active user's explicit profile preference `monitoring_enabled: true` enables
background read monitoring. It does not grant trading authority. The periodic
risk job considers only that user's synthetic accounts with `mandate.fixture=true`;
external accounts are never candidates. Existing profile preferences can be
reviewed/edited through the authenticated browser profile form. No opt-in was
changed for real users during acceptance work.

Every60seconds the scheduler selects up to100 due accounts in oldest-due order.
It uses separate30second leases, bounded SQL/lock waits and a20second whole-cycle
deadline. Candidate selection and execution recheck active ownership and opt-in.
A live database-clock fence is checked before committing observation/halts and
completion together. A failed/expired worker cannot claim a completed observation.
Missed cycles are coalesced; they do not replay orders. No model, broker, PDF or
notification service is invoked. Cycle exhaustion is logged as RISK_CYCLE_TIMEOUT.

Risk halts only stop new orders; they do not cancel existing orders or liquidate
positions. No quote timestamp is refreshed by this observer. Missing/stale marks
therefore fail closed, and the new-order paths independently recheck risk even
between scheduled observations. A sleeping/offline host cannot observe or alert;
external heartbeat setup remains separately authorized work. One cycle can leave
additional accounts due under load; this is not a per-account60second guarantee.

Fixture evidence: risk-monitor-first.txt and risk-monitor-fencing.txt, covering
opt-in, simultaneous workers, no model construction, malformed opt-in and expiry
after a computed halt. The scheduler itself was not deployed to production.

### Broker observation evidence (migration0012)

Migration0012 introduced broker observations; current head is0018_job_lease_clock. Existing production instances
require separately authorized backup and explicit migration; startup only checks
this head. The three marked acceptance fixtures were upgraded, while prior
restore-test databases remain at their original verified versions. Downgrading
0012 drops its callback journal and requires preserving/exporting that evidence
first; do not run a destructive downgrade against real data as a routine rollback.

Brokerage Accounts now offers Saved execution evidence (local owned data) and
Read broker executions (separate browser confirmation, CSRF and existing vault
read consent). A new IBKR form does not preselect read consent. Refresh reads
available executions/open orders in one bounded worker; it never submits, binds,
cancels or liquidates orders, verifies a paper/live environment, or proves complete
history/late commission delivery. A failed window can preserve already-observed
facts with partial status. Disconnect/retry cannot imply permission to trade.

Actual provider connectivity remains a separate approval gate. Browser acceptance
uses a synthetic callback worker and explicitly disables the SDK connection path.

Broker evidence refreshes now use a90second scoped database lease and30second
pacing after completion. Saved evidence includes refresh_state, last_success,
next_due and bounded failure codes. A failed/partial read is not a successful
snapshot or financial reconciliation. An expired running attempt displays
interrupted; only an explicit new browser read may retry. There is no automatic
broker reconnect/order replay.

Timeout/cancellation keeps the lease until its deadline because the native SDK
read may still be cleaning up. The in-process worker slot remains occupied until
native completion. Lease expiry does not prove native termination; a later read
can still encounter broker client-ID/session failure and must report it. No
expired lease permits order submission or resubmission. Token-fenced completion
and journal publication share one database transaction, so a replaced/expired
worker cannot publish a successful refresh or late callback facts.

## Verified current-schema fixture recovery (2026-09-25)

`evidence/full-fixture-recovery-0012.json` records PASS for migration
0012_broker_observations:27 table count/content hashes match, filesystem hashes
match, synthetic vault decrypts and wrong key rejects, restored existing GGUF
passes3 structured tasks. Source fixture rows were removed; retained target is
test_recovery_20260925_v1 with private archive/work directory
.qa/recovery-test_recovery_20260925_v1. No production data or broker connections.

Reproduction uses `scripts/verify_fixture_recovery.py --source test_acceptance_expenses
--target <new_test_database_name> --model models/qwen2.5-1.5b-instruct-q4_k_m.gguf
--output <new_evidence_path>` with the matching TEST_DATABASE_DISPOSABLE_TOKEN.
Use a new test_ destination after inspecting prior run status; never overwrite
the retained target. The script validates source identity, disk space and paths.
This is local fixture recovery, not off-host storage or production restore approval.

## Report source admission

Synchronous report source reads share two report-specific admission slots and a
30-second per-call deadline. Busy/timeout results are explicit unavailable
collection evidence and yield partial reports. Timed-out native work retains its
slot until it actually returns; cancellation does not allow unbounded replacements.
The owner context propagates to the worker. Stored-news asynchronous lookup also
has a30-second deadline. This is separate admission from PDF rendering, although
the existing asyncio executor is shared. A native provider hang cannot be killed
by Python cancellation; restart/recovery remains an operator concern. These are
per-source bounds, not an end-to-end report SLA or measured risk-control isolation.


### Durable simulator event order (migration0013)

Startup/readiness now require0018_job_lease_clock; they never perform an
implicit upgrade. Existing production migration still needs separate approval,
a verified backup and a writer maintenance window. This migration takes an
exclusive execution_events table lock, preserves payloads/timestamps, and assigns
historical rows a deterministic observed_at/id order. Existing supported fills
are purchases, whose accounting commutes; historical ordering is not evidence of
external broker economic order. No new sale capability is enabled by migration.

New events receive a database GENERATED ALWAYS bigint identity and unique
constraint. Owned account locks serialize application callback writers; values
survive restarts and ignore wall-clock regression. Rollback gaps are expected;
never infer missing fills merely from gaps or reset the sequence. Reconciliation
uses the recorded sequence and hashes it with evidence. To roll back application
and database together, restore a reviewed backup; downgrade intentionally refuses
to discard ordering evidence.

Only marked test_acceptance_expenses/test_browser_expenses were upgraded in this
milestone (execution-sequence-fixture-upgrade.json). The soak database and earlier
restore databases remain at their previous revisions; upgrade an authorized
fixture explicitly before starting the updated soak runner. Production untouched.


### Strategy decision evidence (migration0014)

The explicit upgrade adds `strategy_decisions` with unique `(account_id,tick_key)`
and scope indexes. It neither backfills invented decisions nor rewrites orders.
Stop application writers and take a verified backup before an authorized upgrade;
startup only checks the revision and never performs DDL. Production upgrades still
require separate approval. Downgrade refuses to destroy decision evidence; rollback
uses a reviewed backup and compatible application version.

Decisions and their orders commit together under the account lock. A retained
no-trade tick cannot become a new order when a quote changes or a worker retries.
A submitted decision references the current order lifecycle on replay; its original
quote, risk and decision result remain retained. Evidence hash mismatch persists
`STRATEGY_EVIDENCE_CONFLICT`; investigate and reconcile before any new trading.
Hashes do not resist a database administrator rewriting both content and hash.
Owner account snapshots return the newest100 decisions with a truncation flag.
No decision deletion, revision-inventory transfer or halt clearing is implicit.


Current disposable recovery evidence: [0014 full restore](evidence/full-fixture-recovery-0014.json)
and [retained decision](evidence/strategy-decision-restored.json). For a new exercise,
run from the checkout using the already-installed local model and a new target:

```sh
PYTHONPATH="$PWD" TEST_DATABASE_DISPOSABLE_TOKEN=fixture-acceptance-20260909 .venv/bin/python scripts/verify_strategy_recovery.py --target test_recovery_new_decisions --output-prefix new-decisions
```

The wrapper proves the fixed acceptance source marker/revision, refuses existing
target/evidence/work directories, and cleans only its own synthetic source rows.
Run it after other source-database tests finish. Retain the resulting private
restore directory for inspection; this does not authorize production restoration.


### Simulator dispatch failure recovery

`SIMULATOR_JOB_TIMEOUT` and `SIMULATOR_STORAGE_FAILED` mean the active work
transaction failed and rolled back; they are not fills. Where the lease is still
owned, the next due time and in-app alert record the failure in a separate bounded
transaction. Inspect job failure codes, account halt status and retained decisions
before retrying. `failure_persistence=unavailable` means durable reporting could
not be established; a returned failure must not be counted as a successful job.
`SIMULATOR_CYCLE_TIMEOUT` returns partial failure alongside any already committed
results; an unfinished claimed job remains subject to lease recovery. Cancellation
and unexpected code errors propagate and roll back their active transaction.
No timeout path cancels broker orders, liquidates holdings or clears a halt.

[Current regression evidence](evidence/suite-bounded-dispatch.txt) includes actual
PostgreSQL lock contention and continuation to the next mandate, failed alert
persistence, external cancellation, stale workers and timeouts after intent creation.
No external broker runtime or host service-level guarantee is implied.


Synthetic split database recovery (no vault/model repetition):

```sh
PYTHONPATH="$PWD" TEST_DATABASE_DISPOSABLE_TOKEN=fixture-acceptance-20260909 \
.venv/bin/python scripts/verify_split_recovery.py \
  --target test_recovery_new_splits --prefix new-splits
```

Use fresh names; existing targets/evidence are refused. The verifier proves the
fixed disposable source identity, creates only its synthetic fixture, compares
all29table hashes, and verifies persisted split quantities/basis/cash/halt and
reconciliation. It cleans only its source fixture records. The restored database
and private archive under .qa/split-recovery remain for inspection. This is not
permission to restore production or clear a corporate-action review halt.

### Verify expense-history removal after restore
Migration0016 adds only minimal owner-scoped identity hashes; no automatic purge.
From this checkout, use a fresh target/prefix and the explicit disposable marker:

```sh
PYTHONPATH="$PWD" TEST_DATABASE_DISPOSABLE_TOKEN=fixture-acceptance-20260909 \
.venv/bin/python scripts/verify_expense_retirement_recovery.py \
  --target test_recovery_UNIQUE --prefix UNIQUE
```

The verifier proves source identity/revision, seeds and removes only its synthetic
records, compares all30table hashes, checks restored absence/tombstones/reimport
suppression, and cleans only its sourcefixtures. Existing targets/evidence are
refused. Archives and restored target remain private under .qa for review.
Restore older backups only with explicit review: pre-removal backups may restore
previously erased content. This runner does not select backup-expiry policy.

### Verify immutable valuation recovery
From the marked fixture checkout, choose fresh target and evidence prefix:

```sh
PYTHONPATH="$PWD" TEST_DATABASE_DISPOSABLE_TOKEN=fixture-acceptance-20260909 \
.venv/bin/python scripts/verify_split_recovery.py --with-dividend --with-valuations \
  --target test_recovery_UNIQUE --prefix UNIQUE
```

This compares31table hashes at0017 and exact source/restored observed-period
PnL after a synthetic split and dividend; sourcefixtures are cleaned. Fresh targets
are mandatory. Prior vault/model/expense-removal-specific evidence is separate.
Snapshot capacity is10000peraccount; capture refuses overflow rather than deleting
history or weakening currentrisk controls. User-facing capture is browsercookie+CSRF;
list/compare operations remain owner-scoped and bounded. No broker API is called.

## Job clock fencing (0018)

Current startup/readiness revision is0018_job_lease_clock. Reviewed upgrades require
stopped compatible writers and the usual verified backup; only marked disposable
fixtures were upgraded here. Migration adds nullable leased_at without fabricating
acquisition times for existing leases. Existing NULL leases cannot complete. They
can be acquired afresh only after their prior lease/due deadlines; do not manually
clear durable scheduling state to force missed work to replay. Each new acquisition
records PostgreSQL clock time. Completion requires matching unconsumed token and
`leased_at <= database_now < lease_until`; completing also invalidates the token.

A backward database clock step before acquisition time rejects completion, causing
transactional workers to roll back their work. Forward jumps/sleep that expire a
lease reject its old worker; fresh acquisition schedules the next observation from
current time rather than replaying every missed interval. This does not guarantee
wall-clock monotonicity or detect every small clock adjustment during a lease. A
clock step can delay jobs until time catches up; inspect clock/heartbeat and reconcile
before resuming authority. No host clock or power setting was changed. External
broker execution is not rolled back by a local PostgreSQL transaction.

Downgrade is refused: restore a reviewed backup with stopped compatible application
code. Do not run mixed writer versions across this migration; old code does not set
leased_at or consume completed tokens. Existing order, ledger, checkpoint and alert
records remain. Real-host sleep/network/Docker and external broker recovery remain
separate gates; these PostgreSQL tests simulate clock observations and stale leases.
