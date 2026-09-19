# Financial definitions and current limits

Numeric values used for risk and persisted simulator/replay ledgers use Decimal
and fixed-precision SQL columns. UI floats are display/compatibility fields; exact
expense/replay values are separately serialized as decimal strings. Rounding for
display never creates a valid quantity or replaces tick/lot checks.

## Portfolio valuation

Position quantity retains fractional precision. Source price and currency remain
source values. USD valuation requires either USD source currency or an explicit
finite positive FX rate with an aware timestamp. Missing price/currency/FX yields
unavailable valuation and partial aggregate totals, rather than zero or relabelled
USD. Broker-account identity accompanies collected positions. Complete external
cash/order/corporate-action reconciliation is still required.

## Simulator account

The current execution engine supports purchases in isolated fixture accounts.
Trade cost in account base currency equals quantity × source price × contract
multiplier × explicit FX-to-base, plus base-currency fee. Cash decreases and
position cost basis increases by that cost; no contribution or withdrawal is
fabricated. Reserved cash is a claim against existing cash, not extra equity.
Partial fills release their proportional remaining reservation. Uncertain orders
retain reservations until reconciled; terminal cancellation/rejection releases
unfilled reservation. Late discrepant fills are recorded and halt the account.

Unrealized PnL is current marked position value less its fee-inclusive basis.
Marked equity is cash plus marked holdings. Mandate daily loss compares equity
against the first observed equity of that UTC calendar day; it is not a claimed
exchange opening valuation. Drawdown compares against the persisted equity high
water mark. FX changes are included in marked base-currency equity; separate FX
attribution is not implemented. Clock regression and exceeded loss limits halt
new orders. Operator halts survive midnight and restart. Risk observations require
current eligible data; stale or uncertain states do not permit new trading.

Realized sale PnL is unavailable in this buy-only execution path. Strategy-owned
sales, corporate actions, late standalone commissions and independent broker
reconciliation remain incomplete. Existing `DailyPnL`/legacy trade rows are not
proof of reconciled performance. A configured threshold alone proves nothing;
see mandate and concurrent ledger regression evidence.

## Historical replay

`REPLAY.md` defines source availability, later-session fills, costs, calendars,
corporate-action assumptions and exact evidence reproduction. The separate replay
engine supports sells with basis release. Results include retained unsold terminal
positions; no fictitious final liquidation. Daily-bar evaluation is unsuitable for
claims about immediate news execution. Synthetic held-out comparisons provide no
investment-edge evidence; research remains INSUFFICIENT EVIDENCE.

## Expenses

Signed source amount is retained exactly. Expenses are negative, income/refunds
positive; transfers retain direction. Pending and deleted records do not enter
booked expense/income totals. Identity includes owner, provider, bank account and
external ID; fallback hashes preserve currency/direction/precision. Category
overrides survive provider revisions and create minimal owner-scoped audits.

Totals are grouped by source currency. Mixed currencies never become one total
without dated conversion. Current UI totals cover the explicitly labelled page,
not every transaction in the requested period. Receipt timestamps record when the
application imported data; provider success timestamps record completed retrieval,
including empty batches. The most recent success across owned connections does
not prove that all accounts are current. Per-connection status remains visible.

## Simulator commission revisions

Commission callbacks are absolute totals per execution/revision, not incremental
charges. Highest revision is authoritative; older observations remain evidence.
Before-fill fees wait for their execution. A higher revision after a fill changes
cash, aggregate order fees and position cost basis by the difference only. Source
currency, explicit FX/time and base amount are preserved. Fill events retain the
fixture quote's FX/multiplier/time and original caller fee separately from the
applied commission. These are simulator observations, not external broker proof.

Actual fee overruns remain recorded, halt new orders, and never auto-clear a halt
when later fees decrease. Legacy fills lacking valuation or reservation evidence
require reconciliation. Position sales/realized PnL and external callbacks remain
separate incomplete capabilities. Evidence: commissions-first.txt (ordering,
correction, currency, concurrent duplicate, restart and overrun cases).

## Global simulator marked risk

Both manual and autonomous new-order paths now check marked equity, independent
of model inference. The fixture account loss_limit caps loss from initial
synthetic capital and loss since its first observation of the current UTC day.
There are no external flows in this accounting convention. Mandate-specific
daily-loss/drawdown checks remain additional constraints, not replacements.
Unknown/stale position marks, uncertain execution and clock regression halt
new orders. HTTP risk denial commits that halt and its local alert before
returning409; order approval and reserved cash remain unchanged. No midnight
or quote refresh clears an operator/risk halt. This is not external broker PnL
reconciliation. Tests: manual-risk-first.txt and suite-manual-risk.txt.

### Internal simulator reconciliation

`execution/reconciliation.py` compares materialized cash, order fees/fills,
position quantity/basis and aggregate reserved cash with retained fill and latest
absolute commission evidence. It reads at most10,001 rows per evidence category
and refuses to verify oversized or incomplete ledgers. New manual/autonomous
orders and periodic risk checks halt on discrepancy or unverifiable evidence.
The original balances remain intact for diagnosis. This does not establish
external broker agreement or support external flows/corporate actions.

Fill principal, fee and pretrade reservation must fit ten decimal places; excess
precision is rejected before changes. Proportional partial-fill reservation
release rounds down at ten places and leaves residual dust until final fill.

### Broker source observations

External source evidence is stored separately as JSON decimal strings bounded to
40digits/20decimal places. This retains reported average costs and source values
without applying the simulator's ten-place storage scale. Normalization and
snapshot differences use a local60digit decimal context. Tests verify database
roundtrip and a large-balance difference of1.00000000000000000001 exactly. This
preserves the SDK-supplied representation; it cannot recover precision already
lost upstream or prove compatibility with an unobserved broker gateway.

Position/cash snapshots preserve source currency and request windows. Cash is
never totalled across currencies without dated FX; missing cash is incomplete,
and sequential broker reads are non-atomic. Changes trigger reconciliation review,
not inferred trades/PnL or replacement of stored balances. Full external
execution/flow/corporate-action reconciliation remains incomplete.

### Explaining observed changes

Owned broker review can compare balance deltas with retained executions and fees
available by the closing observation. It preserves contract units/multiplier and
fee currency, supports fractional fills and completed buy/sell round trips, and
reports unexplained residuals. It does not infer deposits, PnL or corporate
changes from a residual. Missing/conflicting evidence, correction families,
unknown contract basis, partial pages and executions during non-atomic snapshot
windows prevent an explanation. Matching evidence yields observed_changes_match
with complete_reconciliation=false and execution_authority=none: complete flows,
corporate actions, broker history and snapshot timing are still unverified.
Evidence: broker-change-explanation.txt and broker-roundtrip-explanation.txt.
