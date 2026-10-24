# Local implementation and validation plan

## Owner direction — 22 October 2026

The application will deploy on a different computer. This laptop's 24-hour soak,
component-mapped CPU-temperature checks and clock repair are **DEFERRED to the
actual final host**, not passed. Stop pursuing those laptop checks; the pending
Portable ZIP download/setup request here is cancelled. Preserve historical evidence.
Final-host OS, architecture and hardware are unknown; follow the
[final-host handoff](FINAL_HOST_HANDOFF.md) before any target-specific action.

The owner explicitly keeps **research and Paper gates OPEN**. L04/L14/L15 are not
deferred or completed. Portable checkout implementation and offline verification
may continue; the fixture-only durable Paper intent/attempt journal does not grant
actual broker connectivity or SDK write authority. The Goal remains incomplete,
external writes remain closed and live trading stays OFF. Existing e154/0019,
860-unit/392-PostgreSQL and amd64-image evidence remains scoped to its recorded
inputs; later code/migrations require affected verification and a newly resolved
checked-out migration head. No future schema number or hardware acceptance is
inferred from those historical results.

## Portable software milestones — 22–23 October 2026

The [offline submission journal](BROKER_SUBMISSION_CONTRACT.md) now passes
[119 focused checks](evidence/paper-submission-focused-20261022.json) and
[907 unit +431 PostgreSQL cases](evidence/paper-submission-backend-20261022.json)
on unchanged source `b46651e69925c7e56f6ebf4e43816cf781bfa3330f94eef29b03c5e3ac3f0765`.
Migration0020 and startup/readiness guards are aligned.
[Local DB-only durability](evidence/paper-submission-durability-20261023.json) now
passes actual ownedPG restart/new journal object/no resend and33tables/17rows
restored with independently matching SQL counts/hashes. It does not prove a Python
process restart, ephemeral vault-key recovery or restored-copy dispatch. Local
[image/runtime/restart checks](evidence/paper-submission-image-review-20261023.json) pass.
The exact approved16-file patch is [published](evidence/paper-submission-publication-20261023.json)
as a2b2f42; [187context/184image bytes reconcile](evidence/paper-submission-published-image-reconciliation-20261023.json)
to that commit. [CI39875250173](https://github.com/Investments-Assistant/investments-assistant-local-machine/actions/runs/39875250173)
completed SUCCESS: [verified CI](evidence/paper-submission-ci-20261023.json) confirms907unit/431PG/1342overlapping combined cases,24browserflows,8TLS/WSSchecks and the exact-SCM Sonar gate PASS. Actual Paper and final-host gates remain pending.
The owner started Docker Desktop; explicit desktop-linux version29.8.2/linux-amd64
checks pass. The new local image has now passed; publication is explicitly approved
and complete for this exact16-file bundle. The historical e154 CI/image results below do not
validate the candidate. The Goal service reports PAUSED; this user-authorized
portable work changes no Goal status. Latest custom audit:90%, raw90.375/100.

### Required portable work now in progress

The fixture-only lost-acknowledgment correlation unit is now implemented and
[locally verified](evidence/paper-recovery-backend-20261023.json):920unit tests,
458 initially passing PostgreSQL cases and the one unchanged clock-sensitive case
passing on a single targeted retry. The initial `CLOCK_DISCONTINUITY` failure is
retained; this is not a clean full PostgreSQL-tier pass. [172 focused tests](evidence/paper-recovery-focused-20261023.json)
cover reference provenance, ambiguity, later conflicts, revocation, legacy hashes,
bounds, reload and no resend. Correlation remains uncertain and grants no authority.

The exact [six-file review](evidence/paper-recovery-publication-review-20261023.json)
and [patch](evidence/paper-recovery-publication-review-20261023.patch) are prepared,
[approved and published asd5aa99e](evidence/paper-recovery-publication-20261023.json).
[New image build and isolated smoke PASS](evidence/paper-recovery-image-review-20261023.json)
for image5631759f/source13aa:187context/184copiedimagefiles match, nonroot/read-only/
networknone and newreference/default-denial checks pass; temporarycontainer is gone.
Only three source modules changed;184deployment/model/UI/migration/config inputs
are unchanged. Independent review supports scoped reuse of priora2bmodel/startup/
restart evidence, with no new fullruntime execution claimed. Exact six-file
publication is complete; [exact current-CI/Sonar39983987095](evidence/paper-recovery-ci-20261023.json)
passes allfourjobs:920unit/459PostgreSQL/1383overlapping combined cases,24browserflows,
8TLS/WSS checks and84.40% measuredcoverage including browser-server lines. The
configured primary report-task Sonar gate explicitly PASSED for exactd5aa. Do not rebuild or rerun successful checks merely
because publication changes HEAD; reconcile exactcommittedblobs to testedbytes.
The [new native test fixture is cleanly stopped](evidence/paper-recovery-owned-cleanup-20261023.json).
No migration or actual broker connection/order occurred. Research/Paper remain OPEN;
actual final-host24h/temperature checks remain deferred.

## Recorded baseline before this direction

Authority: attached instructions read completely, most recently2026-10-20.
Scope is this checkout. Live trading and external SDK writes remain denied.
Read-only Paper connectivity was separately authorized and performed once through
the owner's authenticated UI and reviewed finite loopback relay. The TWS Paper
banner was verified visually; persisted SDK evidence still labels environment
unverified, with no execution authority. No production deployment, real external
notifications, paid calls or further OS changes are authorized.

Current HEAD:e154a0a365ece2a9fd81657034139c43c8e0abe6 on local master/origin main.
The exact approved seven-file cash/halt patch is published; current remoteCI
[39083730719](https://github.com/Investments-Assistant/investments-assistant-local-machine/actions/runs/39083730719) allfourjobs and configured Sonar gate PASS for exacte154.
The approved26-file credentials patch and approved two-file packaging repair are
published; unrelated local documents/evidence are preserved. Both fields remain
required without custom character/length rules. [Credential checks](FLEXIBLE_CREDENTIALS.md),
[published CI](evidence/build-input-ci-20261017.json) and
[local image validation](evidence/flexible-credentials-image-review-20261017.json)
pass. Exact image build-context bytes reconcile to the committed files in
[context review](evidence/postpublication-context-review-20261017.json); original
image provenance is preserved, with no additional cold-build claim.

A real WSL kernel restart interrupted the private app and new-source observation.
[Boot evidence](evidence/native-kernel-interruption-20261017.json) and
[retained soak review](evidence/soak-24h-credentials-20261017-interruption-review.json)
prove interruption, not a24h pass. Existing operator PostgreSQL recovered without
initialization/migration/key replacement; its one persisted read has complete
positions but incomplete cash and is non-atomic. Normal app recovery now passes native and ordinary Windows HTTPS checks;
the owner confirms Enabled/Read Authorized were unchecked and saved. Relay17497 is closed;
no automatic broker retry. Historical valid checks remain scoped to their
recorded source. The retained fe94d676 halt-harness milestone changes no image
inputs. The subsequent cash-collector source change does affect the image;
its final fingerprint is4fd1380c and full local validation passes. Both fixes
are approved/published in e154a0a; exact current remoteCI and Sonar now pass.

On20Oct another kernel restart invalidated79f7 and the old app-only refresh
proposal. Private app recovery above describes17Oct historical evidence, not a
current readiness claim. No recovery, SQL or secret access was performed on20Oct;
see [native metadata and limits](evidence/operator-runtime-metadata-20261020.json).

Last recorded pre-deferral custom audit90% (raw89.875/100); one scoped persisted actual read
earns partialL04 credit. Goal service now reports ACTIVE after continuation;
no overall completion is claimed. Actual full
Paper lifecycle/reconciliation and rights-cleared research remain open. Mapped
cooling and the continuous host observation remain incomplete and are now deferred
to the final host. The53a8 window was stopped after its restart halt-check gap
was reproduced. Local fix,24affected tests and a90.214-second/five-restart
real smoke pass. Current publication/remote CI pass; the new24-hour window remains incomplete.
A separately reproduced missing selected-account cash path and stopped-cache
freshness case are fixed:110 focused cases (included in860 full unit),392
PostgreSQL cases, and the new image/runtime/cleanup pass. See
[cash safety](CASH_READ_SAFETY.md) and the
[exact candidate review](evidence/cash-halt-publication-review-20261018.json).
Window79f7ab59792c was interrupted by another kernel restart before24hours.
Its stale RUNNING checkpoint is partial evidence only; old-window retention is verified. The new078d window then failed its clock guard;
read-only clock evidence confirms a311ms backward step. See CHECKPOINT.md.
Prior app/image proofs remain scoped to their recorded inputs.

Sequence (continue while safe productive work remains):
1. Reproduce authorization and numerical defects; fix deterministic boundaries.
2. Repair financial normalization, expenses, simulator, and factual orchestration.
3. Add durable execution/risk, migrations, scoped operations and provider fixtures.
4. Repair isolated PostgreSQL fixtures and CI; run unit/integration/browser tests.
5. Continue portable Paper/research implementation and verify affected local checks;
   carry host/model/continuous observation acceptance to the actual final computer.
6. Review all gates; record external blockers and reproducible checkpoint.

## Gate matrix

PENDING means required local work remains, not an external blocker.
DEFERRED means the owner moved a check to the final host; it earns no PASS credit.
Latest milestone and exact partial results: [CHECKPOINT.md](CHECKPOINT.md).
No aggregate gate is promoted solely on a subset of regression tests.
The publishedd5aa offline journal/correlation passes current imagebuild/smoke,
committedbyte reconciliation and exactCI/Sonar, including a clean459-case CI PGtier.
The earlier localCLOCK_DISCONTINUITY failure/retry remains preserved. Actual
external Paper and economic acceptance remain incomplete; final-host hardware
checks remain deferred.

| Gate | Status | Evidence / remaining work |
|---|---|---|
| L01 Baseline | PASS | HEAD/dirty-state preserved; [feature and authority map](ARCHITECTURE.md), [audit disposition](AUDIT.md), [measured host and explicit unknowns](MODEL_HOST.md) |
| L02 Authorization | PASS (local candidate) | [Authority invariants](AUTHORITY_REVIEW.md) plus [flexible credential and session review](FLEXIBLE_CREDENTIALS.md): current825unit/390reconciledPG and real browser checks cover independent approval, scopes, exact identity, legacy/compact cookies, canonical revocation, concurrent credential-change denial and bounded verification. External Paper authority remains separate. |
| L03 Risk | PASS | Trusted fixture price/FX, atomic reservations, halt/protected tests; [approved simulator mandates](MANDATES.md), marked-loss/drawdown and concurrent tick tests; manual marked-risk/durable rejection tested; periodic risk monitor and [internal ledger reconciliation](evidence/suite-reconciliation-final.txt) tested; [global manual/strategy caps and concurrency](evidence/global-exposure-guards.txt), [881 current tests](evidence/suite-global-exposure.txt) and [browser](evidence/browser-global-exposure.txt) pass. External broker reconciliation remains L04/L15. |
| L04 Broker lifecycle | PASS (offline local fixtures); BLOCKED (external validation) | [Submission contract](BROKER_SUBMISSION_CONTRACT.md), [172 focused checks](evidence/paper-recovery-focused-20261023.json) and [current exact-CI backend](evidence/paper-recovery-ci-20261023.json) (920unit/459PostgreSQL) verify committed handoff, scoped idempotency, uncertainty/no-resend, revocation, bounded unfinished tasks and retained callback discrepancies. Committed reference/late-execution correlation now passes: strict binding/contract/hash match, uncertain/noresend, sticky contradictions and legacy/truncated evidence denial. No runtime SDK transport is registered; actual broker identity/authority/reconciliation remain incomplete.  [Cash safety](CASH_READ_SAFETY.md) and [backend proof](evidence/cash-collector-backend-review-20261018.json):110 focused cases within860 unit, plus392 PostgreSQL PASS. Fresh primary-account callbacks, matching end/readiness, Decimal bounds, cleanup and stopped-cache denial verified. Durable local lifecycle/uncertainty/restart fixtures pass; [capability review](BROKER_CAPABILITIES.md). Earlier actual read remains one partial non-atomic snapshot: positions complete, cash incomplete, operator-declared Paper/SDK-unverified, authority none. User read flags OFF; no repeat. Full external history, reauthentication, execution/reconciliation and separately approved forward plan remain absent. |
| L05 Financial correctness | PASS (local fixtures) | Decimal/FX/mixed currency/rebalance regressions and [persisted synthetic cash-flow/risk/concurrency tests](evidence/account-events-concurrency.txt) pass; [persisted synthetic splits and restore](evidence/split-recovery-verified-split.json) pass; [received dividend/withholding replay and restore](evidence/dividend-recovery-split.json) pass; [unpaid entitlement/linked payment, risk/valuation/report and exact fixture recovery](ACCOUNTING.md) verified; [1031 fullsuite](evidence/suite-dividend-receivables.txt) and [browser](evidence/browser-dividend-receivables.txt) pass. Foreign/special corporate actions and external reconciliation remain explicit unavailable/partial states and external gate limitations |
| L06 Useful chat/autonomy | PASS (local runtime) | [Requirement-by-requirement review](CHAT_REVIEW.md), [923 unit/PostgreSQL tests](evidence/suite-scanner-source-quality.txt), [default scanner factual quality](evidence/workflow-scanner-candidates-cpu-20261007.json), [native comparison](evidence/workflow-scanner-native-cpu-20261007.json), [current source-validator recheck](evidence/source-quality-current-validator.json); scoped reads, parsing, follow-up, exclusions, injection and tool-error conditions pass. Economic edge and external execution remain separate gates. |
| L07 Reports | PASS (local fixtures) | Period/evidence repairs, persisted failure status and [422-suite failure/migration checks](evidence/suite-report-status.txt); [real PDF/status reload](evidence/browser-report-status.txt); [history failure propagation verified](evidence/report-history-persistence.txt); [deterministic financial rendering and validated model extracts](evidence/suite-report-authority.txt); [reconciled simulator-period execution/PDF evidence](evidence/execution-period-report-persistence.txt); [immutable boundary valuations, accrued/received income, report truthfulness and restore](ACCOUNTING.md), [1031 fullsuite](evidence/suite-dividend-receivables.txt), [37 affected report checks](evidence/dividend-report-truthfulness.txt) and browser pass. Missing historical marks/benchmark basis remain explicitly unavailable; external reconciliation and comparative research remain separate gates |
| L08 Expenses | PASS (local fixtures) | Identity/currency/lifecycle/pagination/isolation, [retention](RETENTION.md), [explicit changed-identity resolution and bounded older-history recovery](BANK_SYNC.md), [12 sync guards](evidence/bank-history-cursor.txt), [899 tests](evidence/suite-bank-history.txt) and [browser](evidence/browser-bank-history.txt) pass. Real bank consent/access/credentials remain a separate blocked external gate. |
| L09 Persistence | PASS (local0020 fixtures and DB-only recovery) | [Current exact-CI backend](evidence/paper-recovery-ci-20261023.json) verifies upgrades through0020 and journal concurrency/reload. [Independent durability](evidence/paper-submission-durability-20261023.json) proves actual ownedPG restart/new journal object/no resend and33tables/17rows restored with identical SQL counts/hashes. No Python-process restart, ephemeral key recovery or restored-copy dispatch is claimed. Earlier restore proofs remain scoped. Explicit migrations through0019, including exact credential/key upgrade and [synthetic dump/restore](evidence/flexible-credentials-restore-20261016.json); full reviewed-schema upgrade/quarantine tests; [current 0015 fixture vault/PDF/model recovery PASS](evidence/account-events-recovery-full.json), [restored no-trade decision PASS](evidence/strategy-decision-restored.json), [0010 database restore PASS](evidence/restore-report-status.json); [durable chat evidence and inactive-content retention tested](CHAT_EVIDENCE.md); [owned report tombstones and restart recovery](RETENTION.md) tested; [coherent bundle publication/expiry and full 0018 vault/PDF/model recovery](RETENTION.md) verified. Resolve and verify the actual checked-out migration head for new work; actual Paper, final-host and production/off-host validation remain separate |
| L10 Operations | PASS (recorded local controls); 24h host acceptance DEFERRED | Scoped jobs/alerts/recovery and startup/continuity tests pass; [90-second/five-restart smoke](evidence/soak-halt-guard-smoke-20261017-dc10b4e9d5cb-review.json) proves GET-before-POST halt checks. The79f7 window was interrupted at2824cycles/80574.770seconds,87restarts/23model runs; fresh078d failed CLOCK_DISCONTINUITY after39.744seconds. Neither earns24h credit. The [read-only probe](evidence/clock-soak-failure-20261020-078d596f2f79.json) retains the311ms backward step. On22Oct the owner moved stable-clock/fresh86400-second/24-run/72-answer observation and independent terminal audit to the final host. Preserve all guards; no laptop retry/clock repair is pending. See [handoff](FINAL_HOST_HANDOFF.md) and [historical observation](SOAK.md). |
| L11 CI | PASS (published d5aa99e) | [Exact-commit CI](evidence/paper-recovery-ci-20261023.json): allfour jobs SUCCESS;920unit/459PostgreSQL/1383overlapping combined cases, zero failures/errors/skips;24Chromium flows,8actualTLS/WSS checks,10556/12507=84.40% measured coverage including131browser-server line-bit rows. Configured legacy Sonar report-task gate explicitly PASSED for SCMd5aa; separate neutral/uncomputed check excluded. [New image build/smoke](evidence/paper-recovery-image-review-20261023.json) and [187context/184image committed-byte mapping](evidence/paper-recovery-published-image-reconciliation-20261023.json) pass. Original localclockfailure/retry remains retained, distinct from the clean new CI tier. |
| L12 UI E2E | PASS (published d5aa99e; synthetic model/providers) | [Exact-commit CI](evidence/paper-recovery-ci-20261023.json) verifies24realChromium flows, zero unexpected console errors,8isolated actualTLS/WSS checks and measured browser-server coverage. Independent simulator approval/lifecycle, owned portfolio/account evidence, alerts/reports, expenses and cross-user denial pass. This is not actual Paper execution or a real-model answer benchmark. |
| L13 Host/model | DEFERRED (actual final-host acceptance; not PASS) | Historical source4fd1380c [image/runtime/recovery](evidence/cash-collector-image-review-20261018-5d8b5cb04c1b.json) PASS on the recorded amd64/CPU profile: readonlyGGUF/nonroot app, persisted halt, app7.167s/DB1.130s restarts, owned cleanup and184context/181copied files. Prior [ingress proof](evidence/cash-collector-unchanged-ingress-review-20261018-5d8b5cb04c1b.json) is reused within unchanged surfaces. The22Oct direction moves new-host inventory/model/profile, mapped cooling and fresh continuous observation to the unknown final computer. Laptop HWiNFO ZIP/setup and clock repair are cancelled/deferred here; no universal ARM/GPU/OS support or thermal PASS is inferred. See [handoff](FINAL_HOST_HANDOFF.md). |
| L14 Research | BLOCKED (permitted data) | Cost-aware replay and fixed chronological fixture comparison; [web replay/evidence integration tested](REPLAY.md); [proposed forward observation/sample plan](FORWARD_OBSERVATION.md) documented but unapproved; [historical source review](evidence/research-source-review-20261013.md) identifies GDELT/SEC news candidates but no authorized historical price series; Yahoo historical and market/FX egress permissions are independently default OFF until operator rights review; FRED SP500 and Nasdaq WIKI are unsuitable for acceptance evidence; user says they have a rights-cleared source/universe but cannot identify the source, universe, coverage or local data path; no rights-cleared research dataset was loaded; one unintended unmocked test lookup has an unknown connection/data outcome, documented in CHECKPOINT.md; economic result remains INSUFFICIENT EVIDENCE |
| L15 External paper | BLOCKED (full lifecycle/authority) | User-selected encrypted account and read-only UI confirmation produced one persisted callback snapshot before WSL restart.1 read session, no orders; partial cash/non-atomic evidence, SDK environment unverified. Relay gone/17497closed, no retry. App recovered; owner confirms Enabled/Read Authorized unchecked and saved. Full external execution/reconciliation and separately approved forward plan remain absent; read success cannot substitute. |
| L16 Live readiness | PASS (NO-GO; safely disabled) | `.env` keeps `LIVE_TRADING_ENABLED=false`; external SDK writes are unconditionally denied. `tests/unit/acceptance_authority_test.py` passes 9/9, including a test that even a true live flag cannot authorize route/cancel. Evidence: [live-disabled gate](evidence/live-disabled-gate-20261013.txt). No live mandate or trading was created. |

## Decision log

- 22Oct: defer laptop24h/CPU-temperature/clock work to the actual final computer;
  cancel the laptop Portable ZIP/setup request. Keep research and Paper gates open.
  This changes scheduling, not evidence or completion credit; no live/SDK-write
  authority or production deployment permission is added.
- Use maintained `ib_async` 2.1.0 after current IBKR documentation confirmed
  `ib_insync` is based on a legacy TWS API release and no longer updated. Its
  no-socket package/API contract and fixture suite pass on the verified Python
  3.12 runtime. A real gateway login is still required before external readiness;
  all writes remain denied. `ib_async` constrains tzdata below 2026, so the lock
  selects 2025.3; revisit this dependency when upstream releases a compatible
  constraint or the host's timezone data support changes.
- Enforce server-side write restrictions before enabling simulator-only workflows.
  Tool catalogs and model instructions cannot grant authority.
- Visible WSL resources are not proof of physical RAM, cooling, GPU acceleration,
  sleep behavior or 24-hour availability. Measure separately; do not borrow Pi assumptions.
- External gates do not block local fixture development. NO-GO for live deployment;
  strategy edge remains INSUFFICIENT EVIDENCE.
