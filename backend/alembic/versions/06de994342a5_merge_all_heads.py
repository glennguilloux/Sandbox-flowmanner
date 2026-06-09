"""merge all heads

Revision ID: 06de994342a5
Revises: 202605051230, phase3_new_tables_001, add_missing_tables_001, b2c3d4e5f6a7
Create Date: 2026-05-18 23:16:45.349873

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "06de994342a5"
down_revision: Union[str, Sequence[str], None] = (
    "202605051230",
    "phase3_new_tables_001",
    "add_missing_tables_001",
    "b2c3d4e5f6a7",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
