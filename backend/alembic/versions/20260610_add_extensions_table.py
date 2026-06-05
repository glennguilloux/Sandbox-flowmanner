"""Add extensions table for the plugin/extension system.

Revision ID: add_extensions_table
Revises: phase85_webhook_delivered_at, phase104_retarget_aux_tables, add_community_comments
Create Date: 2026-06-10
"""

from alembic import op
import sqlalchemy as sa

revision = "add_extensions_table"
down_revision = (
    "phase85_webhook_delivered_at",
    "phase104_retarget_aux_tables",
    "add_community_comments",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extensions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "version",
            sa.String(50),
            nullable=False,
            server_default="1.0.0",
        ),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("author", sa.String(255), nullable=True),
        sa.Column(
            "manifest",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="disabled",
        ),
        sa.Column("workspace_id", sa.String, nullable=True),
        sa.Column(
            "config",
            sa.JSON,
            nullable=True,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_extensions_workspace_id", "extensions", ["workspace_id"])
    op.create_index("ix_extensions_status", "extensions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_extensions_status", table_name="extensions")
    op.drop_index("ix_extensions_workspace_id", table_name="extensions")
    op.drop_table("extensions")
