"""Minimal owner-scoped expense change audit, without bank payloads or secrets."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


class ExpenseAudit(Base):
    __tablename__ = "expense_audit"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    transaction_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(32))
    changes: Mapped[dict] = mapped_column(JSON)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
