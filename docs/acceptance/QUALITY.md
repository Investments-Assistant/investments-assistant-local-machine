# Quality and dependency review — 2026-10-11

Current status (2026-10-14): the user accepted the four reviewed findings. Sonar
records RESOLVED/WONTFIX and the quality gate is now OK, including 82.6% coverage.
These are accepted review decisions, not code fixes. The prior failed CI job is
rerunning at unchanged commit cd049bf. See [review outcome](SONAR_REVIEW.md).
Earlier failures and review proposals below are historical evidence.

Remote run38097627974 at5fefb1a authenticates and uploads successfully to Sonar.
696 unit tests pass; its quality gate fails reliability3/security4/newcoverage56
against unchanged thresholds1/1/80. Later test jobs are skipped. No remote issue
has been dismissed and no threshold/exclusion was changed.

## Published pipeline correction

Partial unit and integration scans previously overwrote the same branch analysis.
Their early gates could prevent the combined coverage run from being reached.
Only the combined job now scans and checks quality, after all three test tiers.
Missing SONAR_TOKEN fails its explicit preflight; test failures still block it.
Standalone unit/integration workflows now report their test tier only. Source:
[Sonar Python coverage](https://docs.sonarsource.com/sonarqube-server/analyzing-source-code/test-coverage/python-test-coverage).
Local YAML, bash syntax, required dependencies and missing-token checks are in
[evidence/ci-combined-gate-review.json](evidence/ci-combined-gate-review.json).
The user approved the exact15-file bundle, published as cd049bf. Remote38185591707
unit, integration and Chromium/ingress jobs pass; combined1086 tests pass; the mandatory quality gate fails on four remaining
findings documented in SONAR_REVIEW.md.

## Findings

- Six route log-injection findings reproduced with exception text containing a
  private value and forged newline. Fixed logs retain operation and exception
  type, omitting raw identifiers/exception messages.35 focused and702 unit tests
  pass. The same pattern in other route failures was corrected too.
- S4830 at public HTTPS construction: ssl.create_default_context() enforces
  certificate and hostname verification. Actual local TLS tests accept trusted
  matching hostname and reject wrong-hostname/untrusted certificates; production
  code unchanged.20 TLS/public-fetch checks pass. Candidate false positive for
  authorized Sonar review, not silently suppressed. See
  [Python TLS defaults](https://docs.python.org/3.12/library/ssl.html#ssl.create_default_context).
- S3330: ia_session is HttpOnly; ia_csrf is intentionally readable for the
  double-submit request header. Both are Secure and SameSite=strict in production.
  A production Settings regression verifies CSRF cannot authenticate, absent or
  mismatched headers fail403, matched headers pass. Browser CSRF/isolation checks
  also remain required. Remote finding needs contextual review; no cookie policy
  was weakened to satisfy a scanner.
- Two S2583 dispatcher findings: _live_route_allowed deliberately always returns
  False. This blocks retained legacy SDK routing for orders and cancellation.
  Real Settings regression verifies even live_trading_enabled cannot authorize
  either call. Do not enable that path to remove an unreachable-code warning.
  Adapter contract tests stub this guard only with mocked SDKs. Remote reliability
  findings remain open pending review; no new execution authority exists.

## Dependency work

PyJWT2.12.1 empty HMAC JWK accepted before repair (3 failing tests); targeted
hash-locked2.15.1 upgrade makes all3 pass. A further mutable-options/expired-token
regression passes. No application uses PyJWT to authenticate browser sessions;
retained broker/MCP dependencies still warranted the update. Reference:
[upstream empty-key advisory](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-pxh4-856f-4h89).

Fifteen packages have reviewed lock updates. After publication and a successful
Dependency Graph run, a read-only GitHub query finds1 open medium diskcache alert,
down from81; no alerts were manually dismissed. The final23-flow local browser run,
remote710 unit/372 integration tests and updated Docker build/runtime/ingress pass.
The separate local host-clock failure remains documented below. MCP remains on
supported1.x (>=1.28.1,<2) to preserve the current bridge API, following
[upstream support policy](https://github.com/modelcontextprotocol/python-sdk/blob/main/SECURITY.md).
WeasyPrint70 is required by its
[security release](https://github.com/Kozea/WeasyPrint/blob/main/docs/changelog.rst).
Exact package deltas: evidence/dependency-security-changes.json.

The diskcache advisory has no patched version in the current repository alert:
unsafe pickle reads require attacker write access to the cache. It is a
llama-cpp-python dependency; this application's source never constructs a disk
cache or calls set_cache. Do not expose/load untrusted cache directories. Keep
this residual advisory explicit; no upstream fix or closed GitHub alert claimed.

Three alerts have no patched-version floor in the saved metadata. PyJWT options
mutation is covered by the passing expired-token/options-preservation regression
on2.15.1. WeasyPrint presentational-hints injection requires that feature enabled;
this application does not enable it and escapes untrusted Markdown/HTML before
rendering. Diskcache exposure is described above. These are contextual assessments,
not claims that every upstream advisory is fixed. The later repository query
records80 automatic closures and1 remaining diskcache alert.

## Clock evidence

The first current coverage/browser attempts failed on clock/quote/lease boundaries.
clock-quality-probe.json captured a backward wall step1.3107s versus forward
monotonic0.0104s. This supports a clock-related explanation but does not establish
the exact cause of every earlier failure. The later20.623s probe saw no jumps;
browser-security-coverage-v2 passes. Production clock/lease safeguards remain
unchanged. The following full backend run records six backward wall steps during211.4s.

## Browser coverage

The instrumented server executes1106 main-route and194 simulator-route lines
(browser-coverage-measurements.json). Coverage subprocess instrumentation preserves
normal server startup/termination; the workflow downloads this mandatory artifact
and combines it with the backend measurement before Sonar. Source:
[Coverage process measurement](https://coverage.readthedocs.io/en/7.13.5/subprocess.html).
No coverage exclusions or quality thresholds were broadened.

## Latest validation boundary

Current15-package dependency set:710unit +371integration +4other checks PASS;
one integration cancellation/recovery case failsSTALE_JOB_LEASE. The concurrent
clock monitor captured six backward steps~0.54–0.63s. No guard was relaxed.
The final browser-security-coverage-v3 run passes all23flows on both viewports,
including real PDF generation and session/CSRF/isolation checks. Localcombined
linecoverage82.68% includes measured browser routes; no remotequalityPASS claimed.
A separate60s probe saw no regressions, which does not invalidate the earlier
under-test clock failures. Reproduce bounded clock observations with:

```sh
.venv/bin/python scripts/verify_clock_stability.py --seconds 60 --output .qa/clock-new.json
```

Use a new output filename. The command only reads time and writes its report; it
returns1 on backward wall steps. Docker was restored; updated-image build, native
smoke, real-GGUF startup/restart and ingress checks pass with owned cleanup.
Remote710 unit tests pass in25.039s and372 integration tests in149.654s; no
failures/errors/skips in their JUnit artifacts. The23-flow Chromium and8-check
Nginx jobs pass. The combined suite passes1086 tests in165.877s without failures/errors/skips;
measured combined linecoverage is82.63%. Sonar analysis/upload succeeds and newcoverage82.6% passes. The mandatory gate
still fails on four remaining security/reliability findings; see SONAR_REVIEW.md. See
evidence/remote-ci-38185591707-test-artifacts.json and
evidence/container-runtime-security.json. No trading, production deployment,
OS configuration or remote Sonar issue state was changed.

CI verification complete: run38185591707 attempt2 atcd049bf finishedSUCCESS, including the mandatory Sonar quality gate. Fresh combined1086testsPASS167.652s; allfourjobsSUCCESS. L11PASS. Accepted findings remain documented decisions, not code repairs; other physical/external/research gates remainopen.

## Current local candidate — 2026-10-13

After migrating the IBKR adapter to `ib_async==2.1.0`, the local candidate
passes719 unit tests and374 full PostgreSQL integration tests. The updated
Docker image builds and passes a network-disabled, non-root package/adapter
import smoke. See `evidence/ib-async-migration-20261013.txt` and
`evidence/container-build-ibasync-20261013.txt`. Remote run38478734435 for
published candidate `1d01bb5` has unit, PostgreSQL integration, and
Chromium/browser jobs passing; the combined Sonar quality gate remains in
progress. The build's yanked `soupsieve 3.0.1` warning is documented in the
container evidence; the image runtime is Python 3.12 and both build and import
smoke pass.


## Published IBKR migration CI — 2026-10-14

GitHub Actions run [38478734435](https://github.com/Investments-Assistant/investments-assistant-local-machine/actions/runs/38478734435) for `1d01bb5517d5f1a7424efd9daca766223850a2df` completed `success`; unit, PostgreSQL integration, Chromium/browser and combined Sonar quality-gate jobs all succeeded. Downloaded artifacts report717 unit tests,373 integration tests,1,094 tests in the combined E2E-tier report (overlapping tiers; do not sum as unique), and82.63% combined line coverage. This validates the published SHA, not the remaining unpublished local work.
