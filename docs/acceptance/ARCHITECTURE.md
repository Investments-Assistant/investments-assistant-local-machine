# Architecture and authority map

Current checkout: local-machine only; audit baseline 65ea1d7. Updated 2026-10-05. Source paths below are relative to `src/` unless otherwise stated.

| Request path / feature | Implementation | Classification / evidence |
|---|---|---|
| Browser login and saved chats | web/auth.py, web/routes.py, static/app.js | Implemented and tested: login, owned history/delete routes and real browser authenticated chat/report |
| Projects, preferences and account management UI | web/routes.py, static/app.js, tools/broker_accounts.py | Implemented; scoped unit tests retained. Full project/account-management browser coverage remains unverified |
| HTTP/WS origin and user identity | web/auth.py, web/network.py, routes.py | Same-origin and trusted proxy tests pass; durable revocation, active-user HTTP/MCP checks and open-WS revocation pass |
| Agent inference/orchestration | agent/orchestrator.py, clients/llama_cpp_client.py | Implemented and tested with deterministic fixtures and local 1.5B/3B CPU benchmarks; broader native task evaluation pending (MODEL_HOST.md) |
| Default portfolio/scanner factual reads | clients/llama_cpp_client.py | Deterministic scope selection tested; scheduled active-user identity and leases repaired |
| Tool permissions and vault | tools/dispatcher.py, broker_accounts.py | Implemented and tested: model self-approval denied; SDK/portfolio helpers reject unscoped reads even with global credentials (scoped-helper-reads.txt) |
| Browser simulator approvals | web/simulator_routes.py → execution/service.py | Real browser and PostgreSQL tests; cookie/CSRF and immutable nonce/details checked |
| Simulator risk and lifecycle | execution/policy.py, execution/models.py | Implemented and tested in isolated fixtures: locks/reservations, lifecycle races, approved versioned mandates, bounded buy ticks and marked-loss halts; opted-in manual sales tested; separately approved price-band strategy sales tested; durable no-trade decisions and concurrent replay tested; external reconciliation incomplete (MANDATES.md) |
| Direct IBKR adapter | tools/brokers/ibkr.py → ib_insync → TWS/Gateway | Explicit-account readonly fixture contracts tested; no external connection evidence |
| Other external SDK adapters | tools/brokers/{alpaca,coinbase,binance}.py | Read implementations retained; all write entrypoints disabled through execution/external.py |
| Application MCP bridge | scripts/mcp_server.py → /api/tools/invoke | Application bearer token is separate from ChatGPT connectors; userless broker reads now denied; MCP_USER_ID explicitly binds an active user |
| Financial valuation | finance/normalization.py, tools/portfolio.py | Exact fractional quantity/currency/FX totals, synthetic flow/split/received-dividend ledger, fee revisions and immutable observed period valuations tested (ACCOUNTING.md); separate observed price/FX attribution verified; historical boundary coverage, benchmark attribution and broader actions remain incomplete |
| Reports | scheduler/reporter.py | Implemented and tested: requested periods, structured evidence, typed failures, bounded off-loop PDF; browser persisted PDF/reload and exact observed-boundary PnL verified; publication lock covers DB commit; owner retention and explicit orphan cleanup tested (RETENTION.md); historical boundaries and external broker performance remain incomplete |
| Expenses | expenses/sync.py, summary.py, web routes/UI | Implemented and tested: signed currency/account identity, atomic imports, pagination, category audit/override and page export with browser isolation; fixture provider sync recovery tested; bank setup/status controls added with synthetic UI verification; raw/history export-and-purge with re-import suppression tested (RETENTION.md); real bank connection remains separately blocked |
| Database | db/models.py, migrations/ | Implemented and tested: reviewed-schema upgrades through 0018, ownership quarantine and durable sessions/evidence/mandates; 0018 database31-table restore verified (job-clock-restore.json); prior full PDF/vault/model recovery remains historical; owned chat/report/news/expense retention tested; coherent backup-bundle expiry remains open |
| News ingestion | news/ingestion.py, sources.py, search.py | Implemented and tested: public pinned-DNS HTTPS bounds, explicit private newsletter ownership, immutable corrections and availability-aware historical retrieval; durable per-source leases/retry and RSS validators tested (NEWS.md); source-specific policies, syndicated-copy deduplication and expired-text cleanup tested; real configured-provider operation remains unverified |
| Jobs and notifications | scheduler/jobs.py | Implemented and tested: scoped leases, in-app dedup/ack/local delivery recovery, bounded simulation/PDF workers, short restart/model contention smoke and0018 clock/token fencing tests; 24-hour observation and OS/Docker interruption pending (SOAK.md) |
| Container/network/CI | Dockerfile, docker-compose.yml, .github/workflows | CPU build path retained; manual x86_64 validation replaces automatic Pi deployment; Docker host build blocked by daemon availability |

## Authority and data separation

A model can request scoped reads and propose candidates; it cannot create human
approval events or change policy. The browser-only simulator approval route checks
authentication and CSRF and binds an immutable proposal to a cookie-derived session
hash, account, expiry, details digest, and consumed nonce. Account row locks reserve
budgets before submission. All execution state here belongs to a simulator namespace;
no simulator order can reach a broker SDK.

The external SDK write boundary is closed in `execution/external.py`. A configuration
flag, model schema, port 4002, test success, or six-share SPYL example grants no write
capability. Direct ib_insync and the HTTP MCP bridge are separate layers; ChatGPT
connector credentials are neither discovered nor reused by this application.

IBKR readonly calls bind an actual managed account and preserve contract/currency
identity. Open-order queries are not execution-history reconciliation. Durable
external callbacks, commission repair, reconnect observation, and verified paper
account evidence remain required before external writes could be considered.

## Primary protocol references consulted

- [IBKR API](https://www.interactivebrokers.com/docs/tws-api/doc/introduction)
- [IBKR order placement](https://www.interactivebrokers.com/campus/trading-lessons/python-placing-orders/)
- [ib_insync API and event semantics](https://ib-insync.readthedocs.io/api.html)
- [IBKR third-party adapter status](https://www.interactivebrokers.com/docs/tws-api/doc/third-party-api-platforms/non-standard-tws-api-languages-and-packages/ib-insync-and-ib-async)
- [IBKR reauthentication](https://www.interactivebrokers.com/docs/tws-api/doc/tws-settings/daily-weekly-reauthentication)
- [GoCardless bank-data quickstart](https://docs.gocardless.com/docs/bank-account-data/quickstart-guide)
- [SQLAlchemy transaction isolation in tests](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html)
- [Playwright installation](https://playwright.dev/python/docs/intro)

No library migration was made. Protocol documentation informs contracts; it is not
proof that this host has a connected or entitled external account.

Financial definitions: [ACCOUNTING.md](ACCOUNTING.md). Adapter boundaries and limitations: [BROKER_CAPABILITIES.md](BROKER_CAPABILITIES.md).
