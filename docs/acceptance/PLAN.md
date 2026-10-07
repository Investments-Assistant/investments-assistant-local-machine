# Local implementation and validation plan

Authority: attached instructions read completely on 2026-09-08. Scope is this
local-machine checkout only. No production deployment, broker connections/writes,
real notifications, paid calls, OS changes, or live enablement authorized.
Historical baseline: 65ea1d769c79bf77df3de1d4a3b6274168d92085; initially clean.
Current HEAD: 0e18029fe882497cd7bb998f5b855777ac474889; prior completed work
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
| L04 Broker lifecycle | IN PROGRESS | [40 broker tests](evidence/broker-contracts.txt), durable simulator callbacks/restart and [versioned commission cases](evidence/commissions-first.txt); [scoped callback journal, partial balances and read-recovery tests](evidence/broker-read-failure-alerts-verified.txt); continuous external reconciliation incomplete |
| L05 Financial correctness | IN PROGRESS | Decimal/FX/mixed currency/rebalance regressions and [persisted synthetic cash-flow/risk/concurrency tests](evidence/account-events-concurrency.txt) pass; [persisted synthetic splits and restore](evidence/split-recovery-verified-split.json) pass; [received dividend/withholding replay and restore](evidence/dividend-recovery-split.json) pass; unpaid entitlements and full PnL/corporate-action reconciliation pending |
| L06 Useful chat/autonomy | IN PROGRESS | [Default factual workflows](evidence/workflows.txt) pass; [explicit read-scope exclusions fixed and tested](READ_SCOPE.md); [deterministic financial answers](FINANCIAL_ANSWERS.md) replace observed model valuation errors; broader analysis/follow-up/ambiguity evaluation pending |
| L07 Reports | IN PROGRESS | Period/evidence repairs, persisted failure status and [422-suite failure/migration checks](evidence/suite-report-status.txt); [real PDF/status reload](evidence/browser-report-status.txt); [history failure propagation verified](evidence/report-history-persistence.txt); [deterministic financial rendering and validated model extracts](evidence/suite-report-authority.txt); [reconciled simulator-period execution/PDF evidence](evidence/execution-period-report-persistence.txt); full period valuations, richer analysis and external reconciliation pending |
| L08 Expenses | PASS (local fixtures) | Identity/currency/lifecycle/pagination/isolation, [retention](RETENTION.md), [explicit changed-identity resolution and bounded older-history recovery](BANK_SYNC.md), [12 sync guards](evidence/bank-history-cursor.txt), [899 tests](evidence/suite-bank-history.txt) and [browser](evidence/browser-bank-history.txt) pass. Real bank consent/access/credentials remain a separate blocked external gate. |
| L09 Persistence | IN PROGRESS | Explicit migrations through 0018, full reviewed-schema upgrade/quarantine tests; [current 0015 fixture vault/PDF/model recovery PASS](evidence/account-events-recovery-full.json), [restored no-trade decision PASS](evidence/strategy-decision-restored.json), [0010 database restore PASS](evidence/restore-report-status.json); [durable chat evidence and inactive-content retention tested](CHAT_EVIDENCE.md); [owned report tombstones and restart recovery](RETENTION.md) tested; broader retention review pending |
| L10 Operations | IN PROGRESS | Durable scoped leases and alerts tested; [fair bounded mandate dispatch, rollback and failure alerts](evidence/suite-bounded-dispatch.txt); bounded PDF admission, publication/commit fencing and [explicit temporary/orphan cleanup](RETENTION.md) tested; broker failure alerts/recovery fenced; broader retention/soak/disconnect coverage pending |
| L11 CI | IN PROGRESS | [899 unit/PostgreSQL PASS](evidence/suite-bank-history.txt); CI selects complete test directories, including 113 previously unmarked unit tests; real Chromium CI tier and release target repaired; remote CI/build not observed |
| L12 UI E2E | PASS | [Current real Chromium/PostgreSQL workflow PASS](evidence/browser-bank-history.txt): login, synthetic account evidence, simulator proposal/independent approval/fill/fees, alerts/report and cross-user denial; expense/replay/retention/revocation also tested. Model/provider fixtures explicit; external paper remains L15. |
| L13 Host/model | IN PROGRESS | [Measured CPU/model baselines and host](MODEL_HOST.md); [short concurrent-control/restart smoke](SOAK.md) passes; full soak pending |
| L14 Research | IN PROGRESS | Cost-aware replay and fixed chronological fixture comparison; [web replay/evidence integration tested](REPLAY.md); real historical evidence pending; INSUFFICIENT EVIDENCE |
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
