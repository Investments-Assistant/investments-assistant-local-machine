# Retained broker capabilities

Status describes this checkout's verified behavior, not all features offered by
an upstream broker. No external account connection or order was made during this
acceptance work. Global environment credentials cannot authorize helper reads.

| Adapter | Read boundary | Account/currency fidelity | Durable external lifecycle | Writes / autonomy |
|---|---|---|---|---|
| Isolated simulator | Active authenticated owner, fixture account | Decimal account cash, qualified fixture instrument, explicit dated FX/multiplier; buy-only inventory | Persisted intents, approval/mandate provenance, reservations, partial fills, versioned late/before-fill commissions with dated FX, deduplication, uncertainty and cancel/fill race fixtures | Simulator only; independent human order or versioned mandate approval; global risk checks |
| IBKR | Explicit vault account, read consent, actual managed-account match; environment declaration remains unverified, serialized client worker | Account/currency summary retained; unique stock contract qualification; SPYL/IBIS2/EUR resolution fixture | Incomplete: open orders are not execution history; broker callbacks/reconnect/commission reconciliation unimplemented | All submit/cancel entrypoints fail `EXTERNAL_WRITES_NOT_AUTHORIZED` |
| Alpaca | Explicit owner/account/broker configuration; absent or mismatched account rejected before SDK | SDK account/positions/orders retained; financial normalization rejects missing currency/FX; external fidelity unverified | Absent | All submit/cancel entrypoints disabled |
| Coinbase | Explicit owner/account/broker configuration; absent or mismatched account rejected before SDK | Balance/order reads retained; comprehensive fiat valuation and qualified asset identity unverified | Absent | All submit/cancel entrypoints disabled; crypto outside default mandate |
| Binance | Explicit owner/account/broker configuration; absent or mismatched account rejected before SDK | Spot balance/order reads retained; comprehensive fiat valuation and qualified asset identity unverified | Absent | All submit/cancel entrypoints disabled; crypto outside default mandate |

Source: `src/tools/brokers/`, `src/tools/broker_accounts.py`,
`src/execution/external.py`, `src/execution/service.py`, `src/execution/autonomy.py`.
The authenticated dispatcher/vault establishes ownership. Passing a Python
`BrokerAccountConfig` is an internal trusted interface, not a public authentication
mechanism. Browser/MCP callers cannot supply credential objects directly.

Fixture evidence: `evidence/broker-contracts.txt`, `evidence/scoped-helper-reads.txt`,
`evidence/mandates-concurrency.txt`, `evidence/suite-scoped-helpers.txt`.
Actual account permissions, subscriptions, settled funds, external/manual activity,
and external reconciliation remain unverified and block external execution.

## IBKR environment evidence boundary

The adapter requires matching internal account/user/broker identity before SDK
construction, explicit read consent, an actual broker account ID, a declared
environment, and a dedicated nonzero client ID. After connection, managed-account
membership must match the selected actual ID. That match is separate from the
configured paper/live label: account results expose declared_environment and
verified_environment=null, with operator_configuration_only provenance. Neither
the socket port nor a guessed account-number prefix supplies environment proof.
All external submit/cancel paths remain disabled.

IBKR documents the accessible account IDs returned during the connection
handshake in [Verify API Connection](https://www.interactivebrokers.com/docs/tws-api/doc/connectivity/verify-api-connection).
Its [Paper Trading documentation](https://www.interactivebrokers.com/docs/tws-api/doc/notes-limitations/limitations/paper-trading)
also distinguishes simulated execution behavior from live execution. These pages
do not establish a paper/live response field for this adapter's handshake. The
external-paper gate therefore still needs separately authorized account/environment
verification; no local fixture result is substituted for that observation.

Evidence: ibkr-environment-boundary-final.txt,31targeted tests PASS. Tests use
otherwise configured IBKR fixtures and assert identity rejection before lock/SDK
construction; both common port values leave verified_environment unset.

## Durable read observation journal (fixture verified foundation)

Migration0012 adds a separate append-only broker observation journal. Current
vault ownership, active account/user, read consent and actual-account binding are
checked before collection and again before persistence. Identical callbacks
replayed after a new session deduplicate; conflicting payloads and correction
families remain retained for explicit reconciliation. Neither orderRef nor a
client ID grants strategy ownership. Raw actual-account and execution identifiers
are hashed in journal evidence; environment remains declared and unverified.

The bounded SDK callback window collects open-order status, executions and
commissions using explicit read requests and removes all subscriptions on exit.
It preserves already-received facts if a request fails and labels the window
partial. Empty SDK commission defaults are not zero fees. A completed request
never claims complete broker history or complete late-commission delivery.

Current primary references:
[IBKR Execution fields](https://www.interactivebrokers.com/docs/tws-api/ref/execution)
define separate execution IDs, correction suffixes, account and client/order
identity. [ib_insync events](https://ib-insync.readthedocs.io/api.html)
define execution/commission/disconnection callbacks. No dependency migration or
real connection was performed. Evidence: broker-journal-recovery.txt (7PASS),
broker-refresh-authority.txt (12PASS). Continuous subscriptions, complete external
reconciliation, execution authority and observed external-paper acceptance are
still incomplete; this journal alone does not satisfy L04 or L15.

Retained evidence review now reports conflicting execution/commission versions,
correction families, unpaired commissions/executions and mismatched payload hashes.
It never adds conflicting/corrected quantities as extra fills. A paired window is
still unverified for full history, balance reconciliation and strategy ownership.
Explicit refresh records a scoped in-app alert for unresolved evidence or request
failure. Repeated alerts use the existing durable deduplication/cooldown mechanism.

Saved evidence supports bounded keyset pages (up to1000facts each); a cursor must
belong to the current owner, internal account and actual-account binding. It is
not an export snapshot: restart browsing to include concurrent arrivals. Reviews
of partial pages remain marked incomplete. Evidence: broker-review-pagination.txt
(17PASS). Full external position/cash reconciliation and continuous callbacks
remain required and unverified.

## Balance snapshot observations

The read window now explicitly requests positions and account summary, retaining
at most500selected contracts and100currency rows. Snapshot facts preserve conId,
security type, original currency, exact quantity and average_cost_reported without
claiming that average cost is a dated base-currency valuation. Currency cash uses
CashBalance or $LEDGER-CashBalance, excludes BASE aggregates, and never combines
EUR/USD without FX. Missing cash is incomplete, not zero. Duplicate contract or
currency rows are rejected rather than silently overwritten.

[IBKR per-currency prefixes](https://www.interactivebrokers.com/docs/tws-api/doc/tws-settings/per-currency-account-value-prefix)
explain the optional $LEDGER- namespace. The installed ib_insync0.9.86
reqAccountSummaryAsync requests $LEDGER:ALL and completes through its summary
request future; reqPositionsAsync completes its positions request. These local
contracts were inspected and exercised through SDK-shaped fixtures, not a live
connection or an API-version compatibility claim for an actual gateway.

Sequential requests are explicitly non-atomic. Comparison reports quantities and
cash differences per currency, flags incomplete requests/overlapping windows,
and preserves source evidence. A difference needs flow/corporate-action/execution
reconciliation; an unchanged pair is not proof of a complete ledger or PnL.
Journal read pages also cap serialized payload at2MiB using SQL byte measurements
before loading JSON into application memory. This bounds large snapshot pages
independently of the1000-observation row cap. Source/library buffering remains a
separate upstream limitation; no complete external reconciliation claim is made.

Hard read exceptions, timeouts and cancellation now create a redacted scoped
in-app `broker_read_failure` alert alongside durable attempt failure status.
This does not deliver external notifications, authorize retries or establish
reconciliation. Active-owner checks and stale/reclaimed lease fencing apply to
alert publication as well as callback persistence. Verified in
`evidence/broker-read-failure-alerts-verified.txt` (22 PostgreSQL tests).
