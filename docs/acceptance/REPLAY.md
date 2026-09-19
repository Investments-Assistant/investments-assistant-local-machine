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
