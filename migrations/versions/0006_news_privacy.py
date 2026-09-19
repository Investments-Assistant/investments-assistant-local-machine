"""Quarantine unknown newsletter ownership; never assign a bootstrap owner."""

from alembic import op
import sqlalchemy as sa

revision = "0006_news_privacy"
down_revision = "0005_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("news_articles", sa.Column("user_id", sa.String(36), nullable=True))
    op.add_column(
        "news_articles",
        sa.Column("visibility", sa.String(16), nullable=False, server_default="public"),
    )
    op.create_index("ix_news_articles_user_id", "news_articles", ["user_id"])
    # Preserve legacy evidence for a separately reviewed ownership/retention decision.
    # The shared search/count paths never expose quarantined rows.
    op.execute(
        "UPDATE news_articles SET visibility = 'quarantined' "
        "WHERE url NOT LIKE 'https://%' OR source ILIKE 'Newsletter%'"
    )


def downgrade():
    raise RuntimeError("Restore a reviewed backup; removing visibility would expose private news")
