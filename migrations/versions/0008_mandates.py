"""Independent, versioned human approval for isolated simulator mandates."""

from alembic import op
import sqlalchemy as sa

revision = "0008_mandates"
down_revision = "0007_news_evidence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "simulator_mandates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "account_id", sa.String(36), sa.ForeignKey("simulator_accounts.id"), nullable=False
        ),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(128), nullable=False),
        sa.Column("specification", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("nonce_hash", sa.String(64), nullable=False),
        sa.Column("details_hash", sa.String(64), nullable=False),
        sa.Column("approval_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approval", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_simulator_mandates_account_id", "simulator_mandates", ["account_id"])
    op.create_index("ix_simulator_mandates_user_id", "simulator_mandates", ["user_id"])


def downgrade():
    raise RuntimeError("Restore a reviewed backup; never discard mandate approval evidence")
