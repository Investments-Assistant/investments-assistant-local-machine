"""Durable simulator event ordering independent of wall-clock timestamps."""

from alembic import op
import sqlalchemy as sa

revision = "0013_execution_sequence"
down_revision = "0012_broker_observations"
branch_labels = None
depends_on = None


def upgrade():
    # The table lock also fences concurrent old writers during the backfill.
    op.execute("LOCK TABLE execution_events IN ACCESS EXCLUSIVE MODE")
    op.add_column("execution_events", sa.Column("ledger_sequence", sa.BigInteger(), nullable=True))
    op.execute("""WITH ranked AS (
        SELECT id, row_number() OVER (ORDER BY observed_at, id) AS ordinal FROM execution_events
    ) UPDATE execution_events SET ledger_sequence = ranked.ordinal
      FROM ranked WHERE execution_events.id = ranked.id""")
    next_value = int(op.get_bind().scalar(sa.text(
        "SELECT COALESCE(MAX(ledger_sequence), 0) + 1 FROM execution_events"
    )))
    op.alter_column("execution_events", "ledger_sequence", nullable=False)
    op.execute(
        "ALTER TABLE execution_events ALTER COLUMN ledger_sequence "
        f"ADD GENERATED ALWAYS AS IDENTITY (START WITH {next_value})"
    )
    op.create_unique_constraint("uq_execution_event_sequence", "execution_events", ["ledger_sequence"])


def downgrade():
    raise RuntimeError("Execution ordering is audit evidence; restore a reviewed backup rather than discard it")
