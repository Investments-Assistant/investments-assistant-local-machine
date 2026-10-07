# Local authorization boundary review

Reviewed2026-10-05 against the original L02 conditions. This concerns implemented
local capabilities and denied external writes, not an approved broker-paper/live
capability. The current principal-lifetime version passed840 unit/PostgreSQL tests and the
real Chromium workflow. PLAN.md is the gate-status authority.

| Required invariant | Enforcement | Evidence |
|---|---|---|
| Model cannot approve its own proposal | dispatcher._confirm_trade always denies; browser_identity requires authenticated cookie; CSRF guards independent simulator approval | acceptance_authority_test same-session self-approval; execution_test independent nonce/session/expiry/replay and concurrent approvals; Chromium model denial/approval |
| Model cannot change mode, limits or protected allocation | dispatcher._set_trading_mode denies; external write decorator and router deny regardless of live flag; simulator mandate hash/version is independently approved and checked on every tick | acceptance_authority_test mode/live flag/port denial; mandates_test changed/expired spec and protected/capacity halts |
| Scope cannot cross users/accounts/sessions | account_for_user binds active user and account; order/mandate queries bind account and proposal session; MCP requires an explicit active principal; broker helpers reject global fallback | execution_test cross-user/session rejection; sessions_test MCP binding/deactivation; browser cross-user/CSRF rejection |
| Approval cannot be replayed or changed | account lock, immutable details hash, single-use nonce, expiry; retained idempotency and decision evidence | execution_test approval replay/edited order/concurrency; mandates_test replay/edited spec and concurrent ticks |
| Revocation/deactivation reaches entrypoints | durable session revocation, HTTP/MCP checks, open-WebSocket revocation, active owner at every execution transaction; background strategy/risk account commands use the same boundary | sessions_test and Chromium logout/open-WS; execution_owner_lifetime_test and execution/mandate/runtime cases |
| External evidence grants no authority | external text is evidence; tool dispatcher and execution services still enforce identity/capability, regardless of model output | workflow/read-scope/news injection fixtures; server-level self-approval/mode denial, closed external SDK writes |

The lifetime review found an actual race: a user could be deactivated after a worker
read active status but while it waited for the account lock. The reproduction is
`evidence/execution-owner-race-reproduction.txt`. The execution boundary now holds
FOR SHARE on the active principal before acquiring the account row lock. Deactivation
cannot commit midway through that transaction; once committed it excludes subsequent
commands. This allows already-authorized transactions to finish before deactivation
completes, rather than promising cancellation of work already in progress. The
concurrent PostgreSQL test checks real lock contention and subsequent denial; it
cleans only its own synthetic records. `execution-owner-race-fixed.txt`41PASS covers
this boundary plus approvals, mandates, risk and dispatcher compatibility.

Verification: suite-owner-lifetime.txt840PASS200.26s(exit0); browser-owner-lifetime.txt
real Chromium/PostgreSQL PASS desktop1440x1000/mobile390x844, no unexpected console
errors. Synthetic model/provider fixtures are explicit. The final gate review must
match each L02 condition above; external execution authority remains closed.
No broker/account was connected or externally traded. A separately approved paper
account, external execution/reconciliation and a future explicit live mandate remain
separate blocked gates; local approval never opens those routes.

Final progress-monitor review found no missing local L02 condition and recommended
PASS. PLAN.md now records that decision, with external execution authority and
validation explicitly excluded and retained under their original separate gates.
