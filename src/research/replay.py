"""Daily-session replay. Signals at close can fill only at a later session open.

Prices/actions/FX are explicit input evidence, not inferred from a ticker. This is
not an intraday/news latency simulator and never imports a broker or order tool.
"""

import json
import math
from decimal import ROUND_DOWN, Decimal
import hashlib
from datetime import datetime, timedelta
import statistics
from dataclasses import asdict, dataclass

ZERO = Decimal(0)
ONE = Decimal(1)


@dataclass(frozen=True)
class Bar:
    symbol: str
    open_at: datetime
    close_at: datetime
    open: Decimal
    close: Decimal
    volume: Decimal
    currency: str
    fx_to_base: Decimal
    fx_as_of: datetime
    # Actions apply before the open to holdings carried from previous sessions.
    split: Decimal = ONE
    dividend: Decimal = ZERO


@dataclass(frozen=True)
class NewsEvidence:
    content_hash: str
    symbol: str
    published_at: datetime
    available_at: datetime
    score: Decimal
    source: str
    model_version: str


@dataclass(frozen=True)
class Costs:
    commission_bps: Decimal = Decimal("10")
    minimum_commission: Decimal = Decimal("1")
    spread_bps: Decimal = Decimal("5")
    slippage_bps: Decimal = Decimal("5")
    fx_bps: Decimal = Decimal("10")
    volume_participation: Decimal = Decimal("0.01")
    lot: Decimal = Decimal("0.001")
    signal_latency_seconds: int = 1
    max_fx_age_seconds: int = 86400
    max_signal_age_seconds: int = 345600


DEFAULT_COSTS = Costs()


def canonical_hash(value):
    return hashlib.sha256(
        json.dumps(value, default=str, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate(bars, costs, capital, base_currency):
    if not bars or not capital.is_finite() or capital <= 0 or len(base_currency) != 3:
        raise ValueError("Explicit positive capital, bars and base currency are required")
    for value in (
        costs.commission_bps,
        costs.minimum_commission,
        costs.spread_bps,
        costs.slippage_bps,
        costs.fx_bps,
        costs.volume_participation,
        costs.lot,
    ):
        if not value.is_finite() or value < 0:
            raise ValueError("Costs must be finite and nonnegative")
    if not 0 < costs.volume_participation <= 1 or costs.lot <= 0:
        raise ValueError("Invalid participation/lot")
    if any(
        value > 10000
        for value in (costs.commission_bps, costs.spread_bps, costs.slippage_bps, costs.fx_bps)
    ):
        raise ValueError("Invalid bps")
    if (
        min(costs.signal_latency_seconds, costs.max_fx_age_seconds, costs.max_signal_age_seconds)
        < 0
    ):
        raise ValueError("Negative time policy")
    # This version evaluates one qualified instrument; multi-asset FX/netting must
    # be explicitly implemented before claiming portfolio research equivalence.
    if len({b.symbol for b in bars}) != 1 or len({b.currency for b in bars}) != 1:
        raise ValueError("One qualified instrument/currency is required per replay")
    previous = None
    for bar in bars:
        if any(
            t.tzinfo is None or t.utcoffset() is None
            for t in (bar.open_at, bar.close_at, bar.fx_as_of)
        ):
            raise ValueError("Timezone-aware source timestamps required")
        if bar.open_at >= bar.close_at or previous and bar.open_at <= previous:
            raise ValueError("Sessions must be ordered and non-overlapping")
        previous = bar.close_at
        if any(
            not value.is_finite() or value <= 0
            for value in (bar.open, bar.close, bar.fx_to_base, bar.split)
        ):
            raise ValueError("Positive finite prices/FX/split required")
        if (
            not bar.volume.is_finite()
            or bar.volume < 0
            or not bar.dividend.is_finite()
            or bar.dividend < 0
        ):
            raise ValueError("Invalid volume/dividend")
        if bar.currency == base_currency and bar.fx_to_base != ONE:
            raise ValueError("Base-currency FX must equal one")
        if bar.fx_as_of > bar.open_at:
            raise ValueError("FX unavailable at the simulated execution time")


def replay(
    bars: list[Bar],
    *,
    capital: Decimal,
    base_currency: str,
    strategy="momentum",
    lookback=20,
    costs=DEFAULT_COSTS,
    news: list[NewsEvidence] | None = None,
    source_version: str,
    fixture=False,
):
    validate(bars, costs, capital, base_currency)
    if strategy not in {"cash", "buy_and_hold", "momentum", "momentum_news"} or lookback < 2:
        raise ValueError("Unsupported predeclared strategy/parameters")
    evidence = sorted(news or [], key=lambda item: (item.available_at, item.content_hash))
    for item in evidence:
        if (
            item.available_at.tzinfo is None
            or item.published_at.tzinfo is None
            or item.published_at > item.available_at
        ):
            raise ValueError("News needs publication and first availability timestamps")
        if (
            not item.score.is_finite()
            or not -1 <= item.score <= 1
            or not item.content_hash
            or not item.source
            or not item.model_version
        ):
            raise ValueError("Invalid attributable model/news evidence")
    cash, quantity, basis, fees, realized, dividends = capital, ZERO, ZERO, ZERO, ZERO, ZERO
    pending = None
    equity, exposures, trades, rejected, closed_pnl = [], [], [], [], []
    volume_notional = ZERO
    for i, bar in enumerate(bars):
        # Corporate actions are input events, not discovered using future prices.
        quantity *= bar.split
        distribution = quantity * bar.dividend * bar.fx_to_base
        cash += distribution
        dividends += distribution
        if pending:
            action, signal_at, source_ids = pending
            pending = None  # unfilled residuals expire; no automatic stale replay
            age = (bar.open_at - signal_at).total_seconds()
            stale_fx = (bar.open_at - bar.fx_as_of).total_seconds() > costs.max_fx_age_seconds
            if age < costs.signal_latency_seconds or age > costs.max_signal_age_seconds or stale_fx:
                rejected.append(
                    {
                        "at": bar.open_at.isoformat(),
                        "reason": "STALE_OR_UNAVAILABLE_EXECUTION_EVIDENCE",
                    }
                )
            else:
                # Spread is full bid/ask width; crossing costs half the width.
                impact = (costs.spread_bps / 2 + costs.slippage_bps) / 10000
                px = bar.open * (1 + impact if action == "buy" else 1 - impact) * bar.fx_to_base
                fee_rate = (
                    costs.commission_bps + (costs.fx_bps if bar.currency != base_currency else ZERO)
                ) / 10000
                maximum = bar.volume * costs.volume_participation
                desired = (
                    max(ZERO, (cash - costs.minimum_commission) / (px * (1 + fee_rate)))
                    if action == "buy"
                    else quantity
                )
                filled = (min(maximum, desired) / costs.lot).to_integral_value(
                    rounding=ROUND_DOWN
                ) * costs.lot
                notional = filled * px
                fee = max(costs.minimum_commission, notional * fee_rate)
                if filled <= 0 or action == "sell" and notional <= fee:
                    rejected.append(
                        {"at": bar.open_at.isoformat(), "reason": "NO_EXECUTABLE_LIQUIDITY_OR_SIZE"}
                    )
                else:
                    if action == "buy":
                        cash -= notional + fee
                        basis += notional + fee
                        quantity += filled
                    else:
                        released_basis = basis * filled / quantity
                        pnl = notional - fee - released_basis
                        realized += pnl
                        closed_pnl.append(pnl)
                        basis -= released_basis
                        quantity -= filled
                        cash += notional - fee
                    fees += fee
                    volume_notional += notional
                    trades.append(
                        {
                            "signal_at": signal_at.isoformat(),
                            "filled_at": bar.open_at.isoformat(),
                            "action": action,
                            "quantity": str(filled),
                            "price_in_base": str(px),
                            "fee": str(fee),
                            "status": "partial_expired" if filled < desired else "filled",
                            "source_ids": source_ids,
                        }
                    )
                    if cash < 0 or quantity < 0:
                        raise AssertionError("Replay created leverage or a short position")
        holding_value = quantity * bar.close * bar.fx_to_base
        value = cash + holding_value
        equity.append(value)
        exposures.append(holding_value / value if value else ZERO)
        target = None
        source_ids = []
        if strategy == "buy_and_hold" and i == 0:
            target = True
        elif strategy in {"momentum", "momentum_news"} and i >= lookback:
            # Split-adjust past observed close into today's share units. Dividends
            # are cash flows; this simple price signal does not reinvest them.
            adjustment = math.prod(b.split for b in bars[i - lookback + 1 : i + 1])
            target = bar.close > bars[i - lookback].close / adjustment
            if strategy == "momentum_news" and target:
                known = {
                    n.content_hash: n
                    for n in evidence
                    if n.symbol == bar.symbol
                    and n.available_at <= bar.close_at
                    and bar.close_at - n.available_at <= timedelta(days=3)
                }
                source_ids = sorted(known)
                target = bool(known) and sum(n.score for n in known.values()) > 0
                if not target:
                    rejected.append({"at": bar.close_at.isoformat(), "reason": "NEWS_ABSTENTION"})
        if target is True and quantity == 0:
            pending = ("buy", bar.close_at, source_ids)
        elif target is False and quantity > 0:
            pending = ("sell", bar.close_at, source_ids)
    if pending:
        rejected.append({"at": bars[-1].close_at.isoformat(), "reason": "NO_LATER_SESSION"})
    returns = [float(equity[0] / capital - 1)] + [
        float(equity[i] / equity[i - 1] - 1) for i in range(1, len(equity))
    ]
    peak = capital
    drawdown = ZERO
    for value in equity:
        peak = max(peak, value)
        drawdown = min(drawdown, value / peak - 1)
    volatility = statistics.stdev(returns) if len(returns) > 1 else 0
    result = {
        "strategy": strategy,
        "base_currency": base_currency,
        "source_version": source_version,
        "fixture": fixture,
        "valuation_status": "partial"
        if any((b.close_at - b.fx_as_of).total_seconds() > costs.max_fx_age_seconds for b in bars)
        else "complete",
        "initial_capital": str(capital),
        "final_value": str(equity[-1]),
        "total_return_pct": float((equity[-1] / capital - 1) * 100),
        "max_drawdown_pct": float(drawdown * 100),
        "annual_volatility_pct": volatility * math.sqrt(252) * 100,
        "sharpe_zero_rf_252": statistics.mean(returns) / volatility * math.sqrt(252)
        if volatility
        else None,
        "average_exposure": float(statistics.mean(exposures)),
        "turnover": str(volume_notional / capital),
        "trade_count": len(trades),
        "exit_sample_size": len(closed_pnl),
        "hit_rate": sum(p > 0 for p in closed_pnl) / len(closed_pnl) if closed_pnl else None,
        "fees": str(fees),
        "realized_pnl": str(realized),
        "dividends": str(dividends),
        "unrealized_pnl": str(quantity * bars[-1].close * bars[-1].fx_to_base - basis),
        "cash": str(cash),
        "quantity": str(quantity),
        "trades": trades,
        "rejected": rejected,
        "equity": [
            {"at": b.close_at.isoformat(), "value": str(v)}
            for b, v in zip(bars, equity, strict=True)
        ],
        "conventions": {
            "annual_sessions": 252,
            "risk_free_rate": 0,
            "fill": "later session open",
            "costs": asdict(costs),
            "open_positions": "marked, not silently liquidated",
            "universe": (
                "one supplied instrument; survivorship/delisting completeness not established"
            ),
        },
        "input_hash": canonical_hash(
            {
                "bars": [asdict(b) for b in bars],
                "news": [asdict(n) for n in evidence],
                "costs": asdict(costs),
                "strategy": strategy,
                "lookback": lookback,
                "capital": capital,
                "base_currency": base_currency,
                "source_version": source_version,
                "fixture": fixture,
            }
        ),
    }
    return result
