"""Hotfix: formalize direct SQL fixes for user_api_keys, orchestrator tables, mission_templates.

These changes were already applied via direct SQL during a hotfix session.
This migration captures them in Alembic's history so fresh deploys get them automatically.

Revision ID: hotfix_sql_fixes
Revises: add_expected_behaviors
Create Date: 2026-06-14
"""

import sqlalchemy as sa
from sqlalchemy import inspect, text
from sqlalchemy.dialects.postgresql import JSONB

from alembic import context, op

revision = "hotfix_sql_fixes"
down_revision = "add_expected_behaviors"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        return

    bind = op.get_bind()
    inspector = inspect(bind)

    # ── 1. user_api_keys: add workspace_id column + indexes ────────────
    user_api_keys_cols = {c["name"] for c in inspector.get_columns("user_api_keys")}

    if "workspace_id" not in user_api_keys_cols:
        op.add_column(
            "user_api_keys",
            sa.Column("workspace_id", sa.String(36), nullable=True),
        )

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("user_api_keys")}

    if "ix_user_api_keys_workspace" not in existing_indexes:
        op.create_index(
            "ix_user_api_keys_workspace",
            "user_api_keys",
            ["workspace_id"],
        )

    if "ix_user_api_keys_workspace_user" not in existing_indexes:
        op.create_index(
            "ix_user_api_keys_workspace_user",
            "user_api_keys",
            ["workspace_id", "user_id"],
        )

    # ── 2. orchestrator_executions / orchestrator_tasks tables ─────────
    tables = set(inspector.get_table_names())

    if "orchestrator_executions" not in tables:
        op.create_table(
            "orchestrator_executions",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("goal", sa.Text(), nullable=False),
            sa.Column("status", sa.String(20), server_default="pending"),
            sa.Column("strategy", sa.String(50), server_default="parallel"),
            sa.Column("synthesis", sa.Text(), nullable=True),
            sa.Column("conflict_markers", JSONB, nullable=True),
            sa.Column("agent_count", sa.Integer(), server_default="0"),
            sa.Column("completed_count", sa.Integer(), server_default="0"),
            sa.Column("total_tokens", sa.Integer(), server_default="0"),
            sa.Column("total_cost_usd", sa.Float(), server_default="0.0"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("metadata", JSONB, nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    if "orchestrator_tasks" not in tables:
        op.create_table(
            "orchestrator_tasks",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "execution_id",
                sa.String(36),
                sa.ForeignKey("orchestrator_executions.id"),
                nullable=False,
            ),
            sa.Column("agent_id", sa.String(36), nullable=True),
            sa.Column("agent_name", sa.String(100), nullable=True),
            sa.Column("task_description", sa.Text(), nullable=False),
            sa.Column("task_type", sa.String(50), server_default="general"),
            sa.Column("status", sa.String(20), server_default="pending"),
            sa.Column("output", sa.Text(), nullable=True),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("tokens_used", sa.Integer(), server_default="0"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("depends_on", JSONB, nullable=True),
            sa.Column("priority", sa.Integer(), server_default="0"),
            sa.Column("retry_count", sa.Integer(), server_default="0"),
            sa.Column("metadata", JSONB, nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )

    # ── 3. mission_templates: add created_at / updated_at columns ──────
    if "mission_templates" in tables:
        mt_cols = {c["name"] for c in inspector.get_columns("mission_templates")}

        if "created_at" not in mt_cols:
            op.add_column(
                "mission_templates",
                sa.Column(
                    "created_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.func.now(),
                ),
            )

        if "updated_at" not in mt_cols:
            op.add_column(
                "mission_templates",
                sa.Column(
                    "updated_at",
                    sa.DateTime(timezone=True),
                    nullable=False,
                    server_default=sa.func.now(),
                ),
            )


def downgrade() -> None:
    if context.is_offline_mode():
        return

    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    # mission_templates: drop timestamp columns
    if "mission_templates" in tables:
        mt_cols = {c["name"] for c in inspector.get_columns("mission_templates")}
        if "updated_at" in mt_cols:
            op.drop_column("mission_templates", "updated_at")
        if "created_at" in mt_cols:
            op.drop_column("mission_templates", "created_at")

    # orchestrator tables
    if "orchestrator_tasks" in tables:
        op.drop_table("orchestrator_tasks")
    if "orchestrator_executions" in tables:
        op.drop_table("orchestrator_executions")

    # user_api_keys: drop indexes and column
    existing_indexes = {idx["name"] for idx in inspector.get_indexes("user_api_keys")}
    if "ix_user_api_keys_workspace_user" in existing_indexes:
        op.drop_index("ix_user_api_keys_workspace_user", table_name="user_api_keys")
    if "ix_user_api_keys_workspace" in existing_indexes:
        op.drop_index("ix_user_api_keys_workspace", table_name="user_api_keys")
    user_api_keys_cols = {c["name"] for c in inspector.get_columns("user_api_keys")}
    if "workspace_id" in user_api_keys_cols:
        op.drop_column("user_api_keys", "workspace_id")
