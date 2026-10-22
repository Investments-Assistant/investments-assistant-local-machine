"""Retain offline submission intent and append-only handoff evidence."""

from alembic import op
import sqlalchemy as sa

revision = "0020_broker_submission"
down_revision = "0019_flexible_credentials"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "broker_submission_intents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("broker_accounts.id"), nullable=False),
        sa.Column("account_binding", sa.String(64), nullable=False),
        sa.Column("configuration_sha256", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("broker_order_key", sa.String(64), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("attempt_id", sa.String(36), nullable=True),
        sa.Column("permanent_id", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("account_id", "account_binding", "idempotency_key", name="uq_broker_submission_key"),
        sa.UniqueConstraint("account_id", "account_binding", "broker_order_key", name="uq_broker_submission_order"),
        sa.UniqueConstraint("account_id", "account_binding", "permanent_id", name="uq_broker_submission_permanent"),
    )
    op.create_index("ix_broker_submission_owner_account", "broker_submission_intents", ["user_id", "account_id"])
    op.create_table(
        "broker_submission_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("intent_id", sa.String(36), sa.ForeignKey("broker_submission_intents.id"), nullable=False),
        sa.Column("event_key", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("observation_id", sa.String(36), sa.ForeignKey("broker_observations.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("intent_id", "event_key", name="uq_broker_submission_event"),
        sa.UniqueConstraint("intent_id", "observation_id", name="uq_broker_submission_observation"),
    )
    op.create_index("ix_broker_submission_event_intent", "broker_submission_events", ["intent_id", "created_at"])


def downgrade():
    raise RuntimeError(
        "Broker handoff evidence rollback requires a reviewed backup; uncertain attempts must not be lost"
    )
