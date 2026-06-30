"""Add next_fire_at to mission_programs for proper cron scheduling.

This migration adds a ``next_fire_at`` column to the ``mission_programs``
table, mirroring the existing ``mission_triggers.next_fire_at`` pattern.
Active cron programs are backfilled so they fire on the next tick.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260629_prog_next_fire"
down_revision = "fix_search_vector_trigger_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add the column (nullable, with timezone).
    op.add_column(
        "mission_programs",
        sa.Column("next_fire_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_mission_programs_next_fire_at",
        "mission_programs",
        ["next_fire_at"],
    )
    # Backfill: set next_fire_at = now() for active cron programs so they
    # fire on the next trigger_bridge tick.  This is a one-time bootstrap —
    # after the first fire, the bridge computes the real next_fire_at.
    op.execute(
        """
        UPDATE mission_programs
        SET next_fire_at = NOW()
        WHERE status = 'active'
          AND trigger_config IS NOT NULL
          AND trigger_config->>'type' = 'cron'
        """
    )


def downgrade() -> None:
    op.drop_index("ix_mission_programs_next_fire_at", table_name="mission_programs")
    op.drop_column("mission_programs", "next_fire_at")
