"""Create changelog_entries table (R9 lightweight read-only changelog).

Revision ID: 20260717_changelog
Revises: 20260709_blog
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "20260717_changelog"
down_revision = "20260715_sandbox_run_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "changelog_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("title", sa.String(512), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("category", sa.String(64), nullable=False, server_default="release"),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_changelog_entries_version", "changelog_entries", ["version"])
    op.create_index("ix_changelog_entries_released_at", "changelog_entries", ["released_at"])


def downgrade() -> None:
    op.drop_index("ix_changelog_entries_released_at", table_name="changelog_entries")
    op.drop_index("ix_changelog_entries_version", table_name="changelog_entries")
    op.drop_table("changelog_entries")
