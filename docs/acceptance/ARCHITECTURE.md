# Architecture and authority map

Current checkout: local-machine only; original audit baseline65ea1d7, published
baselinee154a0a. Updated2026-10-22 for the unpublished offline submission journal
and schema0020 candidate. Source paths below are relative to `src/` unless stated.

The [focused offline checks](evidence/paper-submission-focused-20261022.json)
pass119 cases (47new unit,39new PostgreSQL journal,2migration-history and31closed
SDK-boundary cases). The [full candidate backend](evidence/paper-submission-backend-20261022.json)
passes907 unit plus431 PostgreSQL cases:1338distinct tests, zero failures/errors/skips.
Current image, browser and remote CI validation remain pending; historical e154
CI/image proofs do not validate this new candidate. Actual Paper/research gates
remain open. This laptop's24h/CPU-temperature/clock work is deferred to the unknown
final host, not passed; see [FINAL_HOST_HANDOFF.md](FINAL_HOST_HANDOFF.md).

| Request path / feature | Implementation | Classification / evidence |
|---|---|---|
| Browser login and saved chats | web/auth.py, web/routes.py, static/app.js | Implemented and tested: login, owned history/delete routes and real browser authenticated chat/report |
| Projects, preferences and account management UI | web/routes.py, static/app.js, tools/broker_accounts.py | Implemented and fixture-tested: scoped units plus real Chromium profile save/reload, project creation/chat assignment/reload, encrypted IBKR settings create/edit/blank-secret preservation/disable and cross-owner denial (browser-account-overflow-fixed.txt). Separate17Oct owner-authorized normal-UI read retained one partial balance snapshot; no orders and current owner read flags OFF |
| HTTP/WS origin and user identity | web/auth.py, web/network.py, routes.py | Same-origin and trusted proxy tests pass; durable revocation, active-user HTTP/MCP checks and open-WS revocation pass |
| Agent inference/orchestration | agent/orchestrator.py, clients/llama_cpp_client.py | Implemented and tested with deterministic fixtures and local 1.5B/3B CPU benchmarks; broader native task evaluation pending (MODEL_HOST.md) |
| Default portfolio/scanner factual reads | clients/llama_cpp_client.py | Deterministic scope selection tested; scheduled active-user identity and leases repaired |
| Tool permissions and vault | tools/dispatcher.py, broker_accounts.py | Implemented and tested: model self-approval denied; SDK/portfolio helpers reject unscoped reads even with global credentials (scoped-helper-reads.txt) |
| Browser simulator approvals | web/simulator_routes.py → execution/service.py | Real browser and PostgreSQL tests; cookie/CSRF and immutable nonce/details checked |
| Simulator risk and lifecycle | execution/policy.py, execution/models.py | Implemented and tested in isolated fixtures: locks/reservations, lifecycle races, approved versioned mandates, bounded buy ticks and marked-loss halts; opted-in manual sales tested; separately approved price-band strategy sales tested; durable no-trade decisions and concurrent replay tested; external reconciliation incomplete (MANDATES.md) |
| Direct IBKR adapter | tools/brokers/ibkr.py → ib_async 2.1.0 → TWS/Gateway | Explicit-account read-only fixture/package contracts tested. One authorized17Oct UI read persisted positions-complete/cash-incomplete, non-atomic evidence; environment remains SDK-unverified, no orders/authority. Owner Enabled/Read Authorized flags are now OFF; no new connection follows from this map |
| Offline submission journal | execution/broker_submission.py, broker_submission_models.py; migration0020 | Fixture-only canonical intents, committed handoff attempts, no automatic resend, uncertainty/recovery and linked callback/request-discrepancy review;119focused checks PASS. No runtime SDK transport, public entrypoint, approval/mandate/pretrade integration or actual Paper execution; see [contract](BROKER_SUBMISSION_CONTRACT.md) |
| Other external SDK adapters | tools/brokers/{alpaca,coinbase,binance}.py | Read implementations retained; all write entrypoints disabled through execution/external.py |
| Application MCP bridge | scripts/mcp_server.py → /api/tools/invoke | Application bearer token is separate from ChatGPT connectors; userless broker reads now denied; MCP_USER_ID explicitly binds an active user |
| Financial valuation | finance/normalization.py, tools/portfolio.py | Exact fractional quantity/currency/FX totals, synthetic flow/split/earned-and-received-dividend ledger, fee revisions and immutable observed period valuations tested (ACCOUNTING.md); separate observed price/FX attribution verified; historical boundary coverage, benchmark attribution and broader actions remain incomplete |
| Reports | scheduler/reporter.py | Implemented and tested: requested periods, structured evidence, typed failures, bounded off-loop PDF; browser persisted PDF/reload and exact observed-boundary PnL verified; publication lock covers DB commit; owner retention and explicit orphan cleanup tested (RETENTION.md); historical boundaries and external broker performance remain incomplete |
| Expenses | expenses/sync.py, summary.py, web routes/UI | Implemented and tested: signed currency/account identity, atomic imports, pagination, category audit/override and page export with browser isolation; fixture provider sync recovery tested; bank setup/status controls added with synthetic UI verification; raw/history export-and-purge with re-import suppression tested (RETENTION.md); real bank connection remains separately blocked |
| Database | db/models.py, migrations/; execution/broker_submission_models.py | Historical0018/0019 recovery retains its scope. New0020 migration-history/full431PG checks and [local DB-only durability](evidence/paper-submission-durability-20261023.json) PASS: actual ownedPG restart, new journal object/no resend,33tables/17rows restored with matching SQL counts/hashes. No Python-process restart, ephemeral vault-key recovery or restored-copy dispatch was proved. Production/off-host acceptance remains pending; private databases are never upgraded implicitly |
| News ingestion | news/ingestion.py, sources.py, search.py | Implemented and tested: public pinned-DNS HTTPS bounds, explicit private newsletter ownership, immutable corrections and availability-aware historical retrieval; durable per-source leases/retry and RSS validators tested (NEWS.md); source-specific policies, syndicated-copy deduplication and expired-text cleanup tested; real configured-provider operation remains unverified |
| Jobs and notifications | scheduler/jobs.py | Recorded scoped lease/alert/dedup, bounded workers/recovery and clock-token fencing checks pass within their source scope. Fresh24h/mapped CPU cooling/clock acceptance is deferred to the final host; no offline submission job or automatic broker retry is enabled |
| Container/network/CI | Dockerfile, docker-compose.yml, .github/workflows | Published e154 CI/configured Sonar and amd64 image/runtime proofs remain historical for their exact inputs. New journal/schema0020 candidate has no current CI/image/browser pass yet. Final-host OS/architecture/model profile and target ingress require their own validation |

## Authority and data separation

A model can request scoped reads and propose candidates; it cannot create human
approval events or change policy. The browser-only simulator approval route checks
authentication and CSRF and binds an immutable proposal to a cookie-derived session
hash, account, expiry, details digest, and consumed nonce. Account row locks reserve
budgets before simulated submission. Simulator accounting/lifecycle remains in its
own namespace; no simulator order can reach a broker SDK. The separate offline
broker intent/event journal retains only marked-fixture handoff evidence. Its
canonical request is not approval, a mandate or a risk reservation; default dispatch
denies before DB/credential access. A committed attempt with uncertain outcome can
never automatically resend. No runtime broker transport is wired to this journal.

The external SDK write boundary is closed in `execution/external.py`. A configuration
flag, model schema, port 4002, test success, or six-share SPYL example grants no write
capability. Direct ib_async and the HTTP MCP bridge are separate layers; ChatGPT
connector credentials are neither discovered nor reused by this application.

IBKR readonly calls bind an actual managed account and preserve contract/currency
identity. The [17Oct read metadata](evidence/paper-ui-read-metadata-20261017.json)
records one partial snapshot, not complete balances/history or an order lifecycle.
The owner subsequently disabled both read flags; no current read/order authority
is inferred. Open-order queries and offline callback fixtures cannot replace full
actual history/commission/reconnect/reconciliation or independently verified Paper
provenance. Future execution also needs separately approved transport, independent
approval/mandate, qualification and pretrade risk integration.

## Primary protocol references consulted

- [IBKR API](https://www.interactivebrokers.com/docs/tws-api/doc/introduction)
- [IBKR order placement](https://www.interactivebrokers.com/campus/trading-lessons/python-placing-orders/)
- [ib_async API and event semantics](https://github.com/ib-api-reloaded/ib_async)
- [IBKR third-party adapter status and ib_insync deprecation notice](https://www.interactivebrokers.com/docs/tws-api/doc/third-party-api-platforms/non-standard-tws-api-languages-and-packages/ib-insync-and-ib-async)
- [IBKR reauthentication](https://www.interactivebrokers.com/docs/tws-api/doc/tws-settings/daily-weekly-reauthentication)
- [GoCardless bank-data quickstart](https://docs.gocardless.com/docs/bank-account-data/quickstart-guide)
- [SQLAlchemy transaction isolation in tests](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html)
- [Playwright installation](https://playwright.dev/python/docs/intro)

The IBKR client migrated from deprecated ib_insync to ib_async2.1.0 with installed
API and adapter contract tests, as recorded above. Protocol documentation and those
tests do not prove this host has a connected or entitled external account.

Financial definitions: [ACCOUNTING.md](ACCOUNTING.md). Adapter boundaries and limitations: [BROKER_CAPABILITIES.md](BROKER_CAPABILITIES.md).
