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
