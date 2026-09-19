"""Retain immutable observed corrections without inventing legacy availability."""

from alembic import op
import sqlalchemy as sa

revision = "0007_news_evidence"
down_revision = "0006_news_privacy"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("news_articles", sa.Column("available_at", sa.DateTime(timezone=True)))
    op.add_column("news_articles", sa.Column("content_hash", sa.String(64)))
    op.add_column(
        "news_articles", sa.Column("provenance", sa.JSON(), nullable=False, server_default="{}")
    )
    op.create_index("ix_news_articles_content_hash", "news_articles", ["content_hash"])
    op.create_table(
        "news_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("article_id", sa.String(36), nullable=False),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("available_at", sa.DateTime(timezone=True)),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.clock_timestamp(),
        ),
        sa.Column("evidence", sa.JSON(), nullable=False),
    )
    op.create_index("ix_news_revisions_article_id", "news_revisions", ["article_id"])
    # Legacy content is preserved but is not eligible for historical replay: availability unknown.
    op.execute("""INSERT INTO news_revisions (id, article_id, evidence)
        SELECT id, id, json_build_object('title', title, 'summary', summary, 'content', content,
            'source', source, 'url', url, 'published_at', published_at,
            'provenance', json_build_object('availability', 'legacy_unknown'))
        FROM news_articles""")


def downgrade():
    raise RuntimeError("Restore a reviewed backup; never discard correction evidence")
