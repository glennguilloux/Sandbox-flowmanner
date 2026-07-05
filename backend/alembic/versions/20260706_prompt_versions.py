"""prompt_versions table — versioned system prompts per workspace.

Revision ID: 20260706_prompt_versions
Revises: 20260705_workspace_tool_allowlist
Create Date: 2026-07-06
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260706_prompt_versions"
down_revision = "20260705_workspace_tool_allowlist"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column(
            "created_by",
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
        sa.UniqueConstraint("workspace_id", "name", "version", name="uq_prompt_version"),
    )
    # Index for the common query: active prompts per workspace
    op.create_index(
        "ix_prompt_versions_workspace_active",
        "prompt_versions",
        ["workspace_id", "is_active"],
    )
    # Index for name-based lookups within a workspace
    op.create_index(
        "ix_prompt_versions_workspace_name",
        "prompt_versions",
        ["workspace_id", "name"],
    )


def downgrade() -> None:
    op.drop_index("ix_prompt_versions_workspace_name", table_name="prompt_versions")
    op.drop_index("ix_prompt_versions_workspace_active", table_name="prompt_versions")
    op.drop_table("prompt_versions")
