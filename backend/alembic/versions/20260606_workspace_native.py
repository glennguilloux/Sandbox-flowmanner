"""Workspace-native substrate — Phase 3.3.

Adds workspace_id FK columns to all operational and catalog tables,
making the workspace the primary organizational unit for all operations.

Tables modified:
- missions, agents (operational — nullable, SET NULL on delete)
- workflows, workflow_executions (operational — nullable, SET NULL on delete)
- agent_templates (catalog — nullable, SET NULL on delete)
- tools_catalog, capabilities_catalog (catalog — nullable, no FK, NULL = global)
- chat_threads (operational — nullable, no FK)

Revision ID: 20260606_workspace_native
Revises: 20260605_entity_versioning
Create Date: 2026-06-06 10:00:00.000000
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260606_workspace_native"
down_revision: str | Sequence[str] | None = "20260605_entity_versioning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Operational tables (FK → workspaces.id, SET NULL on delete) ──

    # missions
    op.add_column(
        "missions",
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_missions_workspace_id", "missions", ["workspace_id"])

    # agents
    op.add_column(
        "agents",
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_agents_workspace_id", "agents", ["workspace_id"])

    # workflows
    op.add_column(
        "workflows",
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_workflows_workspace_id", "workflows", ["workspace_id"])

    # workflow_executions
    op.add_column(
        "workflow_executions",
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_wf_exec_workspace_id", "workflow_executions", ["workspace_id"])

    # agent_templates
    op.add_column(
        "agent_templates",
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_agent_templates_workspace_id", "agent_templates", ["workspace_id"]
    )

    # ── Catalog tables (no FK — NULL = global/builtin) ──────────────

    # tools_catalog
    op.add_column(
        "tools_catalog",
        sa.Column(
            "workspace_id",
            sa.String(36),
            nullable=True,
        ),
    )
    op.create_index("ix_tools_catalog_workspace_id", "tools_catalog", ["workspace_id"])

    # capabilities_catalog
    op.add_column(
        "capabilities_catalog",
        sa.Column(
            "workspace_id",
            sa.String(36),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_capabilities_catalog_workspace_id", "capabilities_catalog", ["workspace_id"]
    )

    # ── Chat tables (no FK — nullable) ──────────────────────────────

    # chat_threads
    op.add_column(
        "chat_threads",
        sa.Column(
            "workspace_id",
            sa.String(36),
            nullable=True,
        ),
    )
    op.create_index("ix_chat_threads_workspace_id", "chat_threads", ["workspace_id"])


def downgrade() -> None:
    # chat_threads
    op.drop_index("ix_chat_threads_workspace_id", table_name="chat_threads")
    op.drop_column("chat_threads", "workspace_id")

    # capabilities_catalog
    op.drop_index(
        "ix_capabilities_catalog_workspace_id", table_name="capabilities_catalog"
    )
    op.drop_column("capabilities_catalog", "workspace_id")

    # tools_catalog
    op.drop_index("ix_tools_catalog_workspace_id", table_name="tools_catalog")
    op.drop_column("tools_catalog", "workspace_id")

    # agent_templates
    op.drop_index("ix_agent_templates_workspace_id", table_name="agent_templates")
    op.drop_column("agent_templates", "workspace_id")

    # workflow_executions
    op.drop_index("ix_wf_exec_workspace_id", table_name="workflow_executions")
    op.drop_column("workflow_executions", "workspace_id")

    # workflows
    op.drop_index("ix_workflows_workspace_id", table_name="workflows")
    op.drop_column("workflows", "workspace_id")

    # agents
    op.drop_index("ix_agents_workspace_id", table_name="agents")
    op.drop_column("agents", "workspace_id")

    # missions
    op.drop_index("ix_missions_workspace_id", table_name="missions")
    op.drop_column("missions", "workspace_id")
