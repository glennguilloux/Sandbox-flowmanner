"""add_delivered_at_to_webhook_logs

Revision ID: c3d4e5f6a7b8
Revises: b1b2c3d4e5f7
Create Date: 2026-06-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'phase85_webhook_delivered_at'
down_revision: Union[str, Sequence[str], None] = 'b1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('webhook_logs', sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_webhook_logs_delivered_at', 'webhook_logs', ['delivered_at'])
    op.create_index('ix_webhook_logs_status', 'webhook_logs', ['status'])


def downgrade() -> None:
    op.drop_index('ix_webhook_logs_status', table_name='webhook_logs')
    op.drop_index('ix_webhook_logs_delivered_at', table_name='webhook_logs')
    op.drop_column('webhook_logs', 'delivered_at')
