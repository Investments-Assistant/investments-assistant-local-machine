# Remaining gates and prerequisites

Current checkpoint: 2026-10-14T22:51Z, checkout `master` at `1d01bb5517d5f1a7424efd9daca766223850a2df`, tracking `origin/main` at the same commit. The approved IBKR migration is published; the checkout contains preserved local source, test, documentation and evidence changes. Do not reset or discard them. The Goal is active and incomplete. `PLAN.md` is the acceptance matrix; `CHECKPOINT.md` preserves historical decisions and resumable process state.

| Gate or area | Current evidence and unresolved condition | Smallest next step |
|---|---|---|
| L04 Broker lifecycle | Simulator and SDK-shaped lifecycle tests cover durable callbacks, partial fills, uncertain submissions and restart cases. Actual gateway reauthentication and external account reconciliation remain unverified. No broker connection has been attempted during this task. | User explicitly authorized read-only paper connectivity but clarified they only have an IBKR login and do not know about a paper-only TWS/Gateway session. Plain-language help is needed to configure and independently verify a paper session/account before any connection. No credentials or account identifiers in chat; any paper order requires separate explicit approval. Keep external writes denied. |
| L13 Host cooling | The 24-hour candidate soak is terminal PASS_24H and independently verified:86,400.216s,3,060cycles,93restarts,zero failures,halt p95 28.275ms; current-image production startup/model/database/restart checks also PASS. The saved672-sample ACPI THM0 series spans11h11m51s,67.05–95.05C,passive limit100/throttle0. PnP identifies ACPI(_SB_)#ACPI(THM0), but does not map it to CPU/GPU/chassis. Thus the available series does not prove CPU-package cooling. | Keep the completed soak intact; do not resume/restart it. Preserve the unmapped-sensor limitation. Additional component telemetry requires an available read-only source or separately approved sensor setup; no OS/power changes are authorized. |
| L14 Research | Cost-aware replay and fixed synthetic comparison pass, but economic evidence remains `INSUFFICIENT EVIDENCE`. [The source review](evidence/research-source-review-20261013.md) identifies GDELT and SEC as candidate news inputs, not approved providers. No reviewed no-cost source establishes licensed historical prices for an approved instrument universe. The Yahoo adapter now fails closed by default pending explicit operator review; see `evidence/yahoo-source-egress-guard-20261013.txt`. Forward observation plan is still a proposal. | User said they have a rights-cleared source and universe but then clarified they cannot identify the source, instruments, period or data path. Needed to proceed: source/provider name, instruments or universe, date coverage, and exact permitted local file/path (plus any license/retention limits). Example reply: “Source X; SPY and QQQ; 2018–2025; file at D:\research\prices.parquet; local research use permitted.” No data will be fetched or read until these are identified. Then run the unchanged predeclared evaluation; do not tune its split or targets. |
| L15 External paper | Read-only paper connectivity is authorized, but user says they only have an IBKR login and do not understand paper accounts or Gateway/TWS. There is no verified paper-only environment or broker execution/reconciliation evidence. A port number or mock is not account provenance. | Next user step: in the IBKR Client Portal, check whether a Paper Trading account is available/activated (IBKR says new accounts generally receive one, while older accounts may not); if absent, follow IBKR’s official paper-account setup or contact IBKR support. Then start TWS/IB Gateway and explicitly choose Paper at login. Tell me only when that mode is visibly selected and you can confirm the selected account is the paper account; keep credentials/account IDs in the approved local config, never chat. References: [IBKR paper-account overview](https://www.interactivebrokers.com/campus/glossary-terms/paper-trading-account/) and [paper-account setup lesson](https://www.interactivebrokers.com/campus/trading-lessons/request-paper-trading-account/). Keep writes denied; paper orders need separate approval. |
| Local soak fix publication | The two-file synthetic-fixture mandate-duration fix and PostgreSQL regression are local only. Seven integration tests, Ruff, compile checks and the 90-second HTTP/PostgreSQL smoke pass. Exact review patch and hash are in `evidence/soak-expiry-fix-review-20261013.patch` and `.json`. The user's earlier publication permissions covered other exact bundles. | Await the pending approval for this exact two-file bundle before publishing it. The current tracked soak may continue; no commit/push or remote CI run for this patch yet. |
| Current candidate container runtime | RESOLVED: Docker Desktop29.8.2, source-matched candidate image a64ce3a9… and existing model6a1a2eb6… passed production-entrypoint readiness, migrations, operator-halt recovery and app/database restarts6.584s/1.044s against15s. Runner exited0; separate label-based cleanup check found no owned resources. See CONTAINERS.md and evidence/container-runtime-ibasync-new.json. | No rerun needed absent relevant changes or new concerns. This isolated validation grants no production deployment or exposure authority. |
| Real bank synchronization | The adapter boundary, synthetic consent and recovery behavior are tested. No real provider consent, eligible institution or credentials are configured. | Keep disconnected unless the user separately authorizes provider setup and completes provider consent; never request a bank password. |
| Optional external operations | Local sink, fixture restore and alert behavior do not prove production/off-host recovery or delivery to a real external destination. Public/LAN exposure and firewall boundaries are not enabled or newly validated here. | Treat these as deferred until a concrete target, privacy scope and authorization are provided. Do not deploy, send notifications or alter firewall/power configuration. |
| L16 Live eligibility | `PASS (NO-GO; safely disabled)`: `.env` keeps `LIVE_TRADING_ENABLED=false`, external SDK writes are unconditionally denied, and the focused authority suite passes 9/9. | Keep live disabled. This Goal grants no live mandate or trading authority. |

## Safe continuation

The final candidate soak has terminal `PASS_24H` with continuity verified, and
the queued current-image runtime check has passed. Preserve both completed runs
and their raw evidence. Continue any independently authorized local requirement
found by the remaining-work audit. External account/data, publication and mapped
hardware telemetry prerequisites remain unavailable; do not fabricate evidence
or restart passed checks without a relevant change or unresolved concern.

Do not mark the Goal complete while any required gate remains incomplete. Keep
live mode OFF and preserve the full dirty worktree.

A read-only local recheck on 2026-10-14 found no candidate research dataset in
the checkout and no listener on API ports4001/4002; `.env` still says
`LIVE_TRADING_ENABLED=false`. See
`evidence/local-paper-data-prerequisite-check-20261014.txt`. This does not
exclude data outside the checkout or determine paper-account status in IBKR.

### Plain-language next steps

- **IBKR paper account:** The IBKR username/password you already created may
  only be your regular account login. IBKR requires a separate simulated
  (“Paper”) account/session for this check. In IBKR Client Portal, look for
  Paper Trading and activate/request it if needed. When logging in to TWS or
  IBKR's desktop platform, choose **Paper** on the login screen. No need to send
  me any username, password, or account number. Once the screen clearly says
  Paper, tell me only that you have selected Paper; I can then verify read-only
  connectivity. No order will be placed.
- **Historical prices:** This is only needed to evaluate whether the strategy
  had evidence of an advantage. It means an already-permitted file of past
  prices, plus the names of the stocks/funds it covers and the dates in the
  file. If you do not know a source or do not have that file, say so; nothing
  needs to be installed or purchased, and this research gate will remain
  honestly marked as insufficient evidence.
