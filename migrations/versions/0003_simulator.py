"""Durable isolated simulator ledger, with no external broker route."""

import json
from pathlib import Path

from alembic import op

revision = "0003_simulator"
down_revision = "0002_precision"
branch_labels = None
depends_on = None


def upgrade():
    for statement in json.loads((Path(__file__).parents[1] / "simulator_schema.json").read_text()):
        op.execute(statement)


def downgrade():
    raise RuntimeError("Audit ledger deletion requires explicit disposable restore review")
