"""Drop legacy v1 changelog_entries before R9 rebuilds it (UUID schema).

Revision ID: 20260717b_drop_legacy_changelog
Revises: 20260715_sandbox_run_context
Create Date: 2026-07-17

The original ``changelog_entries`` table (integer id + content/entry_type/
published columns) was an artifact of the deleted ``app/api/v1/changelog.py``
router. That router was pruned in commit a7050d94 (Phase 4), but the table was
never dropped and no migration ever tracked it. R9 (commit a5eb76a9) introduces
a new ORM model + migration with a different, UUID-keyed schema sharing the same
table name, which collides at ``alembic upgrade head`` with
``DuplicateTableError: relation "changelog_entries" already exists``.

This migration drops the orphaned legacy table (1 stale, unread v1 row) so the
following 20260717_changelog migration can CREATE the R9 schema cleanly. The
single historical note (version '0.2.0' / 'Platform Hardening') is preserved by
re-seeding it via scripts/seed_changelog.py under the R9 schema.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260717b_drop_legacy_changelog"
down_revision: str | Sequence[str] | None = "20260715_sandbox_run_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("changelog_entries")


def downgrade() -> None:
    # Recreate the legacy integer schema (data is NOT recoverable — the single
    # row was v1 marketing content with no R9 columns).
    op.create_table(
        "changelog_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "entry_type", sa.String(50), nullable=False, server_default="feature"
        ),
        sa.Column(
            "published", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("published_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_changelog_published", "changelog_entries", ["published", "published_at"]
    )
