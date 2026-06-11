"""add_next_retry_at_to_webhook_logs

Revision ID: a1b2c3d4e5f6
Revises: 2c8ebb094375
Create Date: 2026-05-21 10:30:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1b2c3d4e5f7"
down_revision: str | Sequence[str] | None = "2c8ebb094375"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "webhook_logs",
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_webhook_logs_next_retry_at", "webhook_logs", ["next_retry_at"])
    op.alter_column("webhook_logs", "max_retries", server_default="8")


def downgrade() -> None:
    op.drop_index("ix_webhook_logs_next_retry_at", table_name="webhook_logs")
    op.drop_column("webhook_logs", "next_retry_at")
    op.alter_column("webhook_logs", "max_retries", server_default="3")
