"""merge_h4_6_and_a3bc0002_heads

Revision ID: a3bc0003
Revises: h4_6_drop_cancelled_status, a3bc0002
Create Date: 2026-06-02 16:00:00.000000

Merge two divergent head branches into a single head:
- h4_6_drop_cancelled_status (drop cancelled status)
- a3bc0002_idempotency_scope_and_perf_indexes (idempotency scope + perf indexes)

This is a pure merge — no schema operations.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a3bc0003"
down_revision: Union[str, Sequence[str], None] = (
    "h4_6_drop_cancelled_status",
    "a3bc0002",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
