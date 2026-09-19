"""Index owned raw-payload age scans without indexing payload contents."""

from alembic import op
import sqlalchemy as sa

revision = "0011_retention_index"
down_revision = "0010_report_status"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_expense_raw_retention",
        "expense_transactions",
        ["user_id", "synced_at", "id"],
        postgresql_where=sa.text("raw_data::jsonb <> '{}'::jsonb"),
    )


def downgrade():
    op.drop_index("ix_expense_raw_retention", table_name="expense_transactions")
