"""soft_delete_missions

Revision ID: a3bc0001
Revises: 2c8ebb094375
Create Date: 2026-06-02 12:00:00.000000

Adds deleted_at and deleted_by columns to missions table for soft-delete support.
Includes indexes for efficient soft-delete query filtering.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision: str = "a3bc0001"
down_revision: str | Sequence[str] | None = "2c8ebb094375"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "missions",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "missions",
        sa.Column("deleted_by", sa.Integer(), nullable=True),
    )
    op.create_index("ix_missions_deleted_at", "missions", ["deleted_at"], unique=False)
    # Composite index for the common "user's non-deleted missions" query pattern
    op.create_index(
        "ix_missions_user_id_not_deleted",
        "missions",
        ["user_id", "deleted_at"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_missions_user_id_not_deleted", table_name="missions")
    op.drop_index("ix_missions_deleted_at", table_name="missions")
    op.drop_column("missions", "deleted_by")
    op.drop_column("missions", "deleted_at")
