"""Merge phase3_20260601_0603 into workspaces_v3_001

Revision ID: 767ad7700db4
Revises: workspaces_v3_001, phase3_20260601_0603
Create Date: 2026-06-01 06:31:23.107430

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "767ad7700db4"
down_revision: Union[str, Sequence[str], None] = (
    "workspaces_v3_001",
    "phase3_20260601_0603",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
