"""workspace_shares table for cross-workspace permission grants.

Revision ID: ws_shares_001
Revises: 20260606_workspace_native
Create Date: 2026-06-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = "ws_shares_001"
down_revision = "20260606_workspace_native"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_shares",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "source_workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "target_workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(100), nullable=False, index=True),
        sa.Column("permission", sa.String(20), nullable=False, server_default="read"),
        sa.Column(
            "granted_by",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "source_workspace_id",
            "target_workspace_id",
            "entity_type",
            "entity_id",
            name="uq_workspace_share",
        ),
    )
    op.create_index("ix_ws_share_target", "workspace_shares", ["target_workspace_id", "is_active"])
    op.create_index("ix_ws_share_entity", "workspace_shares", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_table("workspace_shares")
