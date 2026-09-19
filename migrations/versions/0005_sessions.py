"""Durable browser session revocation; legacy four-field cookies expire closed."""

from alembic import op
import sqlalchemy as sa

revision = "0005_sessions"
down_revision = "0004_operations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "session_revocations",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column(
            "revoked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_session_revocations_user_id", "session_revocations", ["user_id"])


def downgrade():
    raise RuntimeError("Restore a reviewed backup; do not discard revocation evidence")
