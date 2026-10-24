# Offline broker submission journal

## Scope and evidence status

This is a durable **offline fixture contract**, not a broker execution feature.
The implementation is in [broker_submission.py](../../src/execution/broker_submission.py),
with [journal models](../../src/execution/broker_submission_models.py) and
[migration0020](../../migrations/versions/0020_broker_submission.py). There is no
runtime transport implementation, public route, tool or scheduler integration.
All retained SDK submit/cancel entrypoints remain unconditionally denied, including
under a synthetic true live flag. Read consent is a binding safeguard, never write
consent. The contract supplies no independent approval, mandate, cash reservation,
pretrade risk/quote/contract verification, strategy ownership or execution authority.

The owner explicitly keeps actual external Paper L04/L15 and research L14 **OPEN**.
Live trading stays OFF. The laptop24h/CPU-temperature/clock work is deferred to the
actual final computer; see [final-host handoff](FINAL_HOST_HANDOFF.md). This offline
implementation neither completes those gates nor establishes investment edge.

The22Oct frozen candidate passed [119 focused cases](evidence/paper-submission-focused-20261022.json)
and the [full local backend tiers](evidence/paper-submission-backend-20261022.json):
907 unit and431 PostgreSQL cases, with no failures/errors/skips and unchanged
source/tests throughout those full runs. The published journal commit `a2b2f42` also passes
[image/runtime checks](evidence/paper-submission-image-review-20261023.json) and
[exact-commit CI/Sonar](evidence/paper-submission-ci-20261023.json). These results
validate the published bytes. The later six-file lost-acknowledgment correlation
candidate described below has [local backend evidence](evidence/paper-recovery-backend-20261023.json)
and [new image build/smoke evidence](evidence/paper-recovery-image-review-20261023.json).
The exact six-file patch is now [published asd5aa99e](evidence/paper-recovery-publication-20261023.json).
[Current-commit CI/Sonar39983987095](evidence/paper-recovery-ci-20261023.json)
passes allfourjobs,920unit/459PG/1383overlapping combined cases,24browserflows and
8actualTLS/WSS checks. No new fullmodel/runtime execution is claimed. Actual external Paper remains OPEN.
The initial combined collection attempt hit a duplicate test basename; the
integration file was renamed to `broker_submission_journal_test.py` before rerun.
Published e154 CI,860-unit/392-PostgreSQL and amd64-image proofs remain historical
for their recorded inputs and do not validate this new service/migration. Use the
[checkpoint](CHECKPOINT.md) for subsequently verified results and candidate scope.

The [independent0020 durability review](evidence/paper-submission-durability-20261023.json)
verifies an actual owned PostgreSQL restart and a new journal object that preserves
the uncertain attempt without resending. Both source and restored databases match
the retained inventory for all33public tables/17rows, including the same one intent,
three events, attempt/request/row hashes and unknown permanent ID. This is local
**database-only PASS**: no Python application-process restart was exercised, the
ephemeral fixture vault key was not recovered, and the restored copy was verified
by read-only SQL/hashes without decryption or dispatch. It does not close actual
Paper, final-host, image or current-candidate CI gates; private data was untouched.

Reviewed service SHA256:
`ed9302d64f064cd6fa476a410a1d0a1840bf372f148d81d2cb27637a6518479b`.
Further changes require reviewing the new bytes and affected checks.

## Request and retained records

`SubmissionRequest` freezes declared Paper session/correlation identity, contract
ID, client/order IDs, STK/LMT, exchange/currency, side, quantity, limit, tick, lot
and multiplier. These are caller-supplied contract details, not independently
verified broker terms or financial approval. Integer IDs have strict positive/
nonnegative bounds; extra fields and authority claims are rejected. Exact monetary
inputs accept decimal text, `Decimal` or integers, reject floats/bools, and require
finite positive values below1e18 with at most10 decimal places. Quantity must
match lot and price must match tick. Canonical normalization gives equivalent
decimal representations the same request hash. Constructed model instances are
revalidated rather than trusted.

`broker_submission_intents` retains the owner, application account, hashed account
binding/full configuration, idempotency key, reserved client/order key, canonical
request/hash, state, attempt ID and optional permanent ID. Unique constraints scope
idempotency, client/order reservation and non-null permanent ID to application
account plus binding. These are local identities, not proof of broker-wide ownership.
`broker_submission_events` stores journal events with payload hashes and optional
links to retained observations. Event keys and linked observation IDs deduplicate
within an intent. Events are append-only through this service; this is not a
database-level immutable log or cryptographic proof against arbitrary DB writers.

Foreign keys retain the dependency on the user, account, intent and observation;
the migration adds no cascading deletion. Do not manually delete an uncertain
attempt, reset it to staged or edit hashes to make evidence agree. Retention or
destructive rollback needs a separate reviewed preservation/backup operation.

## State and transaction boundary

The journal accepts a bound `async_sessionmaker`, owns its transactions and rejects
a caller-owned session/transaction. Principal/account locks precede the intent lock.
Concurrent staging of the same idempotency key returns the same matching intent;
different request bytes or an already-reserved client/order identity fail closed.
Staging itself requires a positively verified disposable fixture and current scoped
read consent. It creates no real-account proposal or executable capability.

| State/result | Meaning |
|---|---|
| `staged` | Canonical fixture request and initial event committed; no handoff yet. |
| `handoff_started` | Attempt ID and handoff event committed before injected call. Public `state` is already `uncertain`; `journal_state` preserves this stored distinction. |
| `acknowledged` | Matching synthetic receipt with positive permanent ID; never a fill or current broker-state claim. |
| `rejected` | Matching synthetic rejection receipt without permanent ID; no automatic rearm/resend. |
| `uncertain` | Timeout, cancellation, exception, invalid/conflicting receipt, scope loss or explicit lost-handoff recovery; no resend. |
| default `blocked` response | No transport supplied: immediate `EXTERNAL_WRITES_NOT_AUTHORIZED`, before DB/credential inspection. It does not mutate an existing staged intent or append an event. |

Injected dispatch first proves the fixture and claims bounded process admission.
It locks/rechecks the selected intent, commits `handoff_started` and its event,
then re-proves fixture identity and rechecks scope before calling the synthetic
transport. The committed attempt is visible to an independent connection before
the call. A non-staged intent returns its retained state without another call.

Only the awaiting owner can persist a matching outcome. Recovery can change a
lost `handoff_started` to `uncertain`; it cannot submit, cancel, release a financial
reservation, infer a fill or grant another attempt. Late completion cannot overwrite
an already-recovered uncertain state. Persistence/commit failures propagate for
inspection rather than automatically retrying outcome writes or transport calls.

This is **not distributed exactly-once execution**. A process can die after commit
but before the call, or an external system could accept a future handoff before
its reply is lost. The conservative journal cannot distinguish these cases and
does not resend. Hashes/idempotency do not establish an external broker guarantee.

## Identity, revocation and callback review

Every scoped operation checks an active principal and owned IBKR application
account. The hashed binding includes owner, application account, actual selected
broker account and declared environment. Dispatch additionally requires active
account, exact enabled/read-authorized booleans, declared Paper, matching client
ID and unchanged full configuration hash. Rebinding to another account/environment,
cross-owner access or tampered/noncanonical request/hash/order key is denied.

Owned local history, recovery and linking use the retained binding without
requiring continuing read consent or unchanged endpoint/client configuration.
They still require the active owner, existing owned account, decryptable current
configuration and unchanged actual account/environment binding. This does not
authorize another external read. If consent/configuration changes during handoff,
the stale receipt becomes uncertainty rather than an acknowledgement. Principal
deactivation, rebinding, vault or storage failure can prevent the outcome write;
the committed `handoff_started` still exposes uncertainty and cannot be resent.

`TransportReceipt` accepts only acknowledged/rejected status and strict matching
client/order IDs. Acknowledgement requires a positive permanent ID; rejection
must not supply one. Conflicting permanent IDs produce uncertainty. No receipt
can claim a fill or verified Paper environment. Retained intent views carry
`execution_authority=none`, `environment_verified=null`, `retry_allowed=false`
and `complete_reconciliation=false`.

Execution/order-status links require an existing bound permanent ID plus matching
client/order IDs, same owner/account/binding, and a valid payload hash. Commission
links require an already-linked execution with the same hashed execution identity.
When a timeout/lost receipt leaves the permanent ID unknown, the journal explicitly
reports `permanent_id_unknown_no_callback_association`: it never guesses a match
from client/order IDs, amount, time or a candidate callback. The published `a2b2f42` journal has no recovery protocol for that unknown
identity. A bounded local follow-up is being verified: reuse the already-committed
random attempt UUID as a32hex opaque reference supplied to the synthetic transport,
retain its hash in the handoff event, and compare the hash of a later execution's
freshly decoded reference. No migration is needed. Existing handoffs lacking that
committed hash remain unresolved; no reference is retrofitted to history.

The follow-up resolver is fixture-only and requires the current active owner and
same actual account/environment binding, exact client/order and qualified contract
basis, valid retained hashes, and one positive permanent ID. It reviews bounded
same-binding candidate evidence and keeps truncation or contradictions sticky.
Later identity/contract conflicts invalidate the current correlation while retaining
all earlier linked facts. Missing references and cached order-status objects cannot
bootstrap a match. Successful correlation still leaves state `uncertain`, resend
forbidden, ownership/current state unestablished and execution authority `none`.

The reference is correlation evidence, never authentication. IBKR documents it as
[user-customizable through API or TWS](https://www.interactivebrokers.com/docs/tws-api/ref/execution).
The32hex format is an application convention, not a claimed broker size guarantee.
Only `Execution.orderRef` from decoded execution data is mapped; mutable
`Trade.order.orderRef` is ignored. No raw reference or account identifier is added
to retained observation/event payloads. These behaviors now pass172focused and920unit checks plus459distinct PostgreSQL
cases with passing executions; the original clock-sensitive full-tier failure and
one successful retry are retained. New image build/smoke and exactpublication now pass;
currentremoteCI passes a clean459-casePG tier. The earlier localfailure remains
preserved, with no clock repair or test weakening. This
does not close actual external Paper acceptance.

Stable identity permits retention of contradictory facts; it does not make those
facts correct. Review reuses the existing [callback reducer](../../src/execution/broker_review.py)
for duplicate/correction families, conflicting versions, pending fees and order
status conflicts. Request comparison flags contract/security-type/multiplier,
side/currency, buy/sell limit-price and cumulative quantity discrepancies. Missing
contract basis is explicit; corrected/conflicting executions are not summed as new
fills. Outliers stay retained and produce `needs_review`. No discrepancy-free result
establishes complete history, balances, strategy ownership or current broker state.

## Resource limits and their scope

Injected `submit` must be an async function and its await timeout must be finite,
greater than0 and at most30 seconds. Four process-wide handoff slots are shared
across journal instances. A task ignoring cancellation holds its slot until actual
completion; completed results/exceptions are consumed without publishing late
outcomes. Overflow fails before another handoff claim. This bounds cooperative
synthetic tasks, not arbitrary Python execution, total DB transaction latency,
native hard termination or fleet-wide concurrency. Only trusted offline test
transports may be injected; a marked database is not a sandbox preventing injected
Python from accessing a network. No real transport implementation is supplied.

Fixture verification checks exact bound asyncpg URL and `test_` database identity,
local loopback TCP or an absolute socket below this checkout's `.qa`, exactly one
matching marker token16–256 characters, schema0020 and a supported PostgreSQL
version. Its SQL checks use a5-second statement timeout. Marker/environment labels
alone are insufficient. The existing observation review reads at most1000 linked
observations and2MiB of payload, probes one extra metadata row and explicitly marks
truncation. Those technical limits are not financial risk/mandate limits.

## Explicit migration and reproducible tests

Prerequisite: prepare and positively verify a **new dedicated local disposable
test database**, its actual name, fresh single marker token, owner and transport.
Do not use the private operator database, production volume or any historical
cluster/run identity. Creation/marker setup is a separately reviewed fixture action;
no command below creates, resumes, migrates or cleans an old cluster automatically.
Metadata `create_all` in generic tests does not apply migrations or prove revision.

For this frozen source the required migration is `0020_broker_submission`, extending
0019. Resolve the checked-out head and strict guards again after later changes.
For the freshly verified fixture only, from the checkout root with the locked
compatible Python/Poetry environment and newly selected local variables:

```sh
DATABASE_URL="$APPROVED_DISPOSABLE_URL" poetry run alembic heads
DATABASE_URL="$APPROVED_DISPOSABLE_URL" poetry run alembic upgrade head
DATABASE_URL="$APPROVED_DISPOSABLE_URL" poetry run alembic current

poetry run pytest -q tests/unit/broker_submission_test.py

TEST_DATABASE_URL="$APPROVED_DISPOSABLE_URL" \
TEST_DATABASE_DISPOSABLE_TOKEN="$FRESH_MATCHING_MARKER" \
poetry run pytest -q tests/integration/broker_submission_journal_test.py
```

These commands grant no new infrastructure/deployment/credential authority. Never
put private credentials in command examples, evidence or chat. Existing private
databases need separately approved backup, restore/schema verification, explicit
migration and compatible rollback under the [runbook](RUNBOOK.md); application
startup does not upgrade them.0020 deliberately refuses destructive downgrade so
uncertain attempt evidence is not discarded.

The [unit definitions](../../tests/unit/broker_submission_test.py) cover exact input
and receipt validation, forged models, bound session factories and all denied SDK
write entrypoints. The [integration definitions](../../tests/integration/broker_submission_journal_test.py)
exercise independently committed visibility, concurrent claim/reload/idempotency,
fixture/scope denial, revocation, timeout/cancellation/crash recovery, late-result
fencing, bounded unfinished tasks, callback identity/deduplication, unknown permanent
IDs and retained request discrepancies. They use synthetic transports and their
own newly seeded records, with explicit scoped cleanup; they do not place orders,
verify a real Paper session or replace actual external lifecycle acceptance.
