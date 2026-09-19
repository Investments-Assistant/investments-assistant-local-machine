"""Provider normalization. Display rounding must never change source precision."""

from decimal import Decimal, InvalidOperation
from datetime import datetime


def decimal_value(value: object) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def portfolio_number(value: object) -> float | None:
    value = decimal_value(value)
    return float(value) if value is not None else None


def first_portfolio_number(data: dict, *keys: str) -> float | None:
    for key in keys:
        value = portfolio_number(data.get(key))
        if value is not None:
            return value
    return None


def usd_value(value: object, data: dict) -> float | None:
    amount = decimal_value(value)
    if amount is None:
        return None
    currency = str(data.get("currency") or "").upper()
    if currency == "USD":
        return float(amount)
    rate = decimal_value(data.get("fx_to_usd"))
    try:
        timestamp = datetime.fromisoformat(str(data.get("fx_as_of")).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            return None
    except ValueError:
        return None
    if not currency or rate is None or rate <= 0:
        return None
    return float(amount * rate)


def portfolio_position(position: dict) -> dict:
    quantity = first_portfolio_number(position, "qty", "quantity", "available", "free")
    price = first_portfolio_number(position, "current_price", "market_price", "price")
    value = first_portfolio_number(position, "market_value", "value")
    pnl = first_portfolio_number(position, "unrealized_pnl", "unrealized_pl")
    return {
        **position,
        "symbol": str(position.get("symbol") or position.get("asset") or "Unknown"),
        "quantity": quantity,
        "quantity_exact": str(
            next(
                (
                    decimal_value(position[k])
                    for k in ("qty", "quantity", "available", "free")
                    if decimal_value(position.get(k)) is not None
                ),
                "",
            )
        )
        or None,
        "currency": position.get("currency"),
        "price": price,
        "market_value": value,
        "price_usd": usd_value(price, position),
        "value_usd": usd_value(value, position),
        "pnl_usd": usd_value(pnl, position),
        "valuation_status": "available"
        if usd_value(value, position) is not None
        else "unavailable",
    }
