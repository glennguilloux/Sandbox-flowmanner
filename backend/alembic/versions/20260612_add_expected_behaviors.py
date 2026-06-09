"""Add expected_behaviors to mission_templates.

Revision ID: add_expected_behaviors
Revises: add_extensions_table
Create Date: 2026-06-12
"""

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "add_expected_behaviors"
down_revision = "add_extensions_table"
branch_labels = None
depends_on = None
_TABLE = "mission_templates"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()

    if _TABLE not in tables:
        # Table was dropped by phase103_drop_old_tables — recreate with full schema
        op.create_table(
            _TABLE,
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False
            ),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("category", sa.String(100), nullable=True),
            sa.Column("icon", sa.String(50), nullable=True),
            sa.Column(
                "is_public",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column(
                "is_builtin",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("mission_type", sa.String(50), nullable=True),
            sa.Column("priority", sa.String(20), nullable=True),
            sa.Column("default_plan", JSONB, nullable=True),
            sa.Column("default_tasks", JSONB, nullable=True),
            sa.Column("default_constraints", JSONB, nullable=True),
            sa.Column("tags", JSONB, nullable=True),
            sa.Column("usage_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rating", sa.Float(), nullable=True),
            sa.Column("expected_behaviors", JSONB, nullable=False, server_default="[]"),
        )
    else:
        # Table exists — just add the column
        op.add_column(
            _TABLE,
            sa.Column(
                "expected_behaviors",
                JSONB,
                nullable=False,
                server_default="[]",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = inspector.get_table_names()
    if _TABLE in tables:
        op.drop_table(_TABLE)
