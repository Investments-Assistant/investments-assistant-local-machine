# Getting the remaining prerequisites ready

## Current direction — 22 October 2026

The owner will deploy on a different computer. This laptop's24h observation,
mapped CPU-temperature checks and clock repair are **DEFERRED to the final host**,
not passed. The pending laptop Portable ZIP/download/setup request is cancelled;
no temperature app or clock experiment is requested here. The final OS, architecture
and hardware are unknown. Use the [final-host handoff](FINAL_HOST_HANDOFF.md) once
that target is known; old `.qa` helpers, clusters and process identities are not
portable setup inputs.

The owner explicitly keeps **research and Paper gates OPEN**. The two prerequisites
below remain required; neither is deferred or declared complete. Checkout-only
offline Paper implementation can continue without actual broker reads or orders.
Live stays OFF, external SDK writes remain closed and the Goal is incomplete.

## Recorded evidence before this direction

Published code/CI and the new local cash/halt candidate checks pass within their
recorded scopes. The seven-file candidate passes860unit/392PostgreSQL, fresh
image/runtime/recovery/cleanup and the earlier90-second halt-guard smoke. The exact
seven-file patch is approved/published as e154a0a; allfourcurrentCI jobs and its
configured Sonar quality gate are verified PASS. Window53a8 was
stopped and retained after a reproduced harness gap. Current-source window
79f7ab59792c was interrupted by another kernel restart before24hours; its stale
RUNNING checkpoint earns no24-hour credit. Fresh078d launched once and failed
its clock guard after39.744seconds; a read-only probe reproduced a311ms backward
clock step. Earlier f945 evidence applies only to that older candidate. Preserve
old and failed evidence; no observation is running or authorized for blind retry.
Inspect the [current plan](PLAN.md), [observation status](SOAK.md) and
[checkpoint](CHECKPOINT.md) before any restart or cleanup.

The owner has already selected the encrypted IBKR Paper account and completed
one authorized read. Its retained evidence has complete positions but incomplete
cash, with Paper still SDK-unverified and no execution authority. The owner
subsequently unchecked Enabled and Read Authorized and saved. Do not repeat setup,
connect or place orders merely by following this reference guide. Further Paper
lifecycle/reconciliation and a forward plan need the remaining verified inputs
and separate applicable approval; live stays OFF.

The overall Goal remains incomplete. This guide explains the missing inputs;
it grants no additional trading, provider, installation or deployment permission.
Work through one prerequisite at a time. The Paper setup section below is a
reference for a future explicitly authorized setup, not a pending user action.

## First: find the IBKR practice account

**Paper Trading means simulated trading with pretend money.** Having an ordinary
IBKR login does not by itself identify the practice account or establish which
account this application would connect to.

1. Sign in to IBKR's own website yourself.
2. Open the user menu, then **Settings → Account Configuration → Paper Trading
   Account**. This is the path in IBKR's [Paper Trading Account guide](https://www.ibkrguides.com/clientportal/papertradingaccount.htm).
3. Tell the assistant only whether that page is present. Keep any username,
   password and account number private. Finding the page is an initial setup
   check, not verification that an application connection is Paper-only.

If the page is missing or unavailable, report that result. We can then use the
appropriate IBKR help route; no account assumption or test order is needed.

The next stage uses **Trader Workstation (TWS)** or **IB Gateway**, the broker's
program that this checkout's adapter communicates with. It is separate from
simply being signed in to a website. In TWS the login offers a Paper selection;
see [IBKR's TWS login guide](https://ibkrguides.com/traderworkstation/log-in-to-tws.htm).
We first need to establish which program is installed and verify the selected
Paper session/account locally. No software installation or account connection
has been performed by this guide.

For the already authorized read-only stage, **Read-Only API stays enabled**.
IBKR documents that it blocks API orders. Local-only access must also remain
restricted; do not open firewall ports or broaden trusted addresses to make a
WSL connection work. The application still needs explicit account selection,
current ownership/read consent and independently checked Paper provenance.
A port number or account-prefix guess cannot provide that proof. Relevant
sources: [IBKR API setup lesson](https://www.interactivebrokers.com/campus/trading-lessons/installing-configuring-tws-for-the-api/)
and [API setting definitions](https://www.interactivebrokers.com/docs/tws-api/protobuf/api-settings-config).
Actual connectivity is a later separately verified step. Paper order submission
and its observation plan remain separately unapproved; all external writes stay
closed. TWS/Gateway upgrades can change API settings, so verify the running
settings rather than rely on defaults ([2026 release notes](https://www.ibkrguides.com/releasenotes/prod-2026.htm)).

## Historical prices: a file of past market prices

**23 October update:** the owner has no local price-history file. The next
decision is the [bounded free source-check proposal](RESEARCH_SOURCE_PROPOSAL.md),
not another request for a file. The owner approved the private EODHD Sandbox
source-quality check only. On 24 October they confirmed the free account/key
ready; the nine-request manifest is prepared and awaits confirmation of the
remaining free allowance. No real-study universe is approved and no data request
has started. No purchase or app-provider enablement is authorized. L14
remains open and the economic conclusion remains INSUFFICIENT EVIDENCE.

This means past prices for named shares/funds, with dates and enough source
information to assess how they can be used. An account login or a holdings/trade
statement does not supply that price history.

When an approved source supplies data, inspect its actual format. Before research
acceptance we must establish:

- Who supplied it and permission to use it for this research.
- Which shares/funds it covers, their exchanges and currencies, and the date range.
- What the prices, timestamps, volume, FX and corporate-action adjustments mean.
- Whether news availability and the untouched evaluation split can be established.

The absence of a file is already recorded. No purchase, arbitrary download or
Yahoo-data permission is implied. Public availability and a software package's
license do not establish rights to its underlying data.

There is currently no general CSV-import command to recommend: the retained
public history adapter is source-specific and default-disabled, while the fixed
offline evaluator uses synthetic data. We will inspect the actual permitted
format before preparing its adapter/evaluation. Existing fixture results prove
engineering behavior only; the economic conclusion stays **INSUFFICIENT EVIDENCE**.
See [replay scope](REPLAY.md) and the [unapproved forward plan](FORWARD_OBSERVATION.md).

## Cooling: identify what the temperature measures

This check is deferred to the **actual final computer**. The recorded laptop ACPI
THM0 temperatures do not identify a CPU/GPU component and receive no CPU-cooling
acceptance. The laptop sensor-tool request is cancelled. On the final host, first
identify its OS and an existing trusted component-mapped CPU package/core source;
then review suitable sustained-load telemetry. No Windows-specific tool, install,
driver/service, fan, power or clock change is implied. See the
[historical cooling review](COOLING_REVIEW.md) and [handoff](FINAL_HOST_HANDOFF.md).

## Resume without repeating completed work

After one input changes, resume the Goal with that non-secret information and
read [CHECKPOINT.md](CHECKPOINT.md) and [PLAN.md](PLAN.md). The old79f7 observation
and finite observer did not survive the new kernel boot; do not retry them or
accept their stale RUNNING file as live. Fresh078d is terminalFAILED on a clock
discontinuity; its finite verifier rejected it. Inspect the failed raw/retention/
cleanup receipts before any new proposal; stable clocks remain a final-host
requirement, not a request to repair this laptop. Preserve a
positively verified live runner; never duplicate, restart or clean it, or run
concurrent terminal audits. The old53a8 window was stopped and retained.
Historical completed or interrupted windows and the private operator
database are not cleanup targets. Existing valid evidence is reused; only checks
affected by subsequent work need repeating. No 24-hour pass is inferred before
terminal verification. Live remains OFF; no additional broker connection or
order occurred while updating this guide.
