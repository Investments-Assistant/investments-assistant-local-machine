# Simulator mandate authority

The schema is [mandate.schema.json](mandate.schema.json), implemented in
`src/execution/mandates.py`. Every field is explicit. The supported strategies are
`periodic_fixture_buy` and `price_band_fixture`, version1; the only environment is `simulator`.
This capability does not authorize any broker account, including paper accounts.

An authenticated browser proposes a mandate for an owned practice account and
reviews the exact specification. A second browser action approves the immutable
hash with a five-minute, single-use, session-bound nonce. A new approved revision
supersedes the previous one; it does not clear a halt. Models and MCP cannot approve
or edit mandates. Active-user checks and account locks apply to every tick.

The UI example allocates at most €500 of synthetic capital, €300 per instrument,
€150 per order including assumed fees, one share per tick, at most3 orders/day and
at least60 seconds apart. Its review lifetime is30 minutes. Quote age is at most30
seconds, fees at most10bps, and spread at most5bps. These are explicit practice
values, not recommendations or defaults for actual investments. The synthetic
constant-price feed has zero spread; external/unknown spread data cannot qualify.

`execution/runtime.py` runs current ticks only, coalescing missed scheduled runs.
Each tick reserves its capital atomically and stores its approved mandate/version
and risk evidence. Duplicate workers recover the same durable order. An uncertain
order blocks new ticks pending reconciliation. The forward practice runner records
synthetic fills separately from submission; it does not contact a broker.

Risk equity is cash plus current marked holdings in account currency, without
subtracting reservations a second time. Acquisition fees are included in cost
basis and deducted from cash. Unrealized PnL is marked value minus that basis;
Manual and strategy-sale realized PnL are included in account risk. Daily PnL starts from the first
observed equity of each UTC day; a first observation cannot reconstruct an absent
midnight mark. High-water drawdown persists across days and mandate revisions.
Explicit internal fixture deposits/withdrawals are journaled and excluded from performance/loss changes; external FX cash conversion remains unsupported. Received dividends/withholding and splits are journaled; protected income and corporate-action review halts are preserved (ACCOUNTING.md).

Loss-limit or clock-regression halts persist through restart. Halt stops new orders;
it does not cancel pending orders, flatten positions, or modify protected holdings.
The runtime commits a recorded halt even when the associated tick is denied.

Price-band mandates require explicit positive `buy_below < sell_above`, in source
instrument currency, inside the immutable approval. At/below the lower threshold
buy up to quantity_per_order; at/above the upper threshold sell at most that
quantity from this mandate's verified available inventory. Inside the band or
without owned inventory, return no_trade. Pending strategy orders block another
intent. Manual and superseded-mandate inventory is never inherited. Buy-only
mandates remain unchanged. Sales retain gross-notional order caps, global halts,
protection, fee reservation and quote checks, but do not increase position capital.
The fixture UI offers explicit strategy selection and independent review/approval.

These are engineering strategies, not proven economic signals. Constant-price
forward fixtures cannot demonstrate a profitable edge. Revised mandates do not
transfer prior inventory; disposing it needs a future separately approved transfer
or incident policy. Broader valuation/corporate-action reconciliation and incident
policies remain incomplete. External paper/live gates remain blocked.


Each daily-order, position, pending-reservation and fixture-quote read is bounded
to 10,000 rows plus an overflow sentinel. Overflow persists
`MANDATE_EVIDENCE_CAPACITY` and prevents new orders; runtime checks before changing
quote timestamps and commits the halt/alert on denial. This ceiling does not
authorize pruning accounting evidence or prove a latency SLA.
[Independent-transaction regression evidence](evidence/mandate-runtime-capacity.txt):
17 passing mandate/risk checks.


Verification: [708 unit/PostgreSQL checks](evidence/suite-strategy-sales.txt) and
[real Chromium approval workflows](evidence/browser-strategy-sales.txt) pass.
The strategy tests exercise round-trip realized PnL, manual/revision isolation,
pending-intent exclusion, protected instruments, cap/hash denials and neutral
forward ticks. This does not prove external broker execution or economic edge.
Migration0014 adds retained strategy decisions for both orders and no-trade
outcomes. Each records scope, immutable mandate hash, quote/FX/time, risk and result
with an integrity hash. Account locking and a unique tick key prevent concurrent
reevaluation; a no-trade retry retains its original result after quote changes.
Changed evidence halts execution. Linked order status may advance without changing
the original decision. Older orders keep their prior idempotency protection and
are not assigned invented decision evidence. Owner snapshots expose the latest100
records with an explicit truncation flag. Hashes detect accidental evidence
mutation, not an administrator rewriting both evidence and its hash.


Dispatch uses durable `simulator:<mandate-id>` jobs under the mandate owner's
active user identity. Each call selects at most100 eligible mandates, with
never-attempted and oldest-due work first. Both completed work and policy denial
advance the next due time by60seconds. A denied mandate therefore cannot permanently
occupy the first batch. A separate claim transaction permits worker recovery;
completion checks the lease token and actual database clock. Stale completion
rolls back that worker's orders, fills, decisions and quote refresh. Ordinary
risk denial with a valid lease commits its halt. Deactivation is rechecked before
work. This is local simulator scheduling, not a broker lease or a throughput SLA.


Runtime deadlines match the existing risk monitor's conservative engineering
bounds:20s per cycle,10s per work transaction,5s for a lease claim or failure
recording,5s per SQL statement and2s per database lock wait. They are cancellation
ceilings, not measured service guarantees. A failed work transaction cannot commit
trades; a still-owned lease may record its failure and a scoped in-app alert in a
fresh bounded transaction. If that evidence cannot be persisted, the returned
result says `failure_persistence=unavailable`. Cycle-level failures also remain
explicit where no account scope is available. Unexpected programmer errors and
external cancellation propagate; no broad exception handler converts them into
successful execution. Broker execution is not involved in this runtime.


### Global account exposure limits
New browser practice accounts explicitly set `global_exposure_limits` in their
account mandate: `max_position_base=500`, `max_exposure_base=750`, in EUR. The UI
states these synthetic examples before creation; they are not live policy.
The fixture test seed supplies explicit limits for its own synthetic initial capital.
Existing accounts without finite positive consistent limits halt with
GLOBAL_EXPOSURE_LIMITS_UNAVAILABLE; no migration guesses limits or clears a halt.
Create a new practice fixture to exercise the new policy. Real account policy remains
a separate decision and external execution remains disabled.
Under the same active-user/account lock, manual proposal, human approval and strategy
execution must satisfy marked holdings plus pending cash reservations plus the new
buy reservation. Reservations include bounded fees; sale proceeds are never assumed
before fills. Both per-instrument and whole-account caps apply, even when a strategy
mandate grants a larger amount. Strategy-specific caps can be tighter, never wider.
Risk monitoring also checks existing marked/reserved exposure and persists a breach
halt; gains can breach a fixed absolute cap. A halt does not cancel orders or sell
positions, and a sale request cannot bypass it. Missing/stale valuation remains
fail-closed. Position and pending-order observations are bounded to1000 each.
Evidence:global-exposure-first.txt46PASS and global-exposure-guards.txt10PASS,
including real concurrent transactions with enough cash for both orders but exposure
room for only one. Full current regression/browser validation follows in CHECKPOINT.
