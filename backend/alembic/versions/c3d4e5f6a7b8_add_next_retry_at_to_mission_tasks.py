"""add next_retry_at to mission_tasks for exponential backoff

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-05-02 12:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add next_retry_at column to mission_tasks for exponential backoff."""
    op.add_column(
        "mission_tasks",
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Set default max_retries to 5 for existing rows that have NULL
    op.execute("UPDATE mission_tasks SET max_retries = 5 WHERE max_retries IS NULL")
    # Set default retry_count to 0 for existing rows that have NULL
    op.execute("UPDATE mission_tasks SET retry_count = 0 WHERE retry_count IS NULL")


def downgrade() -> None:
    """Remove next_retry_at column from mission_tasks."""
    op.drop_column("mission_tasks", "next_retry_at")
