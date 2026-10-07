# Retention controls and remaining scope

Expense raw payload cleanup is implemented, with no automatic default policy.
The authenticated browser user chooses a receipt age in whole days, previews up
to500 owned records, then separately checks approval and submits that exact batch.
The plan expires after10minutes. Changing the age clears approval. Changed payloads
or receipt timestamps invalidate the plan; a new preview is required. The model
has no retention tool and MCP credentials cannot use the browser-only endpoints.

The service locks the active owner and selected rows, compares a hash of policy,
owner and selected metadata, removes only raw_data, and appends minimal audit
records in one transaction. SQL computes raw-payload SHA256 so raw copies are not
loaded into application memory for preview. Audit stores hashes and policy, not
raw bank data. Amounts, currency, identities, category overrides, normalized
history, updated_at and synced_at are preserved. A later provider/import receipt
can supply a new raw copy with a new receipt timestamp. This does not revoke bank
consent, delete backups, or erase provider-held data.

API: POST /api/expenses/retention/preview with explicit retain_days; POST
/api/expenses/retention/apply with returned policy/plan_sha256 and explicit
confirm_raw_payload_removal=true. Both require an active browser cookie and CSRF.
No endpoint accepts another owner. Each request has a10s deadline, each SQL
statement5s, and apply lock waits2s. Zero matches does not enable approval. More
than500 matching rows require further previews; completion describes one batch.

Evidence: expense-retention-metadata.txt (three PostgreSQL tests for financial/clock
preservation, owner isolation, stale/changed plans and atomic rollback);
browser-expense-retention-final.txt (real preview, independent confirmation,
cleanup, empty re-preview, CSRF denial, existing transaction UI preserved).
The initial browser helper failed because asyncio.run shared Playwright's loop;
its corrected worker owns and closes its own event loop. Failure log retained.

Migration0011 adds an owned receipt-time partial index for nonempty raw copies.
A6000-row rolled-back fixture selected500rows through this index in0.703ms
without forcing the planner (retention-index-plan.json). This is a single fixture
observation, not a production latency guarantee.

Remaining required work is explicit:
owner-controlled normalized-history retention/export-and-purge policy; report/PDF
and chat retention with evidence-reference handling; source-specific news license
and retention policies; backup expiration and orphan file cleanup. No real data
was purged or production retention policy selected during acceptance work. Only
synthetic fixture copies were removed.

Reproduce the scale check with the Runbook's marked fixture environment:

```sh
.venv/bin/python scripts/verify_retention_plan.py
```

The verifier restricts the endpoint to this checkout's private .qa socket, proves
the test name and marker before inserting synthetic rows, rolls them back, and
refreshes fixture statistics. No planner enable/disable override is used.

Report storage reconciliation and interrupted-render cleanup are now implemented.
`python scripts/inventory_reports.py` reads only PDF paths from the configured
PostgreSQL database in a read-only transaction (5s SQL/15s request budget), includes
all owners and quarantined legacy references, and scans at most10000 directory
entries/references by default. It emits path hashes, counts, sizes and age, never
HTML, report titles or account identifiers. File/reference limits, symlinks,
missing storage, out-of-root references and clock anomalies yield partial status.
Its database/filesystem observations are explicitly non-atomic; an unreferenced
finished PDF is not permission to delete it and could belong to a pending commit.

On the Linux/WSL/container host, interrupted `.report-*` render temporaries have
an explicit operator-only cleanup command. Preview with a chosen aware cutoff
at least24hours old:

```sh
.venv/bin/python scripts/cleanup_report_temporaries.py \
  --reports-dir /absolute/private/reports --before 2026-09-14T00:00:00+00:00
```

Repeat the exact command with `--confirm-sha256 <preview-plan-sha256>` only after
reviewing the count/bytes. It rechecks directory identity and file metadata;
changed plans and exhausted scan limits remove nothing. Completed PDFs, recent
files, symlinks, directories and unrelated files are excluded. Removal or fsync
failures return partial status and the actual number removed; rerun a fresh
preview after investigating. The plan and result contain no source filenames.

New renderers hold a shared local directory flock; preview/cleanup requires an
exclusive nonblocking lock, so active rendering and cleanup cannot overlap.
Use only a private local directory with this matching writer version. This is
not a distributed/NFS lock and cannot coordinate older deployments or unrelated
writers. No automated production retention schedule or cutoff was selected.
This does not resolve completed orphan PDF deletion, report/HTML retention,
normalized expense/chat/news retention, or backup expiration.

Evidence: `evidence/report-retention-postgres.txt`,20tests passed including actual
PDF persistence failures, active-render exclusion, changed previews, truncation,
symlinks and partial removal/fsync failures. Only temporary synthetic fixtures
were deleted. Previous raw-expense retention remains intact.

Owner-controlled saved report retention is now available under **Report retention**
in the browser sidebar. No default age or automatic schedule is selected. The
owner chooses a positive age, previews at most20reports, and independently checks
approval before applying a10-minute content-bound plan. CSRF, cookie identity,
active-owner checks and row locks apply. Changed content, owner, cutoff or expired
previews reject the operation. All source ledgers and existing chat copies remain;
the screen states this boundary and recommends downloading needed PDFs first.

Phase1 commits a tombstone: HTML/title/PnL content is removed; report ID, owner,
period/creation dates and the previous content digest are retained. Phase2 attempts
PDF deletion outside the event loop through one bounded worker. Until it succeeds,
status is `retention_pending`; successful cleanup becomes `retired`. The owned PDF
endpoint returns410 for both, while other users still receive404. List/reload UI
shows removed/pending status instead of implying a complete retained report.
There is no atomic transaction across PostgreSQL and filesystem unlink: a crash
after unlink leaves pending state; a new owned preview/confirmation retries and
accepts an already absent file after syncing the directory. The original content
digest survives retries. Native work already authorized by the committed tombstone
may finish after HTTP cancellation; its admission stays occupied until completion.

Only regular directly contained report PDFs are removed, with the same local
exclusive directory lock used by temporary cleanup. Shared references (including
path aliases), symlinks, unsafe paths, inaccessible roots, scan capacity, render
contention or I/O failures leave cleanup pending. All owners' PDF references are
checked with a10000-row ceiling; no filenames are returned. Shared-file cases need
operator investigation and are never silently unlinked. Filesystem permissions and
private directory ownership remain part of the local deployment boundary.
No real reports were removed, no production migration occurred, and no policy age
was selected for real data. Backup expiration, chat copies, completed orphan PDFs,
normalized expenses and news retention still require their separate workflows.

Evidence:28 focused PostgreSQL/report/storage tests in
`evidence/report-owned-retention-recovery.txt`; real Chromium preview/confirmation,
CSRF/owner denial, tombstone/410/reload in
`evidence/browser-owned-report-retention.txt`. Only synthetic reports and PDFs
were removed. A follow-up ensures an already-absent PDF directory is fsynced before
marking completion; aggregate verification below supersedes this initial run.

Inactive owned chat content/tool evidence retention is also implemented; see
[CHAT_EVIDENCE.md](CHAT_EVIDENCE.md) for explicit preview/confirmation, active-turn
exclusion, bounded batches, stable evidence tombstones and stale-RAM-history
prevention. Source records/reports/backups remain separate, and orphan/unknown-owner
or unfinished conversations are excluded. The real PostgreSQL lock race and
Chromium flows passed (`chat-retention-concurrency.txt`, `browser-chat-retention.txt`).
Remaining retention work includes source-specific news license/expiration policies,
normalized expense-history export-and-purge, completed orphan PDFs and backups.

Declared expired news text and revision cleanup is implemented through the explicit
operator preview/confirm command documented in [NEWS.md](NEWS.md). IDs, URLs,
availability clocks and digests remain; ordinary ingestion cannot restore retired
content. Public and private-owner scopes are explicit, with20article/1000revision
bounds and changed-plan checks.24 PostgreSQL checks passed, including committed CLI
execution, in `evidence/news-cleanup-committed.txt`. No real news was purged.
Legacy unverified-source review, downstream copies and backup expiration remain
separate; this does not claim application-wide erasure of every derived copy.

## Normalized expense history

The owner can now choose **Export and remove expense history** in Expenses.
An explicit positive age selects at most100 settled transactions whose occurrence
and application receipt both predate the cutoff. Pending and recently received
revisions are excluded. Preview downloads the exact normalized batch as JSON
(with Decimal strings, currencies, account handles and original identity/clock
fields; no raw provider payload). The owner must verify that download and separately
approve removal. No default policy or automatic purge is selected.

The ten-minute plan binds owner, policy, complete exported values and raw-payload
hashes. Database reloads preserve canonical ten-decimal amounts in the hash.
Changed content, ownership, expiry or export hash rejects the entire transaction.
Purge deletes only the selected owner's history/raw copies and replaces category
change audit details with a minimal removal receipt. SHA256 identity tombstones
bind owner/provider/account/external identity without retaining those original
identifiers or amounts. Imports and provider sync use the same transactional
owner lock: a concurrent import waits, then reports a retired record as suppressed.
Suppressed records are counted separately from inserts and updates. This does not
revoke bank consent or erase reports, chat, user downloads, providers or backups.
A provider changing its identity can appear as a new record; no fuzzy deletion
rule or automatic restoration is inferred. No public tombstone-reset endpoint exists.

Migration0016 creates expense_retirements; startup/readiness require it. It does
not migrate or purge existing history automatically. No destructive downgrade:
restore a reviewed backup, considering that an older backup predating removal can
restore deleted content. Preview/apply require active browser cookie+CSRF,10second
request/5second statement/2second lock bounds and explicit export/removal flags.
Export is private,no-store. Models/MCP cannot invoke these browser-only endpoints.

Evidence:expense-history-concurrency-fixed.txt16PASS, including committed
import/purge race, rollback and inactive-owner checks; browser-expense-history-fixed.txt
realChromium/PostgreSQL PASS, export/confirmation/removal/reimport/CSRF/isolation.
Only synthetic fixtures were removed. Backup-expiry and completed orphan-PDF
workflows remain separate required scope.

## Completed orphan PDFs

The explicit local operator command below now covers completed PDF files left by
failed report persistence. There is no scheduled deletion or default cutoff.
First ensure this private local report directory is used only by the matching
application writer version; it holds a shared directory lock through PDF publication
and database commit. Older writers and remote/NFS storage are unsupported.

```sh
.venv/bin/python scripts/cleanup_report_orphans.py --before <aware-ISO-cutoff>
```

Use the intended deployment's configured DATABASE_URL and REPORTS_DIR. Cutoff must
be at least24hours old. Preview emits count/bytes and a plan digest, without names,
report content or owner identifiers. After review, repeat the exact command with
`--confirm-sha256 <plan-digest>`. This is operator authority over orphan storage,
not an owned-browser report removal endpoint; no model/MCP tool can invoke it.
No production cleanup is authorized or performed by this implementation task.

Each invocation obtains exclusive nonblocking directory exclusion, then a PostgreSQL
SHARE table lock before reloading every report PDF reference, including unknown
owners and pending retention. Reference inserts/updates/deletes cannot commit during
removal. A changed reference set or file identity/size/mtime/ctime changes the plan.
Only directly contained regular `report_*.pdf` files older than the cutoff and
absent from the reference set qualify. Recent files, render temporaries and unrelated
files remain. Symlinks/nonregular entries, out-of-root references, future file clocks
and exhausted scan limits refuse cleanup with zero removals. Default limits10000;
SQL deadline5seconds, lock wait2seconds, CLI async deadline15seconds. Local bounded
filesystem work runs synchronously in this dedicated operator process; slow kernel
I/O cannot be forcibly timed out and must not be run in a web request.

Unlink is irreversible and cannot be rolled back by PostgreSQL. Per-file metadata
is rechecked; I/O failure returns partial status and the actual number removed.
A successful result requires directory fsync. After partial failure, investigate
and preview again; already removed files are absent from the new plan. An old
confirmation never authorizes newly discovered files. Backups and downstream copies
remain separate. Tests removed only synthetic files in temporary directories.

Evidence: report-publication-lock-reproduction.txt reproduces the previous unsafe
publication/reference gap; report-orphans-first.txt36PASS covers publication fencing,
changed plans/references, aliases, unsafe storage, scan limits and partial failures.

Follow-up evidence:report-orphans-cli.txt11PASS including a new marked disposable
PostgreSQL database, real CLI preview/confirmation and competing reference-write
lock timeout. Only that test-created database was dropped. suite-report-orphans.txt
820PASS and browser-report-publication-lock.txt real Chromium/report persistence
PASS. The extra CLI test was added after full-suite collection; application code
was unchanged. Backup expiration remains open.

## Verified standalone database archive expiry

`scripts/expire_database_backups.py` now provides explicit preview/confirmation for
standalone PostgreSQL test archives emitted by the restore verifier. No automatic
age, schedule or minimum-count policy is selected. Operator supplies an aware
cutoff at least24hours old, `--keep` (at least1 per source), a private archive root
and every selected successful restore receipt via repeated `--evidence` arguments.
Each receipt binds the archive checksum and a hashed PostgreSQL system-identifier/
source-database pair. The actual archive checksum is reverified before every plan
and apply; the newest existing verified archives per source are protected even
when older than the cutoff. Unknown/unregistered files are never deleted.

New restore exercises default to `preserve_unclassified_bundle`; only an explicit
`verify_restore.py --standalone-retention` declaration makes that archive eligible.
Do not select that flag when the dump belongs to a filesystem/configuration/key
recovery bundle. Older evidence without source identity or scope is refused. The
current verifier is fixture-restricted, so this is tested local database-archive
lifecycle support, not an assertion of production or complete-bundle retention.

```sh
.venv/bin/python scripts/expire_database_backups.py \
  --archive-dir /absolute/private/archives \
  --evidence /absolute/verified-restore-older.json \
  --evidence /absolute/verified-restore-newer.json \
  --before <aware-ISO-cutoff> --keep <positive-count>
```

After reviewing count/bytes and protected_count, repeat with the returned
`--confirm-sha256`. The shared writer/exclusive cleanup directory lock spans dump,
restore verification and receipt publication. Matching writers and private local
storage are required; older writers/NFS are not coordinated. Evidence is bounded
at2MiB per receipt; default1000 files/receipts and10GiB total archive hashing can be
lowered. Streaming hashing bounds memory. Scan/byte exhaustion removes nothing.
Directory ownership and writable permissions are checked; archive/evidence final
symlinks, malformed/missing verification, future clocks, altered checksums and
changed plans are refused. Output contains only digests/counts/reasons.

Unlink cannot be rolled back. Partial I/O results report actual removals, and success
requires directory fsync. Receipts remain after expiry; a fresh preview safely
ignores already-absent archives and recalculates protected copies. Missing protected
archives invalidate an earlier plan instead of causing remaining copies to expire.
Filesystem/key bundle expiry and production encrypted/off-host retention still
require their separate coherent-set policy and authorized deployment validation.

Evidence:backup-expiry-bundle-guards.txt11PASS2.35s including real CLI on synthetic
archives. backup-expiry-standalone-restore.json/run.txt31table0017 restore PASS;
backup-expiry-real-preview.json protects its only verified archive, zero deletions.
The earlier backup-expiry-restore.json also passed31tables but predates explicit
standalone classification and is deliberately not eligible. No existing recovery
archives or databases were removed; new restore targets remain for review.
