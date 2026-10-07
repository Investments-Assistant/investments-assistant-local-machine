"""Retain simulator account cash-flow evidence in the execution ordering stream."""

from alembic import op
import sqlalchemy as sa

revision = "0015_account_events"
down_revision = "0014_strategy_decisions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "account_ledger_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("simulator_accounts.id"), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("event_key", sa.String(128), nullable=False),
        sa.Column(
            "ledger_sequence",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("nextval('execution_events_ledger_sequence_seq')"),
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "event_key", name="uq_account_ledger_event_key"),
        sa.UniqueConstraint("ledger_sequence", name="uq_account_ledger_event_sequence"),
    )
    for column in ("account_id", "user_id"):
        op.create_index(f"ix_account_ledger_events_{column}", "account_ledger_events", [column])


def downgrade():
    raise RuntimeError("Account events are audit evidence; restore a reviewed backup instead of deleting them")
