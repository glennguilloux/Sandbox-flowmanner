"""Epic 2.3 E23-D — add ``agent_id`` to PersonalMemoryClaim.

Provenance of the *authoring agent* for a claim. ``NULL`` = human-authored,
which is the highest-trust signal (mirrors ``skill_models.agent_id`` and the
Q5 design in the Q1-Q6 decomposition §7). This unblocks Q5 multi-agent memory
sharing: an agent can read claims it authored and human-authored (``NULL``)
claims, but not another agent's private inferences unless explicitly shared.

This is a read-only nullable column add — no behavior change. Existing rows
are left ``NULL`` (no UPDATE needed); ``NULL`` is itself the strongest trust
signal, so no backfill of real data is required. The column is nullable with
no ``server_default`` so every pre-existing row simply keeps ``NULL``.

The model change and this migration ship together (AGENTS.md ritual rule 6).
The column is indexed for per-agent recall scans.

Revision ID: 20260710_e43_agent_id
Revises:     20260710_q3_create_skills_table
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260710_e43_agent_id"
down_revision = "20260710_q3_skills"
branch_labels = None
depends_on = None

_TABLE = "personal_memory_claims"
_COLUMN = "agent_id"


def upgrade() -> None:
    # 1. Add the nullable agent_id column. Existing rows stay NULL (which is
    #    exactly the desired "human-authored = highest trust" sentinel), so
    #    there is nothing to backfill — no UPDATE, no sentinel of real data.
    op.add_column(
        _TABLE,
        sa.Column(_COLUMN, sa.String(255), nullable=True),
    )

    # 2. Index for per-agent recall scans (Q5 filtering / workspace writes).
    op.create_index(
        f"ix_{_TABLE}_{_COLUMN}",
        _TABLE,
        [_COLUMN],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(f"ix_{_TABLE}_{_COLUMN}", table_name=_TABLE)
    op.drop_column(_TABLE, _COLUMN)
