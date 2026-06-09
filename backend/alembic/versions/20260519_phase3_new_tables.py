"""phase3 new tables and roadmap_votes fix

Revision ID: phase3_new_tables_001
Revises: 20260518_add_mission_advanced_tables
Create Date: 2026-05-19
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "phase3_new_tables_001"
down_revision = "chat_folders_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- learning_models ---
    op.create_table(
        "adaptation_rules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("rule_id", sa.String(36), unique=True, nullable=False),
        sa.Column("agent_id", sa.String(36), nullable=True),
        sa.Column("rule_type", sa.String(100), nullable=False),
        sa.Column("condition", postgresql.JSON(), nullable=True),
        sa.Column("action_params", postgresql.JSON(), nullable=True),
        sa.Column("priority", sa.Integer(), server_default="0"),
        sa.Column("enabled", sa.Boolean(), server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_adaptation_rules_agent_id", "adaptation_rules", ["agent_id"])
    op.create_index("ix_adaptation_rules_rule_type", "adaptation_rules", ["rule_type"])

    op.create_table(
        "learning_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("feedback_type", sa.String(100), nullable=False),
        sa.Column("content", postgresql.JSON(), nullable=True),
        sa.Column("agent_id", sa.String(36), nullable=True),
        sa.Column("mission_id", sa.String(36), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_learning_feedback_feedback_type", "learning_feedback", ["feedback_type"]
    )
    op.create_index("ix_learning_feedback_agent_id", "learning_feedback", ["agent_id"])

    # --- webhook_models ---
    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("path", sa.String(255), unique=True, nullable=False),
        sa.Column("secret", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("verify_signature", sa.Boolean(), server_default="true"),
        sa.Column("signature_header", sa.String(100), nullable=True),
        sa.Column("signature_prefix", sa.String(50), nullable=True),
        sa.Column("handler_module", sa.String(255), nullable=True),
        sa.Column("handler_function", sa.String(255), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="3"),
        sa.Column("retry_delay_seconds", sa.Integer(), server_default="60"),
        sa.Column("timeout_seconds", sa.Integer(), server_default="30"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "webhook_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("endpoint_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("headers", postgresql.JSON(), nullable=True),
        sa.Column("payload", postgresql.JSON(), nullable=True),
        sa.Column("raw_body", sa.Text(), nullable=True),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSON(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_time_ms", sa.Integer(), nullable=True),
        sa.Column("max_retries", sa.Integer(), server_default="3"),
        sa.Column("retry_count", sa.Integer(), server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_webhook_logs_endpoint_id", "webhook_logs", ["endpoint_id"])

    # --- agent_models ---
    op.create_table(
        "agent_registrations",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("agent_id", sa.String(255), unique=True, nullable=False),
        sa.Column("agent_name", sa.String(255), nullable=False),
        sa.Column("agent_type", sa.String(100), nullable=False),
        sa.Column("capabilities", postgresql.JSON(), nullable=True),
        sa.Column("discovered_tools", postgresql.JSON(), nullable=True),
        sa.Column("status", sa.String(50), server_default="active"),
        sa.Column("metadata", postgresql.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_registrations_agent_id", "agent_registrations", ["agent_id"]
    )

    # --- tool_models ---
    op.create_table(
        "tool_chains",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("steps", postgresql.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_chains_owner_id", "tool_chains", ["owner_id"])

    op.create_table(
        "tool_chain_executions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("chain_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("input_data", postgresql.JSON(), nullable=True),
        sa.Column("output_data", postgresql.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tool_chain_executions_chain_id", "tool_chain_executions", ["chain_id"]
    )

    op.create_table(
        "custom_tools",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("endpoint_url", sa.String(500), nullable=True),
        sa.Column("method", sa.String(10), server_default="POST"),
        sa.Column("headers", postgresql.JSON(), nullable=True),
        sa.Column("input_schema", postgresql.JSON(), nullable=True),
        sa.Column("output_schema", postgresql.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("is_public", sa.Boolean(), server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_custom_tools_name", "custom_tools", ["name"])
    op.create_index("ix_custom_tools_owner_id", "custom_tools", ["owner_id"])

    op.create_table(
        "tool_permissions",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tool_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("permission", sa.String(50), server_default="use"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_permissions_tool_id", "tool_permissions", ["tool_id"])
    op.create_index("ix_tool_permissions_user_id", "tool_permissions", ["user_id"])

    op.create_table(
        "tool_analytics",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tool_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("latency_ms", sa.Float(), nullable=True),
        sa.Column("success", sa.Boolean(), server_default="true"),
        sa.Column("metadata_json", postgresql.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_analytics_tool_id", "tool_analytics", ["tool_id"])

    # --- flow models (flows + workflow_runs) ---
    op.create_table(
        "flows",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_flows_user_id", "flows", ["user_id"])

    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("flow_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_runs_flow_id", "workflow_runs", ["flow_id"])
    op.create_index("ix_workflow_runs_user_id", "workflow_runs", ["user_id"])

    # --- flow_schemas (projects + runs) ---
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("slug", sa.String(255), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("creator_email", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), server_default="active"),
        sa.Column("config", postgresql.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_slug", "projects", ["slug"])

    op.create_table(
        "runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("input", sa.Text(), nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("trigger", sa.String(50), server_default="api"),
        sa.Column("sender_email", sa.String(255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("run_metadata", postgresql.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runs_project_id", "runs", ["project_id"])

    # --- 3E: Fix roadmap_votes.user_id type (Integer → String(36)) ---
    op.alter_column(
        "roadmap_votes",
        "user_id",
        existing_type=sa.Integer(),
        type_=sa.String(36),
        existing_nullable=False,
    )
    op.alter_column(
        "roadmap_comments",
        "user_id",
        existing_type=sa.Integer(),
        type_=sa.String(36),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Reverse roadmap_votes type change
    op.alter_column(
        "roadmap_comments",
        "user_id",
        existing_type=sa.String(36),
        type_=sa.Integer(),
        existing_nullable=False,
    )
    op.alter_column(
        "roadmap_votes",
        "user_id",
        existing_type=sa.String(36),
        type_=sa.Integer(),
        existing_nullable=False,
    )

    # Drop tables in reverse dependency order
    for table in [
        "runs",
        "projects",
        "workflow_runs",
        "flows",
        "tool_analytics",
        "tool_permissions",
        "custom_tools",
        "tool_chain_executions",
        "tool_chains",
        "agent_registrations",
        "webhook_logs",
        "webhook_endpoints",
        "learning_feedback",
        "adaptation_rules",
    ]:
        op.drop_table(table)
