# Local implementation and validation plan

Authority: attached instructions read completely on 2026-09-08. Scope is this
local-machine checkout only. No production deployment, broker connections/writes,
real notifications, paid calls, OS changes, or live enablement authorized.
Baseline HEAD: 65ea1d769c79bf77df3de1d4a3b6274168d92085; clean working tree.
No applicable AGENTS.md or prior plan found. Existing functionality is retained.

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
| L02 Authorization | IN PROGRESS | Independent approval, closed external writes, durable logout, HTTP/WS/MCP active-user checks tested; complete mandate review pending |
| L03 Risk | IN PROGRESS | Trusted fixture price/FX, atomic reservations, halt/protected tests; [approved simulator mandates](MANDATES.md), marked-loss/drawdown and concurrent tick tests; manual marked-risk/durable rejection tested; periodic risk monitor and [internal ledger reconciliation](evidence/suite-reconciliation-final.txt) tested; external reconciliation pending |
| L04 Broker lifecycle | IN PROGRESS | [40 broker tests](evidence/broker-contracts.txt), durable simulator callbacks/restart and [versioned commission cases](evidence/commissions-first.txt); [scoped callback journal, partial balances and read-recovery tests](evidence/broker-read-failure-alerts-verified.txt); continuous external reconciliation incomplete |
| L05 Financial correctness | IN PROGRESS | Decimal/FX/mixed currency/rebalance regressions pass; full PnL/corporate-action reconciliation pending |
| L06 Useful chat/autonomy | IN PROGRESS | [Default factual workflows](evidence/workflows.txt) pass; real model/follow-ups/queue tests pending |
| L07 Reports | IN PROGRESS | Period/evidence repairs, persisted failure status and [422-suite failure/migration checks](evidence/suite-report-status.txt); [real PDF/status reload](evidence/browser-report-status.txt); broader source/reconciliation coverage pending |
| L08 Expenses | IN PROGRESS | [17 provider/recovery tests PASS](evidence/bank-safety-final.txt); [bank limits](BANK_SYNC.md), [browser import/pagination/category/export PASS](evidence/browser-expense-category-final.txt); bank controls and receipt/provider clocks implemented; [full-period export PASS](evidence/browser-expanded-lint.txt); [raw payload retention tested](RETENTION.md); broader retention pending |
| L09 Persistence | IN PROGRESS | Explicit migrations through 0012, full reviewed-schema upgrade/quarantine tests; [full fixture vault/PDF/model recovery PASS](evidence/full-fixture-recovery.json), [0010 database restore PASS](evidence/restore-report-status.json); [durable chat evidence and inactive-content retention tested](CHAT_EVIDENCE.md); [owned report tombstones and restart recovery](RETENTION.md) tested; broader retention review pending |
| L10 Operations | IN PROGRESS | Durable scoped leases and alerts tested; bounded PDF admission and [explicit abandoned-render cleanup](RETENTION.md) tested; broker failure alerts/recovery fenced; broader retention/soak/disconnect coverage pending |
| L11 CI | IN PROGRESS | [521 unit/PostgreSQL PASS](evidence/suite-chat-retention.txt); real Chromium CI tier and release target repaired; remote CI/build not observed |
| L12 UI E2E | IN PROGRESS | [Chromium simulator/alert/report/chat-retention/isolation PASS](evidence/browser-chat-retention.txt); expense/replay/mandate browser workflows pass; final coverage review pending |
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
