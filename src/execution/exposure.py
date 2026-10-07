"""Explicit global simulator capital limits, independent of strategy permissions."""

from decimal import Decimal

from src.execution.policy import PolicyDenied, positive
from src.execution.numeric import execution_precision


@execution_precision
def global_limits(account):
    raw = account.mandate.get("global_exposure_limits")
    try:
        if not isinstance(raw, dict):
            raise ValueError("Missing policy")
        position = positive(raw["max_position_base"])
        exposure = positive(raw["max_exposure_base"])
        if position > exposure:
            raise ValueError("Inconsistent policy")
    except (KeyError, ValueError, TypeError):
        raise PolicyDenied("GLOBAL_EXPOSURE_LIMITS_UNAVAILABLE") from None
    return position, exposure


@execution_precision
def require_order_exposure(account, instrument, side, reserve, observation):
    """Called under the account lock with the immediately preceding risk observation.

    Marked holdings plus pending cash reservations (including fees) are bounded.
    Pending sale proceeds never finance a new purchase. Selling grants no new cap.
    """
    position_cap, exposure_cap = global_limits(account)
    if side != "buy":
        return
    current = Decimal(observation["position_exposure"].get(instrument.id, "0"))
    pending = Decimal(observation["reserved_by_instrument"].get(instrument.id, "0"))
    if current + pending + reserve > position_cap:
        raise PolicyDenied("GLOBAL_POSITION_CAP")
    if Decimal(observation["exposure"]) + account.reserved + reserve > exposure_cap:
        raise PolicyDenied("GLOBAL_EXPOSURE_CAP")
