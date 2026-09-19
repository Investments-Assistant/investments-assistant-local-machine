"""Cost-aware daily portfolio replay with a shared cash ledger and later fills.

Decisions use all available closes at the end of a UTC session-date group. They
cannot fill before that decision plus latency. Missing sessions never create
synthetic prices or fills; carried marks are labelled in the evidence.
"""

import math
from decimal import ROUND_DOWN, Decimal
import hashlib
from pathlib import Path
import statistics
from collections import defaultdict
from dataclasses import asdict

from src.research.replay import Bar, Costs, validate, canonical_hash

ZERO = Decimal(0)
ONE = Decimal(1)


def _targets(history, strategy, params, month, previous_month, rsi_states):
    symbols = sorted(history)
    if strategy == "buy_and_hold":
        return (
            {symbol: ONE / len(symbols) for symbol in symbols} if previous_month is None else None
        )
    if strategy == "cash":
        return {}
    if strategy == "momentum":
        lookback = int(params.get("lookback_days", 60))
        top_n = int(params.get("top_n", min(3, len(symbols))))
        if not 2 <= lookback <= 1000 or not 1 <= top_n <= len(symbols):
            raise ValueError("Invalid momentum lookback/top_n")
        if month == previous_month or any(len(history[s]) <= lookback for s in symbols):
            return None
        ranked = sorted(
            ((history[s][-1] / history[s][-lookback - 1] - 1, s) for s in symbols), reverse=True
        )
        selected = [symbol for value, symbol in ranked[:top_n] if value > 0]
        return {symbol: ONE / len(selected) for symbol in selected} if selected else {}
    targets = {}
    for symbol in symbols:
        prices = history[symbol]
        if strategy == "sma_crossover":
            fast, slow = int(params.get("fast", 20)), int(params.get("slow", 50))
            if not 1 <= fast < slow <= 1000:
                raise ValueError("SMA requires 1 <= fast < slow <= 1000")
            if len(prices) <= slow:
                continue
            current = sum(prices[-fast:]) / fast - sum(prices[-slow:]) / slow
            prior = sum(prices[-fast - 1 : -1]) / fast - sum(prices[-slow - 1 : -1]) / slow
            if current > 0 and prior <= 0:
                target = True
            elif current < 0 and prior >= 0:
                target = False
            else:
                continue
        elif strategy == "rsi_mean_reversion":
            buy, sell = (
                Decimal(str(params.get("rsi_buy", 30))),
                Decimal(str(params.get("rsi_sell", 70))),
            )
            if not buy.is_finite() or not sell.is_finite() or not 0 <= buy < sell <= 100:
                raise ValueError("RSI thresholds require 0 <= buy < sell <= 100")
            state = rsi_states[symbol]
            if state["count"] < 15:
                continue
            gain, loss = state["gain"], state["loss"]
            rsi = 100 if loss == 0 else 100 - 100 / (1 + gain / loss)
            if buy <= rsi <= sell:
                continue  # retain the prior target between thresholds
            target = rsi < buy
        else:
            raise ValueError("Unsupported strategy")
        targets[symbol] = ONE / len(symbols) if target else ZERO
    return targets


def replay_portfolio(
    series: dict[str, list[Bar]],
    *,
    capital: Decimal,
    base_currency: str,
    strategy: str,
    params: dict,
    costs: Costs,
    source: dict,
):
    if not series or len(series) > 20 or sum(map(len, series.values())) > 100000:
        raise ValueError("Provide 1..20 instruments and at most100000 session bars")
    if strategy not in {"cash", "buy_and_hold", "momentum", "sma_crossover", "rsi_mean_reversion"}:
        raise ValueError("Unsupported strategy")
    for bars in series.values():
        validate(bars, costs, capital, base_currency)
    if any(any(bar.symbol != symbol for bar in bars) for symbol, bars in series.items()):
        raise ValueError("Instrument series identity mismatch")
    days = defaultdict(list)
    for bars in series.values():
        for bar in bars:
            days[bar.close_at.date()].append(bar)
    cash, fees, realized, dividends, turnover = capital, ZERO, ZERO, ZERO, ZERO
    quantity = {symbol: ZERO for symbol in series}
    basis = dict(quantity)
    history = {symbol: [] for symbol in series}
    rsi_states = {symbol: dict(gain=ZERO, loss=ZERO, count=0) for symbol in series}
    marks, pending, weights = {}, {}, {}
    curve, trades, rejected, pnl_samples, exposure_samples = [], [], [], [], []
    previous_month = None
    last_decision = None
    for day, bars in sorted(days.items()):
        # Equal-time sells precede buys, but never reorder distinct exchange opens.
        for bar in sorted(
            bars, key=lambda b: (b.open_at, pending.get(b.symbol, (ZERO, None))[0] >= 0, b.symbol)
        ):
            symbol = bar.symbol
            quantity[symbol] *= bar.split
            history[symbol] = [value / bar.split for value in history[symbol]]
            rsi_states[symbol]["gain"] /= bar.split
            rsi_states[symbol]["loss"] /= bar.split
            distribution = quantity[symbol] * bar.dividend * bar.fx_to_base
            cash += distribution
            dividends += distribution
            if symbol not in pending:
                continue
            delta, signal_at = pending.pop(symbol)
            delta *= bar.split
            age = (bar.open_at - signal_at).total_seconds()
            if (
                not costs.signal_latency_seconds <= age <= costs.max_signal_age_seconds
                or (bar.open_at - bar.fx_as_of).total_seconds() > costs.max_fx_age_seconds
            ):
                rejected.append(
                    dict(
                        symbol=symbol,
                        at=bar.open_at.isoformat(),
                        reason="STALE_OR_UNAVAILABLE_EXECUTION_EVIDENCE",
                    )
                )
                continue
            buying = delta > 0
            impact = (costs.spread_bps / 2 + costs.slippage_bps) / 10000
            price = bar.open * bar.fx_to_base * (1 + impact if buying else 1 - impact)
            fee_rate = (
                costs.commission_bps + (costs.fx_bps if bar.currency != base_currency else ZERO)
            ) / 10000
            desired = abs(delta)
            capacity = (
                max(ZERO, (cash - costs.minimum_commission) / (price * (1 + fee_rate)))
                if buying
                else quantity[symbol]
            )
            filled = (
                min(desired, capacity, bar.volume * costs.volume_participation) / costs.lot
            ).to_integral_value(rounding=ROUND_DOWN) * costs.lot
            notional = filled * price
            fee = max(costs.minimum_commission, notional * fee_rate)
            if filled <= 0 or not buying and notional <= fee:
                rejected.append(
                    dict(
                        symbol=symbol,
                        at=bar.open_at.isoformat(),
                        reason="NO_EXECUTABLE_CASH_LIQUIDITY_OR_SIZE",
                    )
                )
                continue
            if buying:
                cash -= notional + fee
                quantity[symbol] += filled
                basis[symbol] += notional + fee
            else:
                released = basis[symbol] * filled / quantity[symbol]
                pnl = notional - fee - released
                realized += pnl
                pnl_samples.append(pnl)
                cash += notional - fee
                quantity[symbol] -= filled
                basis[symbol] -= released
            if cash < 0 or quantity[symbol] < 0:
                raise AssertionError("Replay created leverage or a short position")
            fees += fee
            turnover += notional
            trades.append(
                dict(
                    symbol=symbol,
                    signal_at=signal_at.isoformat(),
                    filled_at=bar.open_at.isoformat(),
                    action="BUY" if buying else "SELL",
                    quantity=str(filled),
                    price_in_base=str(price),
                    fee=str(fee),
                    status="partial_expired" if filled < desired else "filled",
                )
            )
        for bar in bars:
            marks[bar.symbol] = bar
            price = bar.close * bar.fx_to_base
            state = rsi_states[bar.symbol]
            previous = history[bar.symbol][-1] if history[bar.symbol] else price
            change = price - previous
            # Match ta.RSIIndicator's Wilder alpha=1/14, adjust=False convention.
            state["gain"] = state["gain"] * Decimal(13) / 14 + max(ZERO, change) / 14
            state["loss"] = state["loss"] * Decimal(13) / 14 + max(ZERO, -change) / 14
            state["count"] += 1
            history[bar.symbol].append(price)
        at = max(bar.close_at for bar in bars)
        held = sum(
            (quantity[symbol] * marks[symbol].close * marks[symbol].fx_to_base for symbol in marks),
            ZERO,
        )
        value = cash + held
        exposure_samples.append(held / value if value else ZERO)
        carried = [
            symbol for symbol in marks if quantity[symbol] and marks[symbol].close_at.date() != day
        ]
        curve.append(dict(at=at.isoformat(), value=str(value), carried_marks=carried))
        # Wait for at least one genuine observed close for each requested instrument.
        if all(history.values()):
            month = day.strftime("%Y-%m")
            target = _targets(history, strategy, params, month, previous_month, rsi_states)
            if target is not None:
                previous_month = month
                changed = (
                    {symbol: target.get(symbol, ZERO) for symbol in series}
                    if strategy in {"momentum", "buy_and_hold", "cash"}
                    else target
                )
                for symbol, weight in changed.items():
                    if weights.get(symbol) == weight and strategy != "momentum":
                        continue
                    weights[symbol] = weight
                    mark = marks[symbol]
                    target_quantity = value * weight / (mark.close * mark.fx_to_base)
                    delta = target_quantity - quantity[symbol]
                    if abs(delta) >= costs.lot:
                        pending[symbol] = (delta, at)
                last_decision = at
    for symbol in pending:
        rejected.append(
            dict(symbol=symbol, at=last_decision.isoformat(), reason="NO_LATER_SESSION")
        )
    values = [Decimal(point["value"]) for point in curve]
    returns = [float(values[0] / capital - 1)] + [
        float(b / a - 1) for a, b in zip(values, values[1:], strict=False)
    ]
    sigma = statistics.stdev(returns) if len(returns) > 1 else 0
    high, drawdown = capital, ZERO
    for value in values:
        high = max(high, value)
        drawdown = min(drawdown, value / high - 1)
    engine_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    return dict(
        engine_sha256=engine_hash,
        parameters=dict(strategy=strategy, params=params),
        initial_capital=str(capital),
        final_value=str(values[-1]),
        total_return_pct=float((values[-1] / capital - 1) * 100),
        max_drawdown_pct=float(drawdown * 100),
        sharpe_ratio=statistics.mean(returns) / sigma * math.sqrt(252) if sigma else None,
        annual_volatility_pct=sigma * math.sqrt(252) * 100,
        equity=curve,
        trades=trades,
        rejected=rejected,
        fees=str(fees),
        dividends=str(dividends),
        realized_pnl=str(realized),
        unrealized_pnl=str(
            sum(
                (quantity[s] * marks[s].close * marks[s].fx_to_base - basis[s] for s in series),
                ZERO,
            )
        ),
        cash=str(cash),
        quantities={s: str(q) for s, q in quantity.items()},
        average_exposure=float(statistics.mean(exposure_samples)),
        turnover=str(turnover / capital),
        exit_sample_size=len(pnl_samples),
        hit_rate=sum(p > 0 for p in pnl_samples) / len(pnl_samples) if pnl_samples else None,
        base_currency=base_currency,
        source=source,
        input_hash=canonical_hash(
            dict(
                engine_sha256=engine_hash,
                series={s: [asdict(b) for b in bars] for s, bars in series.items()},
                capital=capital,
                base_currency=base_currency,
                strategy=strategy,
                params=params,
                costs=asdict(costs),
                source=source,
            )
        ),
        conventions=dict(
            costs=asdict(costs),
            signal="end of observed UTC session-date group",
            fill="later actual session open",
            annual_sessions=252,
            risk_free_rate=0,
            terminal_holdings="marked without fictional sale",
            missing_sessions="no fabricated prices/fills; carried marks enumerated",
        ),
    )
