"""add mission status check constraints

Revision ID: h4_5_mission_status_constraints
Revises: h4_4_delete_tenant
Create Date: 2026-06-02
"""

import sqlalchemy as sa

from alembic import op

revision = "h4_5_mission_status_constraints"
down_revision = "h4_4_delete_tenant"
branch_labels = None
depends_on = None


def upgrade():
    """Add CHECK constraints on missions.status and mission_tasks.status."""
    op.create_check_constraint(
        "ck_mission_status_valid",
        "missions",
        sa.text(
            "status IN ('draft','pending','planning','planned','queued','executing',"
            "'running','completed','approved','failed','paused','aborted','cancelled')"
        ),
    )
    op.create_check_constraint(
        "ck_mission_task_status_valid",
        "mission_tasks",
        sa.text("status IN ('pending','running','completed','failed')"),
    )


def downgrade():
    """Remove the CHECK constraints."""
    op.drop_constraint("ck_mission_status_valid", "missions", type_="check")
    op.drop_constraint("ck_mission_task_status_valid", "mission_tasks", type_="check")
