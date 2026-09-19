"""Durable simulator state, separate from every external brokerage account."""

import uuid
from decimal import Decimal
from datetime import UTC, datetime

from sqlalchemy import JSON, String, Boolean, Numeric, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


def identifier():
    return str(uuid.uuid4())


def now():
    return datetime.now(UTC)


class SimulatorAccount(Base):
    __tablename__ = "simulator_accounts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    reserved: Mapped[Decimal] = mapped_column(Numeric(28, 10), default=0)
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    max_order: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    loss_limit: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(28, 10), default=0)
    halted: Mapped[bool] = mapped_column(Boolean, default=False)
    halt_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Explicit fixture mandate, never a live policy.
    mandate: Mapped[dict] = mapped_column(JSON, nullable=False)


class SimulatorInstrument(Base):
    __tablename__ = "simulator_instruments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    account_id: Mapped[str] = mapped_column(ForeignKey("simulator_accounts.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(32))
    exchange: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(3))
    multiplier: Mapped[Decimal] = mapped_column(Numeric(28, 10), default=1)
    lot: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    tick: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    fx_to_base: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    protected: Mapped[bool] = mapped_column(Boolean, default=False)
    security_type: Mapped[str] = mapped_column(String(16), default="stock")


class SimulatorOrder(Base):
    __tablename__ = "simulator_orders"
    __table_args__ = (UniqueConstraint("account_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    account_id: Mapped[str] = mapped_column(ForeignKey("simulator_accounts.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    session_id: Mapped[str] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(64))
    instrument_id: Mapped[str] = mapped_column(ForeignKey("simulator_instruments.id"))
    side: Mapped[str] = mapped_column(String(8))
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 10))
    limit_price: Mapped[Decimal] = mapped_column(Numeric(28, 10))
    filled: Mapped[Decimal] = mapped_column(Numeric(28, 10), default=0)
    fees: Mapped[Decimal] = mapped_column(Numeric(28, 10), default=0)
    reserve: Mapped[Decimal] = mapped_column(Numeric(28, 10), default=0)
    status: Mapped[str] = mapped_column(String(32), default="proposed")
    nonce_hash: Mapped[str] = mapped_column(String(64))
    details_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approval: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SimulatorPosition(Base):
    __tablename__ = "simulator_positions"
    __table_args__ = (UniqueConstraint("account_id", "instrument_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    account_id: Mapped[str] = mapped_column(ForeignKey("simulator_accounts.id"), index=True)
    instrument_id: Mapped[str] = mapped_column(ForeignKey("simulator_instruments.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 10), default=0)
    cost_basis: Mapped[Decimal] = mapped_column(Numeric(28, 10), default=0)


class ExecutionEvent(Base):
    __tablename__ = "execution_events"
    __table_args__ = (UniqueConstraint("order_id", "event_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    order_id: Mapped[str] = mapped_column(ForeignKey("simulator_orders.id"), index=True)
    event_key: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SimulatorMandate(Base):
    __tablename__ = "simulator_mandates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    account_id: Mapped[str] = mapped_column(ForeignKey("simulator_accounts.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    session_id: Mapped[str] = mapped_column(String(128))
    specification: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16))
    nonce_hash: Mapped[str] = mapped_column(String(64))
    details_hash: Mapped[str] = mapped_column(String(64))
    approval_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approval: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
