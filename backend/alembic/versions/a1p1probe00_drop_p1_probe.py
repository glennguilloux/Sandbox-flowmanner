"""drop p1_probe (orphan diagnostic table, 1 row, zero references).

Reviewed 2026-07-18: confirmed orphan via grep + row count. Safe to drop.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1p1probe00"
down_revision: str | None = "575813539b87"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_table("p1_probe")


def downgrade() -> None:
    op.create_table(
        "p1_probe",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("status", sa.Text()),
    )
