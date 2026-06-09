"""add mission_tasks.updated_at column

Revision ID: a1b2c3d4e5f6
Revises: 20249800e422
Create Date: 2026-04-18 12:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "20249800e422"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add updated_at column to mission_tasks to match TimestampMixin."""
    op.add_column(
        "mission_tasks",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
    )
    # Backfill existing rows with created_at value so they have a valid timestamp
    op.execute(
        "UPDATE mission_tasks SET updated_at = created_at WHERE updated_at IS NULL"
    )


def downgrade() -> None:
    """Remove updated_at column from mission_tasks."""
    op.drop_column("mission_tasks", "updated_at")
