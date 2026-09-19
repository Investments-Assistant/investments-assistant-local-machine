# Durable chat turns and evidence

`src/chat/persistence.py` creates owner-scoped user/assistant records before model
work. The assistant record starts in_progress. Each tool call/result is snapshotted
before it is streamed. A final_answer/done event is emitted only after the answer,
evidence and complete status commit. Model failure persists failed status; cancellation
records interrupted status where storage remains available. If storage fails, the
client receives an explicit error rather than a saved-answer claim. An abrupt
process death may leave in_progress, which the UI labels unfinished on resume.

The existing ChatMessage.tool_calls column stores schema-versioned evidence; no
migration or ownership backfill is required. Completed/failed/interrupted turns
cannot be edited through this service. Conversation/turn queries always bind the
authenticated owner. The separate evidence download is authenticated, no-store and
cross-user denied. Legacy messages retain their prior representation.

Snapshots retain at most32 events and16KiB per event. Credential/nonce/IBAN/account-
secret fields are redacted recursively; URL credentials, queries and fragments are
removed. Larger/deeper data carries explicit omission markers and redacted hashes.
This is structured-field redaction, not a guarantee that arbitrary free text contains
no sensitive information. Snapshots are private user data, not public logs or an
approval capability. Expense/bank scope is not added to model tools.

Restored conversation context includes bounded historical evidence and a warning
that remembered proposals/model text do not establish broker submission/fills.
Beyond8KiB it carries the owned evidence reference and missing-context notice; it
never slices serialized JSON into invalid text. The same rule applies within a
continuing session. Profile context also preserves JSON structure under its budget.

Evidence: `chat-evidence-first.txt` (four real PostgreSQL behavior tests),
`browser-chat-evidence.txt` (real Chromium download/reload/isolation plus existing
workflows), and `suite-chat-evidence-final.txt` (**412 unit/PostgreSQL PASS**).
Initial suite-chat-evidence.txt records a test-module basename collision, corrected
by renaming the unit module to chat_evidence_bounds_test.py without removing tests.
Retention policy and full operational log review remain separate unfinished work.

Owned inactive-chat retention is implemented in `src/chat/retention.py` and the
browser **Chat retention** controls. The owner chooses an inactivity age and
separately approves a content-bound10-minute preview. No automatic age/schedule is
selected. Batches cover at most20conversations/500messages. Recent, other-owner,
unknown-owner/orphan conversation data and any conversation with an in-progress
turn are excluded. An interrupted process can leave an unfinished turn excluded;
this workflow does not guess that the turn is safe to erase.

The transaction removes message text/tool payloads and conversation titles,
retaining message/conversation IDs, owners, dates, project associations and digest
metadata. Assistant evidence URLs return an explicit `retired` tombstone with an
empty evidence array. UI reload labels it “Content removed by owner”; user-message
tombstones do not link to assistant-only evidence endpoints. Source financial
ledgers, report copies and backups are separate retention scopes. Existing explicit
whole-conversation deletion remains a distinct permanent-delete operation.

Append, save, owner deletion and retention lock conversations before messages.
A confirmed plan rechecks active state and hashes under these locks. A real
PostgreSQL test observed retention waiting on a concurrent conversation writer,
then rejected the stale preview after the new turn became active; old content was
not removed. Multi-batch cleanup preserves activity clocks so remaining approved
content can be previewed again without fabricating new user activity.

An open orchestrator refreshes its owned DB history after committing each new turn;
retired and in-progress assistant rows are excluded from model context. A failed
read clears cached history and blocks inference instead of reusing private stale
content. This is application-level retention, not a claim of secure RAM, disk,
provider, downloaded-export or backup erasure. No provider/chat text was transmitted
outside the existing authorized local inference path.

Evidence:17 focused checks in `evidence/chat-retention-concurrency.txt`, including
fresh-context and fail-closed history regressions; real Chromium UI confirmation,
CSRF/foreign-owner denial, tombstone download/reload and second empty preview in
`evidence/browser-chat-retention.txt`. Only synthetic chat content was removed.
