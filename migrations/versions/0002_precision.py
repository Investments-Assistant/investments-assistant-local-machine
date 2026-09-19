"""Exact numerics and scoped expense identity, without invented legacy ownership."""

from alembic import op
import sqlalchemy as sa

revision = "0002_precision"
down_revision = "0001_reviewed"
branch_labels = None
depends_on = None


def upgrade():
    for table, fields in {
        "trades": ["quantity", "price", "pnl_usd"],
        "expense_transactions": ["amount"],
        "daily_pnl": ["realized_usd", "unrealized_usd"],
        "reports": ["total_pnl_usd"],
    }.items():
        for field in fields:
            op.alter_column(
                table, field, type_=sa.Numeric(28, 10), postgresql_using=f"{field}::numeric(28,10)"
            )
    op.add_column(
        "expense_transactions",
        sa.Column("account_key", sa.String(64), nullable=False, server_default="legacy-unassigned"),
    )
    op.add_column(
        "expense_transactions",
        sa.Column("lifecycle", sa.String(16), nullable=False, server_default="booked"),
    )
    op.add_column(
        "expense_transactions",
        sa.Column("category_override", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.drop_constraint(
        "uq_expense_transactions_user_provider_external", "expense_transactions", type_="unique"
    )
    op.create_unique_constraint(
        "uq_expense_transactions_user_provider_external",
        "expense_transactions",
        ["user_id", "provider", "account_key", "external_id"],
    )


def downgrade():
    raise RuntimeError("Precision-reducing rollback requires explicit backup restore review")
