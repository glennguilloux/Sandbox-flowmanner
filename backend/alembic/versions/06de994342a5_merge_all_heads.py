"""merge all heads

Revision ID: 06de994342a5
Revises: 202605051230, phase3_new_tables_001, add_missing_tables_001, b2c3d4e5f6a7
Create Date: 2026-05-18 23:16:45.349873

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "06de994342a5"
down_revision: str | Sequence[str] | None = (
    "202605051230",
    "phase3_new_tables_001",
    "add_missing_tables_001",
    "b2c3d4e5f6a7",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
