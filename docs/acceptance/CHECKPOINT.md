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

## Milestone verified: public news-source permission boundary

Checkout was externally advanced to0e18029fe882497cd7bb998f5b855777ac474889 with
prior work committed; observed clean before these new policy changes. I did not
commit/push/reset. Added explicit SourcePolicy/NEWS_SOURCE_POLICIES boundary before
persistent public-source fetch: reviewed/date-bound operator attestation, exact
article hosts, permitted headline/summary/full-text projection, stored policy digest,
post-fetch revocation check and validator reset after policy change. Empty registry
blocks persistent sources. No publisher license inferred or real source activated.
24 unit/marked PostgreSQL policy/checkpoint tests passed1.10s
(`evidence/news-source-policy-recovered.txt`), session37122 exited0. First run had
16unitPASS/5fixture connection errors because owned PostgreSQL was stopped after
host interruption. Existing .qa cluster restarted with private Unix socket/noTCP,
pg_ctl handle30987 finished0; recovery log confirms interrupted shutdown recovery.
No new cluster, production DB or migrations. Earlier failure log retained.
All handles terminal. Ruff passed. Current next work: newsletter policy boundary,
stored-policy expiry/read exclusion and explicit cleanup; source documentation/config
examples and aggregate regression. retention_days currently records a constraint,
not yet a completed expiration/cleanup implementation.521suite remains historical.

## Milestone verified: stored source expiry and private permission binding

48 focused unit/PostgreSQL tests passed2.07s
(`evidence/news-policy-private-expiry.txt`), session56035 exited0. Stored declared
policies now fail closed at current review/retention expiry, measured from immutable
first-seen time; malformed metadata guarded by PostgreSQL16 input validation.
Private newsletter policies bind owner/mailbox/server/filter, recheck after fetch,
retain private visibility and use one bounded native worker. All IMAP calls mocked.
A second host interruption had stopped .qa PostgreSQL: expiry first run16connection
errors, preserved in news-policy-expiry.txt; existing cluster restarted handle35972
finished0, recovered16cases passed1.74s (news-policy-expiry-recovered.txt), handle47515
finished0. No new cluster or production mutation. All current handles terminal.
Added JSON schema/.env empty-default guidance and NEWS.md boundary documentation.
Added one further private/public-scope denial unit test after48run; aggregate next.
Physical expired-content/revision cleanup, legacy policy review, ephemeral read
adapter policy and downstream-copy retention are explicitly still incomplete.
Current HEAD0e18029; new policy edits unstaged, prior committed work preserved.

## Milestone verified: source-policy aggregate

542 unit + marked real PostgreSQL integration tests passed27.62s in
`evidence/suite-news-source-policy.txt`, session69904 exited0. Standard marked
acceptance command unchanged. This includes final public/private transport-scope
denial, mailbox policy binding, expiry parsing and all previous core regressions.
Ruff/diff checks passed. No UI changes since last Chromium chat-retention PASS;
source-policy-only changes covered by aggregate. PLAN evidence updated542 without
claiming broader gates complete. Current HEAD0e18029; only this source-policy work
and its evidence/docs are dirty. All operations terminal.
Next: bounded explicit expired-news text/revision cleanup with retained digest
references and no silent resurrection; then source deduplication/quality coverage
and a requirement-by-requirement gate audit to distinguish actual missing work
from already satisfied constraints. No real publisher/IMAP access, data purge,
production changes, broker connection/order or live enablement occurred.

## Milestone verified: expired news cleanup and committed CLI

Added src/news/cleanup.py and operator-only scripts/cleanup_news.py with exact
source/public-or-private-owner scope,10-minute content-bound preview,20article/
1000revision capacity and5sSQL/2slock/15srequest budgets. Confirmed cleanup atomically
scrubs article/revision text into digest tombstones while preserving IDs/URLs/
availability clocks. Private owners must be active; source revisions and article
changes invalidate the plan. Retired rows cannot be resurrected by normal upsert
or reappear after clock regression. No automatic/model-invoked cleanup.
24 PostgreSQL tests passed2.60s (`evidence/news-cleanup-committed.txt`), including
actual CLI preview and committed confirmation; session38006 finished0. Earlier23
case pass in news-expired-cleanup.txt, session22965 finished0. Ruff/diff checks passed.
No active handles at this milestone. NEWS/RETENTION docs distinguish controlled
retention erasure from ordinary append-only revisions and remaining derived copies.
Next: aggregate verification after visibility/upsert changes, then requirement-level
gate audit and remaining source deduplication/quality work. HEAD0e18029 unchanged;
prior work preserved, no production/real-data/broker/provider actions.

## Milestone verified: aggregate and complete CI tier selection

Aggregate completed: 550 passed in21.15s, evidence/suite-news-cleanup.txt,
session64193 exited0. Reuse this result for unchanged application code.
CI audit found `pytest -m unit` selected294 of407 unit tests, excluding113
unmarked tests; no automatic collection marker exists. Workflows now select
`tests/unit` and `tests/integration` explicitly. Read-only collection verified
407 unit +143 integration =550 tests; integration marker previously selected all143.
Collection session8730 exited0. Both edited workflows parsed as valid YAML and
explicit directory selectors were checked; git diff --check passed. No remote CI
run is claimed and no test threshold/quality gate was disabled.
PLAN/AUDIT baseline headers now reflect externally committed HEAD0e18029 and
preserved dirty news-policy/cleanup work; PLAN links550-suite evidence.
No interrupted operation or active test process remains at this checkpoint.
Next: finish requirement-level gate audit (especially browser L12 and stale AUDIT
rows), then news syndicated-copy grouping/quality and other concrete local gaps.
Completion estimate given to user: roughly65%, uncertain and not a gate score.
Live remains disabled; no actual broker connection/order or external notification.

## Milestone verified: L12 browser acceptance

Inspected the required login/account evidence/proposal/independent simulator
approval/fill/fees/alert/report/isolation path and ran real Chromium against the
existing marked test_browser_expenses database. Owned PostgreSQL was already
running; no restart needed. Session99393 exited0, evidence/browser-gate-audit.txt
reports PASS and no console errors. Synthetic broker collector and model are
explicit; bank control rendering uses interception. No real connection/order.
L12 minimum gate is PASS, independently of blocked external-paper L15. Current
UI also passes expense/replay/retention and logout/open-WebSocket revocation.
Corrected stale audit rows for durable news identity and restore/migration scope.
Next: conservative syndicated-copy grouping with provenance, privacy and
historical-availability regression coverage. No active operation remains.

## Milestone: syndicated-copy grouping, focused verification

Added conservative normalized exact-text grouping in src/news/syndication.py,
versioned ingestion provenance, and bounded authorized search/recent/as-of grouping.
Preserves original DB records and each visible copy's source/hash/availability;
never counts another owner's or future evidence. Added ephemeral news grouping
before lexical sentiment aggregation and explicit corroboration limitations.
21 focused tests PASS4.94s, session66513 exited0, news-syndication-verified.txt.
Initial run23804 failed collection due to duplicate test basenames; integration
file renamed news_syndication_visibility_test.py. An additional ephemeral sentiment
vote regression is included in aggregate run87782, currently running; poll it before
retrying. Evidence path: evidence/suite-news-syndication.txt.
HEAD remains0e18029. An external operation staged prior changes during this work;
agent did not change index. Preserve staged and unstaged layers. Trimmed trailing
whitespace only from two historical failure logs in worktree (not index); failure
content retained. Full Ruff and git diff HEAD --check pass. Current browser L12
PASS remains valid for unchanged UI; aggregate verifies altered news consumers.
Next: finish aggregate; close ephemeral source-permission bypass, then continue
entity/language quality, broader model/financial/operations and deployment gaps.

## Milestone verified: copy grouping and final fingerprint consistency

Full suite12243 exited0:556 PASS53.95s, suite-news-syndication-final.txt.
Prior aggregate87782 exited1 (5 failed,551 passed): old search fixtures had
MagicMock content instead of PostgreSQL text/null. Replaced row fixtures with
actual NewsArticle instances and explicit clocks/provenance; preserved assertions.
Failure log retained, whitespace only normalized.
Final review moved ingestion fingerprint computation after canonical owner-bound
URL/content hash construction. Added short-text stored/retrieved identity regression.
All47 affected news tests PASS10.31s, session44635 exited0, evidence path
news-syndication-fingerprint-final.txt. Reuse556 aggregate for unchanged paths;
this47-test run verifies subsequent small ingestion adjustment. Full Ruff and
git diff HEAD --check passed. Index staging remains externally managed/preserved.
No running test handles remain. HEAD0e18029 unchanged, new grouping code/tests and
docs are mixed staged/unstaged/untracked; do not reset or restage unrelated work.

Commands (from checkout):
- TEST_DATABASE_URL="postgresql+asyncpg://lulu@/test_acceptance_expenses?host=$PWD/.qa/socket&port=55439" TEST_DATABASE_DISPOSABLE_TOKEN=fixture-acceptance-20260909 .venv/bin/pytest tests/unit tests/integration -q
- Same marked environment: .venv/bin/pytest tests/unit/news_syndication_test.py tests/unit/news_search_test.py tests/integration/news_syndication_visibility_test.py tests/integration/news_privacy_test.py tests/integration/news_runtime_test.py tests/integration/news_policy_expiry_test.py tests/integration/news_cleanup_test.py tests/integration/news_pipeline_test.py -q

Next highest confirmed news gap: src/tools/news.py ephemeral RSS/NewsAPI fetches
still lack SourcePolicy gating, unlike durable src/news/runtime.py. Apply permission
before network and recheck/project permitted fields before returning; fixture-test
missing/expired/revoked policies without real provider calls. Keep typed failure
truthful. Syndication handles exact observed copies only; edited/translated copies,
language/entity quality and actual source freshness remain incomplete. Continue
broader requirement audit and model/financial/operations/deployment gates afterward.
L12 PASS (real browser with explicit fixture providers/model); L01 PASS; other
local gates still IN PROGRESS, L15/L16 blocked. No broker connection/order, production
change, external notification or live enablement performed.

## Milestone verified: on-demand source-policy boundary

src/tools/news.py now requires current public source policies before RSS/NewsAPI
calls and revalidates policy fingerprint after each response. Uses permitted text
for search filtering and sentiment; unauthorized article hosts discard the source
batch. Redacted typed failures distinguish unavailable/partial failure from empty
successful search. Chat deterministic fallback preserves unavailable status and
never calls it no matching news. NewsAPI description-with-null-content bug fixed.
Optional API still requires configured enablement/key; no real provider call made.

New tests/unit/news_ephemeral_policy_test.py covers missing/expired/private/revoked
policy, pre-network denial, headline-only information boundaries, unpermitted hosts,
redacted errors, API projection and truthful chat fallback. Initial test79960 failed
2 code assertions because PolicyDenied subclasses ValueError; precedence fixed,
11 focused PASS3.24s(session57165), then additional host/fallback cases included in
aggregate. Full unit/PostgreSQL suite565 PASS61.47s, session86222 exited0,
evidence/suite-ephemeral-news-policy.txt. Ruff and git diff HEAD --check PASS.
All operations terminal. Prior browser L12 evidence remains valid for unchanged UI;
formatter behavior covered in new tests and aggregate. HEAD0e18029, preserve mixed
external staging; no git index/commit/push action taken.

Next: explicit news entity/language provenance quality (currently raw ticker tags
are called entities), remaining follow-up/ambiguity/model validation, and wider
financial/operations/deployment acceptance audit. Source policies are operator
attestations, not external license verification. No real source/broker/bank access,
orders, notifications, production changes or live enablement occurred.

## In-progress milestone: news provenance quality

Added src/news/quality.py: bounded unverified language declarations and currency/
ticker candidates, always unresolved/no qualified instrument. RSS declaration flows
through ingestion. Source tags no longer labelled verified entities; metadata-only
corrections keep immutable first-seen/text hash and append evidence. Policy text
omission/truncation now recomputes tags/sentiment only from permitted text, avoiding
derived restricted-text leakage.49 focused unit/PostgreSQL tests PASS9.94s,
session81517 exited0, evidence/news-quality.txt. Added real RSS language parser test.
Full suite27251:568 PASS,1 failure (optional feed metadata absent in an older fixture).
Corrected nullable language extraction using getattr consistent with other fields.
Focused sandbox run10403 stalled at async source tests; explicitly interrupted and
confirmed exit130 before retry. Retain news-quality-rss-fixed.txt as partial only.
Full approved-mode rerun now active session17828, evidence/suite-news-quality-final.txt;
poll the actual handle recorded by the tool before any retry. Ruff/diff HEAD checks
pass. Also corrected stale ACCOUNTING/BROKER_CAPABILITIES claims about implemented
simulator commissions and bounded journal callbacks; complete reconciliation still
incomplete. Next: finish this verification, then requirement-level financial/model
acceptance audit separating missing local behavior from external observation gates.

## Milestone verified: news provenance and derived-data scope

Full rerun17828 exited0;569 tests PASS, evidence/suite-news-quality-final.txt.
This supersedes initial568-pass/1-fail aggregate after nullable feed metadata fix.
Ruff and git diff HEAD --check PASS. No active operation remains. HEAD0e18029 and
externally staged changes preserved. L01/L12 PASS; other local gates not promoted.

Next concrete failing reproduction saved in workflow-negation-reproduction.json:
_factual_requests for "Do not access my portfolio. Show stored news only." returns
get_portfolio_summary plus get_latest_news, violating explicit scope restriction.
Offline parser only; no inference/network/broker activity. Fix explicit negation
across deterministic requests and native catalog/execution paths, add durable
regressions for independent allowed requests and follow-ups without interpreting
external evidence as intent. See llama_cpp_client.py lines111-170 (current layout).
Then continue requirement-level financial/model/operations/deployment review;
full entity-to-qualified-instrument resolution and actual provider observations
remain unverified. Live stays disabled; no external account/provider connections,
orders, notifications or production deployment.

## Read-scope guard resume (2026-09-23)

Implemented src/agent/clients/read_scope.py and _dispatch_scoped in the local GGUF
client: explicit user exclusions narrow deterministic reads, selected native catalog,
native dispatch and degraded-client reads. Portfolio exclusions also prevent report
collection and proposals that could access account data. Tool/assistant messages
cannot clear exclusions; explicit supported user allow phrases can. This is a
conservative history-bound intent rule, not a persistent account-policy replacement
or complete natural-language interpretation. Existing financial authority unchanged.
24 focused tests PASS3.95s (read-scope-fixed.txt, session92717 exited0). Added native
stream regression after that run. Prior aggregate launch was rejected before start
by automatic approval review due to usage limit, not by tests; no running handle.
After new-day resume, approved aggregate started as session90049, evidence path
suite-read-scope.txt. Poll that handle; do not duplicate. HEAD0e18029; external
staging now includes newer work and is preserved. No agent git index/commit changes.
Next: verify aggregate/native path, document limits, continue follow-up/ambiguity
coverage and native structured-evidence truncation repair identified during review.

## Read-scope verification recovery

Aggregate90049 finished1:430 unit tests passed,1 new test failed invalid fixture
agent_max_tokens64 (<128 minimum),145 PostgreSQL setup errors because the owned
fixture cluster was stopped. pg_ctl status confirmed no server running. Corrected
test to128; did not weaken application validation. Restart script94117 finished0,
existing pgdata recovered without reinitialization. Full rerun active15152, output
suite-read-scope-recovered.txt; poll before retry. Original failed run retained.
READ_SCOPE.md documents guard coverage and supported-phrase/history limitations.
No external account/provider connection, production deployment or live enablement.

## Milestone verified: explicit read-scope exclusions

Recovered aggregate15152 exited0:576 PASS17.63s (suite-read-scope-recovered.txt).
Includes actual local-client native event loop rejecting a hallucinated excluded
portfolio tool without dispatch, default/degraded scope filtering, independent
news reads, history follow-up exclusion and explicit user reauthorization. Production
Settings used in native regression. All operations terminal; HEAD0e18029 preserved,
externally staged/unstaged changes retained. No live/broker/provider actions.
Next confirmed original requirement gap found during review: native tool loop
still character-truncates oversized structured result at llama_cpp_client.py~835,
while deterministic prefetch uses _bounded_evidence. Repair with structured budget
status and native event-loop regression; then broader ambiguity/follow-up/real-model
and financial/operations gates remain. READ_SCOPE.md states grammar/history limits.

## Milestone verified: native structured evidence budget

Removed native-loop character slicing. Full result remains unchanged in tool_result
event; only model context gets JSON-serialized _bounded_evidence, matching the
existing deterministic path. Oversized results use evidence_budget_exceeded instead
of malformed JSON or fake complete evidence. Added actual local-client native loop
regression with oversized Unicode JSON, production Settings, complete event check
and next-inference context parsing.26 affected tests PASS0.96s, session4058 exited0,
evidence/native-evidence-budget.txt. Reuse576 aggregate for unchanged paths; new
client adjustment verified by26 affected tests. Ruff/diff HEAD checks pass.
No active operations. Next: extend actual local model workflow evaluation for
negation/follow-up/ambiguous/multiple requests, retain deterministic-vs-model evidence,
then continue financial/operations/deployment acceptance audit. Live disabled.

## Active real-model evaluation

Extended scripts/benchmark_workflows.py to fixed workflow-scope-v2 cases: original
portfolio/scanner plus explicit exclusion, exclusion follow-up and Portuguese
portfolio. Added explicit --native-tools mode for later comparison; current run is
default deterministic reads. Existing 1.5B Q4 GGUF, CPU4/context4096/max output128,
synthetic tools only, no download/cloud/provider/broker calls. Run64551 currently
active; output workflow-scope-v2-cpu.json, log workflow-scope-v2-cpu.log. Poll before
retry. Classify tool-scope/event results separately from factual/synthesis quality;
five observations cannot establish production p95 or general multilingual quality.
Command: .venv/bin/python scripts/benchmark_workflows.py --model models/qwen2.5-1.5b-instruct-q4_k_m.gguf --output docs/acceptance/evidence/workflow-scope-v2-cpu.json

## Milestone: real-model scope evaluation and factual failure

Run64551 exited0. workflow-scope-v2-cpu.json contains actual1.5B CPU results,
5/5 expected read scopes and complete events; load1.70s,peak1987.3MiB. Manual
quality review FAIL in workflow-scope-v2-review.json: Portuguese answer claims
EUR4.00 from0.004 units atEUR100 with no supporting multiplier/FX/total; arithmetic
product isEUR0.400. Portfolio English uses deterministic fallback, not model synthesis.
News-only answer adds unsupported generic market inference. Preserve these findings;
harness PASS means scope/event checks only. MODEL_HOST documents limits and L06
remains IN PROGRESS. No active operations. Source/model unchanged after run.
Next highest-priority defect: bound portfolio responses to deterministic exact
facts/missing-data states; do not let model prose invent authoritative valuation.
Then rerun fixed actual-model cases and perform native-tool comparison with typed
per-case failures. Original broader financial/operations/deployment gates remain.
HEAD0e18029, mixed externally staged/unstaged/untracked work preserved. No broker
connection/order, real provider/bank/notification or live enablement.

## Milestone verified: deterministic financial chat facts

Added finance/answers.py exact source-value rendering with explicit missing currency/
as-of/total values and no inferred valuation. Default portfolio/scanner evidence
renders deterministically; scanner retains other source results. Native path collects
tools then replaces unchecked financial prose with the same evidence representation.
Final event records deterministic_financial_evidence. Portuguese portfolio catalog
alias fixed. FINANCIAL_ANSWERS.md explicitly leaves qualitative analysis/schema and
broader accounting acceptance incomplete; do not call this model synthesis.
30 affected tests PASS1.02s (14052 exited0), then582 aggregate PASS27.89s (98763
exited0), suite-financial-answers.txt. Model counterexample covered by native stream
regression. Ruff/diff HEAD checks passed. Now rerunning unchanged five-case workflow
scope-v2 harness with generation provenance added: handle60766,
output workflow-financial-facts-cpu.json/log. Poll before retry. Existing1.5B CPU4,
synthetic tools, no downloads/external calls. No broker orders/live enablement.

## Milestone verified: fixed-case financial boundary rerun

Benchmark60766 exited0; workflow-financial-facts-cpu.json contains5/5 expected
scope/event results. Parsed three financial answers: exact0.004,EUR100 and missing
source market value/USD total preserved. All three label deterministic generation.
Evidence review: workflow-financial-facts-review.json. Load1.33s,peak1979.25MiB;
financial sub-ms timings are skipped inference, not improved model synthesis.
News-only model answer still makes unsupported inference from a synthetic title;
recorded failure, L06 remains IN PROGRESS.582 aggregate evidence remains current
for application code; later harness only added generation provenance.
No active operations. Next: typed grounded model-analysis/abstention for news and
portfolio interpretation (without letting model set numbers), native-tool benchmark
comparison with honest per-case failure handling, and remaining financial/operations/
deployment gates. Source facts alone are not claimed as complete qualitative analysis.
HEAD0e18029; preserve staged/unstaged work. No real broker/provider/bank connection,
order, notification, production deployment or live enablement.

## In-progress milestone: typed news extracts/abstention

Added agent/clients/news_analysis.py strict Pydantic schema: supported_extracts or
abstain, at most3 exact quotes tied to computed source IDs, bounded missing-data
labels. Extra fields, fake IDs/quotes and duplicate extracts fail. Source envelopes
bounded10 excerpts×1200characters with clipping flags; headline-only/short evidence
abstains without inference. Source excerpts are data, never instructions.
Local client uses JSON-schema response_format supported by installed llama_cpp
llama_chat_format.py~991; at most2 inference attempts, then typed abstention. Provider
failure and missing publication/availability/entity/price/corroboration metadata
remain explicit. Native and deterministic news paths use the contract; mixed
news/market preserves independent evidence. This is grounded extraction, not proven
causal/recommendation/strategy analysis. Financial deterministic boundary retained.
30 focused PASS1.03s (22282 exited0, news-analysis-fixed.txt). Initial2 fixture
failures retained: new schema kwarg unsupported by old stub and old expected neutral
prose. Fixtures updated to assert structured abstention while retaining original
progress/event/full-evidence assertions. Added2 mixed/failure tests afterward.
Full unit/PostgreSQL run53070 active, suite-news-analysis.txt. Poll before retry.
Ruff/diff HEAD checks pass. No external provider/broker/model download/live action.
Next: finish aggregate, constrain source-ID schema enum, rerun real fixed headline
cases and actual schema inference with separately labelled substantive synthetic
news evidence; retain both failures and distinctions from model causal analysis.

## Resumption milestone: workspace access and affected verification

Original attached instructions reread completely. HEAD remains
0e18029fe882497cd7bb998f5b855777ac474889; existing externally staged changes
preserved. No applicable AGENTS.md found. No pytest/browser/benchmark process
was running at resumption. Previous run53070 completed:588 PASS17.47s in
evidence/suite-news-analysis.txt, confirmed from saved terminal result.
Normal sandbox still fails on /mnt/wslg/distro; individually approved escalated
commands now work. No mount/security/OS settings changed. The earlier rejected
benchmark did not start.
Fixed source-ID enum assertion line length. Ruff for affected client/schema/test/
benchmark passes;25 affected offline tests PASS1.38s, run48095 exited0,
evidence/news-resume-verification.txt. Reuse588 aggregate for unchanged paths.
Actual existing1.5B CPU headline benchmark is running as session57819; poll before
retry. Output workflow-news-abstention-cpu.json/log. Synthetic tools only.
Next: review headline result, substantive schema inference, native comparison,
then broader remaining acceptance gates. No broker connection/order, provider
connection, paid call, production deployment or live enablement.

## Milestone verified: default-path news model benchmarks

Headline run57819 and substantive run93215 exited0. Each fixed five-case run
passes scope/event checks. Evidence workflow-news-abstention-cpu.json and
workflow-news-substantive-cpu.json; parsed review workflow-news-review.json.
Headline abstains with INSUFFICIENT_SOURCE_TEXT, no invented market narrative.
Substantive source also abstains; schema works on actual existing1.5B CPU model,
but no useful extract/causal analysis is proven. It invents source_unavailable
in missing_data despite supplied evidence: fix collection-owned metadata before
promoting quality. Load1.46s/1.17s, peak1976.5/2007.5MiB respectively.
Native-tool headline comparison currently running session51193; poll before
retry, evidence workflow-native-headline-cpu.json/log. No external calls.

## Milestone verified: collection metadata and native comparison

Native run51193 exited0 but benchmark status FAIL:4/5 read scopes failed, no
required tools dispatched. Tool-call markup appeared as final text. Preserve
workflow-native-headline-cpu.json/log. Native setting remains disabled;
MODEL_HOST.md records comparison and observed latency/resource limits.

Fixed observed false source_unavailable: collection missing-data fields now derive
only from tool evidence. Model can abstain, not invent provider failure or absent
body. Added behavioral regression.26 affected tests PASS1.01s, session49275
exited0, evidence/news-collection-metadata.txt. Ruff and diff HEAD check pass.
Real-model substantive rerun9261 exited0, workflow-news-substantive-metadata-fixed-cpu.json:
5/5 scope/events pass; parsed news missing_data contains neither false source
failure nor missing body. Abstention remains; useful qualitative analysis is not
complete. All benchmark processes terminal; no active operation at checkpoint.
Reuse prior588 aggregate for unaffected code; affected changes verified by26 tests.
Next: repair native tool-call handling or explicit degraded failure with scoped
factual fallback; complete useful analysis evaluation and broader financial,
operations, restoration/deployment gates. L06/L13 remain IN PROGRESS. No broker
connection/order, paid call, real notification, production deployment or live enablement.

## In progress: native read recovery

Shared native final-answer path now completes missing user-derived factual reads
through _dispatch_scoped, preserving exclusions/NO_TOOL_CALLING and full events.
Model textual tool markup is never executed. Final event records
execution_path=deterministic_read_recovery, also captured in benchmark output.
Added5 behavioral tests for invented writes/arguments/malformed calls/exclusions.
Existing native exclusion test now requires requested bounded news read while
retaining denied-portfolio evidence. Initial fixture assertion failures retained
in native-read-recovery*.txt; accidental direct-dispatch expectation edit restored.
Complete unit rerun active12345, unit-native-recovery-final.txt. Native real-model
fixed-case rerun active59084, workflow-native-recovery-cpu.json/log. Poll these
handles before retrying. No broker/provider calls, orders or live enablement.

## Milestone verified: native factual recovery

Run12345 exited0:449 unit tests PASS10.64s, unit-native-recovery-final.txt.
Ruff affected files and diff HEAD whitespace checks pass. Initial fixture failures
remain recorded; direct-dispatch assertion restored, native exclusion assertion
now verifies authorized news only and unchanged denied-portfolio evidence.
Run59084 exited0: workflow-native-recovery-cpu.json5/5 scope/events PASS.
Four cases use explicitly recorded deterministic_read_recovery; no claim of
working native tool generation. Financial answers retain exact0.004/EUR100 and
missing totals, news abstains, excluded follow-up reads nothing. MODEL_HOST.md
records real timings and concurrent unit-load caveat. No active operation.
Original broader gates remain open: qualitative analysis, financial reconciliation/
corporate actions, full restoration/deployment and host soak. Reuse prior145
PostgreSQL tests for untouched persistence code; current449 unit tests verified.
Next: audit remaining financial/report correctness against authoritative ledger
and acceptance matrix; avoid endless model tuning. Native default stays off.
No broker connection/order, provider connection, notification, production
deployment, paid download or live enablement. Existing staged changes preserved.

## Milestone verified: exact portfolio totals

Added usd_decimal_value and decimal aggregate totals with100-digit local context.
Existing floats remain display compatibility fields; *_usd_exact strings persist
through API serialization and financial chat prefers them. Missing FX/source
errors invalidate exact and display totals together. Source precision cannot
recover values already rounded by a provider. No broader cash/PnL claim.
61 focused financial/broker checks PASS1.11s (77989);452 unit tests PASS5.08s
(86145), evidence/portfolio-exact-totals.txt and unit-portfolio-exact.txt. Ruff passes.
Next confirmed report defect: tool contract says YYYY-MM-DD but parsing accepts
timezone timestamps and replaces their offset. Enforce calendar-date contract
and verify inclusive UTC boundaries. No active tests/model benchmarks.

## Report-date verification and PostgreSQL recovery

Calendar boundary tests8 PASS0.45s; Ruff passes. Original report tool contract
requires YYYY-MM-DD; timestamp/noncanonical inputs now reject rather than silently
replacing timezone. Offset-aware evidence inclusion/exclusion verified.
Owned fixture startup65159 exited0 after automatic crash recovery; log confirms
private Unix socket55439, server ready. No files removed or cluster reinitialized.
Full unit+PostgreSQL suite active2243, evidence/suite-financial-calendar.txt;
fixtures require test_acceptance_expenses and fixture-acceptance-20260909 marker
before mutation. Poll before retry. No external broker/provider/write/live action.

## Milestone verified: financial/calendar aggregate

Run2243 exited0:603 unit/PostgreSQL tests PASS18.04s,
evidence/suite-financial-calendar.txt. Whitespace checks pass. Matrix updated.
Current owned disposable source revision confirmed0012_broker_observations;
marker/identity matched. New recovery target test_recovery_20260925_v1 and
.qa/recovery-test_recovery_20260925_v1 did not exist before starting.
Full database/filesystem/vault/PDF/existing-model recovery now active29687;
evidence/full-fixture-recovery-0012.json/log. Poll before retrying; never reuse
or overwrite the target on interruption. Runner checks disk and source identity,
seeds only inactive synthetic records, preserves private archives, verifies hashes
and restored model tasks, cleans its own source fixture IDs. No external calls.

## Milestone verified: current-schema full recovery

Run29687 exited0. evidence/full-fixture-recovery-0012.json PASS:revision
0012_broker_observations,27 tables match counts/hashes, vault decryption/wrong-key
rejection PASS, PDF/settings/model filesystem hashes match,3 restored-model tasks
PASS (sample nearest-rank p95=2.65s, not production SLA). Source synthetic rows
removed; private target/archive retained. No active test/benchmark/recovery process.
PLAN and RUNBOOK link current evidence.603 aggregate result remains valid;
subsequent changes are evidence/docs only. No production migration/deployment,
broker/provider connection/order, real notification, paid service or live enablement.
Next: report collection/reconciled execution presentation and broader financial
coverage remain; inspect operational/host validation gaps after those. L09 still
requires broader retention review; local restore evidence alone is not full gate PASS.

## Milestone verified: report history failure propagation

Confirmed broker error rows were discarded by period filtering, masquerading as
successful empty history. Added bounded _history_evidence before date filtering:
invalid containers/over2000 records unavailable, error/undated/malformed entries
counted with partial_failure, valid out-of-period/empty history remains complete.
Provider failure text is not retained or passed to the model. Source history is
explicitly not reconciled execution proof.
13 unit checks PASS (81318).18 focused unit/real-PG checks PASS1.63s (3503),
evidence/report-history-persistence.txt: real collector with synthetic providers
propagates failure into stored Report status, owner and redacted HTML. Ruff
auto-corrected import ordering only. Reuse603 aggregate for unaffected paths;
new helper/collector behavior verified by focused suite. No active processes.
Original permissions unchanged; no actual broker/provider connections or orders.
Remaining: comprehensive deterministic report numbers/reconciled execution
presentation, broader financial/operations/host/deployment gates. L07 incomplete.

## Milestone verified: explicit report source completeness

Report collection now recognizes available=false, partial/unavailable/unverified
valuation_status and blocked source status as SOURCE_INCOMPLETE. Complete empty
sources remain successful. Failure-stage fixtures now independently test each
stage rather than sharing an unavailable portfolio in every case.27 focused
unit/real-PG tests PASS1.49s, run86154 exited0, report-missing-sources.txt.
Only formatting changed after that run; lint/whitespace verification follows.
No active operations. Broader deterministic narrative/reconciliation and remaining
acceptance gates remain unfinished. No real broker/provider call or live action.

## Milestone verified: bounded report database coverage

Report audit collection now fetches at most1001 rows and includes1000; simulation
collection fetches11 and includes10. Stable id/date ordering, explicit included
counts/has_more and SOURCE_INCOMPLETE propagation prevent silent truncation.
Fallback labels included counts rather than claiming period totals. Real PG
fixtures test empty/exact-limit/overflow and foreign-owner/out-of-period rows.
30 focused tests PASS2.66s,97898 exited0, report-coverage.txt. Ruff/diff checks
pass after formatting-only corrections. Full suite running87702,
evidence/suite-report-coverage.txt; poll before retry. No real provider/broker
connection, order, notification, production deployment or live enablement.

Aggregate87702 exited0: 621 unit/PostgreSQL tests PASS18.31s. Matrix updated; no active test handles. Remaining full report arithmetic/reconciliation and broader gates are unchanged.

## Milestone verified: fallback financial attribution and report HTML

Fallback report now uses exact portfolio_facts values: application account,
source currency, exact quantity/value, source valuation timestamp and distinct
collection timestamp. Missing-currency values unavailable; exact aggregate USD
strings preferred.20-position summary cap exposes omitted count and points to
evidence snapshot. Explicitly unavailable period realized PnL/flows/fees/FX/
benchmark performance; audits/simulation counts do not imply reconciled fills.
Model-authored successful prose still requires a broader numerical authority
boundary; this repair does not claim that gap closed.
HTML renderer now closes a list before a following heading and retains escaping.
Initial new test had a multiline literal syntax error, recorded in
report-attribution-html.txt; fixture corrected without weakening assertions.
Final32 focused unit/PG tests PASS (32429 exited0),
evidence/report-attribution-html-fixed.txt. Earlier31 attribution checks PASS
1.81s in report-fallback-attribution.txt. Ruff passes. No active operations.
Reuse621 aggregate for unaffected paths. No real broker/provider connection,
orders, production deployment or live enablement.

## Milestone verified: report source admission/deadlines

Replaced unrestricted report asyncio.to_thread reads with existing WorkPool
admission:2 slots,30-second per-source timeout, explicit REPORT_SOURCE_BUSY/
TIMEOUT unavailable results. Native slot retained until real completion; scoped
context preserved. Stored-news coroutine has30-second deadline.35 focused
unit/real-PG tests PASS2.29s,72652 exited0, report-source-bounds.txt. Ruff passes.
No end-to-end deadline or dedicated-executor isolation claim.
Browser revalidation active41027, browser-report-source-bounds.txt; actual
Chromium/marked test_browser_expenses with synthetic providers. No prior browser
process was running. Poll before retry. No external broker/provider/write actions.

Browser41027 exited1 at obsolete report generation_status=complete assertion.
Fixture explicitly supplies portfolio.available=false; application correctly
persists partial_failure after completeness repair. Updated assertion to require
exact SOURCE_INCOMPLETE/portfolio error and visible partial-report label. PDF,
reload, cross-user and retention assertions retained. Original failure evidence
preserved. Rerun active35603, browser-report-source-bounds-fixed.txt; poll first.
Also corrected SOAK.md migration prerequisite0012 to match existing runner.

## Milestone verified: browser report revalidation

Browser35603 exited0: real Chromium/real disposable PostgreSQL/stub-model PASS,
evidence/browser-report-source-bounds-fixed.txt. Desktop/mobile, simulator
independent approval/fills/fees/halt, account isolation, expense/replay/bank UI
fixtures, real PDF generation and reload, partial-report status with exact
portfolio SOURCE_INCOMPLETE cause, report/chat retention, logout/WS revocation
all passed. Console errors empty; expected synthetic409 retained. Fixture server
terminated normally. No actual broker connection or external orders. L12 updated.
Earlier browser41027 failure remains documented. Trimmed only trailing whitespace
from four earlier native-recovery failure logs newly staged externally; no index
mutations. Ruff and diff HEAD check pass. No active operations.
Remaining report numerical authority and full financial/reconciliation/operations/
host/deployment gates still open. Source admission bounds are verified, but
not an end-to-end report SLA. Continue independent authorized work.

## Milestone: report model evidence-budget authority

Confirmed failing reproduction87594: oversized collected evidence was replaced
with an omission marker while model still generated fabricated USD999999 report.
Synthetic model and disposable PG only; report-budget-reproduction.txt retained.
Generator now detects whole-context omission and skips model generation with
REPORT_EVIDENCE_BUDGET_EXCEEDED partial status. Deterministic attributed fallback
uses collected facts; full retained snapshot/hash persists for review. This fixes
an evidence-free inference path, not arbitrary model prose validation when the
context fits. Broader numerical authority requirement remains open.
Focused repaired report suite70739 exited0, report-budget-fixed.txt. No active
operation. No actual broker/provider calls, orders, paid use or live enablement.

## Milestone verified: repair preserves complete inference context (2026-09-26)

HEAD remains 0e18029fe882497cd7bb998f5b855777ac474889; existing staged,
unstaged and untracked work preserved. Interrupted prior run completed:473 unit
checks PASS24.40s (unit-repair-context-fixed.txt); no pytest process remained.
Approval service temporarily rejected a read command for usage limit; a fresh
review subsequently approved the read and scoped regression work. No bypass.

Repair and news schema retries pass preserve_context=True to token budgeting.
Original request, history and tool evidence must all fit or inference raises
MODEL_CONTEXT_BUDGET_EXCEEDED. Added reproduction proved the prior safeguard
still omitted user-role tool evidence; repair-evidence-reproduction.txt records
1 failed/6 passed. Fixed budget to reject before any evidence/history omission
in preserve mode. Tests cover user/tool evidence, unchanged original messages,
sufficient budget and actual repair-path flag propagation.

Session94906 exited0:475 unit checks PASS6.16s in
[evidence/unit-repair-evidence-fixed.txt](evidence/unit-repair-evidence-fixed.txt).
Scoped Ruff and git diff --check pass. No active test operation. Existing browser
and PG evidence retained for unaffected paths; this milestone is not a new
real-model or browser acceptance result. No broker/provider connection, order,
production deployment, paid use or live enablement occurred.

Next: report successful-model prose still bypasses deterministic numerical
validation when evidence fits. Review typed evidence-linked analysis/rendering
before closing L07. Full PnL/reconciliation, operations, host/soak/deployment and
conditional external gates remain as recorded in PLAN.md. Goal remains active.

## Milestone: deterministic report authority, browser revalidation running

2026-09-26 HEAD unchanged. First reproduction could not connect to the stopped
owned fixture PostgreSQL (report-authority-reproduction.txt). Confirmed no live
server; existing startup script recovered the cluster via PostgreSQL crash
recovery, logs reached READY, no reinitialization/deletion. Real marked database
then reproduced false complete status for fabricated USD999999/purchase prose
(report-authority-reproduction-running-db.txt,61766 exit1).

Report now always renders financial sections from collected evidence. New
report_analysis.py validates strict typed source selections (maximum3), exact
quoted substring and known source hash; rejects extra fields, inconsistent
status, unknown/duplicate/invented extracts and oversized output. Quotes retain
source/publication/availability metadata, explicitly are not reconciled executions
or trading signals, and cannot introduce Markdown structure via source newlines.
Valid selected evidence/assessment are retained in the hashed report snapshot.
Invalid raw model prose is excluded from report/PDF/persisted evidence and yields
REPORT_MODEL_OUTPUT_INVALID. Empty/error/evidence-budget failure semantics remain.
Browser stub migrated to the typed abstention contract; existing assertions retained.

35 initial focused tests PASS3.54s (67800 exit0,report-authority-fixed.txt).
Full unit/real-PG suite PASS638 in30.42s (46779 exit0,suite-report-authority.txt),
including positive typed abstention, saved failure status, precise financial facts
and source validator regressions. Scoped Ruff/diff check pass.
Browser revalidation is ACTIVE session32875, browser-report-authority.txt:
poll before retry. Uses existing Chromium, marked test_browser_expenses, synthetic
providers/model and real PDF rendering. No actual broker/provider connection,
external order, notification, production deployment or live enablement.

This closes unchecked prose publication, not full analytical reporting: source
extract selection is explicitly limited, richer evidence-linked analysis and full
period accounting/reconciled execution coverage remain required. Real-model
reliability against the new report schema is unverified. L07 remains IN PROGRESS.

Browser32875 subsequently exited0. Evidence browser-report-authority.txt records
real Chromium/marked PostgreSQL/stub-model workflow validation; no test operation
remains active. Preserve source-bounds browser evidence for comparison. Next work:
real-model schema reliability and richer validated report analysis, then remaining
financial/reconciliation/operations requirements in PLAN.md.

## Milestone: actual report model reproduction and structured inference

New scripts/benchmark_reports.py exercises actual generate_report and local GGUF
with synthetic account/news evidence and explicitly stubbed PDF/storage sinks.
Existing 1.5B CPU GGUF only, no download, no provider/tool access. Three cases:
no news, substantive source text, injected source instruction.14828 exited0;
report-model-cpu.json records FAIL3/3 schema validation (correct partial failures,
financial facts retained, no tools). Load2.54s, task15.67/12.71/15.23s,
peak process RSS2006.66MiB. Exit0 means benchmark completed, not acceptance PASS.

Added optional response_schema to client event contract. Structured path calls
existing llama.cpp schema support with complete context preservation, no tools,
no keyword routing or prose repair; incomplete/invalid JSON returns typed error.
Unavailable local model also stops at error/done with no fallback tools for this
path. Reporter supplies schema with known source ID enumeration. Browser fixture
signature migrated to this optional parameter; prior assertions retained.
23 focused tests PASS1.57s before the additional unavailable-backend regression.
Real-model rerun ACTIVE59110: report-model-schema-cpu.log/json. Poll before retry.
Full regression/browser rerun and remaining structured failure review pending.
No broker connection/order, paid calls, real notifications or live change.

Structured rerun59110 exited0 but benchmark overall FAIL: source and injection
cases validated (16.94/21.85s), empty-source semantic selection failed. Narrowed
empty-source schema to abstain/zero observations;18616 exited0 PASS8.11s in
report-model-empty-source-cpu.json. Existing source-case evidence still applies.
Injection quotation was retained as labelled source data; no tool call, but this
is not a claim of high-quality analysis. MODEL_HOST.md records exact commands and
limits. Full regression ACTIVE9059, suite-report-schema.txt; poll before retry.

Full regression9059 exited0:643 unit/PostgreSQL tests PASS31.81s,
suite-report-schema.txt. Scoped Ruff and diff check pass. Browser ACTIVE5699,
browser-report-schema.txt, to verify the changed client signature through real
Chromium/report/PDF/reload paths. Existing schema-source model cases remain valid;
no additional model process is running. No acceptance gate is promoted solely on
these narrow cases; source selection quality, period accounting and broader
financial/ops/host/external requirements remain open.

Browser5699 exited0 PASS:browser-report-schema.txt, real Chromium/marked PG,
stub model and synthetic sources. Report/PDF/reload, preserved expense/simulator/
authorization/retention workflows pass; console errors empty (expected fixture409
only). No active verification process. Next implementation: bounded semantic
report repair and richer evidence-linked analysis, then remaining accounting and
operations acceptance gaps. Live remains disabled and no real broker connection
or order occurred. Goal remains active.

## Milestone verified: bounded semantic report recovery

HEAD remains0e18029fe882497cd7bb998f5b855777ac474889; preserved existing dirty
work/index. No interrupted verification was live at start. report_analysis helper
now permits at most2 attempts for invalid/incomplete model content. Original
prompt/schema/source evidence remain intact; rejected model prose is not fed back
or persisted. Dependencies/contract violations stop immediately; cancellation
propagates. Async streams close on every early termination. Reporter records
model_attempts in the hashed retained evidence, including successful repair and
exhausted failures. No changes to financial rendering or client tool restrictions.

Initial focused53 tests PASS3.65s (49428 exit0). Expanded persisted-recovery
coverage54 tests PASS3.97s (53331 exit0),
evidence/report-semantic-repair-persistence.txt. Covers successful second attempt,
two failures, no dependency retry, cancellation, retained exact financial values,
owner-scoped PostgreSQL status and attempt provenance, exclusion of fabricated
prose. Ruff/diff checks pass after a test-only line wrap. Reuse prior643-suite,
browser-report-schema and model case evidence for unchanged paths; no claim of
new full-suite/browser/model timing results. No active operation.

Further required work: richer validated analysis and period accounting/reconciled
executions remain incomplete; next assess simulator sale/realized-PnL boundary
and remaining financial requirements rather than treating extract-only reports as
full analytical acceptance. No actual broker/provider connection, order, external
notification, production deployment or live enablement. Goal remains active.

## Milestone verified: realized-PnL ledger integrity prerequisite

2026-09-26 HEAD unchanged; no interrupted process at start. Traced purchase-only
assumptions across policy/service/commissions/reconciliation and mandate/UI schemas.
Found reconciliation omitted account.realized_pnl despite risk policy reading it.
Reproduction96042 exited1: changed realized value still reported consistent
(realized-integrity-reproduction.txt). Complete supported purchase ledgers now
compare realized value against zero and include it in inputs_sha256. Unknown
ledgers remain unverified without a fabricated realized comparison. Stored values
are never overwritten. HTTP regression proves discrepancy denial commits the
halt/alert, preserves proposed order and reservations, and halt survives refresh.

28 real disposable-PG ledger/fill/commission/risk tests PASS7.21s,52326 exited0,
realized-integrity-fixed.txt. Ruff/diff pass. Reuse unaffected suite/browser/model
evidence; no active operation. No broker/provider connection, external orders,
notifications, production deployment, OS changes or live enablement.

Sales remain incomplete. Concrete next work must coordinate: explicit side in
immutable proposal/idempotency; strategy-owned quantity reservations and no shorts;
side-aware limit/fill checks; weighted basis disposal and realized proceeds;
late purchase/sale commission allocations; chronological reconciliation and
upgrade path for existing event evidence. Mandate strategy currently constrained
to periodic_fixture_buy/v1; do not silently reinterpret existing approvals.
Protect long-term allocation and retain independent human/mandate authorization.
L03/L05 remain IN PROGRESS; this prerequisite is not sale/accounting completion.

## Milestone: allocation-scoped accounting reducer integrated

HEAD unchanged. New execution/accounting.py validates bounded exact fill evidence,
unique identity/sequence and allocation ownership, computes weighted purchase
basis, partial/final disposal, net proceeds and realized PnL. Replaying final fees
correctly allocates late purchase costs across realized/retained basis. Final sale
releases rounding dust; local Decimal precision is independent of caller context.
Current buy-only reconciliation now uses reducer balances, preserving scope/FX/
fee revision/provenance checks. Sale orders still rejected at policy/reconciliation
boundary until durable sequence/reservations/callback integration is complete.

40 focused unit/real-PG tests PASS7.28s,43647 exited0,
sale-accounting-reducer.txt: chronology, weighted rebuy basis, partial/final sales,
late fee corrections, cross-allocation denial, duplicate sequence/ID, invalid
numbers, existing buys/fees/reconciliation/risk halts. Ruff/diff pass. Full suite
ACTIVE51068, suite-accounting-reducer.txt; poll before retry. No real broker
connection/order, provider calls, notifications, deployment or live enablement.

Full suite51068 exited0: 663 passed in 32.17s; suite-accounting-reducer.txt.
No active operation. Existing browser/model evidence retained for unchanged UI/inference.
Next: durable sale sequencing, allocation-owned quantity reservations, and side-aware
manual approvals/callback accounting. Do not enable sales by changing only preflight.

## Milestone: durable event sequence migration0013

2026-09-27 HEAD unchanged. Temporary approval usage-limit rejection prevented one
read; fresh review succeeded, no bypass. Owned PostgreSQL had stopped; confirmed
no server, restarted existing cluster, crash recovery reached READY. First tests
only failed connection (execution-sequence-migration.txt), no migration executed.
Re-run75934 exit0:2 migration tests PASS1.33s. Full frozen-schema chain now includes
0013; dedicated backfill test preserves payloads/timestamps, deterministic legacy
order, new timestamp-regressed events receive higher IDs, rolled-back sequence
gaps never reused. Generated ALWAYS bigint identity plus unique constraint; no
implicit startup migration. Reconciliation uses retained sequence in reducer/hash.

Positive identity/marker checks upgraded only test_acceptance_expenses and
test_browser_expenses. Existing126/105 events retain exact payload hashes:
execution-sequence-fixture-upgrade.json. Other test/restore/soak and production
schemas untouched. Downgrade refuses audit-order deletion; backup restore needed.
Full regression4487 exited0; suite-execution-sequence.txt records result. Browser
and current-schema recovery validation are next. No broker connections/orders,
real providers, notifications, OS policy changes, production deployment/live use.

Full regression PASS664 in24.57s. ACTIVE browser73289
(browser-execution-sequence.txt) and full synthetic recovery84027
(full-fixture-recovery-0013.log/json), independent databases. Recovery destination
test_recovery_20260927_sequence and matching .qa/recovery directory; do not retry
without inspecting operation/state. Check post-restore sequence continuation in
addition to table hashes. RUNBOOK/SOAK now document0013 prerequisite; soak database
is intentionally not upgraded yet. Current recovery0013 evidence remains pending.

Browser73289 exited0 PASS, browser-execution-sequence.txt; no console errors,
expected synthetic409 only. Recovery84027 exited0 PASS, full-fixture-recovery-0013:
27 table count/hash matches, vault/PDF/settings/model hashes and restored inference,
wrong-key rejection and source-fixture cleanup. Follow-up rolled-back inserts in
positively identified restored database prove identity continues above restored
maximum despite backward timestamps (execution-sequence-restored-continuation.json).
No active operations. Latest full suite664PASS24.57s. Production untouched; all
original safety restrictions preserved. Next: owned quantity reservations and
side-aware simulator approval/callback integration; sales remain disabled.

## Milestone verified: retained allocation ownership provenance

HEAD unchanged, preserved worktree, no live interrupted operation at start.
Confirmed55880 exit1: changing order.approval.mandate_id reassigned retained fills
while reconciliation still reported consistent (allocation-provenance-reproduction.txt).
Reconciliation now reads submitted events and resolves allocation only from one
matching retained event, actor/environment/manual details hash or mandate session/
hash provenance. Missing/mismatched approval becomes ALLOCATION_PROVENANCE_UNAVAILABLE;
no implicit manual fallback. Existing event-count assertion now includes the
previously unchecked submission event (5 versus4), preserving fill/fee coverage.

32 focused PG tests PASS3.90s (86343 exit0,allocation-provenance-fixed.txt).
Expanded ownership/actor/hash and HTTP durable-halt coverage12997 exited0,
allocation-provenance-halt.txt. Scoped Ruff/diff checks pass. No active operation.
Reuse prior664 full-suite and browser/recovery evidence for unaffected paths;
this milestone did not run a new full suite or browser. No external broker/provider
connection, order, notifications, deployment or live enablement.

Next: quantity reservation from provenance-backed allocation inventory, side-aware
manual proposals and callback accounting. Sales remain disabled; existing approved
periodic_fixture_buy mandates must not gain sell authority implicitly.

## Milestone: provenance-backed allocation inventory

HEAD unchanged; no interrupted operation at start. Added execution/inventory.py,
called by reconciliation and consequently exposed through existing owned simulator
snapshot. Quantities/basis and remaining pending-sale claims are allocation scoped;
cancel_requested/uncertain retain claims, terminal/proposed release, anticipated
buys cannot cover sales, duplicate/unknown/unowned/overreserved inputs reject.
Inventory is null unless entire ledger is consistent. Risk summaries omit this
potentially large view while preserving status/evidence hashes.

50 focused tests PASS3.01s (33502 exit0,allocation-inventory.txt), covering pending
states, partial quantities, cross-allocation/duplicate denial and exact fractional
owned inventory hidden on discrepancy. Full suite ACTIVE77064,
suite-allocation-inventory.txt; poll before retry. Ruff pass. Existing sale
submission remains disabled. This calculator does not establish concurrent sale
approval safety until integrated with locked approval transactions. No broker
connection/order, real provider, notification, deployment or live enablement.

Full regression77064 exited0: 681 passed in 20.95s.
No active operation. Reuse prior browser/recovery/model evidence for unchanged paths.
Next: locked side-aware proposal/approval, consuming owned inventory and retaining
reservations across uncertainty/cancellation; callback accounting must be integrated
before enabling simulator sales. All original trading restrictions remain.

## Milestone: commission correction uses replayed accounting deltas

HEAD unchanged; no interrupted verification at start. Traced sale lifecycle and
found commission callback unconditionally assigned all corrections to remaining
basis. It now obtains private before/after replay ledgers and applies only cash,
realized and retained-basis deltas. Public reconciliation response unchanged.
Existing discrepancies are not overwritten: commission evidence persists, typed
reconciliation_required and durable halt prevent new execution. Pending-before-fill
and older revisions retain prior behavior; duplicate callbacks charge once.

41 focused tests PASS11.73s (12292 exited0,commission-replay-deltas.txt).
Expanded reload/downward correction and discrepant-balance preservation tests log
43PASS12.68s in commission-replay-deltas-verified.txt; session93306 last poll still
reported running after final test summary. Poll terminal handle before retry.
Ruff/diff pass. No broker/provider connection, external order, notification,
deployment or live enablement. Latest full681-suite retained for unaffected paths.
Sale approval/quantity consumption and callback integration remain unfinished;
this milestone prepares fee accounting and does not enable sales.

Session93306 subsequently exited0;43 tests PASS12.68s confirmed. No active operation.

## Milestone in verification: manual simulator sales

HEAD unchanged. Initial backend sale tests1269 exited1 with15PASS/1FAIL: fee-before-
fill returned reconciliation_required. Interrupted fix was rejected before execution
by approval usage limit; fresh review succeeded and confirmed it absent, then applied.
Private settled-balance calculation now permits only validated pending-fee evidence
for observed fill accounting; public reconciliation remains unverified/no inventory,
and new approvals remain blocked while fees await fills. No other unknown reasons
are bypassed.54 related checks PASS20.52s (7128 exit0,simulator-sales-fee-recovery.txt).

Opted-in fixture manual sales use side-bound idempotency/details/approval, quote/
fee/order caps, and owned manual-allocation inventory checked again under the
account lock at approval. Pending order quantity claims prevent double reservation;
cancellation requests retain claims. Sale callbacks replay cash/basis/realized PnL;
partial/final/duplicate and cancel/fill cases preserve evidence and halt when needed.
7 end-to-end sale tests PASS3.78s (4488 exit0,simulator-sales-lifecycle.txt), including
independent concurrent database sessions: one approval succeeds, the other cannot
reserve the same shares. Existing accounts lacking explicit fixture/manual_sales
remain denied; protected holdings remain denied; buy mandates gain no sale authority.

Browser/API now offer unchecked manual-sales opt-in for newly created synthetic
practice accounts and an explicit Buy/Sell selector. Each sale still requires its
own independent approval. Full regression ACTIVE91611,suite-simulator-sales.txt;
real Chromium run started browser-simulator-sales.txt (capture/poll its handle).
No real broker/provider connection, external order, paid use, notification, OS
change, production deployment or live enablement. Verification is not complete.

## Milestone verified: opted-in manual simulator sale workflow

Full regression91611 exited0:690PASS75.11s (suite-simulator-sales.txt). Browser7817
exited0 PASS (browser-simulator-sales.txt): unchecked opt-in checked deliberately,
buy proposal/independent approval/fill followed by sale proposal/independent
approval/fill; source side shown, cash999.80EUR, realized-0.20EUR from two synthetic
fees, zero remaining quantity/basis, consistent reconciliation. Existing mandate,
expense, report/PDF, isolation, retention and logout checks retained; no console
errors beyond expected fixture409. Browser artifact's generic fill/fee label is
from the prior label; script now names buy/sell and realized checks explicitly.

Final finite0..100bps fee-policy check added so invalid fixture policy cannot
produce negative sale reserves.42770 exited0; simulator-sales-policy.txt records
focused sale/buy-mandate policy results. Full690/browser results precede only that
validation guard and documentation/label changes; unaffected evidence reused.
ACCOUNTING/BROKER_CAPABILITIES/MANDATES/ARCHITECTURE updated to distinguish manual
simulator sales from unchanged buy-only automated mandates. No active operation.

No actual broker/provider connection, external order, paid use, real notification,
OS policy change, production deployment or live enablement. Goal remains active.
Remaining: broader sale corner cases and autonomous strategy-specific sales,
corporate actions/flows/full period accounting, richer validated report/news
analysis, operations/retention/host soak/deployment and conditional external gates.
Do not promote full financial/broker gates from this synthetic manual workflow.

## Milestone in verification: unreconciled late-sale duplicate status

HEAD unchanged; no interrupted process at start. Reproduction27248 exit1 proved
that cancelled-sale fill after inventory reuse returned reconciliation_required
initially, but duplicate after reload returned filled despite unverified balances.
(sale-unreconciled-duplicate-reproduction.txt). New fill evidence records accounting
outcome before initial transaction commit. Duplicates preserve unresolved status;
legacy sale events without a marker consult reconciliation rather than assume
terminal execution means settled accounting. Observed quantities retained once,
no invented cash/short positions and existing halt preserved.

38 focused sale/execution/commission/reconciliation tests PASS17.70s (17885 exit0,
sale-unreconciled-duplicate-fixed.txt). Expanded legacy-shape regression ACTIVE98114,
sale-unreconciled-duplicate-legacy.txt; poll terminal before retry. Ruff/diff pass.
No actual broker/provider connections/orders, notifications, deployment/live changes.

Legacy regression98114 exited0: 39 passed in 23.97s. No active operation.
Reuse prior suite/browser evidence for unaffected paths; whole goal remains active.
Next: remaining sale ownership/strategy and full accounting/operations gates,
without treating manual simulator acceptance as external execution readiness.


## Milestone verified: bounded mandate evidence and durable runtime halt

HEAD remains 0e18029fe882497cd7bb998f5b855777ac474889; existing dirty work preserved.
Original pasted instructions read completely. Previous goal turn made code/test
progress; checkpoint alone was rejected by automatic review usage limit. Fresh
review now succeeded; failed checkpoint command was verified not to have executed.
Normal sandbox mount failure persists; approved scoped commands remain usable.
Interrupted90323 confirmed terminal exit0:16PASS11.28s (mandate-evidence-capacity.txt).
Daily approved orders, positions, pending reservations and runtime fixture quotes
now use deterministic 10,000-row limits plus overflow sentinel. Overflow persists
MANDATE_EVIDENCE_CAPACITY before a new order; runtime checks before refreshing
quotes. Independent PostgreSQL connection verifies committed halt/alert, unchanged
quotes/cash and no orders. 18945 terminal exit0:17PASS12.35s in
mandate-runtime-capacity.txt. Ruff and git diff --check pass. No active operation.
Command: TEST_DATABASE_URL="postgresql+asyncpg://lulu@/test_acceptance_expenses?host=$PWD/.qa/socket&port=55439" TEST_DATABASE_DISPOSABLE_TOKEN=fixture-acceptance-20260909 .venv/bin/pytest tests/integration/mandates_test.py tests/integration/risk_monitor_test.py tests/integration/manual_risk_test.py -q
This bounds loaded rows, not a measured query-latency SLA. No actual broker/provider
connection, external order/notification, production deployment or live enablement.
Remaining full scope unchanged: autonomous strategy-owned sales, corporate actions/
flows/period accounting, richer analysis, operations/retention/soak, deployment and
conditional external gates. Goal active, not complete.


## Milestone in verification: separately approved strategy-owned sales

Added price_band_fixture v1 alongside unchanged periodic_fixture_buy v1. Explicit
positive buy_below < sell_above thresholds enter immutable mandate review/hash.
Chosen over fixed target quantity because a fixed quantity would not exercise
sales without a mandate revision; no speculative model authority added. At low
price buy bounded quantity; at high price sell only this mandate's available
inventory. Neutral/no-owned-inventory returns no_trade; pending strategy intents
block another. Existing manual-sale opt-in is neither granted nor required for
this separate approved strategy. Revised mandates cannot inherit prior holdings.
Gross order caps apply to sales (fee-only cash reserve is not the order notional).
Retained ledger replay now applies aggregate instrument deltas for mandate-owned
sales while preserving each allocation's independent basis/provenance.
UI offers explicit strategy and threshold selection; approval remains separate.
Schema and mandate/accounting/architecture documentation updated.

36941 exit0:46PASS27.89s (strategy-sales-first.txt).58878 exit0:9PASS2.95s
(strategy-sales-authority.txt), including threshold mutation, protected instrument,
sale gross cap, manual/old mandate isolation, pending intent and exact realized PnL.
Ruff/node syntax/diff checks pass. Added forward-runner neutral/no-fill regression.
ACTIVE55509 full unit/integration suite: suite-strategy-sales.txt.
ACTIVE56669 Chromium on separate marked browser DB: browser-strategy-sales.txt.
Poll both before retry; neither result yet claimed. Main DB disposable marker is
verified by fixture; browser DB separate. No external connections/orders or live
changes. Full gate statuses remain unchanged pending broader verification.


Strategy milestone results: full unit/real PostgreSQL suite records708PASS88.64s
(suite-strategy-sales.txt); poll55509 terminal status if not yet recorded below.
Chromium56669 exit0 PASS (browser-strategy-sales.txt), including original buy-only
and new price-band independent approvals, prior workflows, zero console errors
apart from expected fixture409. No broker connection/external order.
No-trade decisions currently return truthful status but lack immutable durable
decision records; replaying a no-trade tick after quote change is not yet fenced.
Do not claim complete autonomous recovery until fixed. Next concrete work:
durable strategy decision evidence/idempotency for no_trade and signal inputs,
then full accounting/operations/host gates. No goal scope or permissions changed.

55509 confirmed terminal exit0. No active test processes; all milestone evidence saved.


## Milestone in verification: durable strategy decisions and no-trade replay

Previous turn made verified progress (708-suite/Chromium), all handles terminal.
HEAD still0e18029fe882497cd7bb998f5b855777ac474889; existing changes preserved.
Added StrategyDecision and explicit migration0014_strategy_decisions (from0013).
Append-only application evidence retains scope, mandate hash, tick key, quote/FX/
as-of, quantity/side, risk and original result with SHA256 integrity hash.
Account lock plus unique(account_id,tick_key) fences concurrent retries. No-trade
replay returns retained outcome even after price changes; submitted decisions
return current linked order status without reevaluating signal or resubmitting.
Changed evidence halts with STRATEGY_EVIDENCE_CONFLICT. Historical orders retain
legacy idempotency fallback; no invented historical decisions. Neutral decisions
are persisted without fake orders. Snapshot exposes newest100 records plus
truncation flag under active-owner scope. No mutation endpoint exists.

75854 exit0:22PASS13.49s (strategy-decisions-first.txt), including committed
independent-session restart/concurrency and migration chain. Explicit scoped
/tmp/ia_upgrade_strategy_decisions.py upgraded only marked test_acceptance_expenses
and test_browser_expenses to0014; execution payload hashes unchanged
(strategy-decisions-fixture-upgrade.json). Test create_all had made an empty new
table in mainfixture; helper locked it and proved zero rows before replacing it
with the migration-defined table. No existing evidence was deleted.
Startup/readiness/soak prerequisite now0014; production and old recovery/soak DBs
untouched. Latest recovery proof remains0013, so current0014 restore is pending.
ACTIVE92136: strategy-decisions-history.txt, adds owner isolation/history and
migration unique-index assertions. Poll before retry. Full suite/browser for0014
not yet run. No external connections/orders, production migration or live changes.


92136 terminal exit0:23PASS13.90s (strategy-decisions-history.txt).
87267 terminal exit0:Chromium PASS on0014 (browser-strategy-decisions.txt).
ACTIVE49219 fullsuite (suite-strategy-decisions.txt), last observed progressing.
Restore wrapper prepared /tmp/ia_restore_strategy_decisions.py; NOT YET STARTED.
Wait for suite terminal before running it because both use main fixture DB.
It will prove source marker/revision, refuse existing target/workdir, seed one
synthetic no-trade decision, invoke existing full vault/PDF/GGUF recovery runner
into test_recovery_20260928_decisions, verify restored decision hash/quote/outcome,
and remove only its synthetic source owner/allocation/decision records. Target
and .qa/recovery-test_recovery_20260928_decisions must be inspected before retry.
Command: PYTHONPATH="$PWD" TEST_DATABASE_DISPOSABLE_TOKEN=fixture-acceptance-20260909 .venv/bin/python /tmp/ia_restore_strategy_decisions.py
No model download or broker connection is involved. Actual current restore proof
remains0013 until this exercise completes; old results have not been relabelled.


49219 terminal exit0:711PASS110.78s (suite-strategy-decisions.txt).
Current Chromium already terminal PASS87267. Matrix reflects suite and0014 code;
prior0013 recovery remains explicitly historical. Runbook covers0014 and replay.
ACTIVE47259: /tmp/ia_restore_strategy_decisions.py, log
strategy-decision-recovery-run.txt. Do not rerun until terminal and target/workdir
inspection. Full restore uses existing local model, marked disposable databases,
new target only. No external connection/order, production deploy or live change.


47259 terminal exit0:full0014 recovery PASS,28table hashes/counts, vault wrong-key
rejection,PDF/settings/model hashes and3restored model tasks. No-trade decision
hash/quote/outcome preserved (strategy-decision-restored.json); full evidence:
full-fixture-recovery-0014.json. Sample p95=8.6586s for3tasks is not a service SLA.
Temporary synthetic source records cleaned; new target/workdir retained private.
Reusable wrapper saved as scripts/verify_strategy_recovery.py with explicit new
--target and --output-prefix, refuses existing output/target/workdir. Run from
checkout with PYTHONPATH="$PWD" TEST_DATABASE_DISPOSABLE_TOKEN=fixture-acceptance-20260909 .venv/bin/python scripts/verify_strategy_recovery.py --target test_recovery_UNIQUE --output-prefix UNIQUE
Use lowercase target/prefix. Do not overlap source-mutating verification with the
full integration suite. Script extracted from verified wrapper; CLI-only changes
lint/help checked, not a second expensive restore. No active operations.
Goal active; durable no-trade gap closed in local simulator. Remaining scope:
corporate actions/flows/period accounting, broader economic strategy evidence,
operations/retention/host24hsoak/deployment and conditional external gates.
No broker/provider connection, external order/notification, production deployment
or live enablement occurred. Gates not promoted beyond supporting evidence.


## Milestone in verification: research dividend receivables and payment timing

Previous turn completed verified decision/recovery work; all handles terminal.
Confirmed both replay engines credited ex-date dividends directly to cash without
payment evidence.54276 exit1:2 failing cash assertions (dividend-cash-reproduction.txt).
Shared DividendLedger now accrues source-currency entitlement before ex-open fills;
only explicit aware payment time releases cash, with dated positive payment FX
required for foreign currency. Outstanding entitlements remain marked receivables;
missing payment dates yield partial valuation. Later splits do not multiply prior
claims. Dividend accrual, cash paid, receivable and dividend FX PnL are separate.
Pending payments use a time heap and per-instrument amount totals rather than
rescanning all unknown-date claims. Gross-only convention; tax/withholding missing.
Provider history has no payment dates, so does not invent them. Research UI shows
received cash/unpaid receivables and valuation status. No execution/broker changes.
Engine fingerprints cover both replay implementations and the dividend module;
saved evidence decoder retains nullable payment times/FX. Historical results keep
prior-engine evidence rather than being relabelled under this implementation.

93609 terminal exit0 initial related checks.68662 exit0:27PASS5.11s before queue
refinement.85195 exit0:28PASS4.21s after queue/fingerprint changes, including saved
payment evidence reproduction and tamper rejection (dividend-payment-reproduction.txt).
Ruff/node/diff pass. Fullsuite/browser/current fixed research comparison pending.
No active process. No external broker/provider connection/order, paid use or live change.
Full accounting gate remains incomplete: execution corporate actions, external flows,
period attribution and broker reconciliation are not proved by these research tests.


## Dividend milestone verified after interruption

Previous turn made code/test progress; final checkpoint write alone was rejected
by automatic review usage limit. Fresh approval now succeeds.71513/84149 handles
are missing (not live); saved authoritative logs show724PASS88.86s in
suite-dividend-receivables.txt and real Chromium PASS in
browser-dividend-receivables.txt, zero console errors except expected fixture409.
Do not invent terminal exit codes for missing handles; do not rerun passed checks.
Unchanged predeclared comparison is saved in research-dividend-receivables.json:
INSUFFICIENT EVIDENCE/liveNO-GO, no parameter/criteria/holdout tuning.
No active operation. Next: reproduce combined spread/slippage impact allowing
nonpositive simulated sale prices despite individually valid bps. Goal remains
active; full accounting/operations/host/external gates still incomplete.


## Milestone verified: combined execution cost boundary

64534 terminal exit1:6 reproduced failures accepted spread/2+slippage >=10000bps
(research-impact-reproduction.txt). Shared validate now rejects these assumptions
before either replay engine can derive nonpositive sale prices. Positive-price
boundary retained; no weakening of independent fee/FX/lot rules.
32367 terminal exit0:35PASS1.19s (research-impact-fixed.txt), including all dividend,
research and portfolio replay checks. Ruff passed. Prior724fullsuite/Chromium
predate only this shared validation guard/new regression/docs; unaffected evidence
reused. No new whole-suite count inferred. No active operation.

Next discovered operations defect: execution/runtime.py selects first100 approved
mandates ordered by id on every invocation; later ids can starve indefinitely.
Use durable per-mandate scheduling/leases (existing operations/jobs.py requires
active real user identity), update due state on success AND failure so repeated
policy denial cannot monopolize a batch, fence completion, preserve committed
risk halts and same-tick order idempotency. Do not introduce a fake global user or
bypass user activation checks. Add >batch-size and concurrent-worker regressions.
Broader financial/operations/host/external gates remain incomplete. No actual
broker/provider connection/order, paid use, production deployment or live change.


## Milestone in verification: fair durable simulator dispatch

Previous goal turn made verified cost-boundary progress; no interrupted operation.
HEAD unchanged0e18029fe882497cd7bb998f5b855777ac474889, existing work preserved.
Runtime now joins per-user/per-mandate JobLease due state, selects never-run/oldest
due mandates up to100, and claims through the existing active-user lease boundary.
Success and ordinary policy denial advance due time60s; blocked early ids cannot
monopolize every batch. Work uses a fresh timestamp per mandate. Owner activation
is rechecked before any synthetic quote write. Completion is outside the ordinary
PolicyDenied handler: expired/stolen leases roll back all orders/fills/decisions/
quote writes in the work transaction. Ordinary policy halts still commit with
valid completion. Lease clock uses actual PostgreSQL clock_timestamp rather than
transaction-start time so long work cannot publish after lease expiry.

57265 exit1:3PASS/27 setup errors due connection refused; not code-test success.
Verified no postgres process, restarted existing .qa cluster via
bash scripts/start_acceptance_postgres.sh (37055 exit0), no reinitialization/data
removal/TCP service.28344 exit0:30PASS6.36s (simulator-dispatch-running-db.txt).
Coverage includes1-item batches with2 mandates, blocked-first fairness, concurrent
workers, persisted due/failure state, and1.1s lease-expiry rollback of synthetic
orders/fills/positions/decisions/quotes. Added deactivation-after-claim regression
not yet run. No current active process. Fullsuite pending because shared jobs clock
changed. No broker/provider connection/order, production or live-trading change.


Fair-dispatch fullsuite recorded735PASS24.18s (suite-fair-dispatch.txt), including
new deactivation-after-claim regression.19289 terminal status checked separately.
Prior real Chromium remains valid: no UI or approval-route behavior changed in
this milestone. No active work beyond verifying that suite handle is terminal.
Resource review: risk monitor already has cycle/query/lock timeouts; strategy
runtime now has bounded batch/query rows and fenced leases but lacks comparable
cycle/statement/lock timeouts and durable infrastructure-failure alerts. Add those
next using actual failure outcomes, without catching code defects as successes or
weakening user identity/lease fences. No claim of whole operations acceptance yet.


## Milestone in verification: bounded simulator execution and failure evidence

Previous turn achieved fair dispatch,735suitePASS;19289 was confirmed exit0.
Added20s cycle,10s candidate/work,5s claim/failure-persistence deadlines; SQL
statement_timeout5s and lock_timeout2s apply within each transaction. These mirror
existing risk-monitor engineering limits; they are not accepted host workload SLAs.
Recognized DBAPI/timeouts return failures, never success. Timed-out work rolls back
orders/fills/decisions/quote changes, then fenced failure completion plus in-app
alert commit together when the database/user/lease permits. Persistence failure is
explicitly unavailable. Cycle timeout preserves prior completed results and appends
partial_failure; no nonexistent global user/alert scope invented. External task
cancellation and unexpected code errors propagate and roll back active work.

99857 exit0:36PASS12.78s (simulator-dispatch-bounds.txt), including durable job/alert
failure, failed alert-store rollback, cancellation, code error and whole-cycle
expiry. New actual locked-account regression added (not yet run) to verify other
mandates can proceed after PostgreSQL lock timeout. Fullsuite pending. No active
operation. No actual broker/provider connection/order, external notification,
production deployment or live change. Goal remains active and incomplete.


22859 terminal exit0:741PASS34.87s (suite-bounded-dispatch.txt). Includes real
PostgreSQL account-lock contention: first account times out with persisted job
failure/in-app alert and unchanged cash/orders, while next mandate fills normally.
Ruff/diff pass. No active operation. UI unchanged; prior Chromium evidence reused.
Milestone closes strategy-runtime deadline/recognized infrastructure-failure gap;
no whole L10/host SLA claim. Remaining: execution-ledger corporate actions/flows
and full period PnL/report linkage, broader retention/operations/host24hsoak,
research external data quality and separately authorized broker/provider gates.
No actual broker/provider connections or external orders/notifications; no live
mode changes, production deployments/migrations or OS policy changes.


## Milestone in verification: reconciled simulator period reporting

Previous runtime milestone741suitePASS terminal; no interrupted work. Added
read-only execution/reporting.py: active-owner account locks, max20accounts,
reconciliation required before publishing period totals, UTC half-open local
booking interval, exact80digit Decimal totals, max100 displayed executions with
coverage flags and complete selected-row hash. Reconciliation optionally exposes
validated normalized fills linked to order/event/allocation ids and disposal PnL.
Reports collect this source with10s/5sstatement/2slock bounds, promote source failure,
and deterministically render a simulator-only section. No broker fill/PnL claims.
Latest retained fee revisions restate original fill-period results; they are not
period cash-fee flows or a historical point-in-time reconstruction. Missing opening/
closing marks and flows still prevent total weekly portfolio PnL claims.

63482 exit1:53PASS/1failure (execution-period-reports-first.txt); failure was old
capitalized limitation wording. Rendering now explicitly says "Broker accounts:
Realized P&L..." so the existing limitation remains clear while simulator facts
are separately reported. Added detail-cap/complete-total regression. Reverification
pending; no passing aggregate yet. No active process. No external connections/
orders, production deploy/migration, notification or live change.


## Reconciled simulator report milestone verified

51444 terminal exit0:746PASS39.44s (suite-execution-period-reports.txt).
17630 terminal exit0:Chromium PASS (browser-execution-period-reports.txt), model/
report-source fixtures explicitly retained. This browser scenario does not itself
prove the new real collector; separate execution-period-report-persistence.txt
records6PASS3.43s, including actual collector -> deterministic text -> realPDF ->
PostgreSQL report reload and embedded execution evidence.35401 terminal checked.
Model/news/broker-source stubs prevent external calls. Fullsuite predates only the
additional collector/PDF test; code unchanged. No active operation.

Current reports can state simulator booked realized results and attributed fill
fees with event/order/allocation references and reconciliation hashes for a chosen
calendar period. Zero totals only follow complete consistent ledger evidence;
unverified/discrepant accounts return unavailable, never fabricated zero. Details
are capped independently from aggregate totals. Results are current-knowledge
restatements, not reconstructed historical knowledge or total portfolio returns.
Remaining whole-scope gaps unchanged: execution corporate actions/flows, period
valuations and FX/benchmark attribution, richer validated analysis, broad retention/
operations/host24hsoak/deployment and conditional broker/bank/live gates.
No broker/provider connection/order, external notification, paid call, production
migration/deployment or live enablement. Goal remains active, not complete.


## 2026-09-28 resumed: optimized soak guards verified

Command access restored after read-only sandbox mount failures. Original attached
instructions reread completely; HEAD remains0e18029fe882497cd7bb998f5b855777ac474889;
staged/unstaged/untracked work preserved. No new applicable AGENTS.md found.
Prior51148 process confirmed terminal exit0; saved soak-optimized-fixed.txt proves
2PASS1.31s. New49148 terminal exit0:3PASS3.60s in soak-guards-verified.txt, including
optimized-Python acceptance of a correct disposable marker. Ruff format/check pass.
The harness uses unconditional guards rather than removable assertions for database
identity, marker, revision, persistent halt, readiness and stale-quote gates.
soak-fixture-upgrade-0014.json records prior named synthetic database upgrade;
no production migration. PostgreSQL PID7128 remains running on .qa Unix socket.

Active operation42690:90-second smoke, output .qa/soak-20260928-guards, evidence
soak-smoke-guards.txt. Poll this handle/check live PID before retrying. Command:
TEST_DATABASE_URL="postgresql+asyncpg://lulu@/test_soak_acceptance?host=$PWD/.qa/socket&port=55439" TEST_DATABASE_DISPOSABLE_TOKEN=fixture-soak-20260909 .venv/bin/python scripts/soak_acceptance.py --hours 0.025 --interval 2 --restart-every 20 --model models/qwen2.5-1.5b-instruct-q4_k_m.gguf --output .qa/soak-20260928-guards
No24hclaim. Prior746suite/Chromium evidence reused for unchanged application code.
No external broker/provider connection/order, notification, paid call or live change.

Smoke42690 terminal exit0; checkpoint status SMOKE_PASS, 90.165seconds, 49cycles, 4restarts, halt p95 30.805ms. Model run statuses: ['PASS']. No failures. Raw checkpoint retained under .qa/soak-20260928-guards. No active operation.
Next confirmed source defect: FAILED_BUDGET_OR_RESTART_GATE and INCOMPLETE_MODEL_OBSERVATION statuses can exit0. Add a CLI regression and nonzero terminal status before accepting automation exit codes. Full24h and broader matrix remain incomplete.


## Milestone verified: soak CLI failure exit status

Previous turn completed guard/smoke verification; no live interrupted operation.
2822 terminal exit1 reproduced persisted FAILED_BUDGET_OR_RESTART_GATE with CLI
exit0 (soak-exit-reproduction.txt). Runner now returns0 only for SMOKE_PASS/PASS_24H
and raises SystemExit with that result after checkpoint and child cleanup. Other
terminal statuses return1; exceptions retain their failure exit.
63218 terminal exit0:5PASS25.03s (soak-exit-fixed.txt), real marked PostgreSQL/HTTP
CLI runs verify missed restart -> failure/exit1 and observed restart -> smoke/exit0,
plus optimized-Python marker acceptance/rejection. Ruff and git diff --check pass.
Synthetic CLI users/checkpoints retained only in disposable DB and .qa/soak-cli-*.
Application code unchanged; prior746suite/Chromium evidence reused. SOAK.md updated.
No active operation, broker/provider connection, external order/notification,
production deployment or live enablement. Full24h observation remains pending.
Next substantive scope: execution-ledger corporate actions/external flows and
period valuation attribution; retained research dividends do not prove those.
Broader analysis, retention, target-host and conditional external gates remain open.


## Milestone in verification: deterministic reconciliation precision

1703 terminal exit1 reproduced identical persisted fractional-price evidence
changing from consistent to unverified under caller Decimal precision6
(reconciliation-precision-reproduction.txt). Reconciliation now owns precision80
for all evidence validation and aggregation and restores its caller context.
55862 terminal exit0:39PASS9.10s (reconciliation-precision-fixed.txt), covering
reconciliation, commissions, simulator sales and period reporting. Ruff/diff pass.
Active12572 full unit/PostgreSQL suite writes suite-reconciliation-precision.txt;
poll before retry. No browser-facing changes; previous Chromium remains applicable.
No corporate-action/flow support claimed by this correctness repair. Those and
period opening/closing valuation remain incomplete. No external connections/orders,
production changes, notification or live enablement.

12572 terminal exit0:753PASS67.98s (suite-reconciliation-precision.txt). No active operation. ACCOUNTING.md documents context isolation; PLAN L11 evidence refreshed without claiming remote CI. Next: corporate-action and cash-flow ledger integration, including durable provenance, reconciled attribution and report intervals; no production migration authorized.


## 2026-10-03 resumed: synthetic cash-flow persistence in verification

Global task-observer skill/helper read; global observer logs contain no entries.
Global AGENTS progress-monitor policy active. Fixed rubric monitor baseline53;
latest completed audit58% (+5pp), no gate declared complete from focused tests.
AccountLedgerEvent migration0015 shares execution sequence; record_cash_flow is
internal synthetic-fixture-only (no public/model/MCP route or real transfer).
Active-owner lock, explicit fixture flag, base currency/time/reference validation,
idempotency/conflict hash, reserved-cash protection and existing reconciliation
required. Cash, flow evidence and receipt commit atomically. Account/strategy
PnL/high-water checks exclude retained flows; mandate budgets remain unchanged.
Collector/report text now retain period-booked cash-flow IDs/hashes apart from
trading results. Split reducer exists but persisted split integration remains absent.

Recovered42566 handle missing; log proves26PASS6.77s in account-events-risk-report.txt.
Prior first5PASS1.74s includes reviewed-schema migration tests. Initial migration
attempt failed before connecting (PostgreSQL stopped during host interruption).
Verified no live postgres process, restarted existing .qa cluster (78791exit0);
automatic recovery succeeded, Unix-socket-only, no reinitialization. Positively
verified all three named database markers before migration; main empty create_all
fixture table replaced transactionally with actual migration DDL, browser/soak new
table created, markers upgraded14->15. Evidence account-events-fixture-upgrade.json.
No production database touched. Startup/readiness/soak/recovery require15.

Active18358 fullsuite -> suite-account-events.txt; browser handle recorded by next
checkpoint update -> browser-account-events.txt. Poll handles/logs before retries.
Pending current15 full backup/restore and concurrency evidence. Previous753suite
and14restore retained with original scope; not relabelled as current acceptance.
No actual broker/provider connections/orders, paid calls, external notifications,
production deployment, OS policy changes or live enablement.

18358 terminal exit0:777PASS80.61s (suite-account-events.txt).66909 terminal exit0:realChromium PASS (browser-account-events.txt), zero unexpected consoleerrors. Fullsuite includes real receipt collector->text->PDF->persisted evidence test. Recovery first invocation exit1 before imports/db because omitted documented PYTHONPATH. Corrected documented invocation94281 active; evidence account-events-recovery-verified-run.txt, newtarget test_recovery_20261003_flows. Do not retry while live. New concurrencytest added but not run until recovery finishes to preserve dump comparison. No source application changes after fullsuite.


## Cash-flow milestone verified — 2026-10-03

94281 terminal exit 0: current 0015 full synthetic recovery passed.
account-events-recovery-full.json records all table counts/hashes, vault/PDF/settings
and existing local model recovery (3 tasks); account-events-recovery-decision.json
proves original decision/quote and cash-flow digest survive, restored ledger
reconciles, and the shared sequence advances safely after restore. Continuation
probe rolled back; only this runner's source fixture records were cleaned up.
91211 terminal exit 0: 7 PASS in 3.57s (account-events-concurrency.txt), including
actual concurrent withdrawals: one applies, the other cannot reuse consumed cash.
777 full-suite and current browser checks remain valid for application code; only
new test/recovery runner/docs followed them. No current process.

Next: persist split evidence and integrate allocation quantities/basis without
automatically changing approved orders, protected ownership or trading limits.
The pure reducer's 42 tests do not prove persisted split support. Cash-flow service
remains internal fixture-only; real external flows and public confirmation UI are
not claimed. Full period marks/FX/benchmark attribution still absent.
Progress monitor audit requested with these results; keep the established rubric.
All original non-live restrictions preserved. No actual broker connection/order,
real provider access/notification, production deployment/migration or paid use.

Progress audit completed: GOAL PROGRESS61% (+3pp from58), fixed weights retained in PROGRESS_MONITOR.md. Monitor corrected initial overcredit for incomplete report/retention requirements before publication. L07/L09 remain partial; no gate promotion implied. No active process. Next split implementation must share journal ordering, validate instrument ownership, preserve each allocation basis, reject conflicting/pending-order adjustments, invalidate pre-split quotes and preserve/operator-halt pending policy review. Do not interpret pure reducer support as persisted corporate-action completion.


## Persisted split milestone in verification

No previous active operation. Added internal synthetic record_split using the
0015 journal/shared sequence. It validates ownership, source/time/ratio and
idempotency, refuses unresolved/non-filled instrument orders and retroactive
actions, preserves each allocation basis/cash/limits, and invalidates pre-split
quotes. New corporate-action halt requires review; existing operator halt remains.
Reconciliation replays splits with fills/flows and exposes separate period action
references; deterministic reports label these synthetic facts, never broker fills.

60622 exit2: missing-service reproduction.61940 exit1:9PASS/1 fixture error
(buy limit100 against quote120 before intended pending-order split check). Fixed
fixture to use a marketable pending sale.80391 exit1:21PASS/1 fixture error
(report context omitted required period). Corrected explicit period. No thresholds
or assertions weakened. Fullsuite17587 active -> suite-split-events.txt, poll before
retry. Ruff passes. No public/model/MCP write route added. Pending fullsuite,
restore split evidence, and monitor audit before this checkpoint is complete.
No broker/provider/external order/notification, production or live change.

Resumed17587 handle is missing; saved suite-split-events.txt proves782PASS186.97s. No live pytest process, no inferred exitcode. Existing suite reused, not restarted. Split database restore74984 now active; split-recovery-run.txt, newtarget test_recovery_20261003_splits. Runner scripts/verify_split_recovery.py uses original marked source and verify_restore, preserves all database rows/hashes, then checks exact split reconciliation/quantity/basis/cash/halt. Vault/model recovery reused from prior0015 exercise (unchanged paths). Poll before retry.


## Persisted split milestone verified

782 full unit/PostgreSQL PASS186.97s in suite-split-events.txt.17587 missing after
interruption; no live pytest and no inferred terminal code.74984 exit1: first
restore matched all29tables but its source-versus-restored dictionary comparison
used pre-reload Python numeric representations. Restored-state inspection showed
consistent ledger, qty4/basis200/cash800 and required review halt.
Verifier now flushes/expires/reloads source rows before comparison; full equality
assertion retained.73300 terminal exit0 on a NEW target
test_recovery_20261003_splits_verified. Evidence split-recovery-verified-database.json
and split-recovery-verified-split.json:29table hashes, exact reconciliation and
quantity/basis/cash/halt preserved. Original failed target/evidence retained.
Source synthetic records cleaned up by each runner; no existing destination
overwritten. Prior0015 vault/model recovery reused; no additional model work.

Reproduce with a fresh target/prefix from checkout:
PYTHONPATH="$PWD" TEST_DATABASE_DISPOSABLE_TOKEN=fixture-acceptance-20260909 .venv/bin/python scripts/verify_split_recovery.py --target test_recovery_UNIQUE --prefix UNIQUE

No active process. Application code unchanged after fullsuite; only verifier/docs
changed. Ruff/diff pass. Prior Chromium remains evidence for unchanged UI flows,
not a new split interaction. Next required scope: persisted dividend/withholding
events and full period valuations/FX/benchmark attribution; historical split
restatements and operator review UI still not implemented. No actual broker
connections/orders, real notifications, production or live enablement.

Monitor audit complete: GOAL PROGRESS63% (+2pp from61; raw62.5/100). Fixed weights retained, earnedpoints saved in PROGRESS_MONITOR.md. Goal active and incomplete; no remaining operation.

## 2026-10-03 dividend receipts milestone (64%)
HEAD unchanged0e18029fe882497cd7bb998f5b855777ac474889; existing staged/unstaged preserved.
39986 interrupted reproduction recovered exit2 missing service; saved dividend-events-reproduction.txt.
Implemented internal simulator-only received dividend payments with gross/withholding/net attribution,
shared journal sequence/replay, protected-income review halt and report provenance.
82327exit0:43PASS10.46s dividend-events-first.txt. Latest audit64% raw63.5, fixed rubric saved.
No live/broker operations. No public input route or inferred ex-date/receivable entitlement.
Added post-sale allocation/late-fee/tampering/period-boundary checks next; broad suite pending.

Dividend verification:54063exit0,792PASS97.92s suite-dividend-events.txt (includes
post-sale allocation, fee restatement, tampering and period boundaries).
79969exit0: fresh test_recovery_20261003_dividends;29table hashes and exact persisted
reconciliation equality, cash807.5/gross10/withholding2.5/qty4/basis200/halt preserved.
Evidence dividend-recovery-database.json and dividend-recovery-split.json.
Reproduce with fresh --target/--prefix:
PYTHONPATH="$PWD" TEST_DATABASE_DISPOSABLE_TOKEN=fixture-acceptance-20260909 .venv/bin/python scripts/verify_split_recovery.py --with-dividend --target test_recovery_UNIQUE --prefix UNIQUE
No active process; Ruff/diffchecks pass. Existing Chromium evidence remains for
unchanged UI; no fresh dividend UI claim. Next local scope: normalized expense
retention workflow; full valuations/corporate actions/operations also remain.

Dividend recovery audit completed64%delta0,raw64.125/100; fixed points saved.

## 2026-10-03 normalized expense-history retention (65%)
HEAD unchanged, all earlier staged/unstaged preserved. Internal bounded export/purge
and browser controls implemented with explicit owner confirmation, plan/exporthash,
10minute expiry, no pending/recent receipts, import serialization and hashed retirement
keys blocking re-import. Minimal audit replaces removed-history category details.
0016_expense_retirement migration upgraded only main/browser/soak marked fixtures;
expense-retirement-fixture-upgrade.json. Readiness/startup/recovery scripts require0016.
80188exit2 missing service reproduction retained.2910exit1:9PASS1FAIL old test orphanuser;
corrected fixture creates activeuser, policy unchanged.97037exit0:15PASS5.67s in
expense-history-fixed.txt. Added concurrency/rollback/inactive/batch tests and browser
export+confirmation+crossowner+CSRF+re-import workflow verification.
ACTIVE handles9172(focused tests),51960(Playwright). Poll before retry.
Monitor65%raw64.625 saved. Browserplugin absent; repo Playwright used.
No productiondata purged, live disabled, no external bank/broker/order connections.
Remaining broad gates unchanged; latest792suite and29table restore predate0016/retention.

## 2026-10-04 resumed verification
36562/35800 handles missing, no livepytest/browser. Durable logs prove16PASS5.80s
expense-history-concurrency-fixed.txt and ChromiumPASS browser-expense-history-fixed.txt;
no inferred terminalexit. Original9172exit1 source-vs-reload decimal-scale changed
planhash; fixed canonical ten-decimal export, exactchecks retained.51960exit1
browser reimport lacked file after earlierpage reload; helper reselects fixturefile.
Audit66%raw65.625; fixedrubric saved. Temporary screenshots lost after interruption;
harness now saves .qa/browser-evidence. No claims of visual review yet.
76413exit1:559unitPASS238integrationERROR, all fixtureconnection refusal.
43116exit1:fixture server connectionrefused. No runningPG; existingpgdata retained.
72559exit0 restarted owned Unixsocket-only PG. Log proves interrupted Oct3 server
and successful crash recovery Oct4 11:50WEST,ready. No reinit/dropdata.
ACTIVE63401 fullsuite recovered,36326 browser visual recovered. Poll before retry.
New scripts/verify_expense_retirement_recovery.py ready to run ONLY after fullsuite
finishes (avoid dump comparison during fixture writes). Requires fresh target/prefix,
explicit marker; verifies30table restore, removed rows absent, tombstones and reimport
suppression. No source code changed after63401 began except docs/browser evidence paths.

## Retention milestone verified
63401exit1:794PASS3exportfixtureERROR missingactiveusers. Corrected export fixture
creates and cleans its owners; production checks unchanged.42794exit0:3PASS1.39s.
36326exit0BrowserPASS; mobile screenshot captured sidebar transition beforefinish.
Harness waits for hidden sidebar geometry;67565exit0BrowserPASSdesktop/mobile,
zero unexpectedconsoleerrors. Durable .qa/browser-evidence screenshots inspected;
readable controls, no clipping. Browser plugin absent; repoPlaywright used.
6804exit0:30tablehashes revision0016 PASS restored test_recovery_20261004_retirement;
removed rows absent,2retirementhashes preserved,reimport suppressed,sourcefixtures
cleaned. expense-retirement-recovery-database.json and -retirement.json.
49407exit0:797PASS70.03s suite-expense-history-final.txt. Diff/Ruffchecks pass.
Monitor66%raw65.975 fixedpoints saved; no overallcomplete/blocked claim.
No broker/bank connection,orders,realdata purge orproductionmigration;live disabled.
Next: account-risk precision reproduction37467 pendinghandle; log currently6PASS1FAIL
RISK_BUDGET_UNAVAILABLE under caller Decimalprec6. Risk should own numericcontext;
continue regression/fix then full period portfolio valuation. Retentionbackups/orphanPDF,
operations,host24hsoak/CI,broaderchat/research andconditionalexternalgates remain.

## Execution precision milestone (67%)
37467exit1 reproduced false RISK_BUDGET_UNAVAILABLE at callerprec6.
New execution/numeric.py owns128digit tasklocal context including rounding/traps;
wrapped policypositive/orderhash/preflight, manualpropose/approve/fill/transition,
commission corrections, markedrisk and approvedautonomytick. Ten-decimal storage
validation remains unchanged.47PASS7.67s first;26298exit0 48PASS10.05s verified,
including exact1040.0000000002equity, manualsale/latefees and100.1autoreservation,
all preservingcallerprec6ROUND_UP. Added unsupportedprecision rejection/caller
context restoration test. Ruffpass. ACTIVE20870 fullsuite-execution-precision;
poll beforeretry. Prior797fullsuite ispreprecision. Progress67%raw66.975 saved.
Next remains period valuation snapshots/completeperiodPnL, broader retention/ops,
realhost/research/externalgates; no changedauthority orliveenablement.

## Verified resume point:2026-10-04
20870terminalexit0:801PASS88.11s suite-execution-precision.txt. Latest application
source included by fullsuite, Ruff/diffchecks pass. No active operation.
HEAD0e18029fe882497cd7bb998f5b855777ac474889; no agent commits/staging/resets.
Latest UI proof browser-expense-history-visual-final.txt (exit0, desktop/mobile,
realChromium+PG with fixturemodel/provider; inspected .qa/browser-evidence).
Latest persistence proof expense-retirement-recovery-database.json and -retirement.json
(0016,30tables,removedhistory/suppression restored). UI/retention unchanged by later
precisionfix. No claim of fresh browser/external validation of precision arithmetic.
Original objective preserved. Completedthissegment: persisteddividend gross/withholding
and protectedincome accounting/report/restore; normalizedexpense history export/purge/
reimport suppression/browser/migration/restore; execution Decimal-context riskfix.
Next highest local scope: immutable account/user/strategy period valuation snapshots,
opening/closingmarks, flowadjusted portfolioPnL and explicitFX/benchmark attribution.
Current report intentionally leaves portfolio_period_pnl unavailable; risk observations
in account.mandate overwriteprevious and are NOT immutable historical marks. Do not
reinterpret a currentquote as historical or a firstdailyobservation as periodopening.
Other remaining: unpaiddividend entitlements/cashinlieu/otheractions/operatorreview,
backup expiry/completedorphanPDF cleanup, operationssleep/clock/backlog validation,
host24hsoak/remoteCI/build, broadchat/model/evidence/research. L15noapprovedverified
paperaccount,L16liveprereqs/mandate; live staysdisabled. No broker/bank connections,
realorders,externalnotifications,productiondeploy/migrate,OSconfiguration changes.
Finalshortprogressaudit pending; goalACTIVE, no globalblocker/no completion claim.

Final checkpoint audit completed:GOAL PROGRESS68%delta+1pp,raw67.6/100. Fixedrubric updated. No active toolprocess; Goal staysACTIVE and incomplete, next work as above.

## 0017 valuation work in progress
66984exit2 missingmodel reproduction. Added immutable owner/account snapshot model,
current-only capture, exactboundary flowadjusted PnL, unavailablemissingmarks.
0017 upgraded all3markedfixtureDBs (valuation-fixture-upgrade.json); no production.
88732handle missingafterinterruption; authoritativevaluation-first.txt5PASS2.93s,
no livepytest/no inferredexit. Added allocationattribution, sourceclockguard,
reportcollector/fallback, browsercapture/compare and scopedAPI.98545exit1:10PASS2FAIL
oldreporttests expectedno partialerror despite missingmarks. Now explicitpartial
coverage retained; execution/PDF checks retained.31771browser logPASS (handle to poll)
with valuationworkflow+CSRF/crossowner; snapshotscreen notyetinspected.
PG stopped acrosshostboundary (Oct4 22:36smartshutdown log); no livePG beforestart.
26444exit0 restartedexistingprivatefixture,noinit/dropdata. Goal68%raw67.85fixedrubric.
Next runreporttests/broaderbrowser(fullpartialstatus)/suite+0017snapshotrestore.
No brokerconnection/orders/liveenablement. FullperiodFX/benchmark andhistorical
boundarycoverage remainopen; currentmarksneverbackdated.

## Valuation report/browser/restore milestone69%
25553exit0:24PASS6.19s valuation-reporting-fixed.txt, preserving executions/PDF while
missingexactboundaries now explicitlypartial. 31771exit0 initialbrowserPASS.
65575exit0 browser-valuations-layout.txt desktop1440x1000/mobile390x844 realChromium+PG,
source/provider/model fixtures explicit. Savebeforebuy/saveafterfill/compare-0.1PnL,
CSRF403/crossowner409; zero unexpectedconsoleerrors. Inspected durable .qa/browser-evidence/
valuation-desktop.png andvaluation-mobile.png. Exactdisplayonly trims trailingzeros;
no numericalrounding. Native selectors fitviewport, statuswraps.
17984exit0:805PASS64.71s suite-valuations.txt.36094exit0:6PASS0.79s valuation-guards.txt
(includes2tests addedafterfullsuitecollection; applicationunchanged). No historical
pricefabrication; sourcefuturebooking/invalidFX/capacity/tamper guards verified.
15959exit0 verify_split_recovery.py --with-dividend --with-valuations --target
test_recovery_20261004_valuations --prefix valuation-recovery;31tablehashes0017PASS,
exactperioddict/source-restored equality including7.5PnL,split/dividend/cash/basis/halt.
Evidence valuation-recovery-database.json andvaluation-recovery-split.json. Ownsource
fixtures cleaned, newtarget/archive preserved. Goal69%raw68.685fixedweights saved.

## Daily observed history integration in progress
Added one firstUTCday snapshot to existingexplicitopt-in riskmonitor, with savepoint
and dedup in-app alert on archival PolicyDenied. Archivalcapacity never disables
currentriskchecks; no midnightboundary inferred.94386exit0:19PASS3.80s
valuation-monitor-first.txt tests repeateddailyID, updatingcurrentrisk, capacityfailure
anddedupalert. Added lease-expired successfulrisk variant to prove snapshotrollback.
ACTIVE67204 fullsuite-valuation-monitor; poll before retry. Snapshotmonitorcode changed
after priorfullsuite/browser/restore; latestfullsuitepending. No broker/bank/live actions.

Daily snapshot final verification:67204log810PASS62.85s suite-valuation-monitor.txt,
including expiredsuccessfulworker rollback(no snapshot orfalsejobcheckpoint), all
prior risk/manual/valuation tests. Final audit69%delta0raw69.185fixedpointssaved;
intermediate arithmetic corrected inPROGRESS_MONITOR.md. Goalactive/incomplete.
No applicationcode changes after fullsuite, onlydocs. All authorizationrestrictions
preserved. Nextsafeprogress remains originalrequiredgaps listedabove.

## Completed orphan PDF cleanup milestone
Resumed baseline audit69% delta0 raw69.185; previous67204 terminalexit0 confirmed,
810PASS evidence reused. No interrupted test/browser/recovery processes remained.
Reproduced publication/reference gap46330exit1 in report-publication-lock-reproduction.txt:
exclusive cleanup could acquire lock after PDF publication before DB persistence.
Reporter now holds shared directory lock through reference commit/failure; worker
retains its own render lock after request cancellation. New operator-only
cleanup_report_orphans.py previews exact old completed orphan files, then confirms
plan with all-owner references reloaded under directory exclusion and PG SHARE table
lock. No automatic policy; no API/model tool. Bounded scans, unsafe layout/clock
refusal, metadata recheck, private outputs, actual partial deletion counts and fsync.
90883exit0:36PASS2.10s report-orphans-first.txt. Ruff fixed4 formatting/import issues;
diffcheckPASS. Fullsuite and CLI committed-path verification pending. Only synthetic
PDFs removed. No production/broker/bank/live actions. GoalACTIVE; milestoneauditpending.

Milestoneaudit69%delta0raw69.435; L10+0.25 saved. ACTIVE51835fullsuite-report-orphans and49899browser-report-publication-lock; poll before retry.

Orphan verification completed:51835exit0 suite-report-orphans.txt820PASS62.12s;
49899exit0 browser-report-publication-lock.txt PASS desktop1440x1000/mobile390x844,
no unexpectedconsoleerrors; model/providerfixtures explicit, no externalorders.
55417exit0 report-orphans-cli.txt11PASS3.37s (one added test afterfullsuitecollection,
applicationunchanged). New uniquely named marked disposableDB created and dropped
only by test; actual CLI preview/confirm deletes syntheticorphan, preservesreference.
Separate connection referencewrite blocked by PG SHARE lock. Ruff importsort only
followingtests. No activeoperations. Remainingbackup expiry next; GoalACTIVE69%.

Postverificationaudit70%delta+1raw69.685 L10=3.625 saved. All orphanoperations terminalexit0. Nextdatabasebackupexpiry requires verifiedrestoreevidence/exactconfirmation/protectednewest; liveoff.

## Standalone database backup expiry milestone
64968exit0 restartedexistingPGdata after no livePG (Oct5 shutdown/interruption;
automaticWALrecovery, noinit/drop). New backup_retention module/operatorCLI accepts
explicitcutoff/keep>=1 and restoredreceipt/sourceidentity/checksum. Locks matching
writer acrossdump/restore/receipt; newestverifiedper-source protected. Exactplan,
streambyte/filelimits, aliases/symlinks/clock/changedplan guards, truthfulpartialIO.
verify_restore defaults preserve_unclassified_bundle; explicit--standalone-retention
requiredfor eligibility. Fullfilesystem/keybundleexpiry remainsopen, nohiddenclosure.
32566exit0 initial10PASS1.59s;68018exit0 refactored10PASS2.65s;
85111exit0 backup-expiry-bundle-guards.txt11PASS2.35s (includesrealCLI syntheticexpiry).
8683exit0 backup-expiry-restore-run.txt31tables0017, unclassifiedreceipt preserved.
53216exit0 backup-expiry-standalone-run.txt31tables0017, newsourceidentity/standalone
receipt. ActualCLIpreviewexit0 backup-expiry-real-preview.json protects1/deletes0.
Bothnewtargets/archive remain; no earlierartifactpurged. Rufflineformatfixaftertests.
Noactiveprocesses; GoalACTIVE70%raw69.685 untilmilestoneaudit. Nextcoherentbundle
retention and otheroriginalgaps; liveoff/no broker/bank/production/OSchanges.

Milestoneaudit70%delta0raw69.935; L10=3.875saved. Nextpriorityreview schedulerclock/backlogrecovery; coherentbundleexpiry remainsopen.

## Job clock/replay fencing in progress
69441exit1 job-clock-reproduction.txt2FAIL3PASS demonstrates backwardclock pre-acquire
completion accepted and completedtoken replay accepted. Added0018leased_at nullable,
no inventedlegacytimestamp;acquire stampsDBtime;complete requiresleased_at<=now<until
androtatescompletedtoken. LegacyNULL refusescompletion, normalfreshreacquire permitted
afterexistingdeadline. Startup/readiness/recovery/soakrevisionguards now0018.
16706exit0 upgradedall3positivelymarkedfixtureDBs0017->0018, evidencejob-clock-fixture-upgrade.json.
27305ACTIVE job-clock-fixed.txt focusedops/migration/runtime/risk/news tests; pollbefore
retry. Broaderfullsuite/browser/0018restore stillpending. Noexternalwrites/liveactions.
27305exit0:32PASS73.14s job-clock-fixed.txt. Then extended immediate fences in news,
riskclaim and brokerread keep_lease path; added2brokerclockregression cases preserving
running checkpoint. Fullsuite-job-clock nowrunning;pollhandlebefore retry. Legacy
migrationtestedNULLpreservedtoken/checkpoint, freshleasecurrenttime no catch-up replay.

Audit70%delta0raw70.185 L10=4.125saved. ACTIVE36712suite-job-clock,58313browser-job-clock; pollbefore retry.

## Current verification failures and startup-budget repair
36712terminalexit1 suite-job-clock.txt:835PASS2FAIL440.69s; both soak CLI failures
were FIXTURE_SERVICE_START_TIMEOUT with0cycles, not lease assertion failures.
58313terminalexit1 browser-job-clock.txt fixturestartupdeadline; server log saved
browser-job-clock-startup-server.txt shows eventualstartup andcleanstop. No passclaim.
4525restorehandle missing afterinterruption: durable job-clock-restore.json/run.txt
PASS31tables0018, no live restoreprocess; no inferredexitcode/no duplicate restore.
Identified count100 x0.1s loop could fail near10s before predeclared15s startupbudget.
6224exit1 soak-startup-budget-reproduction.txt2FAIL (12s readiness prematurelyfails;
16s casewrong failureclassification). Changed soak loop to actual15s monotonicdeadline,
boundedremaininghealthtimeout/postresponsecheck; budgetNOTincreased.27546ACTIVE
soak-startup-budget-fixed.txt. ExistingPG stillrunning, no restartneeded.
Next:poll27546; runfailedsoaktests and serialbrowser with originalbrowserdeadline;
then acceptanceverification. Authorityreview alsofoundpotential inactiveowner race
account_for_user readsUserwithoutlockbeforewaitingaccountlock; mustreproduce/fixnext.
No other applicationcode changes; liveoff/noexternalbroker/bank/productionactions.

27546exit0 startupbudget2PASS2.82s;59337exit0 soak-startup-reverified.txt5PASS38.67s. Budget15sunchanged. Audit70%raw70.06 L11reduced4.75 basedpendingfailureatinspection. Newowner-racerepro andbrowser-job-clock-reverified inprogress; appcodeunchangedwhileverifying.

## Principal lifetime race repaired
79567exit1 execution-owner-race-reproduction.txt confirms realDBdeactivation could
commitwhileworkerwaitedforaccountlock. account_for_user nowFOR SHARE activeUser
beforeFOR UPDATE account.57687exit0 execution-owner-race-fixed.txt41PASS42.04s;
concurrentdeactivation lockblocked then succeedsafterauthorizedtxn, subsequentworkdenied.
AUTHORITY_REVIEW.md mapsoriginalL02requirements; no gatepromotionyet,currentfull/browserpending.
41560exit0 browser-job-clock-reverified.txt desktop/mobilePASS withunchangedstartup
limit; fixtureprocessstartedbeforeprincipalfix, so thisisclockversionvalidationonly.
Noactiveops now. 0018restore31tableevidencevalid; fullcurrentvalidationnext.

Principal-lifetimeaudit70%raw70.31 L02=4.25saved. ACTIVE26999suite-owner-lifetime; serialcurrentbrowserafterthisrun. Noapplicationchangesafterlaunch.

26999exit0 suite-owner-lifetime.txt840PASS200.26s; includesalllatestclock/owner/startup/backup/orphanchanges. Currentbrowser-owner-lifetime startedseriallyafterfullsuite; pollbefore retry. Noapplicationchangesafterfullsuite. Dockerreadonlyprobe confirmsWSLcommandunavailable; targetbuildgateunchanged.

26823exit0 browser-owner-lifetime.txt currentversionPASS desktop/mobile allworkflows;
0unexpectedconsoleerrors,0brokerconnections/externalorders. Inspected latestvaluation
desktop/mobile screenshots, no newlayoutregressions.840fullsuite+browser currentvalid;
onlydocs editedsince. AUTHORITY_REVIEW verification updated; exactL02gateauditpending.
GoalACTIVE70%raw70.31, allprocessesterminal. Remainingbroaderaccounting/bundleretention/
ops/hostmodel/research/externalgates; Dockerreadonlyprobe stillunavailablehere.

Finalmilestoneaudit74%delta+4raw74.06 L02=8/8; monitorreviewfoundeachactualL02
conditionevidenced, no vaguependingreview. PLANL02PASS localboundary; L04/L15/L16
externalvalidation/authorityremainopenblocked. Noactiveoperations; HEADunchanged,
allstaged/unstaged/untrackedworkpreserved. GoalACTIVE, nextfinancialattribution.


## Price/FX attribution implementation milestone
83561terminalexit1 valuation-fx-first.txt2FAIL8PASS: newtest fee0.2 exceeded
approved0.18reserve, correctlyhalted. Fixturefeeallowance20bps corrected (no risk
policyweakening).29772exit0 second10PASS.78661exit0 valuation-fx-scoped.txt30PASS14.85s.
New schema2 snapshots retain cumulative source/base trade principal/fees and FX
marks; closing-rate decomposition reconciles total and perallocation P&L. Missing
legacyhistory/staleFX explicitunavailable; dormantclosedposition requiresnoFX.
Report/UI updated; browser assertionadded. Ruff touchedmodulesPASS.
Prior840suite/currentbrowser are beforethisunit; fullnew suite/browser/restore next.
Noactivecommands at checkpoint; progressaudit running. GoalACTIVE74%lastverified;
no broker/bank/orders/live/settings/production actions. Preserve currentworktree.


## FX verification resumed October6
87597handlelost; processabsent and suite-valuation-fx.txt terminalsummary846PASS144.99s.
Noexitcodeinferred.14207exit1 browser-valuation-fx.txt: actualUIzero0E-20/0E-40
violatedreadabilityassertion. Exactdecimaldisplay now normalizesonly mathematically
zero strings (noNumberconversion/rounding). Backendunchanged:846suitemaybereused.
Progressaudit74%raw74.06delta0, unchangedweights. CurrentPG5241live. Browserrerun
and fresh0018schema2restore next; no realorders/connections/liveconfigchanges.

26915exit0 browser-valuation-fx-fixed.txt fullrealChromium/PostgreSQL desktop/mobile
PASS, zeroformattednormally,0unexpectedconsoleerrors,0brokerconnections/orders.
Mobilevaluation screenshotinspectedreadable.3731exit0 valuation-fx-recovery-20261006:
31tablehashes0018PASS, split/dividend/exact schema2periodresult survivesrestore;
newtargettest_recovery_20261006_fx andarchive retained. Noactivecommands now.
846backendtests remainvalid (onlyJSzeroformat/docs changedsince). Progressaudit
pending; next scopedchat combinedread/followupdefectreview. Liveoff unchanged.


FXmilestoneaudit74%raw74.185: L11=4.875 fixedrubric saved. Nextreadfollowupwork:
78321exit1 read-followup-reproduction.txt8FAIL2PASS. Combinednews waslostforholdings/
positions/carteira, posiçõesmissing; explicitrefreshfollowups fetchednoevidence.
Independentnewsclassification plus read-onlyuser-refreshcontext fixed; prioractions
andnewtopicscannotreplay, tool/assistantcannotsetscope, dispatchrechecksexclusions.
4285exit0 read-followup-fixed.txt40PASS4.40s.14580exit0 read-followup-stream.txt11PASS
includesactualeventflow unavailableportfolio/news collectedfresh withoutmodelguesses.
RuffPASS.40712ACTIVE realexisting1.5BCPU benchmark workflow-followup-cpu-20261006.json,
8synthetictoolcases, no downloads/provider/broker/orders. Pollbefore retry.
Noapplicationcodechangeswhilebenchmarkruns. Fullsuite aftercurrentchatfixpending.

40712exit0 workflow-followup-cpu-20261006.json PASS8/8scope/eventcases. Reviewedfacts:
0.004/EUR100/noinventedtotal; headlineabstention; load6.30s/peak1976.18MiB.
Mostpathsdeterministic, notmodelquality/speedclaim. Excludedfollowupmodel17.55s generic
refusalstillqualitygap. Fullsuite-read-followup launched next; pollbefore retry.
No backendedits after benchmark. Progressaudit running; last74.185rawdisplay74.

Readaudit75%delta+1raw74.685 L06=3.5 saved; activefullsuite50775suite-read-followup.txt.


50775exit0 suite-read-followup.txt857PASS162.52s. Next simulationfix:71240exit2
badpytestreservedparametername correctedwithoutsourcechange;65452exit1 genuine
4FAILsimulation-ambiguity-reproduction-valid.txt. Parserguessed IT/AGAIN/APPLE and
droppedexplicitexchange; unavailabletoolresultdisplayedcompletedzeroreturns.
Now ambiguous/noexplicitproviderinstrument returns clarification, keepsindependent
scopedreads; explicitlistingrequiresprovider-symbolconfirmation (no guessedmapping).
Deterministicsimulationformatterextracted src/finance/simulation_answer.py rejects
missing/invalidresults, preservesbasecurrency andpartialpersistence.5376exit0
simulation-ambiguity-fixed.txt40PASS1.37s. Added native-modeclarification parameter
coverageafterthat run; broadercurrentverificationnext. Latestprogress75%raw74.685,
L03/L08 exactcriterionreview pendingmonitor. No externalconnections/orders/livechanges.


## Global manual/strategy exposure boundary
Simulationfinalaudit75%raw74.685unchanged;871suitePASS. MonitoridentifiedL03global
manualconcentrationgap andL08providerchanged-ID/outsideoverlapgaps; providerfixNOTstarted.
New global-exposure-reproduction.txt3FAIL verifiesmanualproposal/approval andcross-
instrumentpendingbudget gaps. JSONaccount global_exposure_limits nowrequired;
newbrowserfixtures explicitperinstrument500/total750EUR includingpendingfees.
Existingaccountswithoutlimits failclosed; none retroactivelyassignedlivepolicy.
Riskobservation bounds1000positions/pendingorders; marked+reservedbreachpersists
halt. Sharedorderprojection underaccountlock guardsmanualpropose/approve/autonomy.
42932exit0 global-exposure-first.txt46PASS7.19s.47701exit0 global-exposure-guards.txt
10PASS0.84s inclindependenttransactionconcurrentapproval, stricterglobalvstrategy,
missing/nonfinite/inconsistentlimits, markedgainbreach andsalehaltbypassdenial.
Noactiveprocessesatcheckpoint; fullcurrenttests/browsernext. HEAD0e18029 unchanged,
allpriorstaged/unstaged/untrackedchangespreserved. Noexternalconnections/orders/livechanges.

Globalcapaudit75%raw74.935 L03=7.75saved.84798exit0 suite-global-exposure.txt881PASS69.24s. Currentbrowser-global-exposure startedserially; pollbefore retry. Backendunchangedsince881suite; JSONpolicyrequiresnomigration.

91980exit0 browser-global-exposure.txt desktop/mobilePASS allworkflows, noerrors/
brokerconnections/orders. Finalcapmilestoneaudit75%raw75.185 L03=8/8PASSsaved;
881suitecurrentvalid, appunchanged, noactiveoperations. NextL08changed-IDpending
resolution: officialdocs output-transaction-details consultedOct6, identifiersoptional,
no guaranteedtransitionlink established. Planexplicitowner-reviewedexport/confirm
pending-retirement linkedtobookedrecord, hashedreimportsuppression, no fuzzyguessing.
No providerfixcodeyet; previousoverlapandunmatchedpendinglimitationsstaydocumented.


## Pending/booked reconciliation implementation in progress
New src/expenses/reconciliation.py and web/expense_reconciliation.py provide explicit
owner-selectedpair/export/hash/10minutepreview/independentconfirmation. No fuzzyID
mapping. Sameaccount/provider/currency/type required; unknowntransferdirection and
conflictingcategoryoverrides refused. Confirmedpending removedwithhashedsuppression
andminimalauditlink; bookedamount/sourceclock preserved, categoryoverride retained.
No migration (existing ExpenseAudit/ExpenseRetirement); no providerrequests.
51628exit1 expense-reconciliation-first.txt1FAIL8PASS exposed ORMcategorycopy moving
providerreceivedclock. Explicitdirty retainedsynced_at fixesnewpath andexisting
categoryroute.82639handlelost; no livepytest, durable expense-reconciliation-fixed.txt
terminal19PASS1.08s; noexitcodeinferred. UIselection/export/confirmation nowadded;
notyetbrowserverified. APIreceived_at addedfortruthfulper-rowreceipt evidence.
Next: browserhelper+CSRF/owner/export/reimport/clock checks, rollback/concurrency,
fullsuite/restore. Currentlastfull881/browserglobalcap precedethisunit. GoalACTIVE75%
raw75.185, no activecommands. HEADunchanged/priorworkpreserved/liveoff.


8475exit0 browser-expense-reconciliation.txt realChromium/PostgresPASS; addedhelper
actuallyran despitefirstoutputcheckslistmissingitslabel (metadatafixedafterrun).
Downloadedpair/independentapproval/CSRF/foreignowner/falseapproval/exporthash/replay,
bookedamount/receiptclock/categorypreservation/reimport suppression verified.
Mobile screenshotinspectedreadable; subsequentJSdisplaytrimsamounttrailingzerosonly.
18228exit0 expense-reconciliation-concurrency.txt11PASS0.70s includesatomicrollback
andindependenttransactionimportblockeduntilresolutioncommit then suppressed.
60367exit0 pending-recovery-20261006-run.txt31tables0018restorePASS; -retirement.json
confirms audit/bookedrow/category/clock/identitysuppression exactlyretained.
Targettest_recovery_20261006_pending andarchive retained; onlyownedsourcefixturescleaned.
Noactivecommandsatcheckpoint. Fullsuitecurrentnext, lastscore75raw75.185/L08stillpartial.

98535 observed exit0: suite-expense-reconciliation.txt 892PASS72.31s. Monitor75%raw75.310 L08=4.875 saved. Starting explicit owner-selected historical bank retrieval; no external requests. Prior UI trailingzero presentation verification will run with new controls.

## Explicit bank-history retrieval milestone
Implemented owner-selected date endpoint/UI and sync override; local730day bound,
existing5000record/2MB/30sprovider limits, cookie/CSRF/config/owner/consent/account guards.
Preserves absent transactions, category overrides, retired identities, backoff and
ordinary incremental cursor. Durable metadata explicitly states coverage unverified.
86079exit1 bank-history-reproduction.txt4FAIL5PASS before implementation;31869exit0
bank-history-first.txt9PASS;52700exit0 bank-history-guards.txt11PASS;12269exit0
bank-history-cursor.txt12PASS0.83s includes narrowhistory notskippingbacklog.
25009exit0 browser-bank-history.txt fullChromium/PostgresPASS with interceptedbankUI
and realdisabledAPI/CSRF; reconciliation amountdisplay reverified andmobileinspected.
Currentfullsuite session22951 writes suite-bank-history.txt; inspectbefore retry.
No migrations/externalconnections/orders/livechanges. HEADunchanged, priorchangespreserved.
Monitor milestoneaudit requested; lastcompletedraw75.310/display75%.

22951exit0 suite-bank-history.txt899PASS71.12s. L08localfixturecriteriaPASS; monitorraw75.435display75 L08=5 saved. Realbank remainsseparateblocked. Starting L06observedexclusion-followupanswer qualitygap with failingtests; noappchangesafter899suiteyet.

Bankhistoryfinalaudit75%raw75.435 L08=5/5PASS confirmed after899suite; rubricupdated.
Exclusion-answer reproduction81837exit1 read-exclusion-answer-reproduction.txt4FAIL:
modelgenericrefusal/no useful explanation also degradedpath. Added deterministic
userrestriction answer when onlyrequested scope excluded; no model/tools or authority
change, independent allowedreads continue.56815exit0 read-exclusion-answer-fixed.txt
37PASS0.87s default/native/degraded/externaltext/refresh/scopereallow coverage.
Realexisting1.5BGGUFbenchmark62860 running; inspect before retry. Fullsuiteafterchange
notyetstarted. No externalconnections/orders/livechanges.

62860exit0 workflow-exclusion-answer-cpu-20261006.json8/8PASS, explicitrestriction
content assertionPASS. Existing1.5BGGUF CPUload1.418s peak1955.61MiB; excludedrequest
0.0001s deterministic (not inferencebenchmark). Monitor76%raw75.935 L06=4saved.
88756exit1 suite-read-exclusion-answer.txt903PASS1FAIL69.63s: native_markup test
expected modelmarkuprefusal even though newroute correctly avoids inference entirely.
Updated regression to assert0inference+restriction generation on excludedpath; retained
1inference+markuprejection onNO_TOOL_CALLING path and unchangedno-dispatch assertions.
Next rerunaffected+fullsuite. Broader L06qualitative portfolio answerquality remains.

20565exit0 suite-read-exclusion-answer-fixed.txt904PASS confirms nativeguardupdated
without weakenedno-dispatch behavior. New portfolio_review.py +answerscontractid
readable descriptive sourceanalysis/qualitygaps, account/currency uniqueconId same-
time exposuregroups withDecimal128 and explicitcash/lookthrough/authoritylimits.
portfolio-review-reproduction5FAIL;65613exit0 first26PASS;5438exit0 guards28PASS1.22s
includes postbenchmarkzeroquantityguard/rounding/nonfinite/extreme/Portuguese.
76575exit0 workflow-portfolio-review-cpu-20261007.json9/9PASS with actualanswerquality
assertions; existing1.5BGGUF load1.535s peak1955.98MiB, deterministicpathnotmodelperformance.
Monitor76%raw76.435 L06=4.5saved. Fullsuite70820 active suite-portfolio-review.txt;
inspectbefore retry. Next actual L06 gap: combined portfolio/scanner currently
returns rawnewsJSON instead of validated newsanalysis; source-selection quality needs
safe mixedfact/instruction fixture review. No externalconnections/orders/livechanges.

70820exit0 suite-portfolio-review.txt911PASS79.23s. Portfolio descriptive review
milestoneverified; monitor76%raw76.435 unchanged. Currentnextunit scanner/news:
65468exit1 scanner-analysis-reproduction.txt3FAIL (combinedportfolio bypassednews
analysis and directsourcecommand acceptedasobservation). _financial_response now
joins exactfinancialreview with separatelyvalidated tool-free newsassessment;
sourceinstructionqualityfilter shared news/report; unknown/truncatedcompletion
rejected.99835exit0 scanner-analysis-first.txt49PASS1.02s. Added retry/incomplete
finishregressions afterwards, nextfocusedrunpending. Actual1.5BGGUFmodel6307running
workflow-scanner-quality-cpu-20261007.json/run with512outputtokens; predeclared
factselection/noinstruction/independentreadchecks. No fullsuiteafterthisunityet;
monitor saidrunning but it is pending, only modelbenchmarkisactive. No source,
externalprovider/broker/order or livepermission changes beyondauthorizedcode.

Scanner/model quality milestone ongoing:68345exit0 scanner-analysis-guards.txt52PASS;
6307exit0 workflow-scanner-quality-cpu-20261007.json measuredFAIL (safeabstention,
no usefulfact in2cases; exit0alone notPASS). Added exact bounded sentencecandidates,
recognizeddirective exclusion and quoteenums; sourceevents unchanged.44155exit0
scanner-analysis-candidates.txt53PASS.48490exit0 workflow-scanner-candidates-cpu-
20261007.json2/2PASS: scanner10.976s, scopednews9.133s; factualrevenue selected,
no injectedcommand, limits/scopes/exactfinancialfacts retained; load1.020s peak2012.73MiB.
17554exit0 report-source-quality-cpu-20261007.jsonFAIL22.23s, analysisinvalidafter
rejectinginstruction. Reportpromptnow onlycandidatequotes+period; financialevidence
rendered/storedseparately, original14kcollectionbudget retained.20260exit0
scanner-report-candidates.txt36PASS.21006exit0 report-source-candidates-cpu-20261007
nominalPASS is NOT accepted: manualinspection found thirdquote Enablelive...USD999999;
firstqualityassertiononlytestedIgnorephrase. Expanded explicitenable/disable/change
candidatefilter andbenchmarkchecksallselectedquotes;97303exit0 instructionguards39PASS.
Finalreportbenchmark10368 running report-source-candidates-final-cpu-20261007.json/run.
Inspecthandle/outputbefore retry. No fullsuite since911priorportfolio milestone;
newscanner/reportfullsuite andbrowser pending. Latestfixedrubric76raw76.435 unchanged.

## Scanner/report real-model quality validated; regression work in progress
- Final report benchmark10368 exited0: source-candidates-final JSON PASS13.654s;
  only factory closure and the source's no-forecast/no-price limitation selected.
- Native scanner86289 exited0: workflow-scanner-native JSON PASS38.508s through
  deterministic read recovery. Default scanner10.976s; retain default routing.
- Latest audit77%, raw76.935, L06=5/6; rubric saved. Full current suite is pending.
- Review found history-success UI called cached loadExpenses() rather than forced
  refresh. Added a browser assertion requiring a fresh expenses GET after success;
  reproduction54219 writes browser-history-refresh-reproduction.txt. Inspect it
  before retry. Fix not applied yet. No other process active at this checkpoint.
- No broker/bank connections, external orders, production or live-setting changes.
