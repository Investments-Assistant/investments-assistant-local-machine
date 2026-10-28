# Historical replay and evidence

`src/tools/simulator.py` now uses `src/research/portfolio.py`. Existing strategy
workflows remain: buy and hold, monthly top-N momentum rotation, SMA crossings and
14-session Wilder RSI mean reversion. Cash is also available through the engine.
Signals use observed closes and can fill only at a later exchange session open.
The shared ledger retains Decimal cash, quantities, basis, fees, realized and
unrealized PnL, dividends and split adjustments. Open positions remain marked.

Assumptions are visible in the UI and saved evidence:10bps commission (minimum1
base-currency unit),5bps full spread,5bps slippage,10bps FX charge,1% volume
participation and0.001-share lot. Residual quantities expire after the attempted
fill; unavailable cash/liquidity/dated FX rejects or partially fills the order.
These research assumptions are not a broker tariff or execution guarantee.

The public history adapter requires source currency and a supported exchange.
[exchange_calendars4.13.2](https://github.com/gerrymanoim/exchange_calendars/releases/tag/4.13.2)
supplies exchange schedules; its
[calendar implementation](https://github.com/gerrymanoim/exchange_calendars/blob/master/exchange_calendars/exchange_calendar.py)
was checked alongside the installed version. Tests exercise Xetra holidays/DST.
FX daily closes are conservatively considered available at the following UTC
midnight; the adapter never substitutes publication dates for observed news times.

Yahoo/yfinance inputs remain provider-adjusted historical research data, not
qualified broker contracts. Split-adjusted share units are retained and split
actions are not reapplied; independent vendor corporate-action, delisting and
historical availability reconciliation is unverified. No provider request was
needed for the synthetic acceptance tests. Source limitations travel with results.
The Yahoo history adapter is disabled by default with
`YAHOO_HISTORICAL_DATA_ENABLED=false`; enabling it requires the operator to
review the provider's applicable data-use rights and explicitly authorize that
egress. The application does not assert that the package license grants rights
to Yahoo data. Synthetic adapter tests opt in only to mocked transport.
The engine separately tests raw split/dividend events with explicit fixtures.

Each saved run retains exact bars, source/version metadata, configuration, engine
hash and deterministic results in its user-owned database row. The ordinary history
list omits the large source snapshot. Download one run's evidence explicitly and
recompute it without network, inference or broker adapters:

```sh
.venv/bin/python scripts/replay_saved_evidence.py /path/to/replay-evidence.json
```

The command verifies input/code hashes and the entire recorded result. Changed code
or evidence must not silently claim reproduction. Legacy runs without source/cost
proof are labelled as such. Numerical float fields remain display compatibility;
the evidence contains exact Decimal strings used by the ledger.

These engineering fixtures establish accounting and workflow behavior, not economic
edge. Research remains INSUFFICIENT EVIDENCE and live readiness NO-GO. The original
fixed train/validation/holdout fixture evaluation remains separately documented;
real historical/news availability and forward observation are still required.

[Proposed forward observation plan](FORWARD_OBSERVATION.md) specifies the paired
comparisons, sample limitations, frozen versions, recovery and review rules. It
is unapproved and grants no provider/account/order or live authority.

## Model-score timing in the daily comparison

`NewsEvidence.available_at` identifies article availability;
`score_available_at` separately identifies when its model score is ready. A
non-fixture news comparison requires both aware timestamps, with score readiness
at or after article availability. Neither the article nor its score can influence
a signal before the decision close. Later-session fill and existing article-age
limits still apply. A newly completed score does not refresh an old article.

For example, news received at 16:00 on 3 January cannot justify a 09:00 fill on
4 January when the score only becomes ready at 10:00 that day. The earliest
eligible daily signal is the 4 January close, followed by the 5 January open.
The [timing regression and related accounting checks](evidence/research-score-timing-20261028.json)
cover this case, exact boundaries, invalid or absent readiness and hash changes.

The appended optional field preserves old synthetic constructor calls only when
`fixture=True`; results explicitly label their assumed score timing. Explicit
times are enforced even in fixtures. The timestamps remain supplied evidence or
predeclared counterfactual assumptions, not independent proof of collection,
training cutoff, licensing or investment value. Existing frozen pilot inputs and
results are preserved; they are not rerun or relabelled as news/model research.
