# Read admission, authority and private errors

The remaining-work audit found native read paths bypassing bounded admission and
retained adapters publishing raw SDK failures. The synthetic reproductions are
`evidence/read-admission-before-v3-20261014.txt` (four failures) and
`evidence/portfolio-revocation-before-20261015.txt` (two failures/seven passes).
Interrupted sandbox runs are environment diagnostics, not additional defects.

## Budgets and worker ownership

Synchronous market/tool and scheduled snapshot reads share four dedicated workers;
HTTP portfolio and account/history tools share two dedicated broker-query workers.
The legacy combined RSS reader has one dedicated worker. Admission is immediate:
saturation returns an unavailable/busy state rather than queuing more work.
These per-process bounds separate native reads from the event loop's shared
executor and from deterministic halt controls.

The await deadline is30seconds. This allows ordinary minute-scale monitoring to
abstain when a provider stalls; it grants no trading mandate or provider freshness
guarantee. Fixed slots fit the measured eight-core/16-logical-thread host while
leaving CPU-model and control capacity. Native work keeps its slot after timeout
or caller cancellation until it actually returns. Python cannot force-kill a
native thread; persistent busy states are truthful and require provider/process
diagnosis, not an unbounded retry queue. Context propagation preserves ownership.

Alpaca's locked SDK has no public transport-timeout option and ignores a zero
retry constructor value. An installed-SDK-tested compatibility subclass supplies
5-second connect and10-second read-inactivity timeouts and disables rate-limit
retry/sleep, preserving Session/auth/TLS/response handling. Each short-lived read
closes its Session in `finally`, including failure. These transport limits are
not a total deadline; a responsive streaming peer can outlast an inactivity limit.
Closed external-write guards are unchanged.

## Result authority and disclosure

The portfolio endpoint reloads selected account/configuration scope and rechecks
session/user authority after native work returns. Revocation, owner changes,
account deactivation and configuration changes deny publication of stale private
results. Tool requests retain their existing before/after authority checks.

Provider failure messages are untrusted. Alpaca/Coinbase/Binance reads, portfolio
aggregation and dispatcher failures return fixed safe codes and unavailable states.
No raw exception/traceback is copied to logs or responses. Binance symbol reads
preserve successful orders alongside safe partial errors; all-source failure is
not an empty success. The shared helper retains only explicitly allowlisted whole
codes. This does not hide a provider failure or grant a missing capability.

## Source permission and unsupported market answers

Yahoo market/FX reads now require independent exact-boolean opt-in
YAHOO_MARKET_DATA_ENABLED=true; default false. Historical research permission
does not enable market reads or vice versa. Guards precede provider/technical
analysis imports and client calls, including scheduled refreshes. Existing
central-bank reference behavior is unchanged. The market panel explains missing
source permission. Default and native market-only chat workflows abstain before
asking the model to generate prices when their market read is unavailable.
Unrelated mixed workflows retain their existing independent evidence behavior.

## Final validation

- Full unit:802 passed27.65s
  ([output](evidence/read-final-unit-v2-20261015.txt), matching exit0).
- Isolated PostgreSQL:374 passed128.32s
  ([output](evidence/read-integration-v2-20261015.txt)); new marked test database
  identity/cleanup verified in read-final-validation-databases-20261015.json.
  Later pure chat abstention changes are covered by42 focused tests/full units
  and the final browser; unchanged database integration evidence is reused.
- Clean unmodified Chromium/PostgreSQL workflow passes all original assertions
  plus unavailable-market UI assertion, no unexpected console errors, and owned
  database cleanup: [output](evidence/read-browser-v4-20261015.txt),
  read-browser-v4-database-20261015.json. Exact existing .qa/playwright1234 cache
  supplied the browser; no download was needed. Browser-v3 once stalled at the
  original five-second expense import assertion. No import POST appeared; cause
  remains unknown. Both file-read diagnostic and complete instrumented workflow
  passed, then clean v4 passed. Failed artifacts remain; no import threshold
  or expense application behavior was changed.
- Actual same-process CPU-model/control overlap passes1,362 halt requests,
  p95 52.833ms against250ms, with owned database cleanup:
  [result](evidence/read-control-contention-20261015.json).
- Final locked image investment-assistant:read-abstention-20261015,
  SHA25619c1f19807c99b599e80d5f29dda60618d440f7d86cfcbb2ee11695b528d8753,
  builds and matches the complete179-file copied set. Actual model/database
  readiness, migrations and persistent halt after app/database restart pass
 7.033s/1.104s against15s. Independent cleanup found no owned resources.
  [Source comparison](evidence/read-final-source-match-20261015.json),
  [runtime](evidence/read-final-container-runtime-20261015.json) and
  [cleanup](evidence/read-final-container-cleanup-20261015.json).
- All touched Ruff/compile/diff checks pass. The initial network-disabled build
  failed at a dependency-cache miss; later locked builds pass. Both logs remain.

One baseline test accidentally invoked an unmocked Yahoo FIXTURE lookup; retained
output did not preserve its returned mapping. Connection/data retrieval outcome
is unknown. The corrected test and all subsequent provider tests mock or deny
provider imports. CHECKPOINT.md records the incident and commentary correction.
There were no broker connections/orders or production deployment. The exact
23-file source/test bundle was subsequently published with user approval as
4e62b88; CI38717676258 now passes all four jobs and the combined Sonar gate.
Remote802unit/374PG/1180combined tests pass; combined browser coverage83.93%.
See read-published-ci-test-summary-20261015.json and retained rawJUnit/coverage.
Live trading remains OFF. The final candidate now has its own verified continuous
24-hour window:86,400.165s,3,060 samples,93 restarts,zero failures,halt p9529.102ms
against250ms and maximum restart4.046s against15s. All72 fixed CPU-model answers
pass independent parsing. [Terminal review](evidence/soak-24h-read-final-20261015-terminal-review.json)
and [scope/limitations](SOAK.md) distinguish it from the previous candidate's pass.
Mapped cooling, verified external Paper lifecycle and permitted research data
remain incomplete; the engineering soak does not establish investment edge.
