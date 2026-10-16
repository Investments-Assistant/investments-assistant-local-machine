# Getting the remaining prerequisites ready

The code, CI, current-source24-hour engineering observation and isolated database
cleanup have passed their documented checks. The overall Goal remains incomplete.
This guide explains the missing inputs; it grants no additional trading, provider,
installation or deployment permission. Work through one prerequisite at a time.

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

This means past prices for named shares/funds, with dates and enough source
information to assess how they can be used. An account login or a holdings/trade
statement does not supply that price history.

For a first inspection, identify an existing local price-history file, if you
have one. Its path is useful even if you do not know its format. Before research
acceptance we must establish:

- Who supplied it and permission to use it for this research.
- Which shares/funds it covers, their exchanges and currencies, and the date range.
- What the prices, timestamps, volume, FX and corporate-action adjustments mean.
- Whether news availability and the untouched evaluation split can be established.

If you have no such file, simply report that. No purchase, arbitrary download or
Yahoo-data permission is implied. Public availability and a software package's
license do not establish rights to its underlying data.

There is currently no general CSV-import command to recommend: the retained
public history adapter is source-specific and default-disabled, while the fixed
offline evaluator uses synthetic data. We will inspect the actual permitted
format before preparing its adapter/evaluation. Existing fixture results prove
engineering behavior only; the economic conclusion stays **INSUFFICIENT EVIDENCE**.
See [replay scope](REPLAY.md) and the [unapproved forward plan](FORWARD_OBSERVATION.md).

## Cooling: identify what the temperature measures

The recorded ACPI THM0 temperatures do not identify a CPU/GPU component. The
component-specific providers already checked were unavailable. If an existing
trusted monitoring program displays a clearly labelled CPU package/core sensor,
identify that program and sensor first. We can assess whether it offers a usable
read-only source. Otherwise a concrete sensor-tool setup needs separate review
and approval before installation or any service/OS change. No new measurement is
claimed here; [measured host evidence](MODEL_HOST.md) retains the limits.

## Resume without repeating completed work

After one input changes, resume the Goal with that non-secret information and
read [CHECKPOINT.md](CHECKPOINT.md) and [PLAN.md](PLAN.md). The completed soak and
database cleanup must not be restarted by default. Existing valid evidence is
reused; only checks affected by subsequent work need repeating. Live remains OFF,
and no broker connection or order occurred while preparing this guide.
