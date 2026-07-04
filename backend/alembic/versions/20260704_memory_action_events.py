"""memory_action_events table (AutoMem Phase 1).

Revision ID: 20260704_memory_action_events
Create Date: 2026-07-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON, UUID

# revision identifiers, used by Alembic.
revision = "20260704_memory_action_events"
down_revision = "audit_log_perf_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_action_events",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=False), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mission_id", UUID(as_uuid=False), nullable=True),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("action_input", JSON, nullable=False),
        sa.Column("action_result", JSON, nullable=False),
        sa.Column("action_latency_ms", sa.Float(), nullable=False),
        sa.Column("action_success", sa.Boolean(), nullable=False),
        sa.Column("agent_confidence", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Indexes with IF NOT EXISTS for idempotency
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mem_actions_ws_user_created "
        "ON memory_action_events (workspace_id, user_id, created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mem_actions_mission "
        "ON memory_action_events (mission_id) "
        "WHERE mission_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mem_actions_type "
        "ON memory_action_events (action_type)"
    )


def downgrade() -> None:
    op.drop_table("memory_action_events")
