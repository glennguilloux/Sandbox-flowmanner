"""Merge a3bc0003 and next_level_growth_wave2 heads.

Revision ID: merge_wave2_heads
Revises: a3bc0003, next_level_growth_wave2
Create Date: 2026-06-03 14:00:00.000000
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "merge_wave2_heads"
down_revision: str | Sequence[str] | None = ("a3bc0003", "next_level_growth_wave2")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
