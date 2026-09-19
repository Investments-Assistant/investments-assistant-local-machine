"""Persist report completion honestly; legacy results remain unverified."""

from alembic import op
import sqlalchemy as sa

revision = "0010_report_status"
down_revision = "0009_expense_audit"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("reports", sa.Column("generation_status", sa.String(24), nullable=False, server_default="unverified"))
    op.add_column("reports", sa.Column("generation_errors", sa.JSON(), nullable=False, server_default="[]"))


def downgrade():
    raise RuntimeError("Restore a reviewed backup; do not discard report failure evidence")
