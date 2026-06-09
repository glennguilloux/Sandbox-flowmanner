"""Add agent_tool_bindings, agent_capability_bindings, capability_dependencies tables.

Normalized binding tables for Phase 2.3 — replace ad-hoc JSON arrays
with proper FK-linked many-to-many relationships.

Revision ID: 20260604_bindings
Revises: 20260603_topology
Create Date: 2026-06-04 10:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260604_bindings"
down_revision: Union[str, Sequence[str], None] = "20260603_topology"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── agent_tool_bindings ──────────────────────────────────────────
    op.create_table(
        "agent_tool_bindings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("agent_templates.template_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tool_id",
            sa.String(36),
            sa.ForeignKey("tools_catalog.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), server_default=sa.text("0")),
        sa.Column("config_override", postgresql.JSONB(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_atb_agent_id", "agent_tool_bindings", ["agent_id"])
    op.create_index("ix_atb_tool_id", "agent_tool_bindings", ["tool_id"])
    op.create_index(
        "ix_atb_agent_tool_unique",
        "agent_tool_bindings",
        ["agent_id", "tool_id"],
        unique=True,
    )

    # ── agent_capability_bindings ────────────────────────────────────
    op.create_table(
        "agent_capability_bindings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("agent_templates.template_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "capability_id",
            sa.String(36),
            sa.ForeignKey("capabilities_catalog.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), server_default=sa.text("0")),
        sa.Column("config_override", postgresql.JSONB(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_acb_agent_id", "agent_capability_bindings", ["agent_id"])
    op.create_index(
        "ix_acb_capability_id", "agent_capability_bindings", ["capability_id"]
    )
    op.create_index(
        "ix_acb_agent_cap_unique",
        "agent_capability_bindings",
        ["agent_id", "capability_id"],
        unique=True,
    )

    # ── capability_dependencies ──────────────────────────────────────
    op.create_table(
        "capability_dependencies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "capability_id",
            sa.String(36),
            sa.ForeignKey("capabilities_catalog.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "depends_on_id",
            sa.String(36),
            sa.ForeignKey("capabilities_catalog.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dependency_type",
            sa.String(20),
            nullable=False,
            server_default="required",
        ),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_cd_capability_id", "capability_dependencies", ["capability_id"])
    op.create_index("ix_cd_depends_on_id", "capability_dependencies", ["depends_on_id"])
    op.create_index(
        "ix_cd_cap_dep_unique",
        "capability_dependencies",
        ["capability_id", "depends_on_id"],
        unique=True,
    )
    # Prevent self-referencing dependency
    op.execute(
        "ALTER TABLE capability_dependencies ADD CONSTRAINT chk_no_self_dep "
        "CHECK (capability_id <> depends_on_id)"
    )


def downgrade() -> None:
    op.drop_table("capability_dependencies")
    op.drop_table("agent_capability_bindings")
    op.drop_table("agent_tool_bindings")
