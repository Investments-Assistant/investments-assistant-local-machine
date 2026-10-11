# Quality and dependency review — 2026-10-11

Remote run38097627974 at5fefb1a authenticates and uploads successfully to Sonar.
696 unit tests pass; its quality gate fails reliability3/security4/newcoverage56
against unchanged thresholds1/1/80. Later test jobs are skipped. No remote issue
has been dismissed and no threshold/exclusion was changed.

## Pipeline correction prepared locally

Partial unit and integration scans previously overwrote the same branch analysis.
Their early gates could prevent the combined coverage run from being reached.
Only the combined job now scans and checks quality, after all three test tiers.
Missing SONAR_TOKEN fails its explicit preflight; test failures still block it.
Standalone unit/integration workflows now report their test tier only. Source:
[Sonar Python coverage](https://docs.sonarsource.com/sonarqube-server/analyzing-source-code/test-coverage/python-test-coverage).
Local YAML, bash syntax, required dependencies and missing-token checks are in
[evidence/ci-combined-gate-review.json](evidence/ci-combined-gate-review.json).
Further publication requires approval. Combined coverage is not yet a remotePASS.

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

Fifteen packages have reviewed lock updates; 78 of 81 recorded alerts meet their
published patched-version floors. This is a local version comparison, not remote
alert closure. Backend/browser/build verification remains required for the final
lock. The updated major security packages passed the23-flow browser/PDF run; the
subsequent pydantic-settings update requires a final validation pass. MCP remains on
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
not claims that upstream advisories or remote alerts are closed.

## Clock evidence

The first current coverage/browser attempts failed on clock/quote/lease boundaries.
clock-quality-probe.json captured a backward wall step1.3107s versus forward
monotonic0.0104s. This supports a clock-related explanation but does not establish
the exact cause of every earlier failure. The later20.623s probe saw no jumps;
browser-security-coverage-v2 passes. Production clock/lease safeguards remain
unchanged. The next backend run records clock movement for its entire duration.

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
linecoverage82.63% includes measured browser routes; no remotequalityPASS claimed.
A separate60s probe saw no regressions, which does not invalidate the earlier
under-test clock failures. Reproduce bounded clock observations with:

```sh
.venv/bin/python scripts/verify_clock_stability.py --seconds 60 --output .qa/clock-new.json
```

Use a new output filename. The command only reads time and writes its report; it
returns1 on backward wall steps. Docker rebuild remains pending because the
DockerDesktop Linuxengine pipe is unavailable. No trading, production deployment,
OS configuration or remote Sonar issue state was changed.
