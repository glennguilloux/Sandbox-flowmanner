"""add improvement_batch column to critiques (D30-60, 2a.3)

Revision ID: d30_60_2a3
Revises: f72ba088e872
Create Date: 2026-07-07 00:00:00.000000

2a.3 wires ``ImprovementGenerator`` into ``CritiqueService.create_from_critic``.
The resulting ``ImprovementBatch`` is persisted as JSONB on the ``Critique``
row under a new nullable ``improvement_batch`` column. Nullable (no NOT NULL,
no default) so existing critiques created before 2a.3 keep their row intact
and new critiques only carry a batch when generation succeeds.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d30_60_2a3"
down_revision: str | Sequence[str] | None = ["f72ba088e872", "toolvis_001"]
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable improvement_batch JSONB column to critiques."""
    op.add_column(
        "critiques",
        sa.Column(
            "improvement_batch",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Drop the improvement_batch column from critiques."""
    op.drop_column("critiques", "improvement_batch")
