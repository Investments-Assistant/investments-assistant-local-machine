"""Account-scoped, append-only external callback evidence. No execution authority.

This trusted adapter boundary accepts normalized observations, not arbitrary SDK
objects. It does not connect, submit, update simulated balances or infer ownership.
"""

import re
import uuid
from typing import Literal, Annotated
from decimal import Decimal, localcontext
from datetime import UTC, datetime

from pydantic import Field, BaseModel, ConfigDict, TypeAdapter, field_validator
from sqlalchemy import Text, cast, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert

from src.db.models import User, BrokerAccount, BrokerObservation
from src.execution.policy import PolicyDenied, digest
from src.tools.broker_accounts import decrypt_config
from src.execution.broker_balances import BalanceFacts

READ_PAYLOAD_BUDGET = 2 * 1024 * 1024


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    observed_at: datetime
    actual_account: str = Field(min_length=1, max_length=128, exclude=True, repr=False)
    event_id: str = Field(min_length=1, max_length=128, exclude=True, repr=False)

    @field_validator("observed_at")
    @classmethod
    def dated(cls, value):
        if value.tzinfo is None:
            raise ValueError("An aware observation timestamp is required")
        return value.astimezone(UTC)

    @field_validator("event_id")
    @classmethod
    def identity(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
            raise ValueError("Invalid callback identity")
        return value


class ExecutionObservation(Observation):
    kind: Literal["execution"]
    con_id: int = Field(gt=0, strict=True)
    client_id: int = Field(ge=0, strict=True)
    order_id: int = Field(ge=0, strict=True)
    permanent_id: int = Field(ge=0, strict=True)
    side: Literal["BOT", "SLD"]
    quantity: Decimal = Field(gt=0, max_digits=40, decimal_places=20, allow_inf_nan=False)
    price: Decimal = Field(ge=0, max_digits=40, decimal_places=20, allow_inf_nan=False)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    security_type: str | None = Field(default=None, min_length=1, max_length=16)
    multiplier: Decimal | None = Field(default=None, gt=0, max_digits=40, decimal_places=20, allow_inf_nan=False)
    executed_at: datetime

    _execution_time = field_validator("executed_at")(Observation.dated.__func__)


class CommissionObservation(Observation):
    kind: Literal["commission"]
    amount: Decimal = Field(max_digits=40, decimal_places=20, allow_inf_nan=False)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    # Negative broker-reported rebates are evidence, not an authorization bypass.


class OrderObservation(Observation):
    kind: Literal["order_status"]
    client_id: int = Field(ge=0, strict=True)
    order_id: int = Field(ge=0, strict=True)
    permanent_id: int = Field(ge=0, strict=True)
    status: Literal[
        "ApiPending",
        "PendingSubmit",
        "PreSubmitted",
        "Submitted",
        "PendingCancel",
        "ApiCancelled",
        "Cancelled",
        "Filled",
        "Inactive",
    ]
    filled: Decimal = Field(ge=0, max_digits=40, decimal_places=20, allow_inf_nan=False)
    remaining: Decimal = Field(ge=0, max_digits=40, decimal_places=20, allow_inf_nan=False)


class BalanceObservation(Observation):
    kind: Literal["balance_snapshot"]
    balances: BalanceFacts


OBSERVATION = TypeAdapter(
    Annotated[
        ExecutionObservation | CommissionObservation | OrderObservation | BalanceObservation,
        Field(discriminator="kind"),
    ]
)


async def selected_account(session, *, user_id, account_id, require_consent=True):
    if not await session.scalar(
        select(User.id).where(User.id == user_id, User.is_active.is_(True)).with_for_update(read=True)
    ):
        raise PolicyDenied("PRINCIPAL_INACTIVE")
    row = await session.scalar(
        select(BrokerAccount)
        .where(BrokerAccount.id == account_id, BrokerAccount.user_id == user_id, BrokerAccount.broker == "ibkr")
        .with_for_update()
    )
    if row is None:
        raise PolicyDenied("ACCOUNT_NOT_OWNED")
    if require_consent and not row.is_active:
        raise PolicyDenied("BROKER_ACCOUNT_INACTIVE")
    config = decrypt_config(row.config_encrypted)
    if require_consent and (config.get("enabled") is not True or config.get("read_authorized") is not True):
        raise PolicyDenied("IBKR_READ_CONSENT_REQUIRED")
    if not config.get("broker_account_id") or config.get("environment") not in {"paper", "live"}:
        raise PolicyDenied("EXPLICIT_BROKER_ACCOUNT_AND_ENVIRONMENT_REQUIRED")
    binding = digest(
        {
            "owner": user_id,
            "application_account": account_id,
            "actual": config["broker_account_id"],
            "declared_environment": config["environment"],
        }
    )
    return config, binding


async def record_observations(session, *, user_id, account_id, observations, now=None):
    """Caller commits the batch. Lock and recheck current vault consent each time.

    Identical callbacks are deduplicated; different payloads for the same broker
    identity remain separate immutable observations. Receipt time is excluded from
    identity so replay after reconnect does not duplicate financial facts.
    """
    if not isinstance(observations, list) or not 1 <= len(observations) <= 1000:
        raise PolicyDenied("INVALID_OBSERVATION_BATCH")
    try:
        batch = [OBSERVATION.validate_python(item) for item in observations]
    except ValueError:
        raise PolicyDenied("INVALID_BROKER_OBSERVATION") from None
    config, binding = await selected_account(session, user_id=user_id, account_id=account_id)
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise PolicyDenied("INVALID_OBSERVATION_TIME")
    rows = []
    for observation in batch:
        if observation.actual_account != config["broker_account_id"]:
            raise PolicyDenied("BROKER_CALLBACK_ACCOUNT_MISMATCH")
        if observation.observed_at > now:
            raise PolicyDenied("FUTURE_OBSERVATION")
        if isinstance(observation, ExecutionObservation) and observation.executed_at > observation.observed_at:
            raise PolicyDenied("EXECUTION_AFTER_OBSERVATION")
        if (
            isinstance(observation, BalanceObservation)
            and observation.balances.request_started_at > observation.observed_at
        ):
            raise PolicyDenied("INVALID_BALANCE_OBSERVATION_TIME")
        payload = observation.model_dump(mode="json", exclude={"observed_at", "kind"}, exclude_none=True)
        # Normalize decimals so equivalent provider representations deduplicate.
        for field, value in observation:
            if isinstance(value, Decimal):
                with localcontext() as context:
                    context.prec = 60
                    payload[field] = str(value.normalize())
        payload.update(
            environment_declared=config["environment"],
            environment_verified=None,
            ownership="external_or_unknown",
            execution_authority="none",
        )
        identity = digest(observation.event_id)
        if observation.kind == "order_status":
            identity = digest([observation.client_id, observation.order_id, observation.permanent_id])
        if observation.kind in {"execution", "commission"}:
            payload["execution_identity"] = digest(observation.event_id)
            # IBKR correction suffixes identify a family, not an extra fill.
            stem, separator, suffix = observation.event_id.rpartition(".")
            payload["correction_family"] = digest(stem) if separator and suffix.isdigit() else identity
        rows.append(
            dict(
                id=str(uuid.uuid4()),
                user_id=user_id,
                account_id=account_id,
                account_binding=binding,
                kind=observation.kind,
                identity_sha256=identity,
                payload_sha256=digest(payload),
                payload=payload,
                observed_at=observation.observed_at,
            )
        )
    result = await session.scalars(
        insert(BrokerObservation)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_broker_observation_content")
        .returning(BrokerObservation.id)
    )
    return {"inserted": len(result.all()), "received": len(batch), "execution_authority": "none"}


async def read_observations(session, *, user_id, account_id, limit=1000, cursor=None):
    """Read only the currently selected actual-account binding; no cross-rebind mix."""
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise PolicyDenied("INVALID_OBSERVATION_LIMIT")
    _, binding = await selected_account(session, user_id=user_id, account_id=account_id, require_consent=False)
    filters = [
        BrokerObservation.user_id == user_id,
        BrokerObservation.account_id == account_id,
        BrokerObservation.account_binding == binding,
    ]
    if cursor is not None:
        try:
            cursor = str(uuid.UUID(cursor))
        except (TypeError, ValueError, AttributeError):
            raise PolicyDenied("INVALID_OBSERVATION_CURSOR") from None
        previous = (
            await session.execute(
                select(BrokerObservation.id, BrokerObservation.recorded_at).where(
                    *filters, BrokerObservation.id == cursor
                )
            )
        ).first()
        if previous is None:
            raise PolicyDenied("INVALID_OBSERVATION_CURSOR")
        filters.append(
            tuple_(BrokerObservation.recorded_at, BrokerObservation.id) > (previous.recorded_at, previous.id)
        )
    metadata = (
        await session.execute(
            select(BrokerObservation.id, func.octet_length(cast(BrokerObservation.payload, Text)))
            .where(*filters)
            .order_by(BrokerObservation.recorded_at, BrokerObservation.id)
            .limit(limit + 1)
        )
    ).all()
    selected, payload_bytes = [], 0
    for identity, size in metadata[:limit]:
        if payload_bytes + size > READ_PAYLOAD_BUDGET:
            if not selected:
                raise PolicyDenied("BROKER_OBSERVATION_TOO_LARGE")
            break
        selected.append(identity)
        payload_bytes += size
    rows = (
        (
            await session.scalars(
                select(BrokerObservation)
                .where(*filters, BrokerObservation.id.in_(selected))
                .order_by(BrokerObservation.recorded_at, BrokerObservation.id)
            )
        ).all()
        if selected
        else []
    )
    has_more = len(metadata) > len(selected)
    result = {
        "scope": "retained_callback_evidence_not_complete_broker_history",
        "truncated": has_more,
        "next_cursor": rows[-1].id if has_more else None,
        "payload_bytes": payload_bytes,
        "page_scope": "current retained rows; restart browsing to include concurrent arrivals",
        "execution_authority": "none",
        "observations": [
            {
                "kind": row.kind,
                "payload": row.payload,
                "identity_sha256": row.identity_sha256,
                "payload_sha256": row.payload_sha256,
                "observed_at": row.observed_at.isoformat(),
                "recorded_at": row.recorded_at.isoformat(),
            }
            for row in rows[:limit]
        ],
    }

    from src.execution.broker_review import review_observations
    from src.execution.broker_refresh_state import refresh_state

    result["refresh_state"] = await refresh_state(session, user_id=user_id, account_id=account_id)
    result["review"] = review_observations(result["observations"], truncated=result["truncated"] or cursor is not None)
    return result
