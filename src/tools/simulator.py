"""Investment simulator and backtester.

Supported strategies:
- buy_and_hold: buy on day 1, hold to end
- sma_crossover: buy when fast SMA crosses above slow SMA, sell on crossunder
- rsi_mean_reversion: buy when RSI < rsi_buy, sell when RSI > rsi_sell
- momentum: buy top N performers over lookback window, rebalance monthly
"""

from __future__ import annotations

import math
from decimal import Decimal
from datetime import UTC, datetime
from dataclasses import asdict

import pandas as pd

from src.agent.utils.logger import get_logger

logger = get_logger(__name__)


def _download(symbols: list[str], start: str, end: str, base_currency: str = "USD"):
    from src.research.history import load_history

    return load_history(symbols, start, end, base_currency)


def _momentum(
    prices: pd.DataFrame,
    capital: float,
    lookback_days: int = 60,
    top_n: int = 3,
) -> tuple[pd.Series, list[dict]]:
    """Monthly top-momentum rotation using only prices known at rebalance time."""
    if lookback_days < 2 or top_n < 1:
        raise ValueError("lookback_days must be >= 2 and top_n must be >= 1")
    equity = pd.Series(float(capital), index=prices.index)
    holdings: dict[str, float] = {}
    previous_month = None
    cash = float(capital)
    last_prices: dict[str, float] = {}
    trades: list[dict] = []

    for i, date in enumerate(prices.index):
        available = prices.loc[date].dropna()
        last_prices.update({symbol: float(value) for symbol, value in available.items()})
        if i >= lookback_days and not available.empty:
            month = date.to_period("M")
            if month != previous_month and all(symbol in available for symbol in holdings):
                previous_value = cash + sum(
                    shares * float(available[symbol]) for symbol, shares in holdings.items()
                )
                lookback = prices.iloc[i - lookback_days]
                returns = (available / lookback.reindex(available.index) - 1).dropna()
                selected = returns.nlargest(top_n)
                # Do not force a purchase into a negative-trend asset.
                selected = selected[selected > 0]
                for symbol, shares in holdings.items():
                    if symbol in available:
                        trades.append(
                            {
                                "date": str(date.date()),
                                "action": "SELL",
                                "symbol": symbol,
                                "shares": round(shares, 6),
                                "reason": "monthly momentum rebalance",
                            }
                        )
                holdings = {}
                cash = previous_value
                if not selected.empty:
                    cash = 0.0
                    allocation = previous_value / len(selected)
                    for symbol in selected.index:
                        shares = allocation / float(available[symbol])
                        holdings[symbol] = shares
                        trades.append(
                            {
                                "date": str(date.date()),
                                "action": "BUY",
                                "symbol": symbol,
                                "shares": round(shares, 6),
                                "momentum_pct": round(float(selected[symbol] * 100), 2),
                            }
                        )
                previous_month = month

        value = sum(shares * last_prices[symbol] for symbol, shares in holdings.items())
        equity.iloc[i] = cash + value
    return equity, trades


def _metrics(equity: pd.Series) -> dict:
    """Compute performance metrics from equity curve."""
    if equity.empty or len(equity) < 2:
        return {}
    total_ret = (equity.iloc[-1] / equity.iloc[0] - 1) * 100
    daily_ret = equity.pct_change().dropna()
    annual_factor = 252
    sharpe = 0.0 if daily_ret.std() == 0 else float(daily_ret.mean() / daily_ret.std() * math.sqrt(annual_factor))
    # Max drawdown
    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max
    max_dd = float(drawdown.min() * 100)
    return {
        "total_return_pct": round(float(total_ret), 2),
        "sharpe_ratio": round(sharpe, 3),
        "max_drawdown_pct": round(max_dd, 2),
        "annual_volatility_pct": round(float(daily_ret.std() * math.sqrt(annual_factor) * 100), 2),
    }


def _buy_and_hold(prices: pd.DataFrame, capital: float) -> tuple[pd.Series, list[dict]]:
    # Equal-weight portfolio, buy on first day, sell on last
    n = len(prices.columns)
    alloc = capital / n
    shares = {sym: alloc / prices[sym].iloc[0] for sym in prices.columns}
    equity = sum(shares[sym] * prices[sym] for sym in prices.columns)
    trades = [
        {
            "date": str(prices.index[0].date()),
            "action": "BUY",
            "symbol": sym,
            "shares": round(shares[sym], 4),
        }
        for sym in prices.columns
    ] + [
        {
            "date": str(prices.index[-1].date()),
            "action": "SELL",
            "symbol": sym,
            "shares": round(shares[sym], 4),
        }
        for sym in prices.columns
    ]
    return equity, trades


def _crossover_signal(sma_fast: pd.Series, sma_slow: pd.Series, i: int) -> str | None:
    """Return 'buy', 'sell', or None based on fast/slow SMA crossover at index i."""
    if sma_fast.iloc[i] > sma_slow.iloc[i] and sma_fast.iloc[i - 1] <= sma_slow.iloc[i - 1]:
        return "buy"
    if sma_fast.iloc[i] < sma_slow.iloc[i] and sma_fast.iloc[i - 1] >= sma_slow.iloc[i - 1]:
        return "sell"
    return None


def _sma_crossover(
    prices: pd.DataFrame,
    capital: float,
    fast: int = 20,
    slow: int = 50,
) -> tuple[pd.Series, list[dict]]:
    # Trade each symbol independently
    equity = pd.Series(0.0, index=prices.index)
    trades = []
    for sym in prices.columns:
        p = prices[sym].dropna()
        sma_fast = p.rolling(fast).mean()
        sma_slow = p.rolling(slow).mean()
        position = 0.0
        sym_cash = capital / len(prices.columns)
        sym_equity = pd.Series(sym_cash, index=prices.index)

        for i in range(1, len(p)):
            date = p.index[i]
            signal = _crossover_signal(sma_fast, sma_slow, i)
            if signal == "buy" and sym_cash > 0 and position == 0:
                position = sym_cash / p.iloc[i]
                sym_cash = 0.0
                trades.append(
                    {
                        "date": str(date.date()),
                        "action": "BUY",
                        "symbol": sym,
                        "price": round(p.iloc[i], 4),
                        "shares": round(position, 4),
                    }
                )
            elif signal == "sell" and position > 0:
                sym_cash = position * p.iloc[i]
                trades.append(
                    {
                        "date": str(date.date()),
                        "action": "SELL",
                        "symbol": sym,
                        "price": round(p.iloc[i], 4),
                        "proceeds": round(sym_cash, 2),
                    }
                )
                position = 0.0
            sym_equity.loc[date] = sym_cash + position * p.iloc[i]
        equity += sym_equity
    return equity, trades


def _rsi_mean_reversion(
    prices: pd.DataFrame,
    capital: float,
    rsi_buy: float = 30.0,
    rsi_sell: float = 70.0,
) -> tuple[pd.Series, list[dict]]:
    from ta.momentum import RSIIndicator

    equity = pd.Series(0.0, index=prices.index)
    trades = []
    for sym in prices.columns:
        p = prices[sym].dropna()
        rsi = RSIIndicator(close=p, window=14).rsi()
        sym_cash = capital / len(prices.columns)
        position = 0.0
        sym_equity = pd.Series(sym_cash, index=prices.index)

        for i in range(14, len(p)):
            date = p.index[i]
            r = rsi.iloc[i]
            if r < rsi_buy and position == 0 and sym_cash > 0:
                position = sym_cash / p.iloc[i]
                sym_cash = 0.0
                trades.append(
                    {
                        "date": str(date.date()),
                        "action": "BUY",
                        "symbol": sym,
                        "rsi": round(r, 1),
                        "price": round(p.iloc[i], 4),
                    }
                )
            elif r > rsi_sell and position > 0:
                sym_cash = position * p.iloc[i]
                trades.append(
                    {
                        "date": str(date.date()),
                        "action": "SELL",
                        "symbol": sym,
                        "rsi": round(r, 1),
                        "proceeds": round(sym_cash, 2),
                    }
                )
                position = 0.0
            sym_equity.loc[date] = sym_cash + position * p.iloc[i]
        equity += sym_equity
    return equity, trades


def _simulate(
    name: str,
    symbols: list[str],
    strategy: dict,
    initial_capital: float = 10_000.0,
    period_start: str = "2023-01-01",
    period_end: str | None = None,
    base_currency: str = "USD",
) -> dict:
    """Run cost-aware daily replay; persistable evidence includes exact source bars."""
    from src.research.replay import Costs
    from src.research.portfolio import replay_portfolio

    end = period_end or datetime.now(UTC).strftime("%Y-%m-%d")
    if not symbols or initial_capital <= 0 or not math.isfinite(initial_capital):
        return {"error": "Provide symbols and positive finite capital."}
    stype, params = strategy.get("type", "buy_and_hold"), strategy.get("params", {})
    if stype not in {"buy_and_hold", "momentum", "sma_crossover", "rsi_mean_reversion", "cash"}:
        return {"error": "Unsupported strategy."}
    try:
        series, source = _download(symbols, period_start, end, base_currency)
        costs = Costs()
        result = replay_portfolio(
            series,
            capital=Decimal(str(initial_capital)),
            base_currency=base_currency,
            strategy=stype,
            params=params,
            costs=costs,
            source=source,
        )
    except Exception as exc:
        logger.warning("Historical replay unavailable: %s", type(exc).__name__)
        return {
            "error": "Historical replay unavailable: "
            + (str(exc) if isinstance(exc, ValueError) else type(exc).__name__)
        }
    # Decimal strings remain in durable evidence; floats below are display compatibility only.
    import json

    evidence = json.loads(
        json.dumps(
            dict(
                result=result,
                configuration=dict(
                    strategy=stype,
                    params=params,
                    capital=str(initial_capital),
                    base_currency=base_currency,
                    costs=asdict(costs),
                ),
                bars={symbol: [asdict(bar) for bar in bars] for symbol, bars in series.items()},
            ),
            default=str,
        )
    )
    documented_strategy = dict(strategy, base_currency=base_currency, research=evidence)
    equity = pd.Series(
        [float(point["value"]) for point in result["equity"]],
        index=pd.to_datetime([point["at"] for point in result["equity"]], utc=True),
    )
    weekly = equity.resample("W").last().dropna()
    return dict(
        name=name,
        strategy=documented_strategy,
        symbols=symbols,
        base_currency=base_currency,
        initial_capital=initial_capital,
        final_value=float(result["final_value"]),
        final_value_exact=result["final_value"],
        total_return_pct=result["total_return_pct"],
        max_drawdown_pct=result["max_drawdown_pct"],
        sharpe_ratio=result["sharpe_ratio"],
        annual_volatility_pct=result["annual_volatility_pct"],
        period_start=period_start,
        period_end=end,
        trades_count=len(result["trades"]),
        trades_sample=result["trades"][:20],
        equity_curve=[
            dict(date=str(at.date()), value=float(value)) for at, value in weekly.items()
        ],
        research_status="INSUFFICIENT_EVIDENCE",
        source_limitations=source.get("limitations", []),
        assumptions=result["conventions"],
        input_hash=result["input_hash"],
    )


def run_simulation(
    name: str,
    symbols: list[str],
    strategy: dict,
    initial_capital: float = 10000.0,
    period_start: str = "2023-01-01",
    period_end: str | None = None,
    base_currency: str = "USD",
) -> dict:
    from src.operations.workloads import WorkloadBusy, simulation_work

    try:
        return simulation_work.run(
            _simulate,
            name,
            symbols,
            strategy,
            initial_capital,
            period_start,
            period_end,
            base_currency,
        )
    except WorkloadBusy as exc:
        return {"error": str(exc)}


async def run_simulation_async(**kwargs) -> dict:
    from src.operations.workloads import WorkloadBusy, simulation_work

    try:
        return await simulation_work.arun(_simulate, **kwargs)
    except WorkloadBusy as exc:
        return {"error": str(exc)}
    except TimeoutError:
        return {"error": "SIMULATION_TIMEOUT_WORKER_MAY_STILL_BE_STOPPING"}
