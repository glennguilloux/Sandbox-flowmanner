"""Epic 3.3 — add deleted_at to MemoryEntry (soft-archive for decay job)

Adds a nullable ``deleted_at`` timestamp to ``memory_entries`` so the
retrieval-lifecycle decay job (Epic 3.3) can soft-archive entries that
have not been recalled within the TTL, mirroring the already-existing
``personal_memory_claims.deleted_at`` soft-delete column.

Nullable by design: existing rows have no archive state yet, so no
backfill/sentinel is required. A ``NULL`` simply means "live".

Pairs with the model change in ``app/models/memory_models.py`` (same commit
per AGENTS.md ritual rule 6: migration + model change must ship together).
Chains directly on top of the Epic 3.2 ``last_used_at`` migration.

Revision ID: 20260709_e33_memory_entry_deleted_at
Revises: 20260709_e32_memory_entry_last_used
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260709_e33_memory_entry_deleted_at"
down_revision: str | Sequence[str] | None = "20260709_e32_memory_entry_last_used"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memory_entries",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_memory_entries_deleted_at",
        "memory_entries",
        ["deleted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_memory_entries_deleted_at", table_name="memory_entries")
    op.drop_column("memory_entries", "deleted_at")
