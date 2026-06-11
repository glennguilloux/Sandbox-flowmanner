"""drop cancelled status, merge into aborted

Revision ID: h4_6_drop_cancelled_status
Revises: h4_5_mission_status_constraints
Create Date: 2026-06-02
"""

import sqlalchemy as sa

from alembic import op

revision = "h4_6_drop_cancelled_status"
down_revision = "h4_5_mission_status_constraints"
branch_labels = None
depends_on = None

NEW_STATUSES = (
    "'draft','pending','planning','planned','queued','executing',"
    "'running','completed','approved','failed','paused','aborted'"
)

OLD_STATUSES = NEW_STATUSES + ",'cancelled'"


def upgrade():
    """Merge 'cancelled' rows into 'aborted', drop cancelled from CHECK constraint."""
    # 1. Convert any existing 'cancelled' rows to 'aborted'
    op.execute("UPDATE missions SET status = 'aborted' WHERE status = 'cancelled'")

    # 2. Drop old constraint that includes 'cancelled'
    op.drop_constraint("ck_mission_status_valid", "missions", type_="check")

    # 3. Re-create without 'cancelled'
    op.create_check_constraint(
        "ck_mission_status_valid",
        "missions",
        sa.text(f"status IN ({NEW_STATUSES})"),
    )


def downgrade():
    """Restore old constraint with 'cancelled' (cannot restore old cancelled rows)."""
    op.drop_constraint("ck_mission_status_valid", "missions", type_="check")
    op.create_check_constraint(
        "ck_mission_status_valid",
        "missions",
        sa.text(f"status IN ({OLD_STATUSES})"),
    )
