# IBKR cash observation boundary

The local candidate fixes a reproduced missing-data path. Account-summary ledger
rows may describe an aggregate rather than the selected account. The collector
previously ignored that aggregate correctly, but did not request the separate
selected-account cash update stream. A synthetic reproduction retained an empty
cash result despite available selected-account EUR/USD callbacks. This does not
establish what cash was present in the user's earlier actual read.

`src/tools/brokers/ibkr_balances.py` now resets only the selected account's read
subscription on the existing worker-owned connection. It captures primary
`updateAccountValue` callbacks after that request is sent and before the matching
`accountDownloadEnd`. It never promotes retained SDK cache data to a new
observation. The pinned SDK's Multi-account callback emits the same public event,
so capture uses the primary wrapper method instead of that shared event.

Completeness requires a matching account end, explicit true AccountReady and
valid currency cash. Foreign accounts and BASE aggregates are excluded. Values
retain exact Decimal precision; the map admits at most 100 currencies, repeated
keys replace their previous value, and conflicting source tags cannot be summed
or silently overwritten. Missing/invalid readiness, malformed values, conflicts
or overflow produce incomplete cash without fabricated zero balances. Native
request failures cannot become a completed cash snapshot.

Finally restores the exact prior wrapper/client attributes and stops the read
subscription. Cleanup cannot mask the original request failure. Because that
unsubscribe also stops portfolio-cache updates, a subsequent positions read on
the same persistent owner returns `IBKR_SESSION_NOT_READY` before accessing the
cache. It neither reconnects nor labels stopped updates with a fresh timestamp.

The [110 focused cases](evidence/cash-collector-focused-20261018.xml)
cover primary/Multi/foreign/end-marker interleaving through the installed SDK
decoder, request timing, native timeout, precision, capacity, readiness, cleanup
and persistent-owner cache denial. They are included in the full current-source
860 unit cases; a separate 392 PostgreSQL cases also pass. The
[backend review](evidence/cash-collector-backend-review-20261018.json) retains
source hashes, JUnit identities and guarded fixture cleanup. The
[new image review](evidence/cash-collector-image-review-20261018-5d8b5cb04c1b.json)
verifies all copied files, actual model load and persisted halts across restarts.
The [candidate review](evidence/cash-halt-publication-review-20261018.json)
records exact seven-file approval/publication as e154a0a; [current CI](evidence/cash-halt-ci-20261018.json)
allfourjobs/configuredSonar gate pass for that exact commit.

This change grants no authority and performs no order operation. Actual account
read permissions remain owner-disabled. The earlier single actual read remains
partial, non-atomic evidence with SDK-unverified environment and no execution
authority. No actual broker read was repeated to validate this fix. Full Paper
history, reauthentication, execution/reconciliation and an agreed forward plan
remain separate acceptance gates. Live trading stays disabled.
