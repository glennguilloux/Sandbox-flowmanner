"""merge_v3_heads

Revision ID: 9ebabc12fb98
Revises: 20260529_agent_memory, eval_001, b1b2c3d4e5f7
Create Date: 2026-05-31 12:45:07.898166

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9ebabc12fb98"
down_revision: str | Sequence[str] | None = (
    "20260529_agent_memory",
    "eval_001",
    "b1b2c3d4e5f7",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
