"""Deterministic non-live risk checks independent of inference latency."""

import json
from decimal import Decimal, InvalidOperation
import hashlib
from datetime import datetime, timedelta


class PolicyDenied(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def positive(value) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise PolicyDenied("INVALID_NUMBER") from None
    if not result.is_finite() or result <= 0 or result >= Decimal("1e18"):
        raise PolicyDenied("INVALID_NUMBER")
    # Ledger precision is explicit; reject quantities that cannot be represented.
    if result != result.quantize(Decimal("0.0000000001")):
        raise PolicyDenied("UNSUPPORTED_PRECISION")
    return result


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def order_details(order) -> dict:
    def canonical(value):
        return str(value.normalize()) if isinstance(value, Decimal) else str(value)

    return {
        key: canonical(getattr(order, key))
        for key in (
            "account_id",
            "user_id",
            "session_id",
            "instrument_id",
            "side",
            "quantity",
            "limit_price",
            "expires_at",
            "idempotency_key",
        )
    }


def preflight(account, instrument, quantity, price, side: str, now: datetime) -> Decimal:
    """Trusted simulator feed supplies contract multiplier/FX; client estimates absent."""
    if account.halted:
        raise PolicyDenied("OPERATOR_HALTED")
    if account.mandate.get("environment") != "simulator":
        raise PolicyDenied("ENVIRONMENT_NOT_AUTHORIZED")
    if instrument.account_id != account.id:
        raise PolicyDenied("INSTRUMENT_ACCOUNT_MISMATCH")
    if instrument.protected:
        raise PolicyDenied("PROTECTED_ALLOCATION")
    if instrument.security_type not in {"stock", "etf"} or instrument.multiplier != 1:
        raise PolicyDenied("UNSUPPORTED_INSTRUMENT")
    if side != "buy":
        # Selling needs strategy-owned position reservations; no shorting fallback.
        raise PolicyDenied("SELL_CAPABILITY_UNAVAILABLE")
    expiry = datetime.fromisoformat(account.mandate["expires_at"])
    if now >= expiry:
        raise PolicyDenied("MANDATE_EXPIRED")
    if instrument.as_of > now or now - instrument.as_of > timedelta(seconds=60):
        raise PolicyDenied("STALE_QUOTE")
    if instrument.currency == account.currency and instrument.fx_to_base != 1:
        raise PolicyDenied("INVALID_FX")
    quantity, price = positive(quantity), positive(price)
    multiplier, fx = positive(instrument.multiplier), positive(instrument.fx_to_base)
    if quantity % positive(instrument.lot) or price % positive(instrument.tick):
        raise PolicyDenied("LOT_OR_TICK_PRECISION")
    if price < positive(instrument.price):
        raise PolicyDenied("LIMIT_NOT_MARKETABLE")
    notional = quantity * price * multiplier * fx
    # Explicit fixture fee bound, consumed/released by actual fill events.
    reservation = positive(notional * (1 + Decimal(account.mandate["fee_bps"]) / 10000))
    if reservation > account.max_order:
        raise PolicyDenied("ORDER_CAP")
    if reservation > account.cash - account.reserved:
        raise PolicyDenied("INSUFFICIENT_UNRESERVED_CASH")
    if account.realized_pnl <= -account.loss_limit:
        raise PolicyDenied("LOSS_LIMIT")
    return reservation
