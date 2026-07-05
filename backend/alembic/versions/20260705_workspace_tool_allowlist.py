"""workspace_tool_allowlist table — per-workspace tool permissions.

Revision ID: 20260705_workspace_tool_allowlist
Revises: 20260705_scaffold_rejection_reason
Create Date: 2026-07-05
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260705_workspace_tool_allowlist"
down_revision = "20260705_scaffold_rejection_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_tool_allowlist",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("tool_name", sa.String(200), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column(
            "granted_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "tool_name", name="uq_workspace_tool"),
    )
    # Index for the common query pattern: look up active tools for a workspace
    op.create_index(
        "ix_workspace_tool_allowlist_workspace_active",
        "workspace_tool_allowlist",
        ["workspace_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_tool_allowlist_workspace_active", table_name="workspace_tool_allowlist")
    op.drop_table("workspace_tool_allowlist")
