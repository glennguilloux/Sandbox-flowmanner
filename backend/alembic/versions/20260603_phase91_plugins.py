"""Phase 9.1: Plugin system — installed_plugins table.

Revision ID: 20260603_phase91_plugins
Revises: 20260603_phase82_workspace_api_keys
Create Date: 2026-06-03
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision = "20260603_phase91_plugins"
down_revision = "phase82_workspace_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "installed_plugins",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False, index=True),
        sa.Column("name", sa.String(64), nullable=False, index=True),
        sa.Column("version", sa.String(20), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("author", sa.String(200), nullable=True),
        sa.Column("manifest_json", sa.Text, nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default="upload"),
        sa.Column("listing_id", sa.String(36), nullable=True, index=True),
        sa.Column("install_path", sa.Text, nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="installed",
            index=True,
        ),
        sa.Column("execution_count", sa.Integer, server_default="0"),
        sa.Column("error_count", sa.Integer, server_default="0"),
        sa.Column("last_executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("permissions_json", sa.Text, nullable=True),
        sa.Column("node_types_json", sa.Text, nullable=True),
        sa.Column("config_json", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_installed_plugins_workspace_name",
        "installed_plugins",
        ["workspace_id", "name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_installed_plugins_workspace_name", table_name="installed_plugins")
    op.drop_table("installed_plugins")
