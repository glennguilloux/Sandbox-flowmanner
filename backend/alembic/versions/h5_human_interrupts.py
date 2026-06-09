"""Add human_interrupts table for HITL inbox (H5.2).

Creates the human_interrupts table with columns for:
- mission_id (FK to missions)
- interrupt_type (approval | clarification | escalation)
- context, proposed_action (JSON)
- confidence, deadline
- status (pending | approved | rejected | expired)
- resolved_by, resolved_at
"""

revision = "h5_human_interrupts"
down_revision = "h2_substrate_init"
branch_labels = None
depends_on = None

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    op.create_table(
        "human_interrupts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=False),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "mission_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("missions.id"),
            nullable=False,
        ),
        sa.Column(
            "interrupt_type",
            sa.String(20),
            nullable=False,
        ),
        sa.Column("context", postgresql.JSON(), nullable=True),
        sa.Column("proposed_action", postgresql.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True, server_default="0.5"),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("resolved_by", sa.String(100), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_human_interrupts_mission_id",
        "human_interrupts",
        ["mission_id"],
    )
    op.create_index(
        "ix_human_interrupts_status",
        "human_interrupts",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_human_interrupts_status", table_name="human_interrupts")
    op.drop_index("ix_human_interrupts_mission_id", table_name="human_interrupts")
    op.drop_table("human_interrupts")
