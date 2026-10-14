# Local implementation and validation plan

Authority: attached instructions read completely on 2026-09-08. Scope is this
local-machine checkout only. No production deployment, broker connections/writes,
real notifications, paid calls, OS changes, or live enablement authorized.
Historical baseline: 65ea1d769c79bf77df3de1d4a3b6274168d92085; initially clean.
Current HEAD: 1d01bb5517d5f1a7424efd9daca766223850a2df on local `master`,
tracking `origin/main` at the same commit. The user-approved 19-file `ib_async`
migration is published; all other implementation, regression, validation,
checkpoint, and evidence changes remain dirty and are preserved.
No new commit or push is authorized for the current two-file soak-fixture fix.
Existing functionality is retained.

Sequence (continue while safe productive work remains):
1. Reproduce authorization and numerical defects; fix deterministic boundaries.
2. Repair financial normalization, expenses, simulator, and factual orchestration.
3. Add durable execution/risk, migrations, scoped operations and provider fixtures.
4. Repair isolated PostgreSQL fixtures and CI; run unit/integration/browser tests.
5. Validate host/models, report/research harnesses and available isolated deployment.
6. Review all gates; record external blockers and reproducible checkpoint.

## Gate matrix

PENDING means required local work remains, not an external blocker.
Latest milestone and exact partial results: [CHECKPOINT.md](CHECKPOINT.md).
No aggregate gate is promoted solely on a subset of regression tests.

| Gate | Status | Evidence / remaining work |
|---|---|---|
| L01 Baseline | PASS | HEAD/dirty-state preserved; [feature and authority map](ARCHITECTURE.md), [audit disposition](AUDIT.md), [measured host and explicit unknowns](MODEL_HOST.md) |
| L02 Authorization | PASS | [Complete local invariant review](AUTHORITY_REVIEW.md), immutable independent approvals/mandates, scope/replay/mode/SDK denials and principal-lifetime fencing; [840 current tests](evidence/suite-owner-lifetime.txt) and [current Chromium workflow](evidence/browser-owner-lifetime.txt) pass. External execution remains separately blocked under L04/L15/L16. |
| L03 Risk | PASS | Trusted fixture price/FX, atomic reservations, halt/protected tests; [approved simulator mandates](MANDATES.md), marked-loss/drawdown and concurrent tick tests; manual marked-risk/durable rejection tested; periodic risk monitor and [internal ledger reconciliation](evidence/suite-reconciliation-final.txt) tested; [global manual/strategy caps and concurrency](evidence/global-exposure-guards.txt), [881 current tests](evidence/suite-global-exposure.txt) and [browser](evidence/browser-global-exposure.txt) pass. External broker reconciliation remains L04/L15. |
| L04 Broker lifecycle | IN PROGRESS | [40 broker tests](evidence/broker-contracts.txt), durable simulator callbacks/restart and [versioned commission cases](evidence/commissions-first.txt); [scoped callback journal, partial balances and read-recovery tests](evidence/broker-read-failure-alerts-verified.txt); [persisted order/fill/cancel conflict review](BROKER_CAPABILITIES.md) passes41focused tests; [bounded sustained capture and transactional stream checkpoints](BROKER_CAPABILITIES.md) pass56focused tests including the finite continuous coordinator; [maintained ib_async 2.1.0 dependency/API compatibility](evidence/ib-async-migration-20261013.txt) passes48 broker unit and59 marked-PostgreSQL broker integration tests, with719 unit and374 full integration tests passing; shared owner read routing and explicit browser activation/stop consent controls fixture-tested; user authorized read-only paper connectivity but clarified they have only an IBKR login and no verified paper Gateway/TWS session; real gateway reauthentication and external reconciliation remain incomplete |
| L05 Financial correctness | PASS (local fixtures) | Decimal/FX/mixed currency/rebalance regressions and [persisted synthetic cash-flow/risk/concurrency tests](evidence/account-events-concurrency.txt) pass; [persisted synthetic splits and restore](evidence/split-recovery-verified-split.json) pass; [received dividend/withholding replay and restore](evidence/dividend-recovery-split.json) pass; [unpaid entitlement/linked payment, risk/valuation/report and exact fixture recovery](ACCOUNTING.md) verified; [1031 fullsuite](evidence/suite-dividend-receivables.txt) and [browser](evidence/browser-dividend-receivables.txt) pass. Foreign/special corporate actions and external reconciliation remain explicit unavailable/partial states and external gate limitations |
| L06 Useful chat/autonomy | PASS (local runtime) | [Requirement-by-requirement review](CHAT_REVIEW.md), [923 unit/PostgreSQL tests](evidence/suite-scanner-source-quality.txt), [default scanner factual quality](evidence/workflow-scanner-candidates-cpu-20261007.json), [native comparison](evidence/workflow-scanner-native-cpu-20261007.json), [current source-validator recheck](evidence/source-quality-current-validator.json); scoped reads, parsing, follow-up, exclusions, injection and tool-error conditions pass. Economic edge and external execution remain separate gates. |
| L07 Reports | PASS (local fixtures) | Period/evidence repairs, persisted failure status and [422-suite failure/migration checks](evidence/suite-report-status.txt); [real PDF/status reload](evidence/browser-report-status.txt); [history failure propagation verified](evidence/report-history-persistence.txt); [deterministic financial rendering and validated model extracts](evidence/suite-report-authority.txt); [reconciled simulator-period execution/PDF evidence](evidence/execution-period-report-persistence.txt); [immutable boundary valuations, accrued/received income, report truthfulness and restore](ACCOUNTING.md), [1031 fullsuite](evidence/suite-dividend-receivables.txt), [37 affected report checks](evidence/dividend-report-truthfulness.txt) and browser pass. Missing historical marks/benchmark basis remain explicitly unavailable; external reconciliation and comparative research remain separate gates |
| L08 Expenses | PASS (local fixtures) | Identity/currency/lifecycle/pagination/isolation, [retention](RETENTION.md), [explicit changed-identity resolution and bounded older-history recovery](BANK_SYNC.md), [12 sync guards](evidence/bank-history-cursor.txt), [899 tests](evidence/suite-bank-history.txt) and [browser](evidence/browser-bank-history.txt) pass. Real bank consent/access/credentials remain a separate blocked external gate. |
| L09 Persistence | PASS (local fixtures) | Explicit migrations through 0018, full reviewed-schema upgrade/quarantine tests; [current 0015 fixture vault/PDF/model recovery PASS](evidence/account-events-recovery-full.json), [restored no-trade decision PASS](evidence/strategy-decision-restored.json), [0010 database restore PASS](evidence/restore-report-status.json); [durable chat evidence and inactive-content retention tested](CHAT_EVIDENCE.md); [owned report tombstones and restart recovery](RETENTION.md) tested; [coherent bundle publication/expiry and full 0018 vault/PDF/model recovery](RETENTION.md) verified; production/off-host validation remains separate |
| L10 Operations | PASS (local fixtures) | Durable scoped jobs, bounded dispatch, leases, heartbeat/recovery alerts, report admission/cleanup and deduplication/delivery-failure tests pass. Prior actual Nginx HTTPS/WSS and Windows-loopback ingress pass (INGRESS.md). The current source-matched image passes [production startup, real-model/database readiness, persistent halt and app/database restart recovery](evidence/container-runtime-ibasync-new.json), app6.584s/DB1.044s against15s with [independent cleanup](evidence/container-runtime-ibasync-cleanup-20261014.json). [Verified24h soak](evidence/soak-24h-ib-async-final-20261013-review.json):86,400.216s,3,060cycles,93restarts,0failures,one continuous window,p95 28.275ms. Physical sleep and remote broker/provider recovery remain separate limitations; no production/LAN deployment occurred |
| L11 CI | PASS | Published commit `1d01bb5` replaces the IBKR client with `ib_async==2.1.0`; [run38478734435](https://github.com/Investments-Assistant/investments-assistant-local-machine/actions/runs/38478734435) completed successfully with unit, PostgreSQL integration, Chromium/browser, and combined Sonar quality-gate jobs all SUCCESS. Downloaded artifacts report717 unit and373 integration tests passing,1,094 combined E2E-tier tests passing (overlapping suites, not additive unique tests), and82.63% combined line coverage. Local verification includes [719 unit and374 full PostgreSQL integration tests](evidence/ib-async-migration-20261013.txt), plus [current image build/import smoke](evidence/container-build-ibasync-20261013.txt). |
| L12 UI E2E | PASS | [Current real Chromium/PostgreSQL workflow PASS](evidence/browser-broker-order-review.txt): login, synthetic account evidence, simulator proposal/independent approval/fill/fees, alerts/report and cross-user denial; expense/replay/retention/revocation also tested. Model/provider fixtures explicit; external paper remains L15. |
| L13 Host/model | IN PROGRESS | Actual CPU/model benchmarks and justified default profile are recorded in MODEL_HOST.md; same-process native contention and [verified24h HTTP/PostgreSQL + separate CPU-model soak](evidence/soak-24h-ib-async-final-20261013-review.json) pass. All24model runs/72tasks pass; overlapping halt p95 33.695ms. Current-image production readiness/restarts also pass. [672-sample thermal series](evidence/thermal-telemetry-series-20261014.csv) spans11h11m51s,ACPI THM0 67.05–95.05C,passive limit100/throttle0 throughout. Sensor-to-component mapping and CPU-package cooling remain unverified; GPU inference and physical sleep/network recovery are not claimed |
| L14 Research | IN PROGRESS | Cost-aware replay and fixed chronological fixture comparison; [web replay/evidence integration tested](REPLAY.md); [proposed forward observation/sample plan](FORWARD_OBSERVATION.md) documented but unapproved; [historical source review](evidence/research-source-review-20261013.md) identifies GDELT/SEC news candidates but no authorized historical price series; Yahoo egress is disabled until operator rights review; FRED SP500 and Nasdaq WIKI are unsuitable for acceptance evidence; user says they have a rights-cleared source/universe but cannot identify the source, universe, coverage or local data path; no data was accessed; economic result remains INSUFFICIENT EVIDENCE |
| L15 External paper | BLOCKED | User authorized read-only paper connectivity but clarified they have only an IBKR login and do not know what a paper account/Gateway/TWS session is; selected paper-only environment is unverified and no connection attempted |
| L16 Live readiness | PASS (NO-GO; safely disabled) | `.env` keeps `LIVE_TRADING_ENABLED=false`; external SDK writes are unconditionally denied. `tests/unit/acceptance_authority_test.py` passes 9/9, including a test that even a true live flag cannot authorize route/cancel. Evidence: [live-disabled gate](evidence/live-disabled-gate-20261013.txt). No live mandate or trading was created. |

## Decision log

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
