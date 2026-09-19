"""Scoped durable leases, alerts and bank-sync checkpoint boundary."""

import json
from pathlib import Path

from alembic import op

revision = "0004_operations"
down_revision = "0003_simulator"
branch_labels = None
depends_on = None


def upgrade():
    for statement in json.loads((Path(__file__).parents[1] / "operations_schema.json").read_text()):
        op.execute(statement)


def downgrade():
    raise RuntimeError("Deleting operational evidence requires explicit restore review")
