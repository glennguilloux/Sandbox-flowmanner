"""add typed handoff packet fields

Additive migration: all 7 new columns are nullable with safe defaults.
Existing rows in handoff_records continue to load and serialize as
HandoffRecord without the new fields set.

Revision ID: handoff_packets_001
Revises: tool_routing_001
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers
revision = "handoff_packets_001"
down_revision = "tool_routing_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Each op.add_column is a separate statement — avoids asyncpg
    # multi-statement pitfall from chunk 2.
    op.add_column("handoff_records", sa.Column("goal", sa.Text(), nullable=True))
    op.add_column(
        "handoff_records",
        sa.Column("success_criteria", JSONB, nullable=True),
    )
    op.add_column(
        "handoff_records",
        sa.Column("retrieved_context_ids", JSONB, nullable=True),
    )
    op.add_column(
        "handoff_records",
        sa.Column("tool_candidates", JSONB, nullable=True),
    )
    op.add_column(
        "handoff_records",
        sa.Column(
            "budget_remaining_usd",
            sa.Numeric(precision=12, scale=6),
            nullable=True,
        ),
    )
    op.add_column(
        "handoff_records",
        sa.Column("hitl_state", JSONB, nullable=True),
    )
    op.add_column(
        "handoff_records",
        sa.Column("depth_policy_state", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("handoff_records", "depth_policy_state")
    op.drop_column("handoff_records", "hitl_state")
    op.drop_column("handoff_records", "budget_remaining_usd")
    op.drop_column("handoff_records", "tool_candidates")
    op.drop_column("handoff_records", "retrieved_context_ids")
    op.drop_column("handoff_records", "success_criteria")
    op.drop_column("handoff_records", "goal")
