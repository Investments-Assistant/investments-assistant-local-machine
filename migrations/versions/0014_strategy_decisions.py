"""Retain strategy decisions, including no-trade outcomes, without invented orders."""

from alembic import op
import sqlalchemy as sa

revision = "0014_strategy_decisions"
down_revision = "0013_execution_sequence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "strategy_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("simulator_accounts.id"), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("mandate_id", sa.String(36), sa.ForeignKey("simulator_mandates.id"), nullable=False),
        sa.Column("tick_key", sa.String(64), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "tick_key", name="uq_strategy_decision_tick"),
    )
    for column in ("account_id", "user_id", "mandate_id"):
        op.create_index(f"ix_strategy_decisions_{column}", "strategy_decisions", [column])


def downgrade():
    raise RuntimeError("Strategy decisions are audit evidence; restore a reviewed backup instead of deleting them")
