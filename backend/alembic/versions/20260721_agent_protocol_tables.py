"""Add agent protocol tables: agent_messages, debate_rounds, handoff_records, escalation_records.

Phase 26 Week 3: Agent Protocol - inter-agent communication infrastructure.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "20260721_agent_protocol"
down_revision = "2c8ebb094375"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # agent_messages
    op.create_table(
        "agent_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("sender_id", sa.String(255), nullable=False, index=True),
        sa.Column("sender_name", sa.String(255), nullable=True),
        sa.Column("recipient_id", sa.String(255), nullable=False, index=True),
        sa.Column("recipient_name", sa.String(255), nullable=True),
        sa.Column("type", sa.String(20), nullable=False, index=True),
        sa.Column("sub_type", sa.String(50), nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("priority", sa.Integer, default=0, nullable=False),
        sa.Column("correlation_id", sa.String(36), nullable=True, index=True),
        sa.Column("parent_message_id", sa.String(36), nullable=True),
        sa.Column("execution_id", sa.String(36), nullable=True, index=True),
        sa.Column("status", sa.String(20), default="delivered", nullable=False, index=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("tags", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_foreign_key(
        "fk_agent_messages_parent",
        "agent_messages", "agent_messages",
        ["parent_message_id"], ["id"],
        ondelete="SET NULL",
    )

    # debate_rounds
    op.create_table(
        "debate_rounds",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("debate_id", sa.String(36), nullable=False, index=True),
        sa.Column("round_number", sa.Integer, nullable=False),
        sa.Column("topic", sa.Text, nullable=False),
        sa.Column("criteria", postgresql.JSONB, nullable=True),
        sa.Column("position_a", sa.Text, nullable=True),
        sa.Column("position_b", sa.Text, nullable=True),
        sa.Column("rebuttal_a", sa.Text, nullable=True),
        sa.Column("rebuttal_b", sa.Text, nullable=True),
        sa.Column("agent_a_id", sa.String(255), nullable=True),
        sa.Column("agent_b_id", sa.String(255), nullable=True),
        sa.Column("judge_id", sa.String(255), nullable=True),
        sa.Column("judge_score_a", sa.Float, nullable=True),
        sa.Column("judge_score_b", sa.Float, nullable=True),
        sa.Column("judge_reasoning", sa.Text, nullable=True),
        sa.Column("judge_verdict", sa.String(50), nullable=True),
        sa.Column("consensus_reached", sa.Boolean, default=False, nullable=False),
        sa.Column("consensus_synthesis", sa.Text, nullable=True),
        sa.Column("consensus_score", sa.Float, nullable=True),
        sa.Column("tokens_used", sa.Integer, default=0, nullable=False),
        sa.Column("status", sa.String(20), default="pending", nullable=False, index=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )

    # handoff_records
    op.create_table(
        "handoff_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("from_agent_id", sa.String(255), nullable=False, index=True),
        sa.Column("from_agent_name", sa.String(255), nullable=True),
        sa.Column("to_agent_id", sa.String(255), nullable=False, index=True),
        sa.Column("to_agent_name", sa.String(255), nullable=True),
        sa.Column("task_description", sa.Text, nullable=False),
        sa.Column("task_type", sa.String(50), nullable=False, default="general"),
        sa.Column("context", postgresql.JSONB, nullable=True),
        sa.Column("constraints", postgresql.JSONB, nullable=True),
        sa.Column("priority", sa.Integer, default=0, nullable=False),
        sa.Column("result", sa.Text, nullable=True),
        sa.Column("result_metadata", postgresql.JSONB, nullable=True),
        sa.Column("parent_handoff_id", sa.String(36), nullable=True),
        sa.Column("execution_id", sa.String(36), nullable=True, index=True),
        sa.Column("status", sa.String(20), default="pending", nullable=False, index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_foreign_key(
        "fk_handoff_parent",
        "handoff_records", "handoff_records",
        ["parent_handoff_id"], ["id"],
        ondelete="SET NULL",
    )

    # escalation_records
    op.create_table(
        "escalation_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), nullable=False, index=True),
        sa.Column("task_description", sa.Text, nullable=False),
        sa.Column("level", sa.Integer, default=0, nullable=False),
        sa.Column("attempted_agent_id", sa.String(255), nullable=True),
        sa.Column("attempted_agent_name", sa.String(255), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("escalated_to_agent_id", sa.String(255), nullable=True),
        sa.Column("escalated_to_agent_name", sa.String(255), nullable=True),
        sa.Column("resolved", sa.Boolean, default=False, nullable=False),
        sa.Column("resolution_output", sa.Text, nullable=True),
        sa.Column("resolution_agent_id", sa.String(255), nullable=True),
        sa.Column("max_retries_per_level", sa.Integer, default=2, nullable=False),
        sa.Column("retries_at_level", sa.Integer, default=0, nullable=False),
        sa.Column("escalation_policy", sa.String(50), default="default", nullable=False),
        sa.Column("status", sa.String(20), default="active", nullable=False, index=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("escalation_records")
    op.drop_table("handoff_records")
    op.drop_table("debate_rounds")
    op.drop_table("agent_messages")
