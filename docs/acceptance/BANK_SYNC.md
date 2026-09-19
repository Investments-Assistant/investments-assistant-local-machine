# Bank-data boundary and remaining external gate

GoCardless contract was checked against its current
[quickstart](https://docs.gocardless.com/docs/bank-account-data/quickstart-guide),
[endpoints](https://docs.gocardless.com/docs/bank-account-data/endpoints), and
[statuses](https://docs.gocardless.com/docs/bank-account-data/statuses-and-error-code)
on 2026-09-08. Published API documentation is available; this does not establish
this user's eligibility, free allowance, credentials, or institution access.
HTTP 402 produces an explicit decision-required error and never buys access.

`expenses/providers.py` implements the token/refresh, consent requisition,
linked-account verification, and account-transaction contract. Fixed HTTPS origin,
validated UUID paths, disabled redirects, 10-second requests, 30-second work limit,
2 MB responses and 5,000 records bound each operation. Remote error bodies are not
logged or returned. No payment/transfer API or bank-password field exists.

`expenses/provider_sync.py` binds one connection to an authenticated user and one
explicitly selected account. Credentials, requisition/account IDs and consent
reference are Fernet-encrypted using a separate BANK_CREDENTIALS_KEY. The browser
uses opaque account handles. Local disconnect removes the encrypted token and
stops polling; it truthfully does not claim provider-side consent revocation.
Reconnect replaces consent for the same account, preserving its prior checkpoint.

Polling has a durable per-connection lease and checkpoints. A successful fetch
atomically upserts all normalized records and advances the cursor. Seven days of
overlap permit revisions; first retrieval requests 90 days, subject to institution
limits. Account IDs plus provider IDs isolate deduplication. Category overrides
survive revisions. Invalid batches leave the last successful checkpoint untouched;
429/backoff persists across process restarts. Consent expiry requires reconnection.
The polling default is six hours, not a provider freshness promise.

`GET /api/banks` reports receipt and successful retrieval timestamps separately.
The successful retrieval time is not the bank's source-data as-of time. Imports do
not advance provider synchronization state. Expense SSE validates session authority
before emitting data. Expense data is not a model tool or a source of trading
capabilities.

No provider network request occurred during implementation: tests use synthetic
httpx responses and real disposable PostgreSQL. External access defaults disabled
(`BANK_SYNC_ENABLED=false`). Enabling it requires separate authorization, provider
access/credentials, an approved HTTPS callback, and independent bank consent. UI
connection setup and institution discovery remain to be completed; current API
routes prepare the workflow but do not constitute a verified real-bank connection.

Known limits needing further local work: exports/retention, browser pagination and
category editing, source last_updated handling, reconciliation of a pending item
whose bank changes its identity when booked, and correction/deletion outside the
bounded overlap. Missing records are never silently treated as deletions. Generic
imports accept explicit revised/deleted lifecycle states. Canonical absolute
amount plus signed exact amount in reviewed metadata preserves transfer direction;
legacy rows without that evidence show unavailable signed amount.

## Browser controls and timestamp semantics

The Expenses view displays configured/disabled provider access and owner-scoped
connection status. Starting/renewing consent requires an explicit button action;
the returned HTTPS GoCardless link opens only when the user follows it. Account
selection uses opaque consented handles. Stop local synchronization removes local
tokens and explicitly does not claim provider-side consent revocation. No bank
password is collected. Consent credentials missing from configuration keep the
start/renew buttons disabled; existing connections can still be inspected.

Expense polling reports the latest application receipt independently of the
selected period/page, and the latest completed provider retrieval across owned
connections, including successful empty batches. Manual imports do not advance
provider success. Each connection shows its own timestamps and errors; one recent
success does not imply that every connected account is current. Provider events
carry both receipt and success timestamps and trigger an authenticated refresh.

Validation: `evidence/bank-sync-clocks.txt` contains 12 passing targeted tests,
including real PostgreSQL ownership/empty-batch/manual-import clock assertions.
`evidence/browser-bank-status.txt` verifies real disabled-state rendering. The
extended browser harness uses intercepted synthetic bank responses for consent,
account selection, rejection/retry, renewal, local disconnect and mobile layout;
these UI checks are separate from fixture HTTP adapter tests and establish no
actual bank connectivity or consent.
