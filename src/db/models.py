"""SQLAlchemy ORM models."""

from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Text,
    Float,
    Index,
    String,
    Boolean,
    Integer,
    Numeric,
    DateTime,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class ChatMessage(Base):
    """One turn in the chat conversation."""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Legacy unknown-owner rows remain quarantined; startup never assigns ownership.
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant | tool
    content: Mapped[str] = mapped_column(Text)
    tool_calls: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())


class Project(Base):
    """A user-owned workspace for grouping related conversations."""

    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_projects_user_name"),
        Index("ix_projects_user_updated", "user_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, server_default=func.now()
    )


class Conversation(Base):
    """Durable metadata for one resumable assistant conversation."""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_user_updated", "user_id", "updated_at"),
        Index("ix_conversations_user_project_updated", "user_id", "project_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200), default="New chat")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, server_default=func.now()
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class User(Base):
    """A local operator account and its durable UX preferences."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    display_name: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    trading_mode: Mapped[str] = mapped_column(String(16), default="recommend")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class BrokerAccount(Base):
    """Encrypted per-user brokerage connection configuration."""

    __tablename__ = "broker_accounts"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "broker",
            "display_name",
            name="uq_broker_accounts_user_broker_name",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    broker: Mapped[str] = mapped_column(String(32), index=True)
    display_name: Mapped[str] = mapped_column(String(128))
    # Contains the complete provider configuration, including secrets, as a
    # Fernet token. Plaintext credentials never enter a normal ORM column.
    config_encrypted: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Trade(Base):
    """A trade executed or recommended by the agent."""

    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    broker_account_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    broker: Mapped[str] = mapped_column(String(32))  # alpaca | ibkr | coinbase | binance
    symbol: Mapped[str] = mapped_column(String(20))
    side: Mapped[str] = mapped_column(String(8))  # buy | sell
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 10))
    price: Mapped[Decimal | None] = mapped_column(Numeric(28, 10), nullable=True)
    order_type: Mapped[str] = mapped_column(String(16))  # market | limit | stop_limit
    status: Mapped[str] = mapped_column(String(16))  # pending | filled | cancelled | rejected
    broker_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mode: Mapped[str] = mapped_column(String(16))  # auto | manual | simulated
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    pnl_usd: Mapped[Decimal | None] = mapped_column(Numeric(28, 10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Analysis(Base):
    """A market analysis snapshot produced by the agent."""

    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    trigger: Mapped[str] = mapped_column(String(32))  # scheduled | user_request | alert
    symbols: Mapped[list] = mapped_column(JSON)
    summary: Mapped[str] = mapped_column(Text)
    sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)  # bullish | bearish | neutral
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0–1
    recommendations: Mapped[list] = mapped_column(JSON, default=list)
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())


class Report(Base):
    """A weekly (or on-demand) investment report."""

    __tablename__ = "reports"
    __table_args__ = (Index("ix_reports_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(256))
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    html_content: Mapped[str] = mapped_column(Text)
    pdf_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    generation_status: Mapped[str] = mapped_column(String(24), default="unverified", server_default="unverified")
    generation_errors: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    total_pnl_usd: Mapped[Decimal | None] = mapped_column(Numeric(28, 10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())


class DailyPnL(Base):
    """Daily profit-and-loss snapshot (used for auto-mode safety limits)."""

    __tablename__ = "daily_pnl"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_daily_pnl_user_date"),
        Index("ix_daily_pnl_user_date", "user_id", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    realized_usd: Mapped[Decimal] = mapped_column(Numeric(28, 10), default=0.0)
    unrealized_usd: Mapped[Decimal] = mapped_column(Numeric(28, 10), default=0.0)
    auto_trading_halted: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class NewsArticle(Base):
    """A news article ingested from RSS, API, web scraping, or email newsletter."""

    __tablename__ = "news_articles"
    __table_args__ = (
        # GIN index on the concatenated tsvector enables fast full-text search.
        Index(
            "ix_news_articles_fts",
            text(
                "to_tsvector('english', coalesce(title, '') || ' ' || "
                "coalesce(summary, '') || ' ' || coalesce(content, ''))"
            ),
            postgresql_using="gin",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String(16), default="public", server_default="public")
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(100), index=True)
    url: Mapped[str] = mapped_column(String(1000), unique=True)  # deduplication key
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())
    # fetched_at is immutable first-seen time; availability is never backdated to publication.
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    sentiment_label: Mapped[str] = mapped_column(String(20), default="neutral")
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    tags: Mapped[list] = mapped_column(JSON, default=list)  # tickers / topics extracted


class NewsRevision(Base):
    """Immutable observed content; callers only append and read revisions."""

    __tablename__ = "news_revisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    article_id: Mapped[str] = mapped_column(String(36), index=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
    evidence: Mapped[dict] = mapped_column(JSON)


class SimulationResult(Base):
    """Results from a backtested or forward-simulated investment strategy."""

    __tablename__ = "simulation_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    strategy: Mapped[dict] = mapped_column(JSON)
    initial_capital: Mapped[float] = mapped_column(Float)
    final_value: Mapped[float] = mapped_column(Float)
    total_return_pct: Mapped[float] = mapped_column(Float)
    sharpe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    trades_count: Mapped[int] = mapped_column(Integer, default=0)
    period_start: Mapped[str] = mapped_column(String(10))
    period_end: Mapped[str] = mapped_column(String(10))
    equity_curve: Mapped[list] = mapped_column(JSON, default=list)  # [{date, value}]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())


class ExpenseTransaction(Base):
    """A user-owned bank transaction normalised for expense analytics."""

    __tablename__ = "expense_transactions"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "provider",
            "account_key",
            "external_id",
            name="uq_expense_transactions_user_provider_external",
        ),
        Index("ix_expense_transactions_user_occurred", "user_id", "occurred_at"),
        Index("ix_expense_transactions_user_category", "user_id", "category", "occurred_at"),
        Index(
            "ix_expense_raw_retention",
            "user_id",
            "synced_at",
            "id",
            postgresql_where=text("raw_data::jsonb <> '{}'::jsonb"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(String(256))
    account_name: Mapped[str] = mapped_column(String(128), default="Bank account")
    account_key: Mapped[str] = mapped_column(String(64), default="legacy-unassigned")
    lifecycle: Mapped[str] = mapped_column(String(16), default="booked")
    category_override: Mapped[bool] = mapped_column(Boolean, default=False)
    merchant: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text, default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(28, 10))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    transaction_type: Mapped[str] = mapped_column(String(16), default="expense")
    category: Mapped[str] = mapped_column(String(64), default="other", index=True)
    subcategory: Mapped[str] = mapped_column(String(96), default="uncategorised")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    pending: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, server_default=func.now()
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, server_default=func.now()
    )


# Import registers isolated execution tables with this declarative metadata.
from src.expenses.models import ExpenseAudit  # noqa: E402,F401
from src.execution.models import (  # noqa: E402,F401
    ExecutionEvent,
    SimulatorOrder,
    SimulatorAccount,
    SimulatorPosition,
    SimulatorInstrument,
)
from src.operations.models import JobLease, BankSyncState, OperationalAlert  # noqa: E402,F401
from src.security.sessions import SessionRevocation  # noqa: E402, F401


class BrokerObservation(Base):
    """Immutable account-bound callback evidence; never a simulated fill."""

    __tablename__ = "broker_observations"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "account_binding",
            "kind",
            "identity_sha256",
            "payload_sha256",
            name="uq_broker_observation_content",
        ),
        Index("ix_broker_observations_owner_account", "user_id", "account_id", "recorded_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36))
    account_id: Mapped[str] = mapped_column(String(36))
    account_binding: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))
    identity_sha256: Mapped[str] = mapped_column(String(64))
    payload_sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp())
