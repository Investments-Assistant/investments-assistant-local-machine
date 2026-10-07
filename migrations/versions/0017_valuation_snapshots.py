"""Persist immutable account-scoped observed valuation evidence."""

from alembic import op
import sqlalchemy as sa

revision = "0017_valuation_snapshots"
down_revision = "0016_expense_retirement"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "valuation_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("simulator_accounts.id"), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("snapshot_key", sa.String(128), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("account_id", "snapshot_key", name="uq_valuation_snapshot_key"),
    )
    for column in ("account_id", "user_id", "as_of"):
        op.create_index("ix_valuation_snapshots_" + column, "valuation_snapshots", [column])


def downgrade():
    raise RuntimeError("Valuation evidence requires a reviewed backup restore, not destructive downgrade")
