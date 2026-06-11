"""add oauth token fields to integration_connections

Revision ID: 20260525_add_oauth_token_fields
Revises: 20260721_agent_protocol
Create Date: 2026-05-25 05:30:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260525_add_oauth_token_fields"
down_revision: str | Sequence[str] | None = "20260721_agent_protocol"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "integration_connections",
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
    )
    op.add_column(
        "integration_connections",
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
    )
    op.add_column(
        "integration_connections",
        sa.Column("token_type", sa.String(50), nullable=True, server_default="Bearer"),
    )


def downgrade() -> None:
    op.drop_column("integration_connections", "token_type")
    op.drop_column("integration_connections", "encrypted_refresh_token")
    op.drop_column("integration_connections", "encrypted_access_token")
