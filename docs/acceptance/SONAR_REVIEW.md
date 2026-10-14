# Remaining Sonar review at cd049bf

CI run38185591707 completed with all test tiers passing and only the mandatory
Sonar quality gate failing. Actual new-code coverage82.6% passes80%; security4
and reliability3 fail their unchanged thresholds1. Six log-injection findings
are absent from the current open-issue response. No issue has been reclassified,
no suppression added, and no quality threshold changed.

Evidence: [current issues](evidence/sonar-issues-cd049bf.json),
[current gate](evidence/sonar-quality-cd049bf.json),
[CI artifacts](evidence/remote-ci-38185591707-test-artifacts.json).

The following are proposed review dispositions, not completed remote actions.
A repository security/quality reviewer must decide and record them in Sonar.

| Finding | Evidence | Proposed disposition |
|---|---|---|
| `AaEoT1R0IbC7RohpPcR3`, S4830, `src/news/http.py:82` | `ssl.create_default_context()` sets CERT_REQUIRED and hostname checking. Three real local TLS handshakes accept trusted matching host and reject wrong host/untrusted cert. Published `tests/unit/public_fetch_tls_test.py`; current unit and combined CI pass. | False positive: certificate validation is already enabled. |
| `AaEoT1J9IbC7RohpPcNR`, S3330, `src/web/routes.py:329` | Only the independent CSRF token is JavaScript-readable for the double-submit header. Session credential is HttpOnly; production cookies are Secure/SameSite strict. Published `cookie_security_test.py` proves CSRF cannot authenticate and missing/mismatched headers fail403; actual browser checks also pass. | Review as intentional non-session cookie; record justified disposition under project policy. |
| `AaEoT1C0IbC7RohpPcLN`, S2583, `src/tools/dispatcher.py:668` | `_live_route_allowed` intentionally returnsFalse pending independent external acceptance. `acceptance_authority_test.py::test_port_and_live_flag_cannot_authorize_external_writes` proves order routing remains blocked even with a production live flag. | Accept the intentional permanently closed legacy write guard; this is not a claim the condition can evaluate differently. |
| `AaEoT1C0IbC7RohpPcLO`, S2583, `src/tools/dispatcher.py:725` | Same unconditional boundary blocks external cancellation; same published regression and combined CI evidence. | Accept intentional closed cancellation guard. Never enable the path to satisfy static analysis. |

Project issue view:
https://sonarcloud.io/project/issues?id=Investments-Assistant_investments-assistant&branch=main

After authorized review, query the quality API and inspect a fresh authorized CI
check if needed. A review disposition is not a broker mandate and does not authorize
external execution. Keep live OFF. SONAR_TOKEN remains a repository secret; do not
paste it into chat or extract it from GitHub. This agent has not been authorized
to change remote finding state.

## Finding navigation

The four findings are the unresolved BUG/VULNERABILITY subset on main in the new-code period, not the whole-project issue count or Top issues list. Public API recheck still returns exactly4. Direct links:

- [TLS validation](https://sonarcloud.io/project/issues?id=Investments-Assistant_investments-assistant&branch=main&issues=AaEoT1R0IbC7RohpPcR3&open=AaEoT1R0IbC7RohpPcR3)
- [Order write guard](https://sonarcloud.io/project/issues?id=Investments-Assistant_investments-assistant&branch=main&issues=AaEoT1C0IbC7RohpPcLN&open=AaEoT1C0IbC7RohpPcLN)
- [Cancellation guard](https://sonarcloud.io/project/issues?id=Investments-Assistant_investments-assistant&branch=main&issues=AaEoT1C0IbC7RohpPcLO&open=AaEoT1C0IbC7RohpPcLO)
- [CSRF cookie](https://sonarcloud.io/project/issues?id=Investments-Assistant_investments-assistant&branch=main&issues=AaEoT1J9IbC7RohpPcNR&open=AaEoT1J9IbC7RohpPcNR)

## Authorized review outcome — 2026-10-13

The user accepted all four findings. Read-only API verification records each as
RESOLVED/WONTFIX, not a code repair or a false-positive classification. Sonar quality
is nowOK: security/reliability ratings1 and newcoverage82.6%. Exact responses:
[evidence/sonar-reviewed-issues-reviewed-20261013.json](evidence/sonar-reviewed-issues-reviewed-20261013.json),
[evidence/sonar-quality-reviewed-20261013.json](evidence/sonar-quality-reviewed-20261013.json).

Retain the TLS handshake, production-cookie and external-write-denial regression
tests. Revisit accepted decisions when these code paths change. Do not infer
external execution authority from accepted static-analysis findings. The historical
failed CI job is rerunning at unchangedcd049bf (attempt2) to verify the gate inCI.

CI verification complete: run38185591707 attempt2 atcd049bf finishedSUCCESS, including the mandatory Sonar quality gate. Fresh combined1086testsPASS167.652s; allfourjobsSUCCESS. L11PASS. Accepted findings remain documented decisions, not code repairs; other physical/external/research gates remainopen.
