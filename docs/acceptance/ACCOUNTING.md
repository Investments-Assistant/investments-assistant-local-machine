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

The execution engine supports purchases and explicitly opted-in, independently
approved manual sales in isolated fixture accounts. Existing buy mandates do not
gain sell authority, and manual sales cannot consume mandate-owned holdings.
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

Manual-sale realized PnL uses fee-inclusive weighted-average basis and net sale
proceeds, with exact residual basis released on final disposal. Autonomous
strategy-owned sales, corporate actions and independent broker reconciliation remain incomplete.
Versioned standalone simulator commissions are implemented as described below;
external callback coverage is a bounded read window, not complete history. Existing `DailyPnL`/legacy trade rows are not
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
require reconciliation. Manual simulator sales/realized PnL are supported as described below; external
callbacks and autonomous sales remain separate incomplete capabilities. Evidence: commissions-first.txt (ordering,
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

### Exact portfolio summary serialization

Position-source market value and unrealized PnL now convert with Decimal before
aggregation, using100-digit local arithmetic. Summary *_usd_exact strings retain
small amounts beside large source balances and survive JSON/API serialization.
Existing numeric totals remain display compatibility fields; financial chat prefers
exact totals. Missing FX or provider errors invalidate both representations.
This cannot recover precision already lost by an adapter/provider, and does not
prove complete cash, realized-PnL or corporate-action reconciliation.
Evidence: portfolio-exact-totals.txt (61 focused tests), unit-portfolio-exact.txt
(452 unit tests before subsequent report-date changes).

Report periods accept canonical YYYY-MM-DD calendar dates only. Both boundaries
are UTC midnight and the ending calendar day is inclusive through a half-open
next-midnight cutoff. Offset-aware evidence timestamps compare as instants;
timestamps supplied as date arguments are rejected instead of losing their offset.
Evidence: report-calendar-boundaries.txt (8 tests).

### Report collection coverage

Internal legacy trade audits are bounded to1000 rows in stable created_at/id
order, with one extra row fetched to detect omissions. Saved simulation runs
are bounded to10 with the same extra-row detection. Coverage records included
counts, limits and has_more; omissions make generation partial. Simulations
are selected by run creation date, and retain their separate simulation horizon.
No legacy audit status is promoted to a reconciled fill. Complete empty results
remain distinct from unavailable, undated or failed broker history. Provider
error text is redacted before collection evidence reaches a model/report.
Evidence: report-coverage.txt, report-history-persistence.txt and
report-missing-sources.txt. These bounds do not establish full financial
reconciliation or validated model report arithmetic.

### Realized-PnL integrity prerequisite

Complete purchase-only simulator ledgers now require realized_pnl=0; purchase
fees remain in position basis. A different materialized realized value is a
reconciliation discrepancy, not evidence of a realized gain/loss. The input hash
includes the stored value. Incomplete/unsupported ledgers remain unverified and
do not assert an expected realized value. Discrepancies preserve balances and
halt new approvals through the existing durable risk/alert transaction boundary.
The current reducer also reconciles explicitly authorized manual sales against
recorded fills, including realized PnL; it never trusts the stored realized field alone.

### Allocation-scoped accounting reducer

`execution/accounting.py` now provides deterministic weighted-average basis
accounting, and current buy/manual-sale reconciliation calls it. Each fill requires
a unique execution identity, explicit unique positive sequence, instrument,
allocation, side, exact base-currency principal and final applicable fee. Evidence
normalization/FX validation and commission-revision selection remain outside the
reducer. It accepts at most10,000 fills and validates the ledger's ten-place scale
and numeric range under its own high-precision Decimal context.

Purchase principal plus fee enters that allocation/instrument's basis. A sale
releases proportional weighted basis, with partial-sale rounding down at ten
places; the final sale releases the entire residual. Net sale proceeds less
released basis is realized PnL. A sale cannot consume another allocation's
quantity or create a short. Fee corrections replay the same economic sequence
with the latest absolute fee, dividing corrected purchase costs between retained
basis and realized PnL rather than charging everything to remaining holdings.
Negative cash from observed costs remains visible for separate risk handling.
This is an accounting convention for the simulator, not a tax-lot calculation.

Durable reconciliation accepts supported manual-sale evidence. Migration0013
backfilled legacy purchase order and future callbacks receive database identity
sequences under the owned account lock. These sequences order observed simulator
fills, not historical broker economic events. Manual approval consumes only
verified manual inventory; the read view itself never grants authority.

### Allocation provenance

Reconciliation now includes retained submitted events when establishing fill
ownership. Mutable order approval must exactly match one retained submission,
with simulator environment and supported actor. Manual ownership requires the
browser approval event and immutable order-details hash, with no mandate ID.
Mandate ownership requires the mandate submission event, matching mandate
session identity and recorded mandate hash. Unknown/mismatched provenance leaves
accounting unverified and stops new approvals with a persistent reconciliation
halt; it never silently defaults a filled order to manual ownership. This does
not provide cryptographic protection from an administrator rewriting both records.
Locked manual-sale reservations and callback integration are verified below.
Autonomous sale strategy/version approval remains unimplemented.

### Owned inventory and pending quantity claims

`execution/inventory.py` computes allocation/instrument quantity, basis, reserved
quantity and remaining available quantity from reconciled fills plus validated
order provenance. Remaining sell quantity is quantity minus filled; submitted,
acknowledged, partially filled, cancellation-pending and uncertain orders retain
their claims. Only unapproved proposals and terminal states have no pending claim.
Claims cannot borrow another allocation's quantity or anticipated buy fills.
Duplicate/unknown orders, missing provenance and overreservation fail closed.

The owned simulator snapshot now includes this view in reconciliation only when
all ledger checks are consistent. Discrepant/unverified states expose null rather
than misleading sellable inventory. Persistent risk summaries retain hashes and
status without duplicating the full inventory. This view does not itself approve
or reserve a new order: sale approval must read and consume it while holding the
account lock. The manual sale path now does so; existing buy mandates gain no
new authority and old practice accounts remain buy-only unless already explicitly enabled.

### Replayed commission corrections

The commission callback now obtains pre/post-revision ledger balances and applies
only the change in cash, realized PnL and per-instrument retained basis. The
private ledger return is not part of the public snapshot response. Revisions
remain append-only and duplicates charge nothing. A pre-existing discrepant or
unverifiable ledger records the new commission but returns reconciliation_required
and halts without overwriting suspect cash/basis. Operators must reconcile that
state before further execution. Lower fee revisions never clear an existing halt.

This replaces the assumption that every corrected fee belongs entirely to the
remaining position. Persisted manual sale callbacks and approvals now use the
same ledger, including fee-before-fill and later purchase-fee corrections. Existing
buy-only mandates remain buy-only; separately approved price-band mandates can sell their own allocation.


### Explicit manual-sale practice workflow

A new practice account offers an unchecked manual-sales opt-in. Existing accounts
are not modified. The browser selects Buy or Sell, displays side-bound immutable
proposal details, and requires a separate approval and fill action. Protected
instruments, non-stock/ETF defaults and external accounts remain outside this path.
Manual sales require fixture=true and manual_sales=true; model tools cannot set
those fields or approve orders. Approved buy mandates retain their original scope.

Approval rechecks provenance-backed available manual quantity while holding the
account lock. Concurrent approvals cannot consume the same holdings. Pending sale
quantity is inferred from durable order quantity minus filled; cancel_requested
and uncertain retain claims, confirmed terminal cancellation releases them. Sale
cash reservation covers bounded fees, not proceeds; trusted quote/FX notional still
faces the global order cap. Fee policy must be finite0..100bps. Quotes and tick/lot,
protected allocation, persistent halts and independent approval checks remain.

Observed fills use durable event order to update cash, basis and realized PnL.
Late cancelled fills are retained and halt new orders. Evidence insufficient to
replay an observed sale yields reconciliation_required rather than fabricated
balances. Known pending commissions can expose a private settled pre-fill balance
only to fill accounting; public inventory remains unverified until evidence joins.

Evidence: simulator-sales-first.txt records the initial fee-before-fill defect;
simulator-sales-fee-recovery.txt and simulator-sales-lifecycle.txt verify recovery,
partial/final/deduplicated fills, cancellation and concurrent independent sessions.
suite-simulator-sales.txt records690PASS; browser-simulator-sales.txt verifies the
opted-in round trip and a EUR0.20 realized loss from its two synthetic fees. These
are engineering fixtures, not a profitable strategy or external broker validation.

### Unreconciled late-sale retries

When a cancelled sale fills after its released inventory has been consumed by a
replacement, the observed execution is retained but no fabricated short/balance
is applied. The account halts, public inventory is unverified, and the initial
fill evidence retains accounting_status=reconciliation_required. Repeated delivery
returns that same review status after reload rather than inferring settlement
from order.status=filled. Execution state and accounting state are distinct.
Older sale evidence without this field is checked against current reconciliation
before a duplicate response can imply settled accounting. Retained historical
payloads are not rewritten by that compatibility check. A separate reviewed
reconciliation resolution is still required; no automatic halt clearing occurs.


### Research dividend timing and receivables

Dividend entitlement and payment are distinct; see the
[SEC investor explanation](https://www.investor.gov/introduction-investing/investing-basics/glossary/ex-dividend-dates-when-are-you-entitled-stock-and)
and an [issuer's separate ex-date/payable-date history](https://www.investor.nexteraenergy.com/stock-information/dividend-history).
The replay bar's dividend is gross per-share entitlement on the supplied ex-open,
for shares carried into that session (after any simultaneous split). It is not
cash until `dividend_pay_at`. Missing payment dates retain receivables and mark
valuation partial. No payment date is inferred from Yahoo's dividend series.
Foreign payments require explicit positive `dividend_payment_fx` and dated
`dividend_payment_fx_as_of`, available by payment and within the FX age policy.

Receivables are marked using current supplied source-currency FX; payment-time
conversion gains/losses are shown separately as `dividend_fx_pnl`. `dividends`
records gross entitlement valued at ex-time, `dividends_paid` records cash received,
and `dividend_receivable` records unpaid marked assets. Equity includes unpaid
assets; order buying power uses cash only. Payment during a session cannot fund
its earlier opening fill. A later split leaves already earned cash entitlements
unchanged. Withholding, special-dividend entitlement exceptions, actual broker
receipt timing and execution-ledger corporate actions remain unverified; this is
an explicit research input convention, not a claim of broker reconciliation.

[Payment timing and offline reproduction tests](evidence/dividend-payment-reproduction.txt)
cover both replay engines, payment FX, delayed/unknown dates, splits and invalid
evidence. Code/input fingerprints change with these accounting rules. Prior
results remain evidence of the earlier engine and must not be relabelled.


Research execution costs validate the combined adverse price impact as well as
individual bps fields: `spread_bps / 2 + slippage_bps < 10000`. Otherwise a sale
could imply zero/negative execution price. Both replay engines reject the invalid
assumption before trading, even if the selected sample happens to contain no sale.
[Six reproduced failures](evidence/research-impact-reproduction.txt) and
[35 passing affected checks](evidence/research-impact-fixed.txt) establish the fix.
This is input validity, not a claim that extreme but positive-price costs are
realistic or profitable.


### Reconciled simulator report periods

Reports now include a separate synthetic-account section backed by
`execution/reporting.py`. It filters validated fill evidence by local booking time
using an inclusive start and exclusive end (the report UI's end date includes the
whole UTC day). It sums disposal realized results and fees attributed to those
fills using exact Decimal arithmetic. Each statement retains order, fill-event,
allocation and instrument identifiers plus reconciliation and period-row hashes.
Mixed account currencies are never combined into a labelled single-currency sum.

Results are **restated with the latest retained fee corrections at collection**.
A later fee on an earlier purchase may change basis and realized results assigned
to the sale's original period. Attributed fill fees are not fee-payment cash flows.
Collection start/end are retained; this does not reconstruct what was known on a
historical report date. Missing opening/closing valuations, external flows,
corporate actions, FX attribution and benchmarks still prevent total portfolio
period-performance claims. No actual brokerage execution is implied.

A discrepant or unverified ledger publishes unavailable totals and no reconciled
execution statements. The source reads at most20accounts and at most the existing
reconciliation capacity per account; it displays100executions per account while
hashing and totaling all validated in-period rows. Account/detail truncation is
explicit. Source timeout or denial yields a partial report. Read-only collection
uses active-owner checks and account locks; no order or balance is changed.
[Full regression](evidence/suite-execution-period-reports.txt) and
[actual collector/PDF/persistence checks](evidence/execution-period-report-persistence.txt)
cover ownership, period boundaries, late-fee restatement, withheld discrepant
results, capped details and retained evidence. Browser fixtures remain separately
labelled in [the Chromium result](evidence/browser-execution-period-reports.txt).


### Reconciliation arithmetic context

Internal execution reconciliation validates source-to-base products and aggregates
under its own 80-digit Decimal context, matching the weighted-basis reducer. It
restores the caller context on exit; display/inference code precision must not
change whether identical ledger evidence is consistent. The PostgreSQL regression
uses a ten-decimal-place fill price and checks identical evidence and inventory
under ordinary and six-digit caller precision. This does not add corporate actions
or external flows to the ledger.


### Synthetic account cash-flow receipts

Migration0015 adds an account-scoped receipt journal sharing the execution sequence.
The internal fixture service records base-currency deposits/withdrawals atomically
with cash, under active-owner account locking; it performs no payment operation and
has no model/MCP/browser route. It requires an explicit simulator fixture flag,
source reference and aware nonfuture effective time. Duplicate matching receipts
return their original event; changed details conflict. Withdrawals cannot consume
reserved cash. No mandate limit, protected allocation or initial capital is changed.

Reconciliation verifies receipt ownership/currency/provenance/digest and replays
flows with fills. Invalid evidence withholds verified inventory. Cumulative flows
are excluded from capital PnL; daily flow changes are excluded from daily PnL.
Strategy high-water observations adjust for flows, preventing a withdrawal from
looking like drawdown or a deposit from hiding trading losses. Legacy observations
precede flow support and carry zero flow baseline.

Reports select receipt booking times with the same half-open period convention,
show effective times separately, retain event IDs/digests, and distinguish net
cash flows from trading PnL. These are current-knowledge synthetic reports, not
external-broker statements or historical point-in-time returns. Foreign-currency
flows, persisted splits/dividends, opening/closing marks and full benchmark/FX
attribution remain incomplete. Pure split arithmetic is tested independently;
that does not establish persisted corporate-action support.


### Persisted synthetic split receipts

The internal fixture service now records splits in the account journal, ordered
with fills and cash receipts. Every allocation retains its basis and ownership;
quantity changes must be exactly representable. Cash and realized PnL do not
change from a split. Late fee corrections replay through retained split events.

The service refuses another account's instrument, malformed ratios, conflicting
receipts, retroactive split timing and any non-filled order for that instrument.
It does not rewrite immutable approved orders or assume a cancelled order cannot
receive a late fill. Nonrepresentable fractions require separate evidence; no
cash-in-lieu or disposal is invented. Existing protected flags and mandate limits
are preserved. Quotes are made stale, and a persistent corporate-action review
halt prevents trading on old thresholds. Existing operator halts are preserved.
There is no automatic adjustment of price-band mandates or model authority to
clear this halt.

Reconciled reports retain split event IDs, ratios, booking/effective timestamps
and evidence hashes separately from fills and cash flows. This supports synthetic
forward split facts; external corporate-action feeds, historical restatement,
dividend/withholding accounting, mergers/spinoffs, cash-in-lieu and operator review
UI remain incomplete. Pure research dividend support is not execution accounting.

### Received dividend evidence (synthetic only)
The internal fixture receipt service records base-currency gross dividend and explicit
withholding separately. Replay credits net cash to its historical allocation without
changing position basis, deposits or sale realized PnL. Payments after disposal are
permitted when allocation ownership history exists; this does not prove ex-date
eligibility. No unpaid entitlement, withholding rate or foreign-currency conversion
is inferred. Protected instruments halt consumption pending review; existing halts
are retained. Reports use half-open booking-time intervals, retain receipt hashes,
and show gross/withholding/net separately from execution fees. Tampered receipts
invalidate reconciliation. No public submission route or broker/payment call exists.

Execution arithmetic owns its Decimal context at policy, manual proposal/approval/
fill/transition, commission, marked-risk and autonomous-tick boundaries. A128digit
intermediate context covers bounded fixed-point products and aggregates without
inheriting another caller's rounding/trap/precision changes. Caller settings are
restored on success/failure; ledger precision validation remains ten decimals.
Regression reproduces a false RISK_BUDGET_UNAVAILABLE halt at callerprec6 and tests
exact marked valuation, manual lifecycle/latefees and autonomous reservations.

### Immutable observed valuations
Migration0017 retains account/user-owned valuation snapshots with reconciliation hash,
current cash/basis/fees/flows/income, allocation attribution, and exact held quantities,
source prices/currency/multiplier/FX with their shared simulator feed timestamp.
Capture holds the account lock, rejects inconsistent ledgers, stale/future quotes,
future booking clocks, invalidFX and capacity overflow. Keys deduplicate without
replacing earlier evidence; tampered hashes make the observation unavailable.

In Simulation, save two current observations and compare them. Exact-boundary
PnL is closing equity minus opening equity minus net external flows. It must
reconcile to realized change + unrealized change + net dividend income, both for
the account and the sum of allocations. Fees are included already; informational
fee changes must not be subtracted again. Later fee revisions affect later observed
cash/basis/PnL; the snapshots are not rewritten as if the correction were known earlier.

Requested report periods only use snapshots at the exact requested boundaries.
Missing marks yield partial collection and unavailable portfolioPnL while valid
period execution evidence/PDFs remain. Reports do not substitute current quotes,
a first daily risk observation, or a nearby snapshot for a historical boundary.
For schema1 snapshots, separate FX attribution and benchmark evidence remain unavailable and explicitly
labelled. Cross-currency account totals are not fabricated.

Opted-in fixture risk monitoring saves at most one first observation per UTC date.
This is an actual observation time, never an invented midnight mark. Archival
capacity/error is visible via a deduplicated in-app alert; current deterministic
risk controls remain independent. No automatic historical backfill, real broker
connection, production snapshot capture or retention policy is authorized by this work.


### Observed price and FX attribution (schema 2)
New immutable snapshots retain cumulative signed execution principal in source and
base currency, cumulative execution fees by allocation/instrument, and fresh closing
FX marks (including closed instruments). Historical schema1 snapshots stay intact;
comparison with them retains verified P&L but explicitly reports attribution unavailable.
For each allocation/instrument, with source market values V0,V1, signed period trade
principal Ns,Nb, opening base market value B0, and closing FX r:
`price=(V1-V0-Ns)*r`; `FX=(V0+Ns)*r-B0-Nb`.
Thus price + FX - period execution fees + net received dividends must equal the
flow-adjusted P&L, both overall and for each allocation. Fees are never subtracted
again from the reported P&L. This is a closing-rate convention: price/FX interaction
is assigned to price, and FX includes differences between execution and closing rates.
It is attribution in account base currency, not a cash FX-conversion service.
Fresh closing FX is required even for a position sold during the interval; missing
FX leaves decomposition unavailable without discarding otherwise verified P&L.
Dormant closed positions with no interval exposure or trades need no FX mark.
External flows are excluded; later booked fee corrections affect the later observed
interval. Exact historical boundaries and benchmark evidence are still required and
are never reconstructed from current quotes. No production/live capability added.
Verification: valuation-fx-scoped.txt, 30PASS including foreign open/partial/full
sales, stale closed-position FX, dormant positions, opening exposure/interaction,
legacy history, received dividends, flows, late fees and report rendering.


### Explicit unpaid synthetic dividend receipts (2026-10-08)

Entitlements and linked settlement now have distinct immutable account events.
The supplied eligibility time, action identity, allocation, instrument, exact
eligible quantity, gross base amount and explicit withholding form fixture
evidence; no exchange calendar, tax rate, special-distribution rule or foreign FX
is inferred. Current quantity is accepted only if no later fill/split invalidates
its use at the supplied eligibility time. Unsupported historical eligibility is
rejected for separate reconciliation, not reconstructed from current holdings.
This follows the distinction between entitlement and payment in the linked SEC
source above; special distributions require their own verified evidence.

Accrual creates a nonspendable fixed net receivable. Payment references the exact
entitlement, transfers its net asset to cash once, and does not create a second
income event. Later sales/splits cannot resize an already earned dividend. New
unlinked legacy payments are refused for allocations/instruments that have entered
this explicit entitlement path; old idempotent receipt replay is retained. No
matching between old unlinked receipts and new issuer actions is invented.

Reconciliation, manual/mandate risk equity and immutable schema3 valuation
snapshots include receivables. Period income is received cash income plus change
in outstanding receivables; price+FX-fees+income still reconciles to equity less
external flows. Existing schema1/2 snapshots remain immutable and predate supported
entitlement booking. Reports show received cash and accrued income separately.
Protected income preserves operator halts and requires review; no receivable can
fund a new order because cash/reservation checks still use actualcash only.

`dividend-receivable-integration-guards.txt`53checks PASS includes concurrent
receipt/payment, duplicate/conflict, unsupportedhistory, tamper, risk, exact
valuation and report tests. Fullsuite/browser/restore verification pending at
this checkpoint. These are base-currency simulator fixtures, not verified broker
corporate-action entitlements or live financial policy.

Recovery follow-up: `dividend-receivable-recovery-20261008-database.json` verifies
31table hashes after actual isolated restore; the companion `-split.json` verifies
unpaid income/cash separation and identical exact period accounting. Target
`test_receivable_20261008` is retained. Concurrent receipts and linked payments
commit once; `dividend-receivable-cash-verified.txt`11PASS also verifies cross-owner
denial and that pending income cannot fund an order. Current fullsuite/browser
checks are in progress.

Final entitlement validation: `suite-dividend-receivables.txt`1031PASS81.79s/exit0
and `browser-dividend-receivables.txt`desktop/mobile realChromium/PostgreSQL
workflowPASS/exit0. No unexpected console errors, broker connections or orders.
The browser proves preserved application workflows, while the explicit entitlement
accounting/report/risk and restore invariants are covered by the focused PG tests
and recovery artifacts above. Foreign/special distributions and unavailable
historical evidence remain explicit unsupported/partial states.
