"""Append-only broker callback evidence, separate from simulated balances."""

from alembic import op
import sqlalchemy as sa

revision = "0012_broker_observations"
down_revision = "0011_retention_index"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "broker_observations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("account_binding", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("identity_sha256", sa.String(64), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.clock_timestamp()),
        sa.UniqueConstraint(
            "account_id",
            "account_binding",
            "kind",
            "identity_sha256",
            "payload_sha256",
            name="uq_broker_observation_content",
        ),
    )
    op.create_index(
        "ix_broker_observations_owner_account", "broker_observations", ["user_id", "account_id", "recorded_at"]
    )


def downgrade():
    op.drop_table("broker_observations")
