# Private historical-price source check — 23 October 2026

The owner confirms they have **no local price-history file**. Do not ask for that
file again. The owner **approved** the bounded, no-purchase source check below on
23 October. On 24 October the owner confirmed the free account and locally saved
key; the exact nine-request manifest is prepared. Actual access has **not started**:
remaining free allowance confirmation is still required. This does not
pass L14 or establish an investment result.
The machine-readable scope is [research-source-proposal.json](research-source-proposal.json).

## Proposed source and purpose

EODHD's Sandbox lists $0/month, one year of daily stock/ETF history and corporate
actions, 20 API calls/day and 20 requests/minute. Its EOD documentation says the
free tier supports any ticker within its history/call limits. Check available
allowance before each request; stop rather than upgrade or exceed the cap.
Sources: [pricing](https://eodhd.com/pricing),
[EOD API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes).

Published personal-use terms allow eligible nonprofessional individuals to store
and analyze data privately. They restrict shared access and redistribution.
The proposed use is a private, noncommercial, headless source-quality check only.
The owner must choose the provider and accept applicable account terms themselves;
recheck any additional terms at signup. The owner reports creating the free
account; no agent has accessed the token or requested market data. Do not buy,
attach payment details or activate a paid
trial. Source: [personal-use terms](https://eodhd.com/financial-apis/terms-conditions).

Proposed sample: **SPY.US, MSFT.US, AAPL.US**. These are source-check examples,
not recommendations, an approved trading universe or an economic-study plan.
They do not replace the protected six-share SPYL/Xetra/EUR proposal fixture.
Use only completed daily sessions from the preceding available year. Before the
first request, freeze exact dates, identities and the request manifest. An absent
instrument or insufficient coverage is a failed qualification, not permission to
substitute another asset or silently shorten the evaluation.

## Request and storage bounds

- Free account and owner-controlled token supplied only through an agreed secure
  local path after approval; never paste the token into chat or commit it.
- At most 12 HTTP requests and 20 documented API call units in this first check,
  further limited by the account's remaining free allowance; at most 20 requests
  per minute. No automatic retry, polling, subscription or upgrade.
- Allow only daily EOD, dividend and split endpoints, with up to three instrument
  identity lookups if their free eligibility and call cost are verified first.
  Do not call an endpoint with unknown cost. No news, intraday, bulk or broker API.
- Keep any response and provider-derived research output in a new ignored private
  local directory. No Git, public artifacts, chat extracts, app display or shared
  access. A public checkpoint may record request identities, hashes, qualification
  status and limitations without reproducing prices or research results.
- No provider enablement, application scheduler/configuration change or strategy
  run is included. Yahoo remains independently default-disabled.

## Qualification before any real study

Verify actual instrument identity, quote/dividend currencies, completed-session
coverage, duplicates, missing sessions and corporate actions. EODHD documents raw
OHLC, close adjusted for both splits and dividends, and split-adjusted volume.
Its action JSON distinguishes split-adjusted dividend `value` from historical
`unadjustedValue`; dividend currency may differ from the quote currency, and
payment/record/declaration dates are not universally available. Do not count a
dividend twice, assume raw-volume units or feed this schema into the Yahoo adapter.
Sources: [price semantics](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes),
[corporate actions](https://eodhd.com/financial-apis/api-splits-dividends).

One year is **not yet shown sufficient** for the unchanged engineering fixture's
120/60/60 sessions plus ten-session lookback. There is no five-year acceptance
minimum. Do not change the [fixture plan](research-fixture-plan.json), inspect a
held-out outcome for tuning or infer historical point-in-time availability from a
current download. Survivorship, revisions, FX, news/model availability, an approved
real-study universe, costs and capital remain separate unresolved research inputs.
The economic conclusion remains **INSUFFICIENT EVIDENCE**.

## Alternatives considered

Tiingo Starter is unsuitable for retained reproducible input: its terms, updated
6 October 2026, prohibit durable storage of Starter/trial data **and derived
results** (§1.6(a)). [Terms](https://app.tiingo.com/tos/).
IBKR history is not assumed available from the visible TWS quotes: most securities
API data requires a relevant Level 1 subscription. No entitlement or new connection
is verified or authorized here. [IBKR subscription introduction](https://www.interactivebrokers.com/docs/general/market-data-subscriptions/introduction).

## Decision and unchanged gates

Owner decision recorded: **“Approve the free data check”**, response to
`call_74bd452a29e64cecaf97bc2e99810272`. This satisfies the original requirement
for an explicit provider decision (attachment lines 47 and 57). It does not supply
the account, token, free allowance or actual data by itself. The owner subsequently
confirmed the free account and saved local key via `call_2934bdcbcb314d608ec359d6f892fe9f`;
no credential has been read by an agent. The pending question asks only whether at
least nine free API calls remain today.

The one-shot helper and 25 offline mock-only safety checks are retained under
`.qa/research-source-check-20261023/`; root reviewed the actual terminal-success
receipt, JUnit and code after the interruption without repeating the tests.
The exact plan requests EOD/dividends/splits for each sample, nine requests/units,
for 25 October 2025–23 October 2026. It is private, hash-bound and expires at
11:22:15 UTC on 25 October 2026. Before any fetch, inspect that same plan, its
hash and `started.json`/attempt/result receipts. A started or partial run must
never be blindly retried, copied to another directory or rearmed. Missing or
expired prerequisites permit preparation only, not a request. Source identity,
currency, coverage and point-in-time availability remain unverified even after
raw collection; there is no strategy run in this step.

Approval of this proposal authorizes only the bounded source check, subject
to obtaining the free account/token and checking current terms. It would not
authorize a purchase, actual Paper read/submission/cancellation, provider sharing,
production deployment or live trading. Both saved Paper read flags remain OFF;
external SDK writes stay denied. Final-host 24-hour and CPU-temperature checks
remain deferred; no laptop soak or sensor setup is requested.
