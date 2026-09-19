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

Remaining work is explicit: source licensing/retention policy, syndicated-copy
corroboration grouping, complete source/entity quality review, freshness observations
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
