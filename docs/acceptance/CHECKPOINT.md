# Resume checkpoint — 2026-09-08

**Read the newest milestone entries at the end first.** Earlier entries below are
historical checkpoints and may describe failures or missing capabilities subsequently
resolved. Current evidence: 332 full tests, plus focused degraded-inference/scanner
checks; real Chromium flows pass; CPU model and disposable restore evidence exist.
Mandatory local work remains, especially full risk/mandates, research UI integration,
news provenance/SSRF, expense UX/retention, full restore and soak. No external writes.

HEAD remains `65ea1d769c79bf77df3de1d4a3b6274168d92085`. All task changes are
uncommitted in this checkout. Do not reset, clone, or modify the Pi checkout.
Full original instructions were read from the attached file; PLAN.md tracks L01–L16.

## Completed and verified at this milestone

- 8 authority regressions passed: no model self-approval/mode change/global broker
  fallback; caller estimates cannot authorize excess notional; external writes denied.
- 7 financial regressions passed: fractional quantity, dated FX, currency/account/
  direction expense identities, missing fact rejection, per-currency totals,
  momentum rebalance valuation 108.333333333333 on 2024-02-01.
- 18 workflow tests passed (5 new + 13 existing): portfolio/scanner read selection,
  SPYL parsing, privilege catalog filtering, structured evidence budget handling.
- 2 report period/structured evidence tests passed.
- 26 dispatcher contract/safety tests passed with existing marshalling coverage
  deliberately separated from production authority checks.
- Initial existing PostgreSQL integration suite: 19 passed. After new ledger and
  migration cases: 26 passed, 1 failed. Failure was the previously vacuous sentiment
  assertion (`sentiment` is a string, not a dict). Corrected and made non-vacuous;
  rerun is required.
- Last broad unit run: 255 passed, 1 failed (old denial-message assertion). Corrected;
  subsequent schema/report/UI edits require a new broad run.

## Implemented since some earlier passing checks (verification pending)

- Frozen Alembic baseline + Decimal/account lifecycle migration + isolated simulator
  schema (0001_reviewed → 0002_precision → 0003_simulator).
- Startup verifies revision only; no implicit DDL or unknown-owner backfill.
- Simulator PostgreSQL service: independent single-use approval, immutable details,
  cash reservations under account row locks, partial/duplicate fill accounting,
  uncertain submission, cancel/fill race halt, persistent halt. Seven real-PG ledger
  tests passed, including concurrent reservations and reconnect persistence.
- Browser-only simulator routes and practice controls added to existing simulation
  screen. Human action binds cookie-derived session hash; no broker SDK import.
  JS syntax passed. Browser behavior has NOT been tested yet.
- Expense UI labels imported data, separates mixed currency totals, states page scope.
- Report PDF off-loop, typed failures, evidence hash/snapshot, period filtering.
- ARM64/Pi auto-deployment replaced by manual x86_64 CPU image validation only.

## Environment and interrupted operations

- WSL2 x86_64 Ubuntu 24.04, i7-11850H, 16 logical CPUs, ~31 GiB visible RAM,
  ~883 GiB available filesystem space. Existing 1.5B/3B/7B GGUF files present.
- Docker Desktop daemon unavailable (verified outside sandbox). GPU NVML access
  blocked in sandbox; physical RAM/cooling/sleep/clock/GPU and benchmarks unresolved.
- Isolated PostgreSQL 16.15 extracted under /tmp; no system installation. Cluster
  `/tmp/ia-acceptance-pgdata`, private Unix socket `/tmp/ia-acceptance-pgsocket`,
  port namespace 55439, no TCP listener. RUNBOOK.md has test URL/marker/stop command.
- Unit/integration operation handles 11331 and 14355 checked on resume: both finished
  exit 1 (failures above), not running. Initial broad sandbox unit run was cancelled.
- Sandbox AnyIO thread wakeup hung; the identical fully mocked HTTP test passed
  outside sandbox in 1.38s. Tests explicitly override application DATABASE_URL.
- No browser runtime installed: no Browser skill/plugin, no Playwright package or
  browser cache. Frontend testing skill loaded; authorized local Playwright setup
  is the next browser path. No browser QA claims yet.
- No broker connection, order, external notification, model download, production
  deployment, firewall/power change, or live enablement occurred.

## Next actions

1. Verify test PostgreSQL status before restarting; do not restart blindly.
2. Fix two known ruff long lines in reporter/dispatcher; format/check new routes.
3. Rerun affected unit/integration suites outside sandbox; include schema upgrades.
4. Install/lock local browser test dependency and run real browser login → simulator
   proposal → independent approval → fill → halt; cross-user/CSRF denial.
5. Continue unresolved original gates: actual broker contract/lifecycle adapter,
   scoped scheduler/durable alerts, provider-sync boundary, portfolio aggregation,
   cost-aware research, runtime inference bounds/benchmarks, auth revocation,
   migration/backup restore, real UI reports/alerts, 24-hour soak runner.
6. Save a concise checkpoint after every subsequent milestone.

External paper/bank consent, production deployment, live mandate and unavailable
host observations remain separate gates. Local work remains; do not call the goal
complete or blocked merely because external gates are blocked.

## Milestone update: resumed verification

- Ruff passed on new execution/finance/expense/report/migration modules and focused tests.
- Affected full runs now PASS: **258 unit**, **27 real PostgreSQL integration**.
  Evidence: `evidence/unit-after-simulator.txt`, `evidence/postgres-after-simulator.txt`.
- New database `test_acceptance_migrated` created in the disposable cluster with marker.
  CLI Alembic failed before schema mutation because Settings ignored DATABASE_URL and
  resolved its configured hostname instead. No database connection succeeded in that
  migration attempt. URL precedence is now fixed with a regression; rerun CLI chain.
- Playwright 1.62.0 added to the Poetry lock; package/browser installation pending.
- Session 5277 (dependency resolution) and 98532 (failed migration) both checked as
  completed. Do not recreate either database or re-add the dependency on resume.

## Milestone update: browser functionality and discovered regressions

- Full Alembic CLI chain now succeeded on fresh marked `test_acceptance_browser`.
  The earlier `test_acceptance_migrated` had already been populated by integration
  `create_all`, so it correctly refused a baseline CREATE; it was not stamped/deleted.
- Playwright/Chromium installed under checkout venv and `/tmp/ia-playwright`.
- First browser run exercised all simulator actions but failed console gate on
  WebSocket origin rejection. Fixed scheme detection and trusted proxy peer checks.
- Second browser run PASS for login, portfolio view, propose/approve/fill+fees/halt,
  tool self-approval denial, CSRF and cross-user denial, with zero console errors.
  Evidence: `evidence/browser-after-origin-fix.txt`; model is explicitly stubbed.
- Screenshot inspection found an existing responsive sidebar overlap on desktop →
  mobile resize. Added automatic close at breakpoint and wrapping header/evidence;
  visual/browser rerun pending. Do not claim the mobile layout passed yet.
- Portfolio totals now preserve precision and become partial/unavailable rather
  than summing unconverted currencies or inventing zeros. Focused tests in progress.

## Milestone update: brokerage boundary and precise totals

- **40 focused tests PASS**: IBKR explicit read consent/account scoping, per-currency
  summary, SPYL/IBIS2/EUR synthetic qualification, ambiguity rejection, failure
  disconnect/lock release, and closed submit/cancel gate on all four adapters.
  `evidence/broker-contracts.txt`. No broker network connection was attempted.
- Shared `src/execution/external.py` now guards retained SDK write entrypoints as
  well as dispatcher restrictions. IBKR synchronous reads own worker event loops,
  use readonly=True and dedicated nonzero client IDs, and filter actual account.
  External history/reconciliation remains unavailable; open orders are labelled
  snapshots and unknown ownership. Paper/live environment selection is configuration,
  not proof of external paper acceptance.
- **25 network/portfolio regressions PASS** (`evidence/network-portfolio.txt`). Tests
  explicitly force production Settings because root test fixtures set ENVIRONMENT
  to development. Unknown FX/valuation no longer fabricates USD totals.
- Browser functional test plus responsive DOM assertions passed. Screenshot capture
  initially caught the sidebar mid-transition; runner now waits for its geometry
  to leave the viewport before visual evidence. Rerun once for final screenshot.
- Original mandatory gates still incomplete: durable jobs/alerts/provider sync,
  revocation, advanced ledger/strategy mandates, cost-aware research, real model
  benchmarks, full report/alert browser path, backup/restore and soak, among others.

## Milestone update: durable operations

- **3 PostgreSQL operations tests PASS**: lease exclusion/fenced completion,
  expired-worker recovery, alert deduplication/ack/reopen, local delivery failure
  and retry, and alert cross-user denial (`evidence/operations-first.txt`).
- Migration 0004_operations adds job leases, alerts and a bank-sync checkpoint
  table. Browser database must explicitly upgrade from 0003 before next run.
- Scans/reports now iterate active users with `preferences.monitoring_enabled=true`,
  use durable leases and bounded callbacks, and persist scoped chat evidence.
  No unowned global Analysis writes or global broker credentials on that path.
- Simulator halt emits an in-app alert. Alert HTTP routes enforce user ownership;
  UI acknowledges alerts. Browser test extended to cover this and real report PDF
  creation/download with synthetic model/evidence, plus cross-user PDF denial.
  Extended browser rerun pending. No external notifications configured or sent.

## Milestone update: session lifetime and verified browser reports

- Interrupted operations checked: 302-test run completed; browser database revision
  was 0004_operations. No operation was blindly retried or database recreated.
- Extended real Chromium/real PostgreSQL/stub-model workflow PASS, including alerts,
  acknowledgement, real PDF creation/download and cross-user PDF denial. Mobile
  screenshot inspected: no horizontal overflow/sidebar overlap. Screenshot after
  reload correctly shows no currently selected fixture, not invented restored state.
- Added migration 0005_sessions and applied only to marked test_acceptance_browser.
  Logout persists token hashes; old cookies cannot replay. Active-account and
  revocation checks cover HTTP, WS before messages/with a one-second watchdog,
  SSE before data/at bounded intervals, and production tool calls. External writes
  remain closed even if a cancelled worker continues read computation.
- Cookie format now includes issuance time; legacy cookies require re-login. All
  session revocation uses database wall time; no reusable token is stored. MCP now
  requires MCP_USER_ID explicitly bound to an active user (no global identity).
- Full affected suite: **305 PASS**, evidence `evidence/suite-sessions-final.txt`.
  Earlier run's 2 failures were route-unit mocks missing the new auth-store boundary;
  no security assertion removed. Real PostgreSQL HTTP/revocation tests added.
- Browser including logout cookie replay + closure of an already-open WS: **PASS**,
  `evidence/browser-sessions.txt`, zero console errors in positive workflow. Per-run
  synthetic users prevent fixture quota buildup from making repeat runs unreliable.
- Added MCP production integration check after full suite; `sessions-mcp.txt` is the
  affected follow-up. Session 41465 may need result inspection on resume.
- No broker connection, external order, real notification, production deploy or
  new model download. HEAD unchanged; all implementation remains uncommitted.
- Remaining local work still includes provider sync, realistic research, actual
  model/resource measurements, full durable risk/mandates, provenance, retention,
  restore/soak and broader UI/CI acceptance. Do not mark overall goal complete.

## Milestone update: fixture-tested bank synchronization

- Added GoCardless protocol boundary, explicitly gated production factory, human
  consent/account/reconnect/disconnect API routes and durable scoped polling job.
  No bank/provider credentials were read and no provider network request occurred.
- Bounded requests/responses, encrypted account/token/reference storage, atomic
  per-account upserts/checkpoints, persisted retry/backoff, expired consent and
  same-account reconnect are implemented. Expense signed amount metadata/refunds,
  pending lifecycle and deleted-row summaries corrected without lossy rounding.
- **310 full unit/integration PASS** before final reconnect/tests additions:
  `evidence/suite-bank.txt`. **17 focused provider/PG PASS** after those additions:
  `evidence/bank-safety-final.txt` (session 78856 completed; inspect if resuming).
  Earlier failing call-log slice and missing optional reconnect parameter were fixed,
  not suppressed. `BANK_SYNC.md` documents protocol/evidence/remaining limits.
- Migration head remains 0005_sessions. No bank-schema mutation needed; 0004 already
  introduced durable state. External bank config defaults disabled. Actual bank
  consent/access, external paper and live readiness stay separate blocked gates.
- Next useful work: real local-model baseline and bounded inference cancellation,
  cost-aware research, full risk mandates, restore/soak; bank/UI/retention gaps remain.

## Milestone update: real inference baselines and disposable restore

- Added bounded model admission (4 admitted, 15s queue wait), 16-chunk stream buffer,
  native worker exclusion retained across async cancellation, bounded inference,
  and token-aware envelope budgets preserving structured omission markers.
  **16 focused workflow/lifetime tests PASS** (`evidence/inference-budgets.txt`).
  Sandboxed thread-wakeup test was inspected/cancelled; host rerun passed, matching
  the previously documented sandbox limitation. No native worker may invoke tools.
- Existing local models only, llama-cpp-python 0.3.20, CPU4/context4096:
  raw 1.5B JSON baseline 0/3 (Markdown fences; retained failure evidence), structured
  1.5B 9/9, median2.685s/p95-nearest-rank7.230s, peakRSS1972MiB; structured3B9/9,
  median4.056s/p957.247s, peakRSS3792MiB. Small synthetic direct-inference tier;
  no trade edge or full application acceptance implied. JSON/log evidence `model-*`.
- Repaired stale model prompt claims that it could self-confirm, change modes or
  route forex orders. Server-side policy remains the authority boundary.
- Real application default portfolio/scanner model benchmark with synthetic tools
  is running as session **55749**; checked live. Inspect its result before retrying.
  Files `model-default-workflows.log` / `.json`. A style-only long line in
  scripts/benchmark_workflows.py remains to fix.
- **Disposable restore PASS**: pg_dump/custom archive → new test_restore_20260908_a,
  23 tables, migration0005, per-table row counts and digests equal, source stable.
  Evidence `restore-database.json` / `.log`. No overwrite/drop or production data.
  Archive `/tmp/test_restore_20260908_a.dump`; runner refuses existing destination.
  Filesystem report/vault-key restore is still a separate pending requirement.
- Many mandatory local gates remain. Continue research/risk/provenance/UI/soak work;
  do not mark overall goal complete. No broker/bank connection or external order.

## Milestone update: research fixtures, CI browser tier, host and degraded inference

- Full unit/real PostgreSQL suite **332 PASS** (`suite-inference-research.txt`).
  Real Chromium after bank/auth changes **PASS**, `browser-after-bank.txt`.
- New cost-aware single-instrument replay: signal close→later open, fees/spread/
  slippage/FX, partial/nonfill, explicit splits/dividends, no fictional final sale,
  availability-time news dedup, PnL/exposure/turnover metrics. **6 tests PASS**.
  Fixed chronological fixture plan/result saved with data/code/plan hashes;
  conclusion INSUFFICIENT EVIDENCE, live NO-GO. This engine is not yet wired into
  the existing web historical simulator; integration and broader realistic data
  remain mandatory. Do not present synthetic returns as strategy edge.
- Actual app model benchmark session55749 finished (85.42s/27.12s). Compact prompt+
  CPU4 prefill rerun session29789 finished (13.33s/7.52s), correct read scopes/event
  contract; first answer is deterministic fallback, scanner includes known holdings.
- Model failure now yields explicit degraded deterministic reads; readiness checks
  loaded state and revision. **19 focused tests PASS** (`inference-degraded.txt`).
  Scheduled scans now record model failure after persisting partial evidence; this
  final small change needs its targeted test/full-suite follow-up.
- Real browser CI job added (Chromium + migrated disposable PG, synthetic model).
  Combined-coverage CI database now has the required disposable marker. Existing
  quality gates retained. Remote workflow execution/build remains unobserved.
- Windows hardware: physicalRAM68,408,107,008 bytes (~63.7GiB), WSL~31GiB. NVML:
  RTX3050Ti Laptop4096MiB, sampled65C/14.69W. Installed llama library is CPU-only.
  Read-only sleep timeout AC/DC=0; other sleep behavior and CPU cooling unverified.
  Windows clock reports synchronized status. No settings changed. MODEL_HOST.md
  records baselines, candidate budgets and still-pending resource/soak acceptance.
- No broker/bank connection, external order, real notification, cloud/model download,
  production deploy or OS setting change. All work remains uncommitted at original HEAD.

## Milestone update: public-content fetch boundary

- Added `news/http.py`: HTTPS-only/443, public address validation, DNS pinned to a
  numeric TCP target while TLS verifies original hostname, redirect revalidation,
  bounded DNS workers/timeouts/body size, and denial of private/mapped/transition
  address bypasses. RSS parsers receive bytes instead of fetching arbitrary URLs.
  Guardian and official-site scraper transports use the same boundary. No actual
  feed requests were made while developing this change.
- Source batches retain explicit failures, so an unavailable source is not reported
  as a successful empty ingestion. **55 focused source/ingestion/SSRF tests PASS**:
  `evidence/news-public-fetch-final.txt`. Session7714 terminal output inspected.
- Degraded scheduled scan regression **PASS**, `scheduler-degraded.txt`: partial
  evidence finishes persistence before the scoped job reports model failure.
- New finding requiring next implementation: newsletter URLs contain configured
  mailbox identity and globally stored email-derived content is not owner-scoped.
  `news/email_reader.py` constructs email://<mailbox>/<message-id>, then calls shared
  ingestion. Add explicit newsletter owner binding, private/quarantined visibility,
  hashed reference and user-scoped news search before treating news isolation passed.
  Never infer a bootstrap owner or expose legacy unknown-owner email rows publicly.
- News first-seen/available-at, content hashes/corrections/conditional-fetch durable
  checkpoints remain pending. No news schema migration has been added yet; head
  remains0005_sessions. Next planned revision number is still free.
- Risk/approved autonomous mandates, replay→web-simulator integration, expense UX/
  retention, full restore and 24-hour runner/observation remain mandatory local work.
  Keep goal active; no broker/bank connection or order occurred; live remains disabled.

## Milestone: newsletter ownership and full migration chain (resume run)

- Preserved original HEAD and staged/unstaged completed work. Prior /tmp infrastructure
  was absent on resume; no interrupted test/model/browser process was found. Recreated
  PostgreSQL 16.15 from extracted Ubuntu packages, private socket/no TCP, no OS service.
- Migration `0006_news_privacy` adds explicit owner and public/private/quarantined
  visibility. Existing email/non-HTTPS/newsletter rows remain unknown-owner quarantined.
  No automatic bootstrap assignment. Ingestion accepts owner only as a trusted argument;
  private references hash owner/mailbox/message identity; active-user checks precede IMAP
  and persistence. Search, headlines and SQL counts enforce visibility and deactivation.
- IMAP reads use a worker thread, TLS timeout, readonly mailbox and BODY.PEEK, bounded
  message count/body size; subject/sender/raw exception details removed from logs.
  No mailbox was contacted. Missing explicit NEWSLETTER_OWNER_USER_ID blocks ingestion.
- Unit suite **312 PASS** (`evidence/suite-news-privacy-unit.txt`); real PostgreSQL
  integration **40 PASS** (`evidence/news-privacy-integration.txt`), including all
  migrations 0001→0006 with legacy quarantine and private/public/cross-user/deactivation.
  Focused news tests **43 PASS**. Ruff passes changed news and migration/test modules.
- Current disposable DB `test_acceptance_news_privacy`, socket
  `/tmp/ia-acceptance-pgsocket`, port namespace55439, marker
  `fixture-acceptance-20260908`. TEST_DATABASE_URL:
  `postgresql+asyncpg://lulu@/test_acceptance_news_privacy?host=/tmp/ia-acceptance-pgsocket&port=55439`.
  Cluster `/tmp/ia-acceptance-pgdata`; extracted binaries `/tmp/ia-postgres-root` with
  LD_LIBRARY_PATH=/tmp/ia-postgres-root/usr/lib/x86_64-linux-gnu. Fresh Alembic head0006.
- Current source `git diff --check` passes. Historical staged raw test/Windows evidence
  contains trailing whitespace/CRLF, and staged config test predates whitespace fix;
  do not confuse staged snapshot with working tree or erase failure evidence.
- Mandatory remaining: durable news provenance/corrections/checkpoints, approved
  autonomous mandates/full risk, replay integration, expense UX/retention, complete
  restore/soak, broader UI/host verification. All aggregate local gates remain in progress.
  External paper/bank/live permissions unchanged. No broker connection or order occurred.

## Milestone: observed news revisions and historical availability

- Migration `0007_news_evidence` adds observed availability, content hash, provenance
  and append-only application revision storage. Existing content is archived with
  unknown availability rather than assigned a fictional historical availability time.
  Language/license/retention metadata remains explicitly unverified unless supplied;
  this is not a claim that provider licenses or retention decisions are resolved.
- Ingestion preserves first-seen `fetched_at`, atomically updates changed content and
  appends its exact revision. Exact repeated payloads are skipped. Search returns
  hashes/availability/provenance. `get_news_evidence_as_of` uses only revisions observed
  by the decision timestamp and enforces current ownership/deactivation.
- New correction regression initially exposed stale SQLAlchemy identity-map objects
  after upsert RETURNING, causing an incorrect archived correction. Fixed with
  populate_existing; before/after/as-of regression now passes. Initial failure kept
  in `evidence/news-correction-regression.txt`; final broader evidence below.
- **353 unit + real PostgreSQL tests PASS**, `evidence/suite-news-evidence.txt` (5.64s).
  Same marked disposable test_acceptance_news_privacy now at0007; production untouched.
  Ruff passes changed news/models/migrations/tests. Runtime readiness requires0007.
- Still pending: provider conditional-fetch/durable backoff checkpoints, syndicated
  content equivalence/entity licensing policies, replay UI integration, approved
  autonomous mandate/risk work and remaining matrix requirements. No aggregate gate
  declared complete. No actual IMAP/feed/bank/broker connection or order occurred.

## Milestone: independently approved simulator mandate records

- Added strict `MandateSpec` with explicit simulator environment, strategy/version,
  instrument allowlist, capital/position/order limits, daily loss/drawdown, order
  frequency, quote age, fee/spread, UTC hours/weekdays, quantity and review expiry.
  No implicit live or capital defaults. `0008_mandates` persists immutable proposal
  details/hash and independently authenticated browser approval provenance.
- Browser-only CSRF routes propose/review then approve with a session-bound nonce.
  Account lock serializes approval and supersedes the previous active revision.
  Model/MCP tools do not expose these routes or approval functions. This milestone
  creates mandate authority records; autonomous execution enforcement/runner is next.
- **27 targeted tests PASS**, `evidence/mandates-approval.txt`: independent approval,
  wrong session/nonce, replay, edits/expiry, full migration chain and HTTP regressions.
  Disposable DB now0008; production unchanged. No broker or bank activity.

## Milestone: approved forward simulator and marked-risk enforcement

- `execution/autonomy.py` executes only an approved immutable simulator mandate;
  worker input carries identities/tick correlation, never caller prices or policy.
  Enforces fixture/allowlist, scope, hours/expiry, quote/FX/lot/tick/fees, order and
  position/capital limits, frequency, uncertain-order reconciliation and durable halt.
  Account lock + durable tick key serializes duplicate workers and reservations.
- Marked equity, cost basis, fees, daily first-observation UTC PnL and persistent
  high-water drawdown are recorded in account risk state and submission evidence.
  Marked-loss/clock-regression halts persist; runtime commits denials instead of
  rolling back the halt. Frequency/capital checks follow the marked-risk calculation.
  This remains buy-only isolated practice; sells/reconciled external daily ledger,
  independent monitoring beyond expired mandates and complete risk snapshots remain.
- `execution/runtime.py` provides bounded forward ticks for up to100 approved active
  users' simulator mandates. Explicit constant-price synthetic feed; no market data
  or broker route. Scheduler coalesces missed ticks; no historic-order backlog replay.
  Browser practice offers separate review/approval of a clearly labelled30-minute
  example mandate; nonce never rendered/stored, changing displayed details disables
  approval of previously displayed details. Operator halt never liquidates holdings.
- Standalone mandate schema export exposed an import cycle hidden by pytest ordering.
  Fixed db package model exports to load lazily; direct module import/schema export
  and legacy `from src.db import Trade` verified. JSON schema saved in acceptance docs.
- **358 unit/PostgreSQL PASS** (`evidence/suite-mandates.txt`,7.06s); subsequent
  **6 mandate tests PASS** (`mandates-concurrency.txt`) include actual separate-worker
  concurrent tick deduplication. Forward runner unapproved/approved/fill/dedup PASS.
- **Real Chromium PASS**, `evidence/browser-mandates.txt`: prior workflow plus new
  mandate review→independent approval, desktop/mobile, zero console errors.
  Its summary list predates naming the added mandate check; the harness assertions
  did execute. Screenshots `/tmp/ia-browser-evidence`. Model still deterministic stub.
- Test DB test_acceptance_news_privacy and separate browserDB test_browser_mandates
  both head0008; marker/socket same as previous checkpoint. All named test/browser
  sessions finished; no app server remains. Original HEAD/staged work preserved.
- Next: tighten full mandate/risk/missing-data cases, simulator historical replay UI
  integration and accounting, news checkpointing, expense UX/retention, full restore,
  resource/soak/CI and acceptance documentation. Do not mark aggregate goal complete.
  No broker/bank/IMAP connection or external order; live remains disabled.

## Milestone: shared atomic expense persistence

- Extracted `expenses/persistence.py`; JSON imports and provider sync now share the
  same PostgreSQL conflict identity and category-override protection. Insert/update
  counts compare a generated row ID returned atomically, eliminating select/insert
  races. Import errors log only exception type, not sensitive transaction parameters.
- **9 affected unit/PostgreSQL tests PASS**, `evidence/expense-shared-upsert.txt`.
  Previous full358 suite and six concurrent mandate tests remain valid for unaffected
  paths. Expense import UI/pagination/refund signs and stronger concurrent import
  verification are next. Goal remains active; no external bank/broker activity.

## Milestone: expense import, signed display and pagination in Chromium

- New file-import control accepts bounded JSON, current-user persistence and explicit
  click. Page controls use bounded server offsets. Refunds show positive signs,
  transfers preserve signed direction, and unknown currency no longer defaults EUR.
- New concurrent import test initially could not run because /tmp infrastructure had
  disappeared. Earlier commentary claiming that test passed was corrected immediately;
  failure logs retained. Recreated binaries/data under ignored `.qa/` in this checkout.
  `scripts/start_acceptance_postgres.sh` starts only that owned private-socket cluster.
- Current socket `$PWD/.qa/socket`, PGDATA `$PWD/.qa/pgdata`, binaries
  `.qa/postgres-root/usr/lib/postgresql/16/bin`, LD_LIBRARY_PATH
  `$PWD/.qa/postgres-root/usr/lib/x86_64-linux-gnu`; no TCP listener/OS service.
  DBs `test_acceptance_expenses` and `test_browser_expenses`, marker
  `fixture-acceptance-20260909`; both currently0008 before next audit migration.
  Chromium installed at `$PWD/.qa/playwright`. All `.qa/` state verified git-ignored.
- **5 affected tests PASS**, `evidence/expense-concurrent-import-final.txt`: two
  independent transactions return one inserted/one updated, override preserved.
- **Real Chromium PASS**, `evidence/browser-expenses-restored.txt`: actual202-record
  file upload, duplicate202updates/0inserts,200→2→200pagination, mixedcurrency unavailable
  aggregate and separatecurrencynotes, positive refund, plus prior mandate/order/
  reports/auth workflow. Model stub only; no bank/broker connection.
- In progress: category override UI/API and owner-scoped minimal audit; new migration
 0009_expense_audit written, NOT YET applied/tested. Runtime readiness now expects0009.
  Complete this work and migrate only the disposable DBs before next browser run.

## Milestone: category overrides, minimal audit and safe page export

- Added cookie/CSRF-owned category-edit API, explicit override preservation and
  minimal `ExpenseAudit` records (category before/after only, no bank payload copy).
  Migration0009 applied only to the two marked .qa test databases. Readiness expects0009.
- UI category selector uses the existing taxonomy; reimport preserves override.
  Explicit JSON export includes only current displayed page and pagination metadata,
  with no raw provider payloads. User B cannot read/edit User A's expense records.
- **360 full unit/PostgreSQL PASS**, `evidence/suite-expense-ui.txt`; subsequent
  **2 expense concurrency/audit tests PASS**, `evidence/expense-category-audit.txt`.
  Duplicate identical edits yield one audit event; cross-owner edits return404.
- **Real Chromium PASS**, `evidence/browser-expense-category-final.txt`, including
  actual category editing, override through duplicate import, downloaded page JSON,
  cross-user expense read/edit denials plus prior flows. Initial browser failure
  `browser-expense-category.txt` was an invalid test taxonomy choice (education is
  grouped under work); corrected to the actual supported work key without changing
  product validation. No console errors. Category/export assertions are in harness
  even though compact printed check list groups them under expense workflow.
- Current runtime lives in ignored .qa, not /tmp; use previous checkpoint's socket/
  marker paths. No active browser/test process remains; owned PostgreSQL is running.
  Original permissions unchanged; no external provider/broker/IMAP connection or order.
- Remaining local work includes historical replay integration, fuller mandate/risk
  and financial reconciliation, durable news fetching, bank setup/status UI, retention,
  evidence/tool persistence, filesystem restore, resource/soak/CI and final audit.

## Milestone: historical web simulation uses cost-aware portfolio replay

- Added `research/portfolio.py`: shared Decimal cash/basis ledger, later actual-session
  fills, costs/FX/volume limits, partial residual expiry, explicit split/dividend input,
  monthly momentum rotation and retained buy/hold/SMA/RSI workflows. No fictional
  terminal sale. Input/code/parameter hashes and exact source/result snapshots retained.
- `research/history.py` validates source currency/exchange and uses locked
  exchange-calendars4.13.2 for sessions/DST/holidays; historical FX must precede open.
  Actual-calendar/synthetic-provider tests pass (Xetra DST, holidays, currency/FX).
  Provider split-adjusted units are explicitly retained; split events are not applied
  twice. Independent vendor adjustment/delisting/availability reconciliation remains
  unverified and is surfaced in source limitations. No Yahoo request was made here.
- `run_simulation` now calls the corrected engine; legacy helper regressions retained.
  UI chooses USD/EUR/GBP base currency, displays cost assumptions/source gaps and
  downloads owned replay evidence. Large bar snapshots stay out of history summaries.
  `scripts/replay_saved_evidence.py` reproduces without network and detects tampering.
- **373 unit/PostgreSQL PASS**, `evidence/suite-portfolio-replay.txt` (24.57s), and
  **real Chromium PASS** `browser-replay-final.txt`: run/save EUR replay, fee evidence,
  download/offline reproduction, cross-user denial, plus prior flows. Initial browser
  verifier import-path failure retained in browser-replay.txt, fixed in harness.
- Subsequent indicator review fixed SMA initial-trend vs true-cross semantics and
  changed RSI to the retained ta.RSIIndicator Wilder convention. **9 portfolio tests
  PASS**, `replay-indicator-final.txt`, including exact signal comparisons, split/
  dividend and tamper checks. Full suite/browser evidence precedes these indicator
  edits; reuse unaffected checks and verify final affected paths before final acceptance.
- Poetry lock check passes with existing metadata deprecation warnings. New dependency
  uses official exchange_calendars release/source documentation; no large model download.
- Next: bounded heavy-work concurrency, stricter missing-session/valuation provenance,
  remaining news/bank/retention/reconciliation/soak/CI and full gate audit. Original
  authorization unchanged, no broker/order/bank/IMAP/market-provider connection occurred.

## Milestone: bounded simulation/PDF work and final replay compatibility

- `operations/workloads.py` admits at most2 simulation workers and1 PDF worker,
  with immediate busy results rather than an unbounded queue. Async timeout/cancellation
  retains the permit until the native worker finishes; contextvars propagate to workers.
  HTTP and tool simulation paths share the same pool. Full HTML parsing/PDF rendering
  now runs in the PDF worker. Simulation timeout120s, PDF60s; these are resource
  ceilings, not latency acceptance claims. Inference has its separate prior budget.
- **46 targeted worker/web/report/simulator tests PASS**, `bounded-heavy-work.txt`.
  Cancellation and timeout tests prove the occupied worker slot cannot be reused early.
- **Real Chromium PASS**, `browser-bounded-replay.txt`, including offline replay
  reproduction with current engine hash, full expense/mandate/report/auth workflows.
  No console errors, no external/provider/broker calls. Full final suite recorded in
  `suite-bounded-replay.txt`; inspect its terminal result before reporting total.
- All ordinary targeted checks and browser sessions finished. Separate PostgreSQL
  fixture remains under ignored .qa with head0009. Overall gates remain incomplete;
  next planned work is an explicit resumable engineering-soak runner/measurement plus
  remaining operational/news/retention/bank/reconciliation requirements.

## Milestone: resumable soak runner and explicit account helper boundary

- Rechecked prior operations: both soak smoke logs ended SMOKE_PASS; no pytest,
  browser, fixture HTTP, or soak operation was still running. Full prior suite is
  **377 PASS in 10.42s**; browser-bounded-replay.txt remains valid for prior changes.
- Added `scripts/soak_acceptance.py`; constraints, exact resume/start procedure,
  budgets and honest observation limits are in SOAK.md. Latest smoke: 72.22s,
  32 control samples, three service restarts, halt p95 43.69ms, native model 3/3.
  No 24-hour observation claimed. Full observation waits for stable source code.
- Removed global credential fallback from Alpaca/Binance/Coinbase helper configs.
  Missing owner/account or wrong broker fails before SDK access. Portfolio/history
  helpers and the report collector also require explicit accounts. Dispatcher logs
  omit user IDs and lookup exception text. SQL engine disables echo and hides bind
  parameters; this is not a claim of complete application log redaction.
- **42 targeted tests PASS in 1.54s**, evidence/scoped-helper-reads.txt. Tests cover
  globally configured credentials with missing/invalid account, all three read
  surfaces, retained explicit account configuration, and report/portfolio regressions.
  Full suite must be checked for downstream compatibility after this boundary change.
- HEAD remains 65ea1d769c79bf77df3de1d4a3b6274168d92085; existing staged/unstaged
  changes preserved. No commit/push/deploy, broker connection/order, provider/IMAP
  call or OS configuration change. All original restrictions remain in force.
- Remaining: update stale architecture/audit/capability docs; durable news fetch,
  bank setup/status, retention/evidence persistence/complete restore, reconciliation,
  broader model/host/CI and acceptance review. Overall goal remains active.

## Milestone: bank status/clocks and browser controls (final verification in flight)

- Added owner-scoped SQL sync clocks independent of page/date filters; manual
  imports advance application receipt only, provider empty successes remain visible.
  Provider SSE notifications include receipt and success times. Per-connection UI
  shows disconnected/retry status, separate timestamps and missing setup credentials.
- Added explicit consent link, account selection, renewal and local disconnect UI.
  No external bank calls: UI controls tested through intercepted synthetic responses,
  separately from real PostgreSQL + mock HTTP provider contracts. External consent
  links are not followed. Local disconnect copy distinguishes provider revocation.
- 12 targeted clock/import/provider tests PASS (bank-sync-clocks.txt); initial real
  disabled-state browser PASS (browser-bank-status.txt). Browser-controls initial
  run failed because owned PostgreSQL was stopped; pg_ctl confirmed no live server,
  then scripts/start_acceptance_postgres.sh restarted only that private cluster.
- Retry completed controls but verifier counted intentional fixture HTTP409 as an
  unexpected console error. Verifier now records exactly that URL/status separately,
  asserts one expected error, and still fails all other console/page errors.
- Next run caught real pagination race (bank status awaited after expense render).
  Fixed by independent bank status refresh plus pending expense refresh coalescing;
  periodic refresh now preserves current page, filter changes reset page explicitly.
- Current browser command is the RUNBOOK.md .qa command, output
  evidence/browser-bank-pagination-final.txt, process handle 93150 at launch.
  Inspect terminal log/process before retrying. Full suite output is
  evidence/suite-bank-controls.txt; inspect terminal result before claiming total.
- Added ACCOUNTING.md and BROKER_CAPABILITIES.md, updated stale architecture map;
  these explicitly retain external reconciliation/sells/retention limitations.
  Latest prior full authority suite: 393 PASS. Original permissions unchanged.
- Continue final browser validation, save result checkpoint, then remaining durable
  news ingestion, retention/evidence/restore and broader lifecycle/model/host/CI gates.

## Milestone verified: bank controls, sync clocks and pagination

- **394 unit/PostgreSQL tests PASS in 20.69s**, evidence/suite-bank-controls.txt.
- **Real Chromium PASS**, evidence/browser-bank-pagination-final.txt: existing
  routes/real PostgreSQL workflows preserved; bank disabled state plus intercepted
  synthetic consent/selection/rejection-retry/renewal/disconnect controls and mobile
  width checked. Exactly one deliberate fixture HTTP409 is separately recorded;
  unexpected console errors are empty. No external consent link was followed.
- Initial browser failures retained: bank-controls.txt (stopped fixture database),
  bank-controls-retry.txt (expected409 verifier classification), bank-controls-final.txt
  (real pagination race). Product race fixed; final run passes unchanged page counts.
- Receipt/provider clocks, disabled setup handling, signed imports and overrides,
  preserved-page background refresh now verified. Final suite predates only the
  browser-discovered JavaScript pagination fix; full browser evidence covers that fix.
- No browser/test operation remains active from this milestone. PostgreSQL is the
  owned .qa instance, verified/restarted after process loss. No production/external
  connections, broker orders, bank consent, notification or OS changes occurred.
- Next highest local operational gap: durable news-source checkpoints/conditional
  fetch/backoff with explicit service identity, then retention and full restore,
  execution reconciliation/model breadth and acceptance audit. All gates retain scope.

## Milestone: loopback deployment defaults and exact proxy configuration

- Found the audited all-interface publication still present in Compose. Replaced
  it with LOCAL_BIND_ADDRESS default127.0.0.1; LAN access is explicit and documented.
  PostgreSQL/app remain unpublished. Added 10MiB ×3 container log rotation.
- Nginx preserves public Host port for HTTP as well as WS. Compose sets exact
  Nginx peer172.30.80.3/32 in a dedicated configurable subnet; Uvicorn proxy rewriting
  disabled so application peer checks remain authoritative. Other peers cannot
  forge forwarded HTTPS scheme. Docker image now includes explicit migrations.
- Windows Compose v5.5.1 is available even though the WSL docker wrapper is not.
  `scripts/verify_compose_config.py --docker '/mnt/c/Program Files/Docker/Docker/resources/bin/docker.exe'
  --output docs/acceptance/evidence/compose-local-ingress.json` validates synthetic
  loopback/LAN configurations without daemon startup or resolving real .env secrets.
  Inspect latest terminal verifier result (handle57682 at launch) before claiming PASS.
  Targeted origin regression output: evidence/compose-proxy-origin.txt.
- README/.env.example/RUNBOOK document effective configuration versus unobserved
  Docker/WSL ingress. No runtime deploy, Docker startup or OS/firewall changes made.
- Remaining mandatory work retains scope: durable news fetch, evidence/retention,
  fuller reconciliation/restore, model/host/CI review and 24-hour observation.

## Milestone verified: ingress configuration and baseline audit consolidation

- Final Compose verifier returned PASS for both synthetic profiles with exact
  Nginx peer consistency, unpublished app/database and bounded logs; output in
  evidence/compose-local-ingress.json. No daemon/build/deploy was started.
- Four origin tests PASS (2.86s), evidence/compose-proxy-origin.txt. Actual Docker/
  WSL ingress, LAN firewall, image build and source-address observations still pending.
- AUDIT.md maps all ten distinct regression expectations and every named audited
  path to current evidence or explicit remaining work. ACCOUNTING.md and broker
  capability matrix state incomplete reconciliation/sells/commission functionality.
- L01 baseline is now PASS based on preserved HEAD/dirty-state, feature map, audit
  disposition and measured host/unknowns. All remaining implementation gates retain
  their prior status; no overall completion or deployment eligibility is claimed.
- All verification handles from this milestone are terminal. Next: durable public
  news source identity/checkpoints/conditional fetch and remaining mandatory local gates.

## Milestone: durable news source identity, leases and conditional retrieval

- Added src/news/runtime.py using existing JobLease schema (no migration): explicit
  active principal, per-RSS/site/Guardian-section lease/checkpoint and bounded retries.
  Scheduled owner must be configured NEWS_SERVICE_USER_ID; tools pass authenticated
  context. Missing identity blocks before network. No automatic admin assignment.
- RSS conditional validators/304 keep first availability and immutable revisions.
  Article publication and successful checkpoint share one fenced transaction via
  optional caller-owned ingest session. Cancellation leaves lease for expiration;
  stale worker cannot publish. Two native fetch slots remain occupied until work exits.
- Retry-After bounded seconds/HTTP-date, per-source backoff and local alerts added.
  Partial source failures cannot silently become successful empty feeds while not due.
  API/scraper sources retain per-source cadence/retry without conditional caching;
  source licensing/retention/syndication remain incomplete, documented in NEWS.md.
- 51 initial targeted tests PASS; 65 retry/evidence tests PASS; **403 full unit/
  PostgreSQL tests PASS in31.53s** (suite-durable-news.txt). Subsequent source orchestration
  test added; final retry-wait/Guardian metadata refinement running targeted tests in
  evidence/news-durable-final.txt (handle28111 at launch). Check terminal result first.
- Previous source orchestration handle33783 finished; inspect news-durable-scheduler.txt
  for its result. No external feeds, broker connections/orders, provider/IMAP calls,
  notifications, production deploy or OS changes. RFC9110 documentation was read.
- Baseline L01 PASS; other gates retain original scope. Next review final source
  tests, checkpoint results, then retention/evidence/restore and execution reconciliation.

## Milestone verified: durable news with production-like settings

- Final targeted tier: **46 PASS in4.45s**, news-durable-production-settings.txt.
  New complete-orchestration test exposed legacy root MagicMock interval (TypeError),
  not a provider failure. Source fixture now uses actual production Settings;
  successful feed commits while failed feed remains partial/retry_wait, without refetch.
  Prior failures and diagnostic outputs remain preserved.
- Full final suite output: evidence/suite-durable-news-final.txt (handle11797 at
  launch). Inspect terminal result before reporting. Source code is formatted and
  targeted Ruff checks pass. No live/external service has been contacted.
- Next required recovery work: current-head database plus report/vault-key/filesystem
  restore. Existing verify_restore.py only accepts old /tmp sockets and database-only
  restore; adapt it for owned .qa fixtures and extend synthetic filesystem/key recovery.

## Milestone verified: current database, filesystem, vault and model recovery

- Previous execution was rejected before it started by automatic approval review
  due to account usage limit (reset Sep10 03:46). No workaround attempted. After
  reset and new continuation, normal review approved restarting confirmed-stopped
  private PostgreSQL and the synthetic recovery run. No production service touched.
- scripts/verify_restore.py now permits owned .qa sockets/archive destinations as
  well as legacy /tmp, creates archives privately, and still refuses overwrite.
  New verify_fixture_recovery.py restores a synthetic inactive broker record and
  matching generated vault key, real rendered PDF, fixture config and copied
  existing1.5B GGUF. Source fixture rows removed afterward, original model unchanged.
- **PASS** full-fixture-recovery.json/.txt:26 tables at0009, matching DB/file digests,
  correct vault decryption/wrong-key rejection, restored GGUF3/3 tasks,p95 2.654s.
  Artifacts remain `.qa/recovery-test_recovery_20260909_v1`; restored test database
  `test_recovery_20260909_v1` already exists. Never blindly retry/overwrite it.
  Recovery handle9627 is terminal. No broker connection/order or provider call.
- Latest full unit/PostgreSQL suite before recovery-script-only changes is **405
  PASS in31.64s**, suite-durable-news-final.txt. Scripts pass focused Ruff checks.
- Next high-priority local gap: orchestrator persists only user/final text best-effort,
  drops tool evidence/action status, and truncates profile JSON by characters.
  Add durable bounded redacted evidence and truthful persistence/error/cancellation
  status with per-user restart tests; then retention and remaining lifecycle/host gates.

## Milestone: durable chat evidence and truthful completion

- Added src/chat/persistence.py using existing ChatMessage.tool_calls JSON (no schema
  change). Authenticated owner creates durable in-progress user/assistant records;
  tool snapshots save before delivery; complete answer/done emit only after DB commit.
  Failed model turns persist failed state; cancellation saves interrupted state and
  collected evidence. Terminal turns cannot be overwritten or accessed cross-owner.
- Bounded structured snapshots redact credential/nonce/account-secret fields and
  URL credentials/query/fragment; omitted data is explicit. Profile JSON no longer
  sliced after serialization. Historical metadata is labelled untrusted/non-current
  execution proof; oversized context uses the owned evidence link rather than broken
  JSON. Snapshot limits are32 events and16KiB/event, history context8KiB per turn.
- Browser exposes owned evidence download and saved/incomplete state on history.
  Legacy messages retain previous API fields; no bank/expense data scope added to model.
  WebSocket exception/profile-history logs now avoid raw exception/session text on
  touched paths; this is not a claim of complete application-wide log redaction.
- **4 real PostgreSQL tests PASS in1.59s**, chat-evidence-first.txt: saved-before-done,
  restart metadata, secret redaction, cross-owner/terminal mutation denial, cancellation,
  model failure and final storage failure. **Real Chromium PASS**, browser-chat-evidence.txt:
  evidence download/reload/cross-user404 plus all prior workflows, no unexpected errors.
- Final helper adds an8KiB historical-context fallback; full suite running to
  evidence/suite-chat-evidence.txt (handle from latest tool). Browser result predates
  only that internal context-budget refinement; targeted/full tests cover final helper.
- Full synthetic recovery remains PASS26tables/head0009, vault/PDF/model restored.
  Latest prior full suite405PASS. All external/live/production restrictions unchanged.
- Next: inspect final suite, finish retention and data export/purge policy/test boundaries,
  then remaining broker lifecycle/reconciliation, task/model/host/CI and acceptance audit.

## Milestone verified: durable chat and bounded history

- Final suite **412 PASS in19.04s**, evidence/suite-chat-evidence-final.txt. Initial
  suite-chat-evidence.txt stopped at collection because unit/integration test modules
  shared a basename; unit module renamed, no tests removed or thresholds weakened.
- Real browser evidence download/reload/isolation PASS remains valid; subsequent
  internal context-bound helper and final unit/integration suite cover the final code.
  CHAT_EVIDENCE.md records persistence order, bounded redaction and incomplete states.
- No current chat/browser/test process remains. Current schema still0009. Full
  recovery artifacts and database remain under .qa/test_recovery_20260909_v1.
- Remaining: full-period expense export and retention/resource policy, broader
  lifecycle/reconciliation/model/host/CI gates. Original authorization unchanged.

## Milestone verified: full-period expense export

- Added /api/expenses/export and a separate browser action for all categories in
  the selected period. Repeatable-read snapshot uses500-row keyset batches, exact
  signed/source-currency strings, opaque account handle, no raw provider payload.
  Authentication rechecked per batch/while slow streaming. Limit16MiB/100000records/
  60s returns explicit partial completion; browser refuses to label partial download
  complete. Existing displayed-page export preserved.
- **3 PostgreSQL tests PASS in2.11s**, expense-export-first.txt: concurrent new import
  excluded from consistent snapshot, precise fractional amounts, cross-owner scoping,
  limit and revoked-session partial trailers. **Real Chromium PASS**,
  browser-expense-export.txt:202-record full-period download and populated mobile
  width plus prior chat evidence/report/mandate/expense/isolation flows.
- Concurrent pyproject.toml edits appeared: expanded Ruff rules, line-length120,
  import length ordering, tidy imports/codespell config. Preserved these edits and
  fixed only unsupported `length_sort` spelling to `length-sort`. No rule disabled.
  Current global Ruff audit finds179 issues (141 import-order,27 nested-context,
  four suppress-style, two comments, two ternaries, two Depends defaults, one line).
  Next: safe style fixes, inspect remaining findings and full suite/browser as needed.
- Latest pre-export full suite412PASS; export targeted/browser evidence extends it.
  No production/external operations; completed restore targets remain untouched.

## Milestone verified: expanded lint and complete regression rerun

- Interrupted context-manager cleanup had completed; inspected its result before
  proceeding. All expanded Ruff rules now PASS, evidence/ruff-expanded-final.txt.
  Preserved concurrent pyproject settings, assertions and exception semantics.
- Full unit/PostgreSQL suite **415 PASS in50.79s**, suite-expanded-lint.txt.
  Real Chromium/PostgreSQL/stub-model workflow **PASS**, browser-expanded-lint.txt;
  no unexpected console errors, zero broker connections/orders. Replay reproduction
  checked again after source import changes. Both test processes exited0.
- HEAD remains65ea1d769c79bf77df3de1d4a3b6274168d92085,309 working-tree paths;
  git diff --check PASS. No commit, production deployment or live permission change.
- Next: disk/resource admission and retention policy boundaries, then remaining
  broker reconciliation/model/host/CI acceptance work. PostgreSQL already running;
  prior full recovery target remains untouched.

## Milestone verified: bounded report storage

- Report writer checks free space before rendering (default1GiB floor plus16MiB
  allowance), caps bytes during writes, publishes private0600 complete files
  without overwrite, and removes temporary output on ordinary failures. Typed
  partial failures preserve truthful report status. Settings/.env/Runbook updated.
- **5 targeted tests PASS in2.25s**, storage-budget-first.txt: low-space refusal,
  mid-render size/failure cleanup, private publication/non-overwrite plus report
  period/JSON regressions. **Real Chromium/PDF PASS**, browser-storage-budget.txt,
  process91559 exited0; actual generated PDF downloaded200, cross-owner404.
- Full415-suite result predates only this storage feature; targeted/browser checks
  cover its affected paths. Ruff PASS after edits; no new schema or deployment.
- Remaining: retention policy/fixture cleanup, broader risk/broker reconciliation,
  model tasks and host/CI/soak acceptance review. All external/live restrictions
  unchanged; no broker connections/orders.

## Milestone verified: persisted report failure status (2026-09-15)

- Source errors and empty model completion now return partial_failure; provider
  exceptions become stable codes rather than raw text. Reports persist completion
  status/errors, and browser lists display status after reload. Report PDFs state
  known collection/model gaps. Historical reports become unverified, not success.
- Added additive0010_report_status migration and reviewed-schema legacy-report
  upgrade assertion. Applied only after explicit test-name/current-database/marker
  checks to test_acceptance_expenses and test_browser_expenses; both verified0010.
  First migration wrapper failed before mutation (Settings.database_url is a
  read-only property); separate env-configured Alembic subprocesses succeeded.
- **422 unit/PostgreSQL tests PASS in9.85s**, suite-report-status.txt.
  **Real Chromium/PDF/report-status reload PASS**, browser-report-status.txt.
  Ruff PASS, ruff-report-status.txt. Handles91401/45344 exited0.
- Runtime/readiness/soak runner now require0010. Existing soak DB and restored
  target remain0009; they were NOT migrated or overwritten. Full recovery evidence
  at0009 remains historical and must be extended with a fresh target for0010.
- Remaining: retention policy/fixtures, broader lifecycle/reconciliation and
  model/host/CI review, final acceptance audit. No production deployment, external
  broker connection, order, real provider/notification or live enablement.

## Milestone verified: current-schema database recovery

- verify_restore.py restored marked test_browser_expenses to the new target
  test_restore_report_20260915. **PASS26tables at0010_report_status**, exact row
  counts/hashes match, including12synthetic reports,24chat rows and2828expenses.
  Evidence: restore-report-status.json/.txt. Handle24889 exited0.
- Private archive .qa/restore-report-status/test_restore_report_20260915.dump
  and new target remain for review. Never overwrite/retry this destination.
  Older0009 full vault/PDF/GGUF recovery remains valid for unchanged filesystem
  components; current0010 database recovery now independently verified.
- Next: explicit retention policy, bounded owner-scoped purge/preview and fixtures;
  remaining broker reconciliation, model/host/CI and final gate audit unchanged.

## Milestone verified: expense raw-payload retention

- Added explicit browser age/preview/checkbox/apply flow, cookie+CSRF only, no model
  tool. Default policy unset. Owner/payload/receipt/policy hash and10minute expiry
  protect reviewed batch;500row limit,10s request/5s SQL/2s lock bounds. Active
  owner and rows locked; removal+hash-only audit atomic; normalized financial
  records, categories and receipt/update clocks unchanged.
- **425 full tests PASS in9.91s**, suite-expense-retention.txt. Subsequent
  metadata-only SQL SHA256 selection **3PGtests PASS in0.30s**,
  expense-retention-metadata.txt. Real Chromium **PASS**,
  browser-expense-retention-final.txt; initial helper asyncio.run/Playwright-loop
  failure retained in browser-expense-retention.txt, fixed with owned worker loop.
- Browser removes exactly one aged synthetic owned raw copy, requires independent
  checkbox after preview, preserves200-row page, empty re-preview disables apply,
  no-CSRF403. No real data affected. Schema remains0010.
- RETENTION.md documents scope/limits. Next: indexed retention scans and broader
  history/report/chat/news retention, then reconciliation/model/host/CI gate work.
  Current-schema restore target test_restore_report_20260915 must not be reused.

## Milestone verified: indexed raw-retention scans

- Additive0011_retention_index adds partial Btree(user_id,synced_at,id) only for
  nonempty raw payloads. Query uses the same literal predicate; raw contents are
  not indexed or fetched into application memory. Active readiness/soak requires0011.
- Verified fixture identities before upgrading test_acceptance_expenses and
  test_browser_expenses from0010 to0011; restored targets/soak DB untouched.
- **4 PostgreSQL retention/migration tests PASS in1.29s**, retention-index-tests.txt;
  Ruff PASS, ruff-retention-index.txt. Controlled6000-row transaction used actual
  planner selection (no enable_seqscan override), selected500rows via
  ix_expense_raw_retention in0.703ms; retention-index-plan.json. Fixture rows rolled
  back. This is one query observation, not a production p95/SLO claim.
- Last browser retention PASS predates only index/schema-readiness change. Next:
  preserve a reusable scale verifier, verify current startup, then broader
  history/report/chat/news retention and remaining original gates. Latest full
  suite425PASS;0010restore plus0011upgrade tests remain complementary evidence.

## Milestone verified: reproducible retention scale and current startup

- Added scripts/verify_retention_plan.py, restricted to the explicit checkout .qa
  socket/port and marked test_ database.6000synthetic rows are rolled back; fixture
  statistics refreshed afterward. PASS500rows/index selection in0.863ms,
  retention-index-reproducible.json. Run with existing TEST_DATABASE_URL/token.
- **Current0011 Chromium startup and all workflows PASS**, browser-retention-index.txt,
  process76364 exited0. Evidence explicitly lists raw-payload preview/approval.
  Ruff and git diff --check PASS. No test/browser process is outstanding.
- Next highest-priority local lifecycle gap: late/revised commission callbacks
  and persisted fill valuation provenance. Keep simulator boundary explicit;
  no external connection/write authorization. Broader retention and other
  original gates remain listed and must not be silently deferred.

## Milestone verified: versioned simulator commissions

- src/execution/commissions.py stores absolute commission revisions, original
  currency and explicit dated FX. Before-fill observations persist; fill consumes
  highest revision. Late corrections adjust cash/order fees/position basis only
  by the delta. Duplicates charge once; older observations retained without
  regression; conflicting same revisions denied. Account-first locks serialize
  concurrent delivery across sessions. Not connected to any external SDK.
- Fill evidence now preserves principal/base/source currency, multiplier, FX/time
  and applied fee. Approval/mandate stores reserved_base. Late costs exceeding
  original budget or available reserved cash are recorded and persistently halt
  new orders; legacy missing valuation/budget triggers reconciliation halt.
- **16 targeted PGtests PASS in1.14s**, commissions-first.txt.
  **428 full tests PASS in10.00s**, suite-commissions.txt.
  **Chromium PASS**, browser-commissions.txt. Ruff PASS, ruff-commissions.txt.
  Handles67817/54032/43627 exited0.
- Initial test attempt rejected by auto-review usage limit (retry4:43PM), before
  process creation. Reported; did not bypass. Clock later17:58UTC was past reset;
  identical command through normal approval succeeded. No ongoing review blocker.
- Next risk gap: manual approvals use realized_pnl-only loss checks while
  autonomous ticks use marked equity. Unify effective checks and ensure HTTP
  rejection cannot roll back a required durable halt. Broader retention, broker
  reconciliation/model/host/CI gates remain. No external connection or order.

## Milestone: marked manual risk verified; broad checks running

- Added execution/risk.py with bounded marked position valuation, current FX,
  explicit no-external-flow initial-capital and first-UTC-observation loss checks.
  Both manual proposals/approvals and approved autonomous orders call it. Stale
  positions, uncertain orders, malformed budgets/baselines and clock regression
  fail closed. Original per-mandate risk rules remain in force.
- RiskDenied marks an intentional durable halt. Browser risk_checked_command
  commits only this deliberate risk outcome before raisingHTTP409; ordinary
  policy errors still roll back. No order authority or reservation is granted.
- **19 targeted PGtests PASS in2.02s**, manual-risk-first.txt. Actual command
  boundary tests prove mark-loss with realized_pnl=0, stale/uncertain denial,
  persisted owner-scoped halt/alert and unapproved/reserve-zero order across
  sessions. Full suite/browser now running: suite-manual-risk.txt and
  browser-manual-risk.txt; inspect tool handles before retry after interruption.
- Prior full428/browser PASS remains before this change. Schema0011 unchanged.
  Next: inspect broad checks, independent periodic risk monitoring, then remaining
  reconciliation/retention/model/host/CI gates. External/live restrictions unchanged.

## Milestone verified: manual marked-risk regression completion

- **431 unit/PostgreSQL tests PASS in13.54s**, suite-manual-risk.txt.
  **Chromium full workflow PASS**, browser-manual-risk.txt. No new schema change;
  current0011. Manual approval still requires independent browser event/CSRF,
  while global marked risk cannot be bypassed through a manual proposal.
- Next: separately leased periodic simulator risk monitoring (explicit fixture
  opt-in, no broker/model access), before broader reconciliation/retention/model/
  host/CI acceptance work. Latest handles82046/12011 have final success logs;
  inspect handles if resuming before assuming any running operation.

## Milestone: independent periodic simulator risk verified

- Added execution/monitor.py and60second APScheduler registration. Only active
  users explicitly opted into monitoring and their labelled synthetic accounts
  qualify. Due-order selection100/cycle,30s leases,20s whole-cycle cap, SQL5s/lock2s.
  Rechecks identity/opt-in; DB clock fence precedes atomic risk/checkpoint commit.
  No model/broker/PDF access, no quote refreshing, no order creation/cancellation.
- **8 targeted operations/risk tests PASS in1.03s**, risk-monitor-first.txt;
  **3 monitor/fencing tests PASS in1.83s**, risk-monitor-fencing.txt, including
  actual1s lease expiry after computed risk halt. No stale publication.
  Ruff/diff checks PASS; handles98856/17946 exited0.
- Full suite running to suite-risk-monitor.txt; inspect its handle before retry.
  Prior431-suite/browser are still before this scheduling feature. Schema0011.
- Next: full-suite result, updated short control/load soak against current code
  (do not claim24hours), then broader reconciliation/retention/model/host/CI gates.
  Original external/live/production restrictions remain unchanged.

## Milestone verified: full risk-monitor suite; new smoke running

- **434 unit/PostgreSQL tests PASS in11.36s**, suite-risk-monitor.txt.
  Current code now includes independent leased simulator risk observation.
- Verified .qa/soak-smoke-v1/v2 checkpoints SMOKE_PASS and actual runner processes
  absent before new run. Positive test_soak_acceptance marker checked, upgraded
  only that disposable DB from0009 to0011; old recovery targets untouched.
- New smoke running in .qa/soak-smoke-v3, tool handle51579. Command:
  TEST_DATABASE_URL="postgresql+asyncpg://lulu@/test_soak_acceptance?host=$PWD/.qa/socket&port=55439"
  TEST_DATABASE_DISPOSABLE_TOKEN=fixture-soak-20260909
  .venv/bin/python scripts/soak_acceptance.py --hours 0.025 --interval 2
  --restart-every 20 --model models/qwen2.5-1.5b-instruct-q4_k_m.gguf
  --output .qa/soak-smoke-v3
- Evidence stream docs/acceptance/evidence/soak-smoke-v3.txt. Do not change source,
  static assets, dependency files or benchmark/soak scripts during the observation: 
  their fingerprint is enforced. Do not duplicate a live runner or count downtime.
- This is90second engineering smoke only, not24hours or production in-process
  inference. No external connection/trade/provider operation is authorized.

## Milestone verified: current-code control/load smoke

- .qa/soak-smoke-v3 completed **SMOKE_PASS**,90.165seconds,49control samples,
  four owned service restarts, haltHTTPp95=27.112ms against250ms budget, no failures.
  Existing local1.5B GGUF benchmark PASS (model-0000-c845841c.json). Handle51579
  exited0; observation freeze ended. Evidence: soak-smoke-v3.txt/checkpoint.json.
- No24hour claim: this measures separate-process model CPU contention plus
  deterministic HTTP fixture service, not production in-process inference, Docker
  restart, OS sleep/resume, or external broker/provider connectivity.
- Next: IBKR environment/account boundary review. Current source checks declared
  environment and managed-account membership, but declaration is not independent
  environment proof. Official connection/paper docs being reviewed; no connection
  attempted. Preserve all completed work,434-suite baseline and original gates.

## Milestone verified: truthful IBKR identity/environment boundary

- _config now rejects absent account ID/owner or wrong broker before lock/SDK
  construction, consistent with other retained adapters. Account reads expose
  managed_account_match separately from declared_environment; verified_environment
  remainsNone with operator_configuration_only provenance. No port/prefix inference.
- **31 targeted broker tests PASS in1.11s**, ibkr-environment-boundary-final.txt.
  Invalid-identity fixtures otherwise contain valid read-consent/config fields;
  assertions prove no lock acquisition or SDK construction. Ruff PASS.
- Corrected BROKER_CAPABILITIES.md overstatement that environment itself was
  verified. Current official IBKR connection/paper docs reviewed and linked there.
  No actual broker connection, submission, cancellation, or real-account probe.
- Full434 baseline remains before these focused IBKR changes; the31targeted tests
  cover affected reads. No pending test/soak process. Next: durable external
  callback/reconciliation boundary through fixtures, broader retention and
  model/host/CI gates. Goal remains active; no aggregate completion claim.

## Milestone verified: internal simulator reconciliation and approval clock ordering

- HEAD remains65ea1d769c79bf77df3de1d4a3b6274168d92085; preserved existing dirty
  tree. No interrupted test/browser/soak was running when resumed. Original pasted
  instructions reread in full. No external broker/provider operation performed.
- Added bounded account-scoped execution/commission reconciliation against cash,
  positions, fees and reservation totals. Incomplete evidence remains unverified;
  balances are never overwritten. Global new-order risk persists a discrepancy
  halt; HTTP denial commits it. This is NOT external broker reconciliation.
- Initial affected suite:15pass/1failure (reconciliation-initial.txt) exposed
  approval time sampled before account-lock acquisition. Sampling now follows
  locking; explicit injected clock regression remains rejected.
- Fill principal/fees and reservations reject unsupported Numeric(28,10) precision;
  partial release rounds down to ledger scale, leaving dust reserved until final
  fill. No implicit database rounding of these intermediate amounts.
- Full unit/isolated PostgreSQL suite **448PASS14.29s**, suite-reconciliation.txt;
  Ruff affected files PASS. Added partial-fill/late-commission DB roundtrip,
  four balance-tamper cases, incomplete evidence, unsupported precision and
  durable HTTP discrepancy halt. No browser rerun yet for this milestone.
- Next: deepen reservation provenance/evidence digest and callback recovery;
  broader retention, model/host/CI and original gate gaps remain. L01PASS,
  L02-L14IN PROGRESS, L15/L16BLOCKED. Live remains disabled.

## Milestone verified: reservation provenance and current browser regression

- New fill evidence records released_reserve_base. Active order reservations
  reconcile against approved reserved_base minus releases, so jointly altered
  account/order totals no longer hide discrepancies. Missing historical release
  evidence remains unverified. FX validates source currency and same-currency rate.
- Reconciliation hashes its actual inputs as well as its result. Added joint
  reservation-tamper regression. **449full tests PASS13.78s** in
  suite-reconciliation-final.txt; fullRuffPASS ruff-reconciliation.txt.
- **ChromiumPASS**, browser-reconciliation.txt, desktop/mobile simulator/manual
  approval/mandates/fills/fees/expenses/retention/reports/isolation/revocation.
  Test handles69305/69892 both exited0; no pending process.
- Next change begun after these results: expose current internal reconciliation
  evidence in the existing owned account snapshot, with bounded SQL/lock/request
  time; browser assertion added. This API addition not yet verified. No external
  operations or authorization changes. Aggregate gates unchanged.

## Milestone verified: inspectable owned reconciliation snapshot

- Existing account snapshot now returns current internal reconciliation and input
  hash under the existing active-owner check. SQL5s/lock2s/request10s bounds added.
  **ChromiumPASS**, browser-reconciliation-snapshot.txt, including consistent
  internal scope/hash assertions and existing cross-user denial. Handle14794exit0.
- Applied the default-clock-after-account-lock fix to mandate proposal/approval
  and autonomous ticks too. **17targeted execution/mandate/manual-risk tests PASS
  1.86s**, clock-lock-ordering.txt; handle80436exit0. Explicit supplied test clocks
  remain unchanged. Browser runtime began before this clock-only follow-up;
  targeted tests cover it. No test operation remains running.
- Full449suite baseline remains valid for reconciliation; latest clock-only and
  snapshot changes have focused evidence above. No broker connections/orders;
  live disabled. Remaining original gates are unchanged and must be continued.

## Milestone verified: fractional reservation dust

- Added a partial fill whose ideal reservation release exceeds10decimal places;
  database reload preserves conservatively retained dust, and final fill releases
  exactly the remaining reservation. **9reconciliation tests PASS0.94s**,
  reconciliation-dust.txt; handle80498exit0. FullRuffPASS in
  ruff-reconciliation-final.txt. No thresholds weakened or evidence overwritten.
- Halt alert follow-up now carries actual reason rather than generic "halted",
  and states that existing orders/positions need separate review. Account snapshot
  includes halt_reason. This changes no cancellation/liquidation authority.

## Milestone verified: actionable persisted halt alerts

- **10affected manual-risk/operations/monitor tests PASS2.68s**,
  actionable-halt-alerts.txt; handle86615exit0. Checks prove specific persisted
  reason survives denied approval and explain remaining order/position review.
  FullRuff and git diff --checkPASS. No pending test process.
- Next review found news upsert ignores provenance-only corrections (license,
  retention, entities) when article text hash stays equal, and does not update
  corrected source attribution. Implement and test immutable metadata revisions
  without changing first-seen time or claiming verified provider permissions.

## Milestone verified: immutable news metadata corrections

- News upsert now appends a revision when provenance/source/sentiment changes even
  if text hash remains identical. Corrected source attribution updates the current
  article; original first-seen timestamp and previous revision remain unchanged.
  Availability records observation of the correction, never its publication date.
  Exact repeated corrected input remains deduplicated. Source-supplied licensing
  metadata is evidence, not verified permission or execution authority.
- **23news/privacy/runtime/research tests PASS1.18s**,
  news-metadata-revisions.txt. New PostgreSQL regression checks original evidence,
  source/license/entity/sentiment correction, stable content hash/first-seen, and
  no duplicate revision. FullRuff and git diff --checkPASS. Handle5894exit0.
- No running operations. Full449suite baseline plus subsequent9reconciliation,
  17clock-ordering,10halt-alert and23news tests remain the accurate evidence tiers;
  do not claim a newer full-suite total without running it. Latest Chromium
  snapshot test passed before later clock/alert/news changes, covered separately.
- Remaining: external callback/reconnect/reconciliation fixtures; strategy-owned
  sells and full corporate-action/flow PnL; source policy/syndication and broader
  retention; model task breadth, host/container/CI and24hour observation gates.
  Safe productive work remains. Goal ACTIVE, L01PASS, L02-L14IN PROGRESS,
  L15/L16BLOCKED. No broker connection/order, bank/IMAP connection, production
  deployment, real notification, paid call or live enablement occurred.

## Milestone verified: durable broker observation journal foundation

- Added0012_broker_observations and a normalized append-only callback journal.
  It stores execution/commission/order-status facts independently of simulated
  balances. Exact repeats deduplicate; conflicting same-identity payloads and
  correction-family versions remain available rather than silently applying cash.
  Actual account/exec IDs are hashed; environment remains declared/unverified and
  ownership external_or_unknown. No submit/cancel capability is introduced.
- **4PG journal/migration tests PASS1.83s**, broker-journal-first.txt: cross-user,
  wrong-account atomic rejection, vault consent, rebind isolation, correction
  history, bounded reads and concurrent/new-session replay deduplication.
- Only three positively identified marked fixtures upgraded0011→0012;
  upgrade-broker-observations.txt. Production and existing restore targets untouched.
  Startup/readiness require0012. No pending test handles31499/59080; bothexit0.
- Follow-up unverified changes: lock active owner through commit, sanitize schema
  validation failures, reject execution-after-observation, let provider-revoked
  owners read existing local evidence, update soak requiredrevision0012.
- Next: test these follow-ups, implement callback SDK normalization/collection and
  discrepancy projection, connect bounded read-only pipeline. Journal is a tested
  foundation, NOT a complete external lifecycle or verified broker connection.

## Milestone verified: callback window and interrupted fixture recovery

- Follow-up PG run initially failed before tests because fixture socket refused
  connections: broker-journal-validation.txt. Checked owned pg_ctl status and
  started existing .qa cluster; PostgreSQL logged interrupted shutdown recovery
  and became ready (handle9335exit0). No fixture deletion/reinitialization or
  duplicate live server. Retried same affected tests: **7PASS1.99s**,
  broker-journal-recovery.txt; handle34432exit0.
- Added SDK-shaped CallbackWindow: bounded1000events, selected account filtering,
  execution/commission/status normalization, explicit snapshot request, no fake
  zero for missing commission, no history-completeness claim. Disconnect/request
  failure retains received facts as partial. All handlers removed in finally.
  Three pure SDK fixture tests prove order, disconnect, capacity and cleanup.
- Added refresh_observations service: single worker slot40s, scoped read config,
  SQL5s/lock2s/request10s phases, rechecks consent/active owner/active account and
  actual-account binding after worker. Cancellation cannot release native slot
  early or persist late result. It has no scheduler/public route yet; runtime
  integration and broader broker lifecycle remain incomplete.

## Milestone verified: consent-safe callback refresh service

- **12targeted tests PASS1.43s**, broker-refresh-authority.txt; handle49603exit0.
  Post-worker rebind, revoked consent, inactive user and inactive broker account
  each reject persistence. Partial successful observations remain partial after
  persistence. Response strips raw callback/account objects. No external SDK used.
- Added browser GET saved observations and CSRF/independent-confirm POST refresh;
  broker account UI offers both separately. New IBKR enabled/read-authorized
  checkboxes default unchecked (previous UI incorrectly defaulted consent true).
  Test-only server substitutes synthetic callback worker and explicitly prevents
  any IBKR _connection. No scheduler or model tool invokes the refresh.
- New validation RUNNING: full suite handle68484 -> suite-broker-journal.txt;
  Chromium handle21439 -> browser-broker-journal-first.txt. Poll these before retry.
  This milestone's new API/UI/full integration not yet accepted. Live remains
  disabled; external paper and true broker lifecycle validation remain blocked.

## Milestone verified: complete suite with broker journal

- **463unit/PostgreSQL tests PASS20.67s**, suite-broker-journal.txt;
  handle68484exit0. RuffPASS and JS syntaxPASS. Schema/readiness0012 included.
- First Chromium run ended on stale expected text "Simulated strategy halted"
  after prior verified alert copy changed to explicit stop-new-orders wording.
  Failure retained browser-broker-journal-first.txt; handle21439exit0 (wrapper
  prints log tail; actual verifier failed). Updated assertion to current wording,
  preserving halt behavior requirement. New run handle12587 is active:
  browser-broker-journal-second.txt. Poll before retrying.

## Browser defect reproduced and repaired: refresh CSRF

- Second Chromium run reached new journal controls and got403 on confirmed
  refresh: UI omitted X-CSRF-Token. Server safeguard worked correctly.
  browser-broker-journal-second.txt retained; handle12587exit0 (verifier failed).
- Added existing csrfToken() header to that fetch, no server-policy relaxation.
  JS syntaxPASS. Third run handle39870 active -> browser-broker-journal-final.txt.
  Full463suite remains valid; only browser client/header and test-copy changed.

## Milestone verified: browser-owned broker evidence workflow

- **ChromiumPASS**, browser-broker-journal-final.txt; handle39870exit0.
  Actual account form defaults read consent/enablement off; explicit fixture
  configuration, saved empty journal, dismissed confirmation (no ingestion),
  confirmed synthetic read (2persistedfacts), saved fractional quantity/unknown
  environment, hidden raw account ID, cross-user denial, CSRF denial and false
  confirmation422 verified. Existing workflows still pass desktop/mobile.
- Full463unit/PGPASS baseline plus finalRuff/JSsyntax/diffchecksPASS. No running
  operations. Both browser failures retained and fixed, not suppressed.
- API paths: GET /api/broker-accounts/{id}/observations (owned local evidence);
  POST .../observations/refresh (cookie,CSRF,confirm_broker_read=true). Worker
  remains read-only; no model/scheduler tool grants refresh authority.
- Next: external observation discrepancy projection and bounded pagination;
  continuous/reconnect coverage and complete broker reconciliation remain gaps.
  Original gates unchanged: L01PASS,L02-L14IN PROGRESS,L15/L16BLOCKED. No external
  connection/order/provider action; live disabled. Migration0012 only fixtures.

## Milestone verified: callback evidence review and bounded pagination

- Added deterministic review of hash integrity, conflicting execution/commission
  versions, correction families and unpaired evidence. Never infers balances,
  complete history, or strategy ownership; even paired facts stay unverified.
  Refresh persists scoped in-app review alerts with actual reason and no outbound
  delivery. No trading authority or simulator balance mutation is introduced.
- Added account/binding-scoped keyset cursor pages. Cross-account and stale
  binding cursors reject; subsequent/truncated pages explicitly mark partial
  review scope. Concurrent new arrivals require restarting browsing, documented
  in response. UI offers next page and resets its cursor after refresh.
- **17affected tests PASS1.41s**, broker-review-pagination.txt (includes alert
  scope/reason, invalid-batch atomicity and five facts across2/2/1pages).
  FullRuffPASS/JSsyntaxPASS. Handle36910exit0. Previous463suite remains baseline.
- Chromium paging verification now running; check current tool handle/log
  browser-broker-review.txt before retry. Uses real backend pages (limit1) and
  synthetic worker only; external SDK connection remains explicitly blocked.

## Milestone verified: browser callback review pages

- **ChromiumPASS**, browser-broker-review.txt; handle28475exit0. Real backend
  limit1 pages show execution then commission, next-page control works, partial
  review warning is visible and saved-evidence control resets after final page.
  Existing desktop/mobile workflows, independent confirmation, CSRF, ownership
  and session revocation remain passing. No pending processes.
- Current evidence:463full-suite baseline,17subsequent affected tests and current
  ChromiumPASS; no inflated aggregate test count. Ruff/JSsyntax/diffchecksPASS.
- Next required work: full external position/cash snapshot comparison and durable
  connection/recovery coverage; strategy-owned sells/flow/corporate-action PnL;
  broader retention and news-source policy; model breadth/host/container/CI and
 24h observation. Preserve all completed changes. Goal ACTIVE and gate statuses
  unchanged; external paper/live eligibility blocked. No external connection,
  order, production deployment, notification or live enablement occurred.

## Milestone verified: typed broker balance snapshots and payload bounds

- Added typed position/cash snapshot facts to0012's existing JSON journal (no
  new schema revision). Explicit reqPositions/reqAccountSummary observations
  retain account/conId/currency, fractional quantity and broker-reported average
  cost; cash stays per source currency, including current $LEDGER- prefix. BASE
  aggregate is excluded. Duplicate contracts/currencies reject as ambiguous;
  empty positions and missing cash are distinguished. Sequential requests are
  explicitly non-atomic; no FX/PnL/trade inference or simulated balance update.
- Snapshot comparison reports exact position and per-currency changes, incomplete
  requests, overlapping windows and payload hash mismatch. Even unchanged pairs
  do not establish balance reconciliation/history/strategy ownership.
- Read pages now measure serialized JSON bytes in PostgreSQL before loading
  payloads, cap total payload at2MiB and preserve next cursor when byte-bound.
  Oversized single evidence refuses typed BROKER_OBSERVATION_TOO_LARGE.
- Earlier test escalation rejected before start due usage limit, retry8:58PM.
  No workaround used. Clock20:13UTC/21:13Lisbon was past reset; normal approval
  retry succeeded: **23affected tests PASS2.05s**, broker-balance-snapshots.txt;
  handle40550exit0. Rejection resolved; no current permission blocker.
- Follow-up changes after that result: balance differences propagate to review
  reasons/alerts; source row caps and invalid-time checks; browser synthetic
  worker now adds a balance snapshot and verifies a third saved-evidence page.
  Run affected tests/browser next. Full463suite remains older baseline; no full
  newer claim. No real SDK connection or order, live disabled, goal active.

## Active verification: broker balance integration

- Full unit/PG suite running handle20449 -> suite-broker-balances.txt.
- Chromium running handle18806 -> browser-broker-balances.txt.
- Both use separate marked disposable databases. Poll existing handles before
  retrying; no broker connections permitted in fixture server. No source edits
  required while these run. Documentation updated with precise source/version
  boundaries and remaining non-atomic/external reconciliation limits.

## Milestone verified: broker balance integration

- **474full unit/PG tests PASS17.97s**, suite-broker-balances.txt;
  handle20449exit0. **ChromiumPASS**, browser-broker-balances.txt;
  handle18806exit0. Real saved evidence spans execution/commission/balance pages,
  retains fractional quantity and explicit non-atomic/unreconciled labels.
- No current test process. Original live/external restrictions unchanged; no
  connection/order or production changes. Full external reconciliation still
  incomplete; observation differences are not a ledger or PnL attribution.
- Review follow-up: source average costs may legitimately exceed simulator's
  Numeric(28,10) scale. JSON broker observations should retain bounded source
  precision independently; comparison arithmetic must retain that precision.
  Implement and test this before treating the source snapshot contract final.

## Milestone verified: source precision independent of simulator ledger

- Source callback/balance JSON accepts bounded finite40digit/20decimal evidence;
  simulator Numeric(28,10), risk caps and reservations are unchanged. Decimal
  normalization and snapshot subtraction use local60digit contexts, preventing
  implicit28digit rounding of long source values. No inferred FX or zero balances.
- **25affected unit/PostgreSQL tests PASS1.75s**,
  broker-source-precision-postgres.txt; handle20196exit0. Tests preserve a
  16decimal reported average cost through DB and an exact40digit commission;
  large currency balances differing by1.00000000000000000001 compare exactly.
  FullRuff, JSsyntax and git diff --checkPASS. No current running operation.
- Latest full-suite baseline474PASS plus precision-follow-up25PASS; latest
  Chromium balance workflow passed before this numeric-only follow-up. Do not
  claim a newer full-suite count. Reuse unaffected evidence.
- Next: explain balance changes against complete scoped executions/fees/flows
  rather than only compare observations; continuous disconnect/recovery evidence,
  strategy-owned sells/corporate actions, broader retention/news policy and
  model/host/CI/24h acceptance remain incomplete. Goal ACTIVE; L01PASS,
  L02-L14IN PROGRESS,L15/L16BLOCKED. No broker connection/order, production
  deployment, real notification, bank/IMAP action, paid call or live enablement.

## Milestone verified: execution and fee explanations for balance changes

- Added broker_attribution.py and exposed its result in owned evidence review.
  Uses exact source quantity/price/multiplier, BOT/SLD direction and fee source
  currency; no FX fabrication. Execution and fee evidence must be available by
  closing observation and outside non-atomic snapshot request windows. Conflicts,
  corrections, missing fees/contract basis and truncated pages stay unverified.
  Unexplained residuals are not labelled deposits, corporate actions or PnL.
- SDK execution normalization records security type and multiplier (STK's share
  unit is1; other missing multipliers stay unavailable). Legacy evidence without
  the basis cannot authorize arithmetic. Optional missing fields are excluded
  from payload serialization; raw account/exec identifiers remain excluded.
- **35affected tests PASS1.69s**, broker-change-explanation.txt; handle94556exit0.
  Includes PostgreSQL saved snapshots/fractional fill/foreign-currency fee match,
  while complete_reconciliation=false and execution_authority=none persist.
- Review caught a valid closed-roundtrip case: no position in either snapshot
  does not imply missing execution contract. Complete execution contract basis
  now supports that case; **10attribution tests PASS1.23s** in
  broker-roundtrip-explanation.txt. FullRuff and git diff --checkPASS.
- No running operations. Latest full-suite474 baseline and prior Chromium
  balance workflow remain before these focused backend changes. No newer full
  count claimed. Next: full flows/corporate-action/connection coverage, simulator
  strategy-owned exits, broader retention/news policy and model/host/CI/soak.
  Goal ACTIVE, original gates unchanged. No external connection/order/provider
  operation or production deployment; live disabled.

## Milestone verified: durable broker read attempt status

- Explicit broker refresh acquires a scoped90s database lease before its worker;
  completed attempts have30s pacing. No automatic broker retry/scheduler added.
  Success/partial/failure checkpoints distinguish last_success from incomplete
  attempts. Exceptions store stable codes without raw provider text. Timed-out
  or cancelled workers retain lease admission, native_completion unknown; local
  WorkPool still retains its slot until actual native exit. A lease is not proof
  that native work ended and never grants trading/retry-write authority.
- Owned saved evidence exposes refresh_state; expired running attempts display
  interrupted. Completion locks and checks the lease token against live DB time,
  inside the same transaction as callback evidence/alerts. No schema migration.
- **20affected PG tests PASS2.79s**, broker-read-recovery.txt; handle80059exit0.
  Runtime failure, timeout and cancellation preserve redacted durable failure,
  no last_success/no observations, and immediate retry never reaches the worker.
- Follow-up expired/replaced-token rollback tests currently running in
  broker-read-recovery-fencing.txt (poll live handle before retry). Browser needs
  revalidation for new durable state/pacing. Original permissions unchanged.

## Milestone verified: broker refresh publication fencing

- **22PG checks PASS3.30s**, broker-read-recovery-fencing.txt;
  handle41237exit0. Expired/replaced lease tests roll back journal and alerts;
  failures never establish last_success. Configuration/consent/deactivation
  post-worker checks remain passing. Ruff cleanup fixed only line wrapping.
- Chromium currently running handle29237 -> browser-broker-recovery.txt; verify
  terminal state before retry. It uses an explicitly synthetic SDK worker and
  checks saved refresh_state/native_completion/last_success after real commit.
- Scope remains read attempt recovery, not continuous broker lifecycle or full
  external reconciliation. No real connection/order/notification/deployment.

## Milestone verified: browser broker recovery status

- **ChromiumPASS**, browser-broker-recovery.txt; handle29237exit0. Saved
  refresh_state shows observed/last_success/native returned after committed
  synthetic read; ownership, CSRF, confirmation, three evidence pages and all
  existing workflows still pass. No running operation. FullRuff/diffchecksPASS.
- Latest evidence:474full-suite baseline, subsequent precision/attribution/recovery
  focused results and current Chromium. No inflated full-suite total.
- Next required local work includes broader retention, news source policy and
  model-task breadth as well as remaining full flow/corporate-action/execution
  reconciliation and strategy-owned simulator exits. Host/container/remote CI/
  24hour observation and external-paper gates remain unverified or blocked.
  Goal ACTIVE; L01PASS,L02-L14IN PROGRESS,L15/L16BLOCKED. Live stays disabled.

## Milestone verified: bounded read-only report file inventory

HEAD remains 65ea1d769c79bf77df3de1d4a3b6274168d92085; existing dirty tree preserved.
Added `src/operations/report_inventory.py` and operator-only
`scripts/inventory_reports.py`: bounded read-only DB/file inventory, all retained
owners including unknown-owner reports, no HTML/account output, hashed file
names, non-atomic observation explicitly labelled. Scan limits, missing storage,
symlinks and clock anomalies yield partial status; no deletion authorized.
`.venv/bin/pytest tests/unit/report_inventory_test.py tests/unit/storage_budget_test.py -q`
passed 8 tests (0.92s), evidence `evidence/report-inventory.txt`. Ruff passed for
new files. Session37078 finished0; no operation running from this milestone.
Next: explicit preview/confirm abandoned temporary render cleanup with writer
locking; finished PDFs/DB retention still require separate implementation.
No real data cleanup, deployment, broker connection, or order occurred.

## Milestone verified: explicit abandoned report temporary cleanup

Added `src/operations/report_cleanup.py` and operator CLI
`scripts/cleanup_report_temporaries.py`; current report writer shares a directory
flock and cleanup exclusively locks it. Preview/confirmed unchanged digest,
operator-chosen aware cutoff >=24h old, bounded scans, regular `.report-*` only;
never completed PDFs, symlinks or active renderers. Partial unlink/fsync failures
report actual removals. Linux/WSL private-local-directory scope documented in
RETENTION.md. No real data purged or retention schedule activated.
Marked PostgreSQL + unit/PDF regressions passed20/20 in2.26s, evidence
`evidence/report-retention-postgres.txt`; session45434 exited0. Full Ruff passed.
Follow-up inventory classification changed truncated-reference candidates from
unreferenced to reference_unknown; rerun its affected tests before next milestone.
No other operations running. HEAD unchanged; completed edits preserved unstaged.
Broader retention and remaining original acceptance gates remain active; no
broker connection/order, production migration/deploy, or live enablement.

Report cleanup follow-up:14 affected inventory/cleanup/storage tests passed after
reference_unknown correction (`evidence/report-inventory-final.txt`). Session50335
finished0. Real Chromium + marked PostgreSQL acceptance passed with actual PDF
rendering under the new lock (`evidence/browser-report-cleanup.txt`), session53188
finished0; no console errors, broker connections0, external orders0. Existing UI,
report, chat, simulator and ownership flows preserved. No operations running.
Next local gap: hard broker-read failures have durable status but need scoped
in-app operational alerts; add without weakening lease fencing or provider limits.

## Milestone verified: broker read failure alerts

Broker-read failures/timeouts/cancellations now persist a scoped redacted in-app
alert in the same transaction as attempt failure status. No outbound messages.
Deactivated users receive no new alert; expired/reclaimed leases publish neither
alerts nor callbacks. Rebind/revoked consent/disabled-account failures can notify
the active owner without persisting the rejected callback evidence. Existing
cooldown/deduplication and retry pacing remain unchanged.
22 PostgreSQL broker lifecycle/operations tests passed2.38s
(`evidence/broker-read-failure-alerts-verified.txt`), session67401 exited0. Earlier
runs retained: old no-alert expectations required separate assertions for new
failure alerts, and stale-worker cases must still assert no alerts. Full Ruff and
git diff --check passed. All prior handles terminal; no native broker work.
Next: refresh aggregate unit/integration evidence after the accumulated source
precision, attribution, recovery, retention and operational-alert changes, then
continue broader original requirements. Gate statuses not promoted by subsets.

## Milestone verified: aggregate September17 regression suite

503 unit + real marked PostgreSQL integration tests passed in15.20s, evidence
`evidence/suite-retention-recovery.txt`. Exact command:
`TEST_DATABASE_URL="postgresql+asyncpg://lulu@/test_acceptance_expenses?host=$PWD/.qa/socket&port=55439" TEST_DATABASE_DISPOSABLE_TOKEN=fixture-acceptance-20260909 .venv/bin/pytest tests/unit tests/integration -q`.
Session71987 exited0. This supersedes474 as aggregate local-test evidence while
preserving older logs. Latest Chromium pass remains browser-report-cleanup.txt;
subsequent broker failure-alert source changes covered by the22-case focused
PostgreSQL run and this503suite. Full Ruff/diff checks passed before the docs-only
matrix update. No interrupted operation remains from this milestone.
Acceptance matrix updated without promoting aggregate gate status: L01PASS,
L02–L14IN PROGRESS, L15/L16BLOCKED. Next original requirements: owned report/PDF
and chat retention with evidence-reference handling; source-specific news policy;
complete financial reconciliation/strategy exits; host/model/soak/CI breadth.
No deployment, real-data purge, external notifications, broker connection or order;
live remains disabled. Goal active; safe productive work remains.

## Report retention implementation checkpoint (browser verification pending)

Added owned report-content/PDF preview+confirmation service and CSRF browser routes,
with20-row/10-minute plans, active-owner/row locks and content hashes. Confirmed
reports become durable pending tombstones before file cleanup; completed cleanup
marks retired and retains ID/owner/dates/hash. Original ledgers/chat copies remain.
PDF download returns410 for pending/retired owned records; cross-owner404 preserved.
Shared/alias references, symlinks and out-of-root paths block deletion. Worker is
bounded; failed/interrupted cleanup stays pending for explicit fresh preview.
7 PostgreSQL service tests passed0.45s (`evidence/report-owned-retention-first.txt`),
session24738 exited0. UI controls/status added afterward; browser and restart-style
committed recovery still pending. No migration or real report removal performed.
Next: real Chromium preview/confirm/isolation/410, committed recovery regression,
Ruff/JS checks, then retention/runbook documentation and final affected suite.

## Milestone verified: owned report retention and browser recovery

28 focused PostgreSQL/report/storage tests passed2.49s
(`evidence/report-owned-retention-recovery.txt`), session27474 exited0. Committed
multi-transaction recovery proved the original content digest survives interruption
after unlink. Chromium passed real preview/approval, CSRF and cross-user denial,
owned410/foreign404, tombstone reload and empty second preview
(`evidence/browser-owned-report-retention.txt`), session96847 exited0. All browser
providers synthetic, broker connections0/orders0, no console errors.
After these runs, narrowed the plan projection (no generation_errors payload
returned) and fsynced the report directory on already-absent recovery; aggregate
suite rerun next covers these final changes. Ruff/JS syntax passed. RETENTION.md
records two-phase semantics, native cancellation, limits and remaining retention
scopes. No migration or real data removal. No active handles at this checkpoint.

## Milestone verified: final owned-report retention aggregate

511 unit + real marked PostgreSQL tests passed18.32s in
`evidence/suite-owned-report-retention.txt`; session46022 exited0. Exact standard
marked fixture command is the same as the September17 aggregate above. This run
includes the final narrow plan projection and absent-file directory fsync.
Full Ruff, JS syntax and git diff --check passed. Latest real Chromium result is
browser-owned-report-retention.txt (same UI/routes; later two service-only changes
covered by this aggregate). PLAN.md updated511 evidence, statuses unchanged.
No live process/operation remains from this milestone. Existing staged/unstaged
work preserved; HEAD still65ea1d769c79bf77df3de1d4a3b6274168d92085; no commit/push.
Next safe original requirements: chat-content retention with saved evidence
references and active-turn handling; source-specific news license/retention policy;
remaining financial/host/model/soak/CI coverage. Completed report retention is
explicit owner action only, never a newly activated real-data cleanup policy.
No broker connection/order, production deployment, or external notification.

## Milestone verified: chat history retention prerequisite

Every new turn now reloads owned persisted history after committing its active
turn, excludes retired/in-progress messages from model context, and clears RAM
history on read failure before refusing inference. No null-owner legacy fallback.
Chat save/deletion use conversation-before-message locking for retention safety.
9 focused PostgreSQL/chat evidence tests passed1.55s
(`evidence/chat-current-history.txt`), session3053 exited0; Ruff passed. Source
changed after511 aggregate, so that aggregate is historical until affected/new
retention checks finish. Next: inactive-conversation preview/confirm/tombstones,
active-turn exclusion, actual browser controls and evidence-reference handling.
No external/production actions; all handles terminal.

## Milestone verified: inactive chat retention service

Added bounded20-conversation/500-message owned preview+confirmation with10-minute
content-bound hashes, active-user and conversation/message locks. In-progress,
recent and other-owner chats are excluded. Content/tool evidence become explicit
retired tombstones with stable IDs/digests; title redacted, activity clocks retained
so additional approved batches progress. User-message tombstones do not advertise
assistant-only download URLs.16 focused PostgreSQL/chat tests passed1.82s
(`evidence/chat-retention-first.txt`), session74863 exited0. UI controls and actual
Chromium retention test added afterward; Ruff/JS syntax passed. Browser verification
RUNNING session53670 (`evidence/browser-chat-retention.txt`); poll that handle before
retrying. No broker/production activity. Need concurrency review, docs and full
aggregate after the new active-session history refresh/retention behavior.

## Milestone verified: chat retention browser and active-turn race

Chromium passed actual chat preview/confirmation, CSRF/foreign-owner denial,
retired evidence download, reload labels and empty second preview; session53670
finished0, evidence/browser-chat-retention.txt. Model/providers remain fixtures,
0broker connections/orders, no console errors. Real PostgreSQL lock-race test
observed retention waiting on a conversation writer, then rejected the stale plan
after active-turn commit, preserving all old messages.17focused checks passed1.90s,
session36601 finished0, evidence/chat-retention-concurrency.txt. Full Ruff/diff
checks passed; docs now describe the implemented scope and remaining policies.
Next: aggregate regression after orchestrator/history/persistence changes; previous
511 aggregate is historical. No active handles at this milestone, no production
migration, no real-data retention policy activated.

## Milestone verified: chat retention aggregate

521 unit + real marked PostgreSQL tests passed17.01s in
`evidence/suite-chat-retention.txt`; session20996 exited0. Standard marked fixture
command unchanged from September17 aggregate. Current Chromium evidence is
`browser-chat-retention.txt`; subsequent changes were tests/docs only. Full Ruff,
JS syntax and diff checks passed. PLAN.md updated521 and browser evidence without
promoting incomplete gates. L01PASS; L02–L14IN PROGRESS; L15/L16BLOCKED.
No active operation/handle remains. HEAD unchanged; staged/unstaged work preserved,
no commit/push. No real-data purge or automatic retention selected; no broker
connection/order, external notification, production migration/deployment.
Next highest remaining local news gap: source policy is still attributed
`license=unverified`, `retention=operator_review_required` metadata only in
src/news/ingestion.py; no enforced source policy, syndicated-copy grouping or
source retention workflow. NEWS.md describes this honestly. Continue with explicit
source-policy schema/enforcement and synthetic fixtures, without asserting real
publisher licensing or fetching private/paid sources. Other financial/host/model/
research and deployment acceptance gaps remain; original goal active.
