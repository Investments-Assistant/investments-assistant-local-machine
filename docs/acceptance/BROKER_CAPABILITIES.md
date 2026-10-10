# Retained broker capabilities

Status describes this checkout's verified behavior, not all features offered by
an upstream broker. No external account connection or order was made during this
acceptance work. Global environment credentials cannot authorize helper reads.

| Adapter | Read boundary | Account/currency fidelity | Durable external lifecycle | Writes / autonomy |
|---|---|---|---|---|
| Isolated simulator | Active authenticated owner, fixture account | Decimal account cash, qualified fixture instrument, explicit dated FX/multiplier; allocation-owned inventory; explicitly opted-in manual sales | Persisted intents, approval/mandate provenance, reservations, partial fills, versioned late/before-fill commissions with dated FX, deduplication, uncertainty and cancel/fill race fixtures | Simulator only; independent human order or versioned mandate approval; global risk checks |
| IBKR | Explicit vault account, read consent, actual managed-account match; environment declaration remains unverified, serialized client worker | Account/currency summary retained; unique stock contract qualification; SPYL/IBIS2/EUR resolution fixture | Fixture-tested bounded callback collection, durable observation journal, duplicate/correction retention and partial balance attribution; continuous history and complete reconciliation remain incomplete | All submit/cancel entrypoints fail `EXTERNAL_WRITES_NOT_AUTHORIZED` |
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


## Retained order-status and execution comparison

The read journal now reviews order-status facts as well as fills and fees.
Positive broker permanent IDs group observations within the already selected
owner/account binding; client/order-only identity remains explicitly unverified.
Reported filled quantity is compared with unique retained executions, never a sum
of repeated orderStatus quantities. Correction families, conflicting execution
versions (including changed permanent IDs), missing execution evidence, terminal
quantity discrepancies and Filled/Cancelled conflicts require review. A pending
cancel is not confirmation. The review exposes up to100 order details while
counting all selected orders; truncated input remains incomplete.

The output deliberately has `current_state=not_established`, no strategy ownership,
no execution authority and no complete reconciliation assertion, including when
quantities agree. A later-received callback cannot overwrite a previous fact or
prove current broker state. It cannot retry, cancel, submit or change holdings.
These reason codes join the existing refresh alert and owner-scoped evidence API.

IBKR's [order submission documentation](https://interactivebrokers.github.io/tws-api/order_submission.html)
notes repeated status notifications and that not every transition is reported;
execution details must also be considered. This is a historical official reference,
not proof of a current connected broker or verified installed runtime compatibility.
The current [IBKR introduction](https://www.interactivebrokers.com/docs/tws-api/doc/introduction)
and [installed-library API reference](https://ib-insync.readthedocs.io/api.html)
were also consulted. No new SDK, connection or dependency migration was performed.

Evidence: `broker-order-review-reproduction.txt`4FAIL exposed ignored order evidence;
`broker-order-review-verified.txt`41PASS3.66s includes marked PostgreSQL late-fill
recovery, delayed cancel conflict, duplicate replay and masked output, plus exact
partial sums, identity/correction guards and bounded detail tests. Initial expanded
test recreated an execution timestamp and correctly inserted a distinct observation;
the replay fixture was corrected to reuse the original event. This does not close
continuous history, real reconnect/reauthentication or external reconciliation gates.


Final evidence: `suite-broker-order-review.txt`964PASS98.70s and durable exit0;
`browser-broker-order-review.txt` real Chromium/PostgreSQL fixture PASS/exit0, no
unexpected console errors or broker connections/orders. The final computed field
is `pending_cancel_observed` (historical fact, not a claim of currently pending
cancellation); all41affected checks reran afterward in
`broker-order-review-observed-field.txt` PASS2.99s. Unaffected full-suite/browser
results are reused. Continuous session ownership, external reconciliation and
observed paper execution remain incomplete.


## Explicit SDK session ownership foundation

`ReadSessionWorker` owns connection construction, SDK event-loop pumping, read
operations, optional subscription cleanup and disconnect on one thread. Requests
have a bounded queue (default4, maximum16), bounded waits and a finite session
lifetime (default60seconds, maximum600). The native SDK is configured read-only
by the existing connection boundary. Admission rejects missing owner/account/read
consent before thread/SDK construction. Configuration is copied for the session.
A busy request queue still yields to SDK event processing between operations.

Request timeout cancels queued work and stops further admission. In-flight native
work cannot be killed: the owner and existing SDK connection lock remain held
until actual cleanup. `close` reports whether cleanup has finished, not a guessed
success. Disconnect and lifetime expiry fail outstanding queued requests with
stable codes; no automatic reconnect occurs. The collector's existing explicit
snapshot now uses this owner and still removes its handlers and closes afterward.

This is a tested connection-ownership component, not completed continuous broker
monitoring. A continuous coordinator still needs durable batch delivery,
backpressure, current database authority/binding checks, interruption checkpoints,
and explicit activation. No background connection or new read consent is enabled.
Other adapter reads retain their existing scoped connection boundary; a future
continuous owner must also avoid starving these reads.

Evidence: `ibkr-session-collector.txt`48PASS1.66s verifies worker/event-loop identity,
repeated reads and idle pumping, bounded queues/lifetimes, native timeout ownership,
subscription cleanup, and the actual snapshot wrapper with an SDK-shaped fixture.
All SDK construction/connect calls in these tests are mocked; no broker was reached.


## Bounded stream journal foundation (2026-10-08)

CallbackWindow now supports sustained subscriptions and intermediate batches on
the SDK owner thread, with final detach before drain and permanent overflow
reporting. This component retains late callbacks between reads.

`broker_stream_journal` persists batches and their lease checkpoints atomically.
Every batch rechecks active owner/account, read consent, actual-account binding,
and the entire selected configuration (including endpoint/client changes). Database
time fences token ownership, renewals and a maximum ten-minute session lifetime.
Intermediate commits never mark successful completion. Final capture explicitly
requires native cleanup; missing final checkpoints become interrupted after lease
expiry. Gaps close as partial, cannot become success on a later batch, and never
claim complete history or execution authority. Replayed financial facts deduplicate.

The new recovery case reproduced a stale ORM lease after an upsert; refreshing the
lease object fixes it. `broker-stream-journal-first.txt` records1FAIL32PASS, then
`broker-stream-journal-guards.txt`49PASS2.94s/exit0, including separate-transaction
concurrent delivery and atomic rollback when authority expires after insertion.
SDK fixtures remain synthetic; no broker connected. No automatic stream/coordinator
is enabled yet. Continuous routing, disconnect recovery and external reconciliation
remain open. Full suite is in progress in `suite-broker-stream-journal.txt`.


## Finite continuous capture coordinator

`broker_stream.capture_observations` now connects the owner/callback/journal
components for an explicitly invoked finite interval. Subscription remains active
between database batches; it does not reconnect for every read. Capture detaches
before its final drain, and the journal only reports completion after native cleanup.
Cancellation or failure signals immediate stop, retains admission until lease expiry,
preserves the last committed batch checkpoint, and never saves a late cancelled
result. Callback gaps commit a partial checkpoint and a scoped in-app alert.

Durations default to60seconds with5second batches (maximum480seconds/10seconds).
SQL/lock/native waits and buffers are bounded; no automatic retry/reconnect occurs.
This service is intentionally not registered as a route, model tool or scheduler
job. Routing other reads through an active owner is still needed before background
activation, since the existing native connection lock serializes adapter reads.
Real account environment/consent/paper gates remain separate and unverified.

`broker-stream-coordinator-verified.txt`56focused checks pass with a mocked SDK
and actual disposable PostgreSQL, including late commissions, current consent
revocation, disconnect, partial callbacks, cancellation during native connection
setup and native cleanup failure. No broker is contacted. The prior journal-only
fullsuite passed990tests; the coordinator fullsuite is currently in progress.


## Shared owner reads

The finite coordinator now reserves process-local read routing before startup.
Account summary, positions, open orders, contract resolution and explicit snapshot
reads reuse that SDK owner only when principal, application account and full
configuration match. Mismatch, overload, stopping or not-ready states fail without
a new connection fallback. Native timeouts retain the reservation until real
cleanup; cancellation before startup releases its reservation. Synchronous calls
from an async event loop are rejected. Other processes still require their own
client-ID/deployment discipline and durable account leases.

A temporary snapshot subscription removes only its own handlers; ongoing capture
continues. Existing direct reads still use their scoped connection when no owner
is registered. This closes process-local read starvation without enabling any
background job, automatic reconnect or broker access. Evidence:
`broker-read-routing-guards.txt`59PASS8.14s and
`broker-read-routing-subscription.txt`8PASS1.11s (7 overlap). Earlier test failures
are retained; new/old fixtures were corrected to respect immutable configuration
and explicit read consent. Prior coordinator fullsuite997PASS77.52s; current
routing fullsuite is in progress.

Final shared-routing validation: `suite-broker-read-routing.txt`1005PASS78.45s,
terminal exit0 and durable `.exit0`. No subsequent behavior change; the coordinator
docstring now reflects completed shared routing. Existing browser fixture evidence
is reused because this change does not alter UI flows and the browser intentionally
stubs broker transport; it is not evidence of real SDK/broker compatibility.


## Explicit finite browser capture

Authenticated browser callers may POST `/api/broker-accounts/{id}/observations/capture`
with `{"confirm_broker_read":true,"duration_seconds":60}` and valid CSRF protection.
Duration is a strict integer1–480seconds. This is explicit read activation, not a
model tool, scheduled connection, reconnect policy or trading mandate. The account
must already have current owner/read consent; the coordinator rechecks before
connection and every persisted batch. No real account was activated during tests.

202means accepted into one bounded process-local slot, not connected or reconciled.
GET on the same path reports only the caller's task state. DELETE requests stopping
only that caller's matching capture, even if its account read consent was revoked.
Stopping does not attest native SDK cleanup; the SDK owner/lease remains protected
until actual cleanup/expiry. The existing observations endpoint and durable journal
provide evidence and failure details. Private exceptions are not exposed.

Shutdown cancels a running explicit task and waits up to15seconds for its async
cleanup. A fresh process never automatically reconnects; an interrupted durable
lease must expire and a new explicit request must pass current consent. In-flight
native calls may finish later and retain ownership meanwhile; no late result gains
permission to persist. Multiple processes still rely on the existing durable lease
and SDK collision handling, not the in-memory admission slot.

35focusedPG/SDK/HTTP checks in `evidence/broker-capture-activation-guards.txt` verify
activation, denial, bounded input, stop/restart intent and current principal scope.
Fullcurrentregression evidence is tracked in CHECKPOINT.md. Real gateway login,
reauthentication, entitlements and full external reconciliation remain unverified.


## Upstream connection transitions while the API socket remains open

Callback capture listens to the installed SDK's errorEvent as well as its local
disconnectedEvent. IBKR's current [system-message documentation](https://www.interactivebrokers.com/docs/tws-api/doc/error-handling/system-message-codes)
distinguishes1100loss,1101restoration with lost market requests,1102restoration
with maintained market requests, and1300socket-port reset. Each transition during
capture leaves the sticky `BROKER_UPSTREAM_CONNECTION_CHANGED` reason. Even1102
is not proof this application's execution/commission history was uninterrupted;
the reason does not assert that market data was lost. Informational2104 alone
does not mark a connectivity gap. Raw error text/contracts are not retained.

The finite coordinator stops on its next bounded drain, detaches callbacks,
performs native cleanup, persists a partial checkpoint and emits an owner-scoped
in-app alert. A restoration notice cannot clear the gap or set last_success.
The application neither reconnects nor retries automatically. The installed
ib_insync library has its own1102account-summary refresh behavior; this is not
external reconciliation or evidence of completed human reauthentication.

`broker-upstream-reproduction.txt` records4failing regressions before the fix.
`broker-upstream-verified.txt` records66passing unit/PG/HTTP/SDK-shaped checks,
including all4transitions while the fixture SDK remains connected, retained facts,
partial journal/alert state, and error-handler detachment. Real gateway behavior
and dependency-version compatibility remain separate external validation.
