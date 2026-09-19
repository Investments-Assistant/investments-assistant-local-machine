"""Versioned, independently approved simulator authority; never model-configurable."""

from typing import Literal
from decimal import Decimal
import secrets
from datetime import UTC, datetime, timedelta

from pydantic import Field, BaseModel, ConfigDict, AwareDatetime, model_validator
from sqlalchemy import select

from src.execution.models import SimulatorMandate
from src.execution.policy import PolicyDenied, digest
from src.execution.service import account_for_user


class MandateSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    environment: Literal["simulator"]
    strategy: Literal["periodic_fixture_buy"]
    strategy_version: Literal["1"]
    instrument_ids: list[str] = Field(min_length=1, max_length=20)
    capital_limit: Decimal = Field(gt=0, max_digits=28, decimal_places=10)
    max_position: Decimal = Field(gt=0, max_digits=28, decimal_places=10)
    max_order: Decimal = Field(gt=0, max_digits=28, decimal_places=10)
    daily_loss_limit: Decimal = Field(gt=0, max_digits=28, decimal_places=10)
    drawdown_limit: Decimal = Field(gt=0, max_digits=28, decimal_places=10)
    max_orders_per_day: int = Field(ge=1, le=100)
    min_interval_seconds: int = Field(ge=60, le=86400)
    max_quote_age_seconds: int = Field(ge=1, le=60)
    max_fee_bps: Decimal = Field(ge=0, le=100)
    max_spread_bps: Decimal = Field(ge=0, le=100)
    trading_timezone: Literal["UTC"]
    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=1, le=24)
    weekdays: list[int] = Field(min_length=1, max_length=7)
    expires_at: AwareDatetime
    quantity_per_order: Decimal = Field(gt=0, max_digits=28, decimal_places=10)

    @model_validator(mode="after")
    def consistent(self):
        if not self.max_order <= self.max_position <= self.capital_limit:
            raise ValueError("Order <= position <= capital is required")
        if self.start_hour >= self.end_hour:
            raise ValueError("Hours must be an increasing UTC interval")
        if len(set(self.weekdays)) != len(self.weekdays) or any(day not in range(7) for day in self.weekdays):
            raise ValueError("Weekdays must be unique ISO weekday indices 0..6")
        if len(set(self.instrument_ids)) != len(self.instrument_ids):
            raise ValueError("Instrument allowlist must be unique")
        return self


def immutable_details(row):
    return dict(
        account_id=row.account_id,
        user_id=row.user_id,
        session_id=row.session_id,
        specification=row.specification,
        revision=row.id,
    )


async def propose_mandate(session, *, user_id, session_id, account_id, spec: MandateSpec, now=None):
    from src.execution.models import SimulatorInstrument

    account = await account_for_user(session, account_id, user_id)
    now = now or datetime.now(UTC)
    if not session_id or account.mandate.get("fixture") is not True:
        raise PolicyDenied("SIMULATOR_FIXTURE_REQUIRED")
    if not now < spec.expires_at <= now + timedelta(days=30):
        raise PolicyDenied("MANDATE_REVIEW_WINDOW")
    if spec.capital_limit > account.initial_capital or spec.max_order > account.max_order:
        raise PolicyDenied("GLOBAL_CAP_EXCEEDED")
    instruments = (
        (
            await session.execute(
                select(SimulatorInstrument).where(
                    SimulatorInstrument.account_id == account_id,
                    SimulatorInstrument.id.in_(spec.instrument_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    if len(instruments) != len(spec.instrument_ids) or any(
        i.protected or i.security_type not in {"stock", "etf"} or i.multiplier != 1 for i in instruments
    ):
        raise PolicyDenied("INSTRUMENT_NOT_ELIGIBLE")
    count = (
        await session.execute(
            select(SimulatorMandate.id)
            .where(SimulatorMandate.account_id == account_id, SimulatorMandate.status == "proposed")
            .limit(10)
        )
    ).all()
    if len(count) >= 10:
        raise PolicyDenied("PENDING_MANDATE_LIMIT")
    nonce = secrets.token_urlsafe(32)
    row = SimulatorMandate(
        account_id=account_id,
        user_id=user_id,
        session_id=session_id,
        specification=spec.model_dump(mode="json"),
        status="proposed",
        nonce_hash=digest(nonce),
        details_hash="",
        approval_deadline=now + timedelta(minutes=5),
    )
    session.add(row)
    await session.flush()
    row.details_hash = digest(immutable_details(row))
    return dict(
        mandate_id=row.id,
        nonce=nonce,
        details_hash=row.details_hash,
        details=immutable_details(row),
        status=row.status,
    )


async def approve_mandate(
    session,
    *,
    user_id,
    session_id,
    account_id,
    mandate_id,
    nonce,
    details_hash,
    human_event,
    now=None,
):
    if human_event is not True:
        raise PolicyDenied("HUMAN_APPROVAL_REQUIRED")
    await account_for_user(session, account_id, user_id)
    now = now or datetime.now(UTC)
    row = await session.scalar(
        select(SimulatorMandate)
        .where(
            SimulatorMandate.id == mandate_id,
            SimulatorMandate.account_id == account_id,
            SimulatorMandate.user_id == user_id,
        )
        .with_for_update()
    )
    if row is None or row.session_id != session_id:
        raise PolicyDenied("MANDATE_NOT_OWNED")
    if row.status != "proposed":
        raise PolicyDenied("APPROVAL_ALREADY_CONSUMED")
    if now >= row.approval_deadline or now >= MandateSpec.model_validate(row.specification).expires_at:
        raise PolicyDenied("APPROVAL_EXPIRED")
    if not secrets.compare_digest(row.nonce_hash, digest(nonce)):
        raise PolicyDenied("INVALID_NONCE")
    if not secrets.compare_digest(row.details_hash, details_hash) or row.details_hash != digest(immutable_details(row)):
        raise PolicyDenied("MANDATE_CHANGED_AFTER_PROPOSAL")
    # Exactly one active revision per account under the same account lock.
    active = (
        (
            await session.execute(
                select(SimulatorMandate).where(
                    SimulatorMandate.account_id == account_id, SimulatorMandate.status == "approved"
                )
            )
        )
        .scalars()
        .all()
    )
    for old in active:
        old.status = "superseded"
    row.status = "approved"
    row.approval = dict(
        actor="authenticated_browser",
        at=now.isoformat(),
        details_hash=details_hash,
        environment="simulator",
    )
    await session.flush()
    return dict(mandate_id=row.id, status=row.status, environment="simulator")
