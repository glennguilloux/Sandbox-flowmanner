"""Create mission_plan_candidates table — cost-aware plan selection persistence.

Creates:
- ``mission_plan_candidates`` table for storing ranked plan candidates
- Index on mission_id for efficient lookup by mission
- Index on (mission_id, rank) for winner lookup
"""

revision = "20260630_plan_candidates"
down_revision = "20260630_external_events"
branch_labels = None
depends_on = None

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


def upgrade() -> None:
    op.create_table(
        "mission_plan_candidates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "mission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("missions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plan_id", sa.String(100), nullable=False),
        sa.Column("generation_strategy", sa.String(50), nullable=False),
        sa.Column("tasks_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "estimated_cost_usd",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
        sa.Column(
            "estimated_latency_ms",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "estimated_tokens",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "quality_score",
            sa.Float(),
            nullable=False,
            server_default="0.0",
        ),
        sa.Column(
            "risk_flags",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "rationale",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "rank",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Indexes
    op.create_index(
        "ix_mission_plan_candidates_mission_id",
        "mission_plan_candidates",
        ["mission_id"],
    )
    op.create_index(
        "ix_mission_plan_candidates_mission_rank",
        "mission_plan_candidates",
        ["mission_id", "rank"],
    )


def downgrade() -> None:
    op.drop_index("ix_mission_plan_candidates_mission_rank", table_name="mission_plan_candidates")
    op.drop_index("ix_mission_plan_candidates_mission_id", table_name="mission_plan_candidates")
    op.drop_table("mission_plan_candidates")
