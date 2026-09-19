"""Frozen reviewed schema at 65ea1d7; existing installations require verified stamp."""

import json
from pathlib import Path

from alembic import op

revision = "0001_reviewed"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    for statement in json.loads((Path(__file__).parents[1] / "reviewed_schema.json").read_text()):
        op.execute(statement)


def downgrade():
    raise RuntimeError("Destructive baseline downgrade prohibited; restore a verified backup")
