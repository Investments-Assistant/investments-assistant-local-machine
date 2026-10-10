# Local implementation and validation plan

Authority: attached instructions read completely on 2026-09-08. Scope is this
local-machine checkout only. No production deployment, broker connections/writes,
real notifications, paid calls, OS changes, or live enablement authorized.
Historical baseline: 65ea1d769c79bf77df3de1d4a3b6274168d92085; initially clean.
Current HEAD: 9b0df38c333337aee83d8dcd9874fda7f5945eaf; prior completed work
is committed externally. Current news-policy/retention and CI changes remain dirty
and are preserved. The agent has not committed or pushed changes.
No applicable AGENTS.md or prior plan found at baseline. Global AGENTS.md now requires task-observer and milestone progress_monitor audits. Existing functionality is retained.

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
| L04 Broker lifecycle | IN PROGRESS | [40 broker tests](evidence/broker-contracts.txt), durable simulator callbacks/restart and [versioned commission cases](evidence/commissions-first.txt); [scoped callback journal, partial balances and read-recovery tests](evidence/broker-read-failure-alerts-verified.txt); [persisted order/fill/cancel conflict review](BROKER_CAPABILITIES.md) passes41focused tests; [bounded sustained capture and transactional stream checkpoints](BROKER_CAPABILITIES.md) pass56focused tests including the finite continuous coordinator; shared owner read routing and explicit browser activation/stop consent controls fixture-tested; real gateway reauthentication and external reconciliation incomplete |
| L05 Financial correctness | PASS (local fixtures) | Decimal/FX/mixed currency/rebalance regressions and [persisted synthetic cash-flow/risk/concurrency tests](evidence/account-events-concurrency.txt) pass; [persisted synthetic splits and restore](evidence/split-recovery-verified-split.json) pass; [received dividend/withholding replay and restore](evidence/dividend-recovery-split.json) pass; [unpaid entitlement/linked payment, risk/valuation/report and exact fixture recovery](ACCOUNTING.md) verified; [1031 fullsuite](evidence/suite-dividend-receivables.txt) and [browser](evidence/browser-dividend-receivables.txt) pass. Foreign/special corporate actions and external reconciliation remain explicit unavailable/partial states and external gate limitations |
| L06 Useful chat/autonomy | PASS (local runtime) | [Requirement-by-requirement review](CHAT_REVIEW.md), [923 unit/PostgreSQL tests](evidence/suite-scanner-source-quality.txt), [default scanner factual quality](evidence/workflow-scanner-candidates-cpu-20261007.json), [native comparison](evidence/workflow-scanner-native-cpu-20261007.json), [current source-validator recheck](evidence/source-quality-current-validator.json); scoped reads, parsing, follow-up, exclusions, injection and tool-error conditions pass. Economic edge and external execution remain separate gates. |
| L07 Reports | PASS (local fixtures) | Period/evidence repairs, persisted failure status and [422-suite failure/migration checks](evidence/suite-report-status.txt); [real PDF/status reload](evidence/browser-report-status.txt); [history failure propagation verified](evidence/report-history-persistence.txt); [deterministic financial rendering and validated model extracts](evidence/suite-report-authority.txt); [reconciled simulator-period execution/PDF evidence](evidence/execution-period-report-persistence.txt); [immutable boundary valuations, accrued/received income, report truthfulness and restore](ACCOUNTING.md), [1031 fullsuite](evidence/suite-dividend-receivables.txt), [37 affected report checks](evidence/dividend-report-truthfulness.txt) and browser pass. Missing historical marks/benchmark basis remain explicitly unavailable; external reconciliation and comparative research remain separate gates |
| L08 Expenses | PASS (local fixtures) | Identity/currency/lifecycle/pagination/isolation, [retention](RETENTION.md), [explicit changed-identity resolution and bounded older-history recovery](BANK_SYNC.md), [12 sync guards](evidence/bank-history-cursor.txt), [899 tests](evidence/suite-bank-history.txt) and [browser](evidence/browser-bank-history.txt) pass. Real bank consent/access/credentials remain a separate blocked external gate. |
| L09 Persistence | PASS (local fixtures) | Explicit migrations through 0018, full reviewed-schema upgrade/quarantine tests; [current 0015 fixture vault/PDF/model recovery PASS](evidence/account-events-recovery-full.json), [restored no-trade decision PASS](evidence/strategy-decision-restored.json), [0010 database restore PASS](evidence/restore-report-status.json); [durable chat evidence and inactive-content retention tested](CHAT_EVIDENCE.md); [owned report tombstones and restart recovery](RETENTION.md) tested; [coherent bundle publication/expiry and full 0018 vault/PDF/model recovery](RETENTION.md) verified; production/off-host validation remains separate |
| L10 Operations | IN PROGRESS | Durable scoped leases and alerts tested; [fair bounded mandate dispatch, rollback and failure alerts](evidence/suite-bounded-dispatch.txt); bounded PDF admission, publication/commit fencing and [explicit temporary/orphan cleanup](RETENTION.md) tested; broker failure alerts/recovery fenced; [due-aware monitoring and recovered heartbeat alerts](SOAK.md), [report resource alerts](RUNBOOK.md) tested; [actual isolated Nginx HTTPS/WSS and static-header regression](INGRESS.md) pass; actual Docker/host interruption coverage pending |
| L11 CI | IN PROGRESS | [1041 current unit/PostgreSQL PASS on an empty marked database](evidence/clean-ci-verified-suite.txt), [5 real loopback soak/migration checks PASS](evidence/clean-ci-loopback-soak.txt); shared-sequence metadata ordering and migrated soak fixture defects repaired. [Current HEAD remote run37657249888](evidence/remote-ci-37657249888-summary.json) had unitPASS/integrationFAIL/browserSKIPPED before these local fixes; no push or remote rerun. Laptop CPU deployment target retained; Docker WSL integration unavailable, build verification pending |
| L12 UI E2E | PASS | [Current real Chromium/PostgreSQL workflow PASS](evidence/browser-broker-order-review.txt): login, synthetic account evidence, simulator proposal/independent approval/fill/fees, alerts/report and cross-user denial; expense/replay/retention/revocation also tested. Model/provider fixtures explicit; external paper remains L15. |
| L13 Host/model | IN PROGRESS | [Measured CPU/model baselines and host](MODEL_HOST.md); [short concurrent-control/restart smoke](SOAK.md) passes; full soak pending |
| L14 Research | IN PROGRESS | Cost-aware replay and fixed chronological fixture comparison; [web replay/evidence integration tested](REPLAY.md); [proposed forward observation/sample plan](FORWARD_OBSERVATION.md) documented but unapproved; real historical evidence pending; INSUFFICIENT EVIDENCE |
| L15 External paper | BLOCKED | No explicit approved and verified paper account; no connection attempted |
| L16 Live readiness | BLOCKED | No versioned live mandate or accepted prerequisites; remains disabled |

## Decision log

- Keep direct adapter library while verifying its contracts; no unapproved migration.
- Enforce server-side write restrictions before enabling simulator-only workflows.
  Tool catalogs and model instructions cannot grant authority.
- Visible WSL resources are not proof of physical RAM, cooling, GPU acceleration,
  sleep behavior or 24-hour availability. Measure separately; do not borrow Pi assumptions.
- External gates do not block local fixture development. NO-GO for live deployment;
  strategy edge remains INSUFFICIENT EVIDENCE.
