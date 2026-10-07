"""Deterministic non-live risk checks independent of inference latency."""

import json
from decimal import Decimal, InvalidOperation
import hashlib
from datetime import datetime, timedelta

from src.execution.numeric import execution_precision


class PolicyDenied(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@execution_precision
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


@execution_precision
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


@execution_precision
def preflight(account, instrument, quantity, price, side: str, now: datetime, *, mandate_spec=None) -> Decimal:
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
    if side not in {"buy", "sell"}:
        raise PolicyDenied("UNSUPPORTED_SIDE")
    if side == "sell" and not (
        account.mandate.get("fixture") is True and (
            account.mandate.get("manual_sales") is True
            or (mandate_spec is not None and mandate_spec.strategy == "price_band_fixture"
                and mandate_spec.environment == "simulator")
        )
    ):
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
    quote = positive(instrument.price)
    if (side == "buy" and price < quote) or (side == "sell" and price > quote):
        raise PolicyDenied("LIMIT_NOT_MARKETABLE")
    notional = quantity * max(price, quote) * multiplier * fx
    # Explicit fixture fee bound, consumed/released by actual fill events.
    try:
        fee_bps = Decimal(str(account.mandate["fee_bps"]))
    except (KeyError, InvalidOperation, TypeError, ValueError):
        raise PolicyDenied("INVALID_FEE_POLICY") from None
    if not fee_bps.is_finite() or not 0 <= fee_bps <= 100:
        raise PolicyDenied("INVALID_FEE_POLICY")
    gross_budget = positive(notional * (1 + fee_bps / 10000))
    reservation = gross_budget if side == "buy" else gross_budget - notional
    if gross_budget > account.max_order:
        raise PolicyDenied("ORDER_CAP")
    if reservation > account.cash - account.reserved:
        raise PolicyDenied("INSUFFICIENT_UNRESERVED_CASH")
    if account.realized_pnl <= -account.loss_limit:
        raise PolicyDenied("LOSS_LIMIT")
    return reservation
