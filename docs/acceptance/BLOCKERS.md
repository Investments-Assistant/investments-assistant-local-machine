# Remaining gates and prerequisites

Current checkpoint: 2026-10-10, HEAD9b0df38 with preserved uncommitted work.
This ledger does not mark the overall Goal complete or declare all local work done.
Use PLAN.md for every gate status and CHECKPOINT.md for current processes.

| Area | Evidence and unresolved condition | Smallest next action |
|---|---|---|
| Container build and real target ingress/restarts (L10/L11/L13) | Docker CLI reports unavailable WSL integration. Pinned image references and bounded build context pass Compose parsing (BUILD.md); actual image build remains unverified; fixed signed apt snapshots resolve locally and Poetry bootstrap passes isolated hash-locked installation. Actual isolated Nginx TLS/WSS passes (INGRESS.md), but does not prove Docker source-address handling, real LAN ingress or container restart behavior. | Operator restores Docker Desktop WSL integration; then run the documented isolated validation profile. No firewall/power change or production deployment is authorized. |
| Remote CI (L11) | Run37657249888 at current committed HEAD failed fresh-schema integration; working-tree fix passes1041tests from an empty marked database and5loopback soak checks. | Publish reviewed changes only with appropriate authorization, then inspect the new workflow run. Do not rerun the unchanged failing commit as proof of these fixes. |
| External IBKR/paper (L04/L15) | No explicitly approved verified paper account or connection evidence. Native writes remain unconditionally blocked. Finite read capture and SDK-shaped lifecycle tests do not establish external account reconciliation. | User selects and approves a specific verified paper account and permitted observation scope. Confirm gateway/runtime/account provenance before any connection; submission authority remains separate. |
| Real bank synchronization | Tested GoCardless boundary and synthetic consent/recovery are separate from actual provider access. No real bank consent, eligible institution or provider credentials verified. | User completes authorized provider setup/consent; no bank password is requested or stored. |
| Research (L14) | Fixed cost-aware fixture plan and untouched synthetic split do not establish historical news availability, a representative universe or economic edge. Conclusion remains INSUFFICIENT EVIDENCE. | Supply/approve permitted attributable historical inputs and their availability provenance, then evaluate the unchanged predeclared plan. No paid feed or threshold tuning implied. |
| Host observation (L13) | CPU/runtime measurements and short restart/load smoke exist; physical cooling/throttling, actual OS sleep/resume and24h observation remain unverified. | Stable candidate plus an available observation window; use SOAK.md runner. Original instructions explicitly permit leaving24h pending when the session cannot observe it. No power changes authorized. |
| Production/off-host recovery and outbound channels | Local synthetic restore and local sink checks do not prove production restore, remote backup custody or external notification delivery. | Separately approve concrete target/destination/privacy scope before any external write. Preserve local fixture results meanwhile. |
| Live eligibility (L16) | No accepted prerequisites or explicit versioned account mandate; execution/external.py denies external writes. | Keep live disabled. This task does not authorize enabling it even if engineering checks pass. |

Latest remaining-scope review found no additional independent local repair to
perform before the listed prerequisites. This does not promote partial gates to
PASS. Recheck changed evidence on resume; any new authorized local defect remains
actionable. Three consecutive no-progress prerequisite checks recorded in CHECKPOINT.md.
The Goal is being marked blocked after the final monitor audit; no completion
is claimed. Restore Docker Desktop Linux-engine availability, then Resume Goal.
