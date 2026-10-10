# Proposed forward observation plan — not approved

Status: proposal only. No observation campaign or external account connection has
started. This document grants no account, data, order or live authority. The fixed
historical fixture plan remains unchanged; its holdout must not be reused to tune
this proposal. Research conclusion remains INSUFFICIENT EVIDENCE; live is NO-GO.

## Purpose and proposed sample

Measure whether the same frozen strategy gains useful information from news/model
assistance after realistic costs, while separately measuring operational failures.
Start with the existing daily-decision horizon. Daily bars cannot establish
immediate-news execution quality.

Propose 60 exchange sessions, roughly three trading months, with at least20 closed
strategy trades before even a preliminary trade-level comparison. The duration
allows repeated daily observations and recovery exercises;20 is the existing
fixture plan's illustrative minimum, not a statistical power calculation or an
approved real-account standard. Neither count demonstrates economic edge. A
quiet strategy may finish with fewer trades: report insufficient evidence instead
of increasing turnover or extending the experiment indefinitely.

Before starting, the user must agree the horizon, representative eligible universe,
capital/risk mandate, cost assumptions, data rights and observation/sample plan.
Unknown account permissions, prices, news availability or corporate actions stay
unknown; do not manufacture them from the six-share SPYL proposal fixture.

## Separate stages and authority

1. Engineering: use existing isolated simulator and synthetic fixtures. Already
   recorded tests establish accounting, authorization and workflow behavior only.
2. Prospective shadow observation: only after permitted sources and observation
   scope are verified, record candidates and counterfactual simulator outcomes.
   No external orders. Record the actual first-seen/available time, not merely a
   publisher timestamp; preserve revisions and attribution.
3. External paper: requires separately selected and verified paper-account
   provenance and explicit connection/submission approval. The current external
   write boundary remains closed. Implementation and contract validation of that
   execution path precede any approved paper submission. Simulator outcomes are
   never relabelled paper broker evidence.
4. Live: excluded. Passing earlier stages does not enable it or grant a mandate.

## Freeze before collecting outcomes

Record a versioned experiment manifest: plan hash, code revision plus dirty-source
hashes, strategy/model/GGUF hashes, prompts and schemas, universe selection rule,
data/source-policy versions, exchange calendar/timezone, cost/fill assumptions,
account/environment evidence and approved scope. Keep private identifiers masked.
Store corrections as new evidence rather than overwriting the original outcome.

Run paired comparisons on the same eligible opportunities and available inputs:
cash/no-trade, appropriate buy-and-hold benchmark, deterministic strategy, and the
same strategy with frozen news/model assistance. Keep signal time, next eligible
fill time, spread, slippage, commissions, FX and liquidity rules identical. Record
abstentions and missing evidence; do not exclude failed or inconvenient days.
Where a model branch has different input availability, expose the difference.

Actual paper fills, if separately authorized later, remain a separate execution
record. Compare their timestamps, prices, partial fills and fees with assumptions;
do not assume the counterfactual branches could all receive the same broker fill.

## Evidence and review

For every scheduled opportunity retain scoped input references/hashes and clocks,
candidate or abstention, deterministic policy result/rejection, latency, model
failure/queue state, simulated or actual execution identity, and reconciliation
status. Track missing sessions, stale observations, duplicate/corrected messages,
disconnects and recovery. No stale backlog becomes a new trade after recovery.

Report net returns and benchmark excess return with the stated conventions,
drawdown, exposure, volatility/risk metrics, turnover, closed-trade count and hit
rate denominator, rejected signals, operational failures and data gaps. Include
both calendar/session coverage and trade coverage; correlated observations are
not independent samples. Report uncertainty and selection/universe limitations.
Do not claim a statistically established advantage from this proposed minimum.

At sessions20 and40 review safety and data completeness only. Keep strategy/model
parameters frozen. A required repair creates a new version and separates affected
observations; it does not erase losses or silently restart a favorable sample.
At session60, issue GO/NO-GO/INSUFFICIENT EVIDENCE against criteria approved before
the campaign. Here GO means eligible for further review, never live authorization.
If data/sample or execution integrity is insufficient, stop and report that result;
any extension or changed criterion needs a new agreed plan.

Halt new activity on lost scope/consent, stale dependencies, reconciliation gaps
or breached approved limits. Reconcile before resuming. Cancel and flatten remain
separate powers; no recovery action may consume protected allocations.

## Resume prerequisites

Resolve the engineering blockers in BLOCKERS.md, then obtain agreement to the
proposed plan and authorized source/account scope. Preserve the fixed historical
fixture result as engineering evidence. Do not start a campaign merely because
this document exists, and do not send external notifications without destination
approval.
