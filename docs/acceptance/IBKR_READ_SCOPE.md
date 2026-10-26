# Selected-account SDK retrieval

24 October candidate: offline engineering correction, no new external
connection, deployment or account authority. The owner confirmed TWS's Paper
banner; saved application read flags remain OFF. Current local runtime metadata
is in [the prerequisite record](evidence/paper-session-prerequisite-20261024.json).

## Problem and bounded profile

The application previously passed its selected account to `IB.connect`, then
checked membership and filtered results. In pinned `ib_async`2.1.0, that high-level
bootstrap first requests all positions, sub-account updates and executions.
Result filtering does not constrain upstream retrieval. The stock error1102
handler also automatically requests account summary after upstream restoration.
This source inspection establishes a scope limitation, not actual extra-account
exposure in the earlier authorized read.

The corrected profile supports exactly one managed account, matching the explicit
application selection. It uses the SDK's lower-level metadata handshake, verifies
both initial and current managed-account metadata, then downloads only that
account's primary updates. It does not run default positions, execution or Multi
warmups. Missing, mismatched, duplicate or additional managed accounts fail before
financial requests; identifiers never enter the reason code. A multi-account TWS
session is unsupported by this profile and must not be admitted through broader
consent or output filtering.

Later scope changes permanently invalidate the owned connection and stop its
subscriptions. Reverting the account list cannot reauthorize it. Native financial
requests and returned reads recheck scope; account-update unsubscription remains
available for cleanup. Startup health gaps also invalidate admission. The stock
reconnect refresh is removed only on this newly owned SDK instance. Callback
cleanup must not throw account/provider text into SDK diagnostics.

The metadata handshake and selected primary download share the original10-second
SDK request budget. Only the selected account's download-end marker can complete
that synchronization. The worker retains its event-loop/connection ownership,
queue/time bounds and final cleanup. No automatic reconnect or read retry is added.

SDK raw wire/provider diagnostics are suppressed only on the owned instance;
global application logging is unchanged. Application-safe failure codes and
numeric connection events remain available. Evidence and tests use synthetic
identifiers; actual account data and credentials do not belong in public logs.

## Authority and evidence limits

Low-level connection has no wire permission equivalent to `readonly=True`.
TWS Read-Only API must remain enabled and every application SDK submit/cancel
boundary remains unconditionally closed. A sole-account match and Paper banner
do not independently establish account environment, complete history, balances,
strategy ownership, reconciliation or execution authority.

Installed SDK/decoder tests use an in-memory transport with real socket/DNS
attempts forbidden. They must cover handshake ordering/fragmentation, rejected
account scopes before financial sends, selected completion, shared timeout,
upstream health loss, implicit refresh denial, sticky scope changes, privacy and
cleanup. Current source additionally needs affected backend/package validation;
historical d5aa CI/image evidence remains scoped to its own bytes. No new actual
Paper or full Goal acceptance follows from offline tests.

Any private app recovery needs a freshly reviewed preservation/schema plan and
applicable owner approval. Current code requires schema0020; startup never
migrates it. The prior boot-bound0019 recovery helper cannot be reused unchanged.
One further actual read needs its separately scoped approval and normal owner
authentication/consent. Orders, live trading and a forward campaign remain outside
that read authority. Laptop24h/temperature/clock work stays deferred to the final
computer.

SDK references: [2.1.0 source](https://ib-api-reloaded.github.io/ib_async/_modules/ib_async/ib.html),
[public Client API](https://ib-api-reloaded.github.io/ib_async/api.html#client).
The installed pinned implementation and actual in-memory tests determine
compatibility; documentation alone is not an external connection result.
