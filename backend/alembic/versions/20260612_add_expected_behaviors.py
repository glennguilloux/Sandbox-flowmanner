"""Add expected_behaviors to mission_templates.

Revision ID: add_expected_behaviors
Revises: add_extensions_table
Create Date: 2026-06-12
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "add_expected_behaviors"
down_revision = "add_extensions_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mission_templates",
        sa.Column(
            "expected_behaviors",
            JSONB,
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("mission_templates", "expected_behaviors")
