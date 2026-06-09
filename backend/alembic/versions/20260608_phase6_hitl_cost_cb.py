"""Phase 6 — HITL, Cost Attribution, Circuit Breaker, Episodic Memory.

Creates:
- inbox_items: Persistent HITL inbox (approval, clarification, escalation)
- mission_circuit_breakers: Per-mission execution limits and state
- Adds workspace_id + agent_id to llm_call_records for cost attribution

Revision ID: phase6_hitl_cost_cb
Revises: marketplace_v2_001
Create Date: 2026-06-08
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "phase6_hitl_cost_cb"
down_revision = "marketplace_v2_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── inbox_items (Phase 6.2) ──────────────────────────────────────
    op.create_table(
        "inbox_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "mission_id",
            sa.String(36),
            sa.ForeignKey("missions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("task_id", sa.String(36), nullable=True),
        sa.Column("node_id", sa.String(36), nullable=True),
        sa.Column("interrupt_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("proposed_action", JSONB, nullable=True),
        sa.Column("context", JSONB, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolution_payload", JSONB, nullable=True),
        sa.Column("resolution_note", sa.Text, nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_inbox_user", "inbox_items", ["user_id"])
    op.create_index("ix_inbox_mission", "inbox_items", ["mission_id"])
    op.create_index("ix_inbox_status", "inbox_items", ["status"])
    op.create_index("ix_inbox_type", "inbox_items", ["interrupt_type"])
    op.create_index("ix_inbox_workspace", "inbox_items", ["workspace_id"])
    op.create_index("ix_inbox_run", "inbox_items", ["run_id"])

    # ── mission_circuit_breakers (Phase 6.4) ─────────────────────────
    op.create_table(
        "mission_circuit_breakers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "mission_id",
            sa.String(36),
            sa.ForeignKey("missions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("workspace_id", sa.String(36), nullable=True),
        sa.Column("max_llm_calls", sa.Integer, nullable=False, server_default="100"),
        sa.Column("max_cost_usd", sa.Float, nullable=False, server_default="10.0"),
        sa.Column(
            "max_duration_seconds", sa.Integer, nullable=False, server_default="3600"
        ),
        sa.Column("max_tool_calls", sa.Integer, nullable=False, server_default="200"),
        sa.Column(
            "destructive_actions_require_approval",
            sa.Boolean,
            nullable=False,
            server_default="true",
        ),
        sa.Column("llm_calls_made", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tool_calls_made", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "cost_accumulated_usd", sa.Float, nullable=False, server_default="0.0"
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("state", sa.String(20), nullable=False, server_default="armed"),
        sa.Column("trigger_reason", sa.Text, nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("destructive_actions", JSONB, nullable=True),
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
    op.create_index(
        "ix_mcb_mission", "mission_circuit_breakers", ["mission_id"], unique=True
    )
    op.create_index("ix_mcb_workspace", "mission_circuit_breakers", ["workspace_id"])
    op.create_index("ix_mcb_state", "mission_circuit_breakers", ["state"])

    # ── llm_call_records: cost attribution columns (Phase 6.3) ───────
    op.add_column(
        "llm_call_records",
        sa.Column(
            "agent_id",
            sa.UUID(),
            nullable=True,
        ),
    )
    op.add_column(
        "llm_call_records",
        sa.Column(
            "workspace_id",
            sa.String(36),
            nullable=True,
        ),
    )
    op.create_index("ix_llmcr_agent", "llm_call_records", ["agent_id"])
    op.create_index("ix_llmcr_workspace", "llm_call_records", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_llmcr_workspace", table_name="llm_call_records")
    op.drop_index("ix_llmcr_agent", table_name="llm_call_records")
    op.drop_column("llm_call_records", "workspace_id")
    op.drop_column("llm_call_records", "agent_id")

    op.drop_index("ix_mcb_state", table_name="mission_circuit_breakers")
    op.drop_index("ix_mcb_workspace", table_name="mission_circuit_breakers")
    op.drop_index("ix_mcb_mission", table_name="mission_circuit_breakers")
    op.drop_table("mission_circuit_breakers")

    op.drop_index("ix_inbox_run", table_name="inbox_items")
    op.drop_index("ix_inbox_workspace", table_name="inbox_items")
    op.drop_index("ix_inbox_type", table_name="inbox_items")
    op.drop_index("ix_inbox_status", table_name="inbox_items")
    op.drop_index("ix_inbox_mission", table_name="inbox_items")
    op.drop_index("ix_inbox_user", table_name="inbox_items")
    op.drop_table("inbox_items")
