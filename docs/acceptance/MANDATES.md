# Simulator mandate authority

The schema is [mandate.schema.json](mandate.schema.json), implemented in
`src/execution/mandates.py`. Every field is explicit. The supported strategy is
`periodic_fixture_buy`, version1, and the only environment is `simulator`.
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
realized PnL remains zero in the buy-only simulator. Daily PnL starts from the first
observed equity of each UTC day; a first observation cannot reconstruct an absent
midnight mark. High-water drawdown persists across days and mandate revisions.
No deposit/withdrawal or external FX flow is supported in this fixture ledger.

Loss-limit or clock-regression halts persist through restart. Halt stops new orders;
it does not cancel pending orders, flatten positions, or modify protected holdings.
The runtime commits a recorded halt even when the associated tick is denied.

Current limits: this is a buy-only engineering fixture, not an economic strategy
validation. Independent risk monitoring after mandate expiry, strategy-owned sells,
broader daily valuation/reconciliation and additional incident policies still need
implementation and acceptance. External paper/live gates remain blocked.
