"""merge H5 heads (human_interrupts + rename_graph_tables)

Revision ID: f637dac6c054
Revises: h5_rename_graph_tables, h5_human_interrupts
Create Date: 2026-06-03 06:13:40.185996

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f637dac6c054'
down_revision: Union[str, Sequence[str], None] = ('h5_rename_graph_tables', 'h5_human_interrupts')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
