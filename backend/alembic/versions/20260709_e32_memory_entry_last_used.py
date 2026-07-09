"""Epic 3.2 — add last_used_at to MemoryEntry (decay/usage tracking)

Adds a nullable ``last_used_at`` timestamp to ``memory_entries`` so the
retrieval-lifecycle work in Epic 3.3 can track per-entry usage and drive
importance decay without a join to ``personal_memory_claims``.

Nullable by design: existing rows have no recorded usage yet, so no
backfill/sentinel is required. A ``NULL`` simply means "never used".

Pairs with the model change in ``app/models/memory_models.py`` (same commit
per AGENTS.md ritual rule 6: migration + model change must ship together).
Chains directly on top of the GOV-1.6 ``drop`` event migration.

Revision ID: 20260709_e32_memory_entry_last_used
Revises: 20260709_gov16_drop_event_type
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260709_e32_memory_entry_last_used"
down_revision: str | Sequence[str] | None = "20260709_gov16_drop_event_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memory_entries",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("memory_entries", "last_used_at")
