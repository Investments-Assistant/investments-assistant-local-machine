import uuid
from datetime import datetime

from sqlalchemy import JSON, Text, String, Integer, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


class JobLease(Base):
    __tablename__ = "job_leases"
    __table_args__ = (UniqueConstraint("user_id", "name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(64))
    token: Mapped[str] = mapped_column(String(36))
    lease_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    next_due: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)


class OperationalAlert(Base):
    __tablename__ = "operational_alerts"
    __table_args__ = (UniqueConstraint("user_id", "deduplication_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    account_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rule: Mapped[str] = mapped_column(String(64))
    rule_version: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(16))
    deduplication_key: Mapped[str] = mapped_column(String(64))
    evidence_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    observed_value: Mapped[str] = mapped_column(String(128))
    threshold: Mapped[str] = mapped_column(String(128))
    message: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16), default="open")
    cooldown_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    occurrences: Mapped[int] = mapped_column(Integer, default=1)
    delivery_status: Mapped[str] = mapped_column(String(16), default="in_app")
    delivery_error: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BankSyncState(Base):
    __tablename__ = "bank_sync_states"
    __table_args__ = (UniqueConstraint("user_id", "provider", "account_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    account_key: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="disconnected")
    # Only encrypted provider tokens; never bank passwords or raw IBANs.
    encrypted_credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    last_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
