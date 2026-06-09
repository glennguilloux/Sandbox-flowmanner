"""Add tools_catalog, tool_versions, capabilities_catalog, capability_versions tables.

Revision ID: 20260603_tools_capabilities
Revises: 20260603_memory_entries
Create Date: 2026-06-03 22:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260603_tools_capabilities"
down_revision: Union[str, Sequence[str], None] = "20260603_memory_entries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── tools_catalog ────────────────────────────────────────────────
    op.create_table(
        "tools_catalog",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(255), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("tool_type", sa.String(50), nullable=False, server_default="builtin"),
        sa.Column("handler_ref", sa.String(500), nullable=True),
        sa.Column("input_schema", postgresql.JSONB(), nullable=True),
        sa.Column("output_schema", postgresql.JSONB(), nullable=True),
        sa.Column("auth_policy", postgresql.JSONB(), nullable=True),
        sa.Column("visibility", sa.String(50), server_default="public"),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("version", sa.Integer(), server_default=sa.text("1")),
        sa.Column("source", sa.String(50), server_default="db"),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=True),
        sa.Column("tier", sa.Integer(), server_default=sa.text("1")),
        sa.Column("timeout_seconds", sa.Integer(), server_default=sa.text("30")),
        sa.Column("requires_auth", sa.Boolean(), server_default=sa.text("true")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_tools_catalog_slug", "tools_catalog", ["slug"])
    op.create_index("ix_tools_catalog_category", "tools_catalog", ["category"])
    op.create_index("ix_tools_catalog_enabled", "tools_catalog", ["enabled"])

    # ── tool_versions ────────────────────────────────────────────────
    op.create_table(
        "tool_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tool_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_tool_versions_tool_id", "tool_versions", ["tool_id"])

    # ── capabilities_catalog ─────────────────────────────────────────
    op.create_table(
        "capabilities_catalog",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(255), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("handler_ref", sa.String(500), nullable=True),
        sa.Column("input_schema", postgresql.JSONB(), nullable=True),
        sa.Column("output_schema", postgresql.JSONB(), nullable=True),
        sa.Column("auth_policy", postgresql.JSONB(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), server_default=sa.text("30")),
        sa.Column("rate_limit", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("version", sa.Integer(), server_default=sa.text("1")),
        sa.Column("source", sa.String(50), server_default="db"),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index("ix_capabilities_catalog_slug", "capabilities_catalog", ["slug"])
    op.create_index(
        "ix_capabilities_catalog_category", "capabilities_catalog", ["category"]
    )

    # ── capability_versions ──────────────────────────────────────────
    op.create_table(
        "capability_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("capability_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_capability_versions_capability_id", "capability_versions", ["capability_id"]
    )

    # ── agent_templates: add canonical columns ──────────────────────
    op.add_column(
        "agent_templates", sa.Column("slug", sa.String(255), unique=True, nullable=True)
    )
    op.add_column(
        "agent_templates",
        sa.Column("version", sa.Integer(), server_default=sa.text("1")),
    )
    op.add_column(
        "agent_templates", sa.Column("source", sa.String(50), server_default="db")
    )
    op.add_column(
        "agent_templates", sa.Column("definition", postgresql.JSONB(), nullable=True)
    )

    # Backfill slug from model_config->>'slug' for existing rows
    op.execute(
        """
        UPDATE agent_templates
        SET slug = model_config->>'slug'
        WHERE slug IS NULL AND model_config->>'slug' IS NOT NULL
    """
    )
    # For any remaining rows without slug in model_config, derive from name
    op.execute(
        """
        UPDATE agent_templates
        SET slug = lower(replace(replace(name, ' ', '-'), '_', '-'))
        WHERE slug IS NULL
    """
    )
    # Deduplicate: if multiple rows share a slug, keep the newest
    op.execute(
        """
        DELETE FROM agent_templates
        WHERE template_id NOT IN (
            SELECT DISTINCT ON (slug) template_id
            FROM agent_templates
            WHERE slug IS NOT NULL
            ORDER BY slug, created_at DESC
        ) AND slug IS NOT NULL
    """
    )

    op.create_index("ix_agent_templates_slug", "agent_templates", ["slug"])

    # ── agent_template_versions ─────────────────────────────────────
    op.create_table(
        "agent_template_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("template_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
    )
    op.create_index(
        "ix_agent_template_versions_template_id",
        "agent_template_versions",
        ["template_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_template_versions_template_id", table_name="agent_template_versions"
    )
    op.drop_table("agent_template_versions")
    op.drop_index("ix_agent_templates_slug", table_name="agent_templates")
    op.drop_column("agent_templates", "definition")
    op.drop_column("agent_templates", "source")
    op.drop_column("agent_templates", "version")
    op.drop_column("agent_templates", "slug")
    op.drop_index(
        "ix_capability_versions_capability_id", table_name="capability_versions"
    )
    op.drop_table("capability_versions")
    op.drop_index("ix_capabilities_catalog_category", table_name="capabilities_catalog")
    op.drop_index("ix_capabilities_catalog_slug", table_name="capabilities_catalog")
    op.drop_table("capabilities_catalog")
    op.drop_index("ix_tool_versions_tool_id", table_name="tool_versions")
    op.drop_table("tool_versions")
    op.drop_index("ix_tools_catalog_enabled", table_name="tools_catalog")
    op.drop_index("ix_tools_catalog_category", table_name="tools_catalog")
    op.drop_index("ix_tools_catalog_slug", table_name="tools_catalog")
    op.drop_table("tools_catalog")
