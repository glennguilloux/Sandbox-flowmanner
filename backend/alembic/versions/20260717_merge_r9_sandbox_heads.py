"""merge r9 changelog head with sandbox_run_context head

Revision ID: 20260717_merge_heads
Revises: 20260715_sandbox_run_context, 20260717_changelog
Create Date: 2026-07-17

The r9 changelog migration (20260717_changelog, down_revision
20260709_blog) and the sandbox_run_context migration
(20260715_sandbox_run_context, down_revision 20260712_substrate_idem_unique)
both descend from different parents and neither is an ancestor of the other,
producing two alembic heads. This merge makes them a single head so
`alembic upgrade head` (and the offline --sql render used by the deploy
validation gate) resolves unambiguously. No schema change — lineage only.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260717_merge_heads"
down_revision: str | Sequence[str] | None = (
    "20260715_sandbox_run_context",
    "20260717_changelog",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Lineage merge only — no schema change.
    pass


def downgrade() -> None:
    # Lineage merge only — no schema change.
    pass
