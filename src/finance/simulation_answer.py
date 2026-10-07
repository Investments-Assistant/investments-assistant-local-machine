"""Truthful display of calculated simulations, including unavailable storage/data."""

from decimal import Decimal, InvalidOperation


def simulation_answer(result):
    unavailable = "Simulation result unavailable: required calculation evidence is missing or invalid."
    if not isinstance(result, dict):
        return unavailable
    if result.get("error"):
        return f"I could not run the simulation: {result['error']}"
    if result.get("status") not in {None, "complete", "partial_failure"}:
        return unavailable
    required = ("initial_capital", "final_value", "total_return_pct", "trades_count")
    try:
        numbers = {key: Decimal(str(result[key])) for key in required}
        if not all(value.is_finite() for value in numbers.values()):
            return unavailable
    except (KeyError, InvalidOperation, ValueError, TypeError):
        return unavailable
    symbols = result.get("symbols")
    if (not isinstance(symbols, list) or not symbols or not all(isinstance(s, str) and s for s in symbols)
            or not result.get("period_start") or not result.get("period_end")):
        return unavailable
    currency = result.get("base_currency", "USD")  # The legacy tool contract has explicit USD capital.
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha() or not currency.isupper():
        return unavailable
    status = ("Simulation calculated; persistence incomplete"
              if result.get("status") == "partial_failure" else "Simulation complete")
    return (
        f"# {status} — {result.get('name', 'Historical simulation')}\n\n"
        f"- **Symbols:** {', '.join(result['symbols'])}\n"
        f"- **Period:** {result['period_start']} → {result['period_end']}\n"
        f"- **Fake starting capital:** {numbers['initial_capital']:,.2f} {currency}\n"
        f"- **Ending value:** {numbers['final_value']:,.2f} {currency}\n"
        f"- **Total return:** {numbers['total_return_pct']:+.2f}%\n"
        f"- **Sharpe ratio:** {result.get('sharpe_ratio', 'unavailable')}\n"
        f"- **Maximum drawdown:** {result.get('max_drawdown_pct', 'unavailable')}%\n"
        f"- **Trades:** {numbers['trades_count']}\n\n"
        "This is a historical backtest using fake money. It does not place orders or predict future returns."
    )
