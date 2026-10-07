# Public news ingestion and evidence

Scheduled ingestion requires `NEWS_SERVICE_USER_ID`, an explicitly provisioned
active application principal. Missing identity returns `NEWS_PRINCIPAL_REQUIRED`
before any fetch. Interactive ingestion uses the authenticated tool principal;
neither path infers an administrator or accesses global brokerage credentials.
Public article visibility remains public; leases and operational alerts are scoped
to the chosen principal. Newsletter ingestion has its separate explicit private owner.

`src/news/runtime.py` uses existing PostgreSQL job leases for each RSS URL, scraper
site and optional Guardian section. Network work occurs outside DB transactions.
Before publication, the worker locks and validates its lease token/expiry and active
principal. Article revisions and successful checkpoints commit atomically. Expired
or superseded workers cannot publish. Cancellation leaves the lease to expire.
A worker cannot safely retry merely because an HTTP caller stopped waiting.

RSS checkpoints retain bounded ETag/Last-Modified validators. Conditional requests
reuse stored article evidence on304, without inventing new availability timestamps
or duplicate revisions. Empty successful feeds remain valid checkpoints. Scraper
and Guardian adapters currently use source-level intervals/backoff without HTTP
conditional caching. There is no disk cache of raw responses or API-key URLs.

Failed sources retain successful validators and success time, increment bounded
retry metadata and emit a deduplicated local alert. Retry delay starts at300s,
doubles to at most24h and respects bounded provider Retry-After guidance. Both
numeric delay and HTTP-date are parsed; malformed guidance does not bypass local
backoff. Existing failure remains visible as `retry_wait` during backoff. Successful
recovery clears the source failure metadata; alert acknowledgement/resolution remains
an explicit in-app action. RSS and async API/scraper fetches share two admitted
workers; native timeouts retain capacity until actual worker completion.

Protocol basis: [RFC9110 Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#name-retry-after)
and [304 conditional responses](https://www.rfc-editor.org/rfc/rfc9110.html#name-304-not-modified).
The transport still enforces public HTTPS, pinned DNS, redirect revalidation, bounded
bodies and deadlines. No provider calls were made during these fixture checks.

Evidence:

- `evidence/news-durable-first.txt`: 51 targeted tests, including real PostgreSQL
  committed checkpoint/revision reuse, concurrent ownership, stale fencing and
  rollback on checkpoint failure.
- `evidence/news-durable-retry.txt`: 65 tests including HTTP retry bounds, explicit
  identity, source/correction ownership and availability-aware retrieval.
- `evidence/suite-durable-news.txt`: 403 unit/PostgreSQL tests before final retry-wait
  presentation refinement. `news-durable-production-settings.txt` covers those final affected paths (46 PASS);
  preceding orchestration failures exposed the inherited MagicMock interval and are
  retained. The fixture now uses actual production-like Settings.

Subsequent sections implement source policy/retention and exact-copy grouping.
Remaining work includes edited/translated-copy grouping, source/entity quality review, freshness observations
against actually configured permitted feeds and broader market/news-job integration.
Catalog existence does not prove a feed is currently available or licensed for every
use. Historical publication alone never proves that evidence was available to trade.
The synthetic research conclusion remains INSUFFICIENT EVIDENCE.

Metadata-only corrections now append immutable news revisions, including changed
source attribution, licensing/retention/entities and sentiment. The text hash
remains a text hash; first-seen time remains fixed, while correction availability
uses its actual observation time. Repeated identical metadata does not create
another revision. Test evidence: news-metadata-revisions.txt (23PASS). These
metadata values remain attributed claims; they do not verify a provider license
or authorize storage/execution by themselves.

Persistent source policy is now enforced before public RSS/HTML/API fetching and
private IMAP reading. `NEWS_SOURCE_POLICIES` is an explicit JSON mapping; its empty
default returns blocked status instead of silently collecting catalog entries.
Each value follows [news-source-policy.schema.json](news-source-policy.schema.json):
policy ID, operator-reviewed permission basis, HTTPS terms reference, aware review
and review-due dates, transport, permitted text scope, text limit and retention days.
This is an operator attestation, never independent publisher-license verification.
No real permission declaration or source activation was made during acceptance.

Public keys are the exact runtime identities: `rss:<feed URL>`,
`scrape:<configured target URL>` or `guardian:<section>`. Public policies require
exact article hostnames; wildcards, credentialed/non-HTTPS URLs and unexpected
article hosts are rejected. Text retained is limited to headline, summary or full
text according to policy, with explicit omission markers. Adapters cannot grant
rights through their own metadata. Permission is checked again before publishing;
revocation or policy changes during fetch prevent persistence. Changed policies
invalidate old conditional-fetch validators and force a fresh representation.
Private policies use `transport=private_newsletter`, empty article hosts and a key
from `src.news.policy.newsletter_identity(settings)`, binding owner, mailbox,
server/port and sender filter without storing the password in the identity.
Changing that configuration requires a corresponding explicit policy. The private
reader has one native worker slot and a60s caller deadline; cancellation/timeout
retains capacity until native work finishes. No actual IMAP connection was made.

Declared stored policies also govern current read eligibility, including historical
research retrieval. Retention starts at immutable local `fetched_at`, never mutable
publication/correction time. Expired review or retention periods and malformed
policy timestamps/durations exclude the article from search/count/as-of queries.
The PostgreSQL16 parser uses guarded
[soft input validation](https://www.postgresql.org/docs/16/functions-info.html#FUNCTIONS-INFO-VALIDITY-TABLE)
so malformed declarations do not crash every query; fixtures cover invalid times
and numbers. Legacy unverified rows retain their existing explicit unverified
metadata and are not represented as newly licensed by this change.

This milestone is not physical expiration cleanup: expired text/revisions remain
on disk pending the bounded preview/confirm cleanup implementation. Previously
copied chat/report evidence and backups are separate retention scopes. Ephemeral
live-news read adapters are also distinct from this persistent-ingestion boundary.
Real publisher availability, permitted uses and source freshness remain external
validation work; no catalog entry was treated as proof of those facts.

Expired retained news text/revision cleanup is now implemented as an operator-only
command; no model tool, browser route or automatic schedule invokes it. Preview
one exact declared source and an explicit public or private-owner scope:

```sh
.venv/bin/python scripts/cleanup_news.py --public --source-identity 'rss:<configured-feed-url>'
```

For a private source, replace `--public` with `--private-owner <application-user-id>`.
Review counts and repeat with the returned `--as-of` and
`--confirm-sha256` values. The preview expires after10minutes and is bound to the
chosen source/owner and current article/revision contents. Public scope cannot
remove private rows, and private cleanup requires the selected owner to remain
active. At most20articles and1000revisions enter a transaction; excessive revision
counts refuse the operation instead of partially erasing an article's history.
SQL/lock/request budgets are5s/2s/15s. Missing/invalid policy declarations require
review and are not treated as an elapsed retention permission.

Confirmed cleanup removes article title/body/summary/source labels/tags/sentiment
and retained revision payloads, retaining IDs, URLs, original content digests,
availability clocks and explicit erasure digests. Normal ingestion is append-only;
this separately confirmed retention operation is the documented exception that
replaces revision text with a tombstone. It does not backdate a correction or
pretend erased evidence remains reproducible. Retired articles stay excluded from
current/historical queries even after clock regression, and normal ingestion
cannot recreate their text under the same URL. New permissions do not silently
undo a completed purge; restoring erased data requires a separate future workflow.
Report/chat/export/model-cache/backup copies remain separate retention scopes.

The CLI prints completion only after transaction commit. Evidence:
`evidence/news-cleanup-committed.txt` (24 PostgreSQL tests), including actual CLI
preview+confirm across separate committed transactions, complete revision removal,
private isolation, changed previews, capacity refusal and no silent resurrection.
Only synthetic test data was erased; no real source policy or cleanup was activated.

## Syndicated copies and evidence independence

`src/news/syndication.py` groups exact normalized substantive text (at least80
characters and12 whitespace-delimited words). Unicode compatibility and whitespace
normalize; numbers, punctuation and case remain significant. Prefer body over
summary. Short/headline-only observations remain attributed records, not presumed
copies. Identical supplied summaries mean identical observed text, not proof that
unseen full articles match. Edited/translated/near copies remain unresolved.

Ingestion stores the versioned fingerprint in provenance and immutable revisions.
Search, recent headlines and as-of retrieval recompute from their selected records,
including legacy rows, and collapse only within the bounded authorized result
batch. Each representative retains copy URL/source/hash/availability/revision
references. Cross-owner, expired and future rows cannot contribute to counts;
there is no global lookup. Ranking determines the representative, not inferred
publisher originality. Limits cap inspected records, so fewer distinct groups may
be returned and counts are not corpus-wide syndication totals.

Original records/revisions and article counts remain intact. Agent wrappers label
raw article counts explicitly; neither distinct URLs nor distinct groups prove
independent corroboration. Ephemeral market-news lexical sentiment now counts each
matching text group once, with an explicit non-trading-signal note. This does not
validate the lexical classifier or authorize a source. The on-demand fetch boundary is covered in the source-permission section below.

Focused evidence: `evidence/news-syndication-verified.txt` (21 PASS), covering
copies, numerical corrections, owner deactivation, private isolation, historical
availability and existing expiry/cleanup behavior. Initial collection failure is
retained in news-syndication.txt; duplicate unit/integration basenames corrected.

Final validation:556 aggregate tests PASS in suite-news-syndication-final.txt.
A subsequent fallback-fingerprint consistency fix (compute after canonical stored
URL/hash) passed47 affected news tests in news-syndication-fingerprint-final.txt.
The historical five search-mock failures remain recorded; fixtures now use actual
ORM text/null values. No publisher or private mailbox was contacted.


## On-demand source permission boundary

`src/tools/news.py` now requires the same operator-reviewed source policies before
RSS or NewsAPI network access. RSS identity is `rss:<exact feed URL>`; optional
NewsAPI identity is `newsapi:everything` and still requires its existing enabled
flag and explicitly configured key. Public transport and exact article hosts are
required. Permission is revalidated after each response; changed/revoked/expired
policies discard that source's batch. Returned summary/content follow the declared
scope, and both search matching and lexical sentiment use permitted text only.
No publisher terms were inferred from a reachable feed or configured API key.

Failures contain source labels and typed codes, never provider exception messages.
No matching articles after a successful fetch remains distinct from blocked/failed
sources. All-source failure returns `unavailable` and a null sentiment score;
mixed success returns `partial_failure`. The deterministic chat fallback preserves
that distinction. Missing credentials for the optional API means it is not attempted;
RSS fallback also needs its own permissions. This path remains an on-demand read,
not a claim of durable scheduled ingestion, licensed historical data or measured
provider freshness. Legacy raw adapter helpers are not application authority entry
points; the scheduler calls the fenced, scoped runtime.

Synthetic tests: missing/expired/private policy prevents any fetch, revocation
while fetching discards results, unreviewed article hosts fail closed, headline-only
permission cannot leak summary-derived matching/sentiment, provider errors are
redacted, and NewsAPI preserves descriptions when content is null. An initial
error-code precedence failure was corrected (`PolicyDenied` is a `ValueError`).

## Language and entity provenance quality

`src/news/quality.py` records source-declared language tags with
`declared_unverified` status; absent/malformed declarations are `unknown` and
unavailable. RSS carries an entry/feed declaration through ingestion. This is a
conservative tag-syntax check, not language detection or independent validation.

Source tags remain searchable, but provenance now calls them `source_tags` rather
than verified entities. Bounded structured `entity_mentions` distinguishes known
currency-code candidates from ticker candidates, always with unresolved mapping
and no qualified instrument. Tickers alone cannot supply account, exchange,
currency, conId or execution authority. Historical revisions retain their original
metadata; new metadata corrections append a revision without backdating first-seen
or changing the text hash. A verified entity/instrument resolver and broader
language coverage remain incomplete; this change makes that boundary explicit.

When permission projection omits/truncates text, source-derived tags and sentiment
are recomputed from the permitted title/summary/body only. Otherwise restricted
text could leak through a ticker tag or sentiment score even though the text was
removed. Omission metadata records that recomputation. Original input is unchanged.
