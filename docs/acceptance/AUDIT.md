# Audit findings and current evidence

Reference commit: `65ea1d769c79bf77df3de1d4a3b6274168d92085`. Current HEAD remains
that commit; implementation and evidence are staged/unstaged working-tree changes.
The initial checkout was clean. Resumes preserve both staged and unstaged changes;
no commits, pushes or production deployment have been performed. Historical logs
remain evidence of their recorded runs, not assertions that later code was tested.

## Required regression cases

These findings are confirmed defects addressed in this checkout. Current evidence
is the durable behavior-level regression, not a repeated claim about historical CI.
The audited nine reproductions combined quantity and currency; rows below preserve
the ten separate acceptance expectations.

| Finding | Current behavior / regression source |
|---|---|
| Caller estimate1 bypasses 1000×100 notional against cap500 | Trusted notional rejects regardless of caller estimate, including NaN; `tests/unit/acceptance_authority_test.py` |
| Quantity0.004 becomes0 | Exact quantity string0.004 retained; `tests/unit/acceptance_financial_test.py` |
| EUR100 labelled USD100 without FX | Original EUR retained; USD unavailable until dated explicit FX; same financial tests |
| Same-session token allows model confirmation | `_confirm_trade` cannot execute; browser human event required independently; authority tests plus real browser self-approval denial |
| Generic portfolio question has no scoped evidence | Default factual workflow requests portfolio; workflow tests and actual CPU client benchmark with scoped synthetic evidence |
| Scheduled scan acquires only news | Scanner requests news, market overview and portfolio with explicit active-user context; workflow/identity tests and model workflow benchmark |
| SPYL, ON, XETRA parsed as tickers | Example resolves symbol list to SPYL; workflow regression |
| Expense EUR/USD fallback identity collision | Identity preserves currency, direction, account and precision; financial regression |
| 200EUR+100USD summed as300EUR | Separate currency totals; combined value unavailable; financial tests and actual browser mixed-currency import |
| Momentum resets marked value on rebalance | Historical helper regression yields108.333333 on1Feb before costs; actual web simulation now uses cost-aware shared-cash replay with immutable reproducible evidence |

Evidence: `evidence/suite-bank-controls.txt` (394 unit/PostgreSQL tests),
`evidence/browser-bank-pagination-final.txt` (real Chromium/PostgreSQL with stub
model; bank controls separately intercepted), `MODEL_HOST.md` (actual native-model
results and limitations), `REPLAY.md` (new engine and offline reproduction).

## Additional audited paths

| Path/finding | Disposition and evidence limits |
|---|---|
| Write policy differs by entrypoint | External SDK writes uniformly closed; ownerless/wrong-account SDK reads closed; browser simulator policy separately enforced. Full broker execution boundary remains pending external lifecycle implementation. |
| IBKR SMART/USD and account flattening | Explicit account/read consent/environment/qualified stock identity fixtures implemented; external account not connected. Capability limits in BROKER_CAPABILITIES.md. |
| Daily loss depends on absent adapter fields | Simulator mandates compute persisted marked-equity observations and halt on limits; external daily-loss enforcement remains unavailable, writes disabled. ACCOUNTING.md defines limits. |
| Default1.5B profile unmeasured | Existing1.5B/3B CPU structured benchmarks now recorded. GPU offload unavailable in installed build. Broader task accuracy and 24h observation pending. |
| External text in system context / brittle tool routing | Untrusted evidence separated, privileged catalog filtered, token/inference bounds tested. Multilingual ambiguity/follow-up breadth remains incomplete. |
| Final-answer contract differs between checkouts | Laptop final_answer event retained through client/orchestrator/UI; actual client and browser report workflows verified. Pi unchanged; no cross-repository event migration. |
| Monolithic web concerns | Finance normalization, expense persistence/category/provider handling, risk/execution, research and alert routes extracted; web module remains large and further focused extraction is possible. |
| Reports silently truncate/fail | Structured evidence/period helpers and typed source/PDF/persistence failures implemented; actual PDF reload/isolation tested. Reconciled broker performance remains unavailable. |
| Synchronous simulation/PDF blocks async handlers | Shared bounded workers with timeout/cancellation permit retention; actual browser replay/PDF pass. |
| Scheduled/MCP global credentials | Explicit active-user binding enforced; SDK fallback removed. Public news/market job durable service identity still pending. |
| Bank consent/sync incomplete | Fixture-tested adapter/token/consent/account/recovery and explicit browser controls added. Real bank access requires separate consent/configuration. |
| Startup create_all/raw alterations/owner backfill | Versioned reviewed-schema upgrades through0009, explicit startup schema checks and unknown-owner quarantine. Full current filesystem/key restore pending. |
| Nginx all-interface publication | Compose now defaults loopback with explicit LAN bind and exact proxy peer; offline config and origin fixtures pass. Actual Docker/WSL ingress remains unobserved. |
| CPU image mistaken for GPU path | Build remains CPU; installed native library reports no GPU offload. No GPU acceleration claim. |
| CI integration loop/transaction/FTS errors | Function-loop NullPool fixtures, positively marked database, outer rollback/savepoints and real PostgreSQL FTS pass locally. Remote historical run has not been rerun. |
| ARM64 Pi deployment workflow inherited | Replaced with manual x86_64 CPU validation; no automatic deployment. Remote build execution unobserved. |

No listed finding is dismissed as “not reproduced” merely because current tests
pass. External connectivity, funding, permissions, entitlements, real bank access,
physical sleep/cooling and runtime deployment remain unknown or blocked as recorded
in MODEL_HOST.md, BANK_SYNC.md and PLAN.md. Baseline discovery is complete; this
ledger does not promote the implementation/operational gates that still have gaps.
