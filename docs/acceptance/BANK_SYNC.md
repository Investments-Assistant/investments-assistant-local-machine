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
access/credentials, an approved HTTPS callback, and independent bank consent. Browser connection setup and account selection are fixture-tested below. Institution
identifiers are entered explicitly; real eligibility/discovery and consent remain
external gates. These controls do not constitute a verified real-bank connection.

Export, retention, pagination, category overrides and changed-identity resolution
are implemented and tested (see below and RETENTION.md). Missing records are never silently treated as deletions. Generic
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


## Explicit changed-identity resolution (2026-10-06)
The current [transaction field schema](https://docs.gocardless.com/docs/bank-account-data/output-transaction-details)
identifies optional bank `transactionId` and provider `internalTransactionId`; it does
not establish a stable pending-to-booked relation. The adapter does not guess a link
from equal amounts, merchant text or dates. Missing entries still are not deletions.
The owner can now select a pending and a settled entry from the Expenses table,
review and download their normalized export, and independently confirm the pair.
Same owner/provider/account/currency/type are required; unknown transfer direction
or conflicting category overrides blocks resolution. The preview binds both rows,
raw-copy digests and export for10minutes; changed data/owner/export/expired/replayed
plans fail. An owner import lock and row locks make deletion, identity suppression,
minimal audit linkage and optional category-override transfer one transaction.
The booked amount, date and provider-receipt clock stay unchanged. The old pending
entry is removed; all imports matching its identity remain blocked by the retained
hash. This is an explicit owner declaration, not provider-confirmed matching. Saved
reports/chat/backups are separate; the confirmation explains that boundary.
Existing category editing also preserves the provider-receipt clock; user edits
are not evidence of new bank data. API receipt metadata is explicit per record.
Preview/apply require active browser cookie + CSRF; no model or scheduled resolution
path exists. Work is bounded to two rows,10s request/5s SQL/2s lock wait.
Fixture evidence: expense-reconciliation-fixed.txt19PASS; concurrency.txt11PASS;
browser-expense-reconciliation.txt desktop/mobile; pending-recovery-20261006
31table0018 restore retains resolution/category/receipt/audit and suppresses re-import.
All data is synthetic; no bank request/consent was performed. The ordinary seven-day incremental overlap does not discover older revisions.
The explicit retrieval below addresses that limit without claiming complete live synchronization.


## Explicit older-history retrieval (2026-10-06)
For an already consented selected account, the browser owner chooses a start date
and clicks Retrieve older history. POST /api/banks/{id}/history requires active
browser authentication, CSRF, configured provider access and owned connection;
the adapter rechecks consent and account identity before retrieving any records.
The local request bound is 730 days (not a promise of provider coverage), 5,000
records, a 2 MB response, 30 seconds of provider work and a 40-second endpoint
budget, with bounded SQL/lock waits. Provider consent/history limits still apply.
No automatic wider rescan, fuzzy identity matching or implied deletion is added.
A request exceeding the record bound fails explicitly without advancing success.

Returned corrections use the same atomic upsert, category-override preservation,
retired-identity suppression and durable backoff as ordinary polling. Missing
records remain unchanged. Invalid batches do not change the successful checkpoint.
The last successful requested date, retrieval time and record count persist across
ordinary polls, with coverage_verified=false; they establish what was requested,
not that the provider returned all history. Manual requests preserve the incremental
cursor: requesting only today cannot skip an older polling backlog. A first manual
request also does not suppress the initial normal 90-day retrieval. A failed manual
request must be retried explicitly after backoff; it is not silently queued.

Evidence: bank-history-reproduction.txt four failing new cases before implementation;
bank-history-cursor.txt 12 PostgreSQL/MockTransport tests pass, including a correction
absent from the seven-day result but returned by the selected wider request, range/
owner/inactive/disconnected guards, backoff, invalid-batch atomicity and cursor safety.
browser-bank-history.txt verifies the date selection, retry/success/disabled controls,
truthful coverage, real API CSRF/configuration denial and all retained workflows.
No real bank connection, credentials, institution consent or external request occurred.
