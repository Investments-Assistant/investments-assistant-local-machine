"""Fence job completion against clock regressions and legacy unknown acquisition time."""

from alembic import op
import sqlalchemy as sa

revision = "0018_job_lease_clock"
down_revision = "0017_valuation_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    # Never invent the acquisition time of an existing worker. NULL leases cannot
    # complete; after their old expiry/due time a fresh acquisition sets the clock.
    op.add_column("job_leases", sa.Column("leased_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    raise RuntimeError("Lease fencing rollback requires reviewed backup and compatible stopped writers")
