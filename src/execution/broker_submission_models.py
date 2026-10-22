"""Durable offline broker handoff evidence, separate from simulator accounting.

These tables confer no external execution authority. Events are append-only via
the journal service; a handoff record must survive before a transport is called.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Index, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


def identifier():
    return str(uuid.uuid4())


def now():
    return datetime.now(UTC)


class BrokerSubmissionIntent(Base):
    __tablename__ = "broker_submission_intents"
    __table_args__ = (
        UniqueConstraint("account_id", "account_binding", "idempotency_key", name="uq_broker_submission_key"),
        UniqueConstraint("account_id", "account_binding", "broker_order_key", name="uq_broker_submission_order"),
        UniqueConstraint("account_id", "account_binding", "permanent_id", name="uq_broker_submission_permanent"),
        Index("ix_broker_submission_owner_account", "user_id", "account_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    account_id: Mapped[str] = mapped_column(ForeignKey("broker_accounts.id"), nullable=False)
    account_binding: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    broker_order_key: Mapped[str] = mapped_column(String(64), nullable=False)
    request: Mapped[dict] = mapped_column(JSON, nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="staged")
    attempt_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    permanent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)


class BrokerSubmissionEvent(Base):
    __tablename__ = "broker_submission_events"
    __table_args__ = (
        UniqueConstraint("intent_id", "event_key", name="uq_broker_submission_event"),
        UniqueConstraint("intent_id", "observation_id", name="uq_broker_submission_observation"),
        Index("ix_broker_submission_event_intent", "intent_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    intent_id: Mapped[str] = mapped_column(ForeignKey("broker_submission_intents.id"), nullable=False)
    event_key: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    observation_id: Mapped[str | None] = mapped_column(ForeignKey("broker_observations.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
