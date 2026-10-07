"""Retain only owner-scoped identity hashes to prevent purged history re-import."""

from alembic import op
import sqlalchemy as sa

revision = "0016_expense_retirement"
down_revision = "0015_account_events"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "expense_retirements",
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.Column("identity_sha256", sa.String(64), primary_key=True),
        sa.Column("plan_sha256", sa.String(64), nullable=False),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    raise RuntimeError("Retirement hashes prevent re-import; restore a reviewed backup instead")
