"""Owner-scoped category-change audit with no bank payload copies."""

from alembic import op
import sqlalchemy as sa

revision = "0009_expense_audit"
down_revision = "0008_mandates"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "expense_audit",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("transaction_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.clock_timestamp(),
        ),
    )
    op.create_index("ix_expense_audit_user_id", "expense_audit", ["user_id"])
    op.create_index("ix_expense_audit_transaction_id", "expense_audit", ["transaction_id"])


def downgrade():
    raise RuntimeError("Restore a reviewed backup; never discard expense audit evidence")
