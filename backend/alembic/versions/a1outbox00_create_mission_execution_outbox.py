"""create mission_execution_outbox (durable async mission dispatch outbox).

Group D (2026-07-18): the ORM ``MissionExecutionOutbox``
(app/models/mission_models.py:290) is written at runtime by the fail-closed
Celery dispatch path (app/api/_mission_cqrs/commands.py:583) inside the same
transaction that marks a mission QUEUED. The table had no migration and did not
exist in the live DB, so any brief broker outage raised RetryableMissionError.
This is a pure additive CREATE matching the ORM columns exactly.

Column/index parity verified against:
- app/models/mission_models.py:300-310 (columns, nullability, defaults)
- scripts/model_snapshot.json:2214-2218 (index names)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1outbox00"
down_revision: str | None = "a1p1probe00"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mission_execution_outbox",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "mission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("missions.id"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("selected_plan_id", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("picked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mission_execution_outbox_mission_id",
        "mission_execution_outbox",
        ["mission_id"],
    )
    op.create_index(
        "ix_mission_execution_outbox_run_id",
        "mission_execution_outbox",
        ["run_id"],
    )
    op.create_index(
        "ix_mission_execution_outbox_status",
        "mission_execution_outbox",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mission_execution_outbox_status",
        table_name="mission_execution_outbox",
    )
    op.drop_index(
        "ix_mission_execution_outbox_run_id",
        table_name="mission_execution_outbox",
    )
    op.drop_index(
        "ix_mission_execution_outbox_mission_id",
        table_name="mission_execution_outbox",
    )
    op.drop_table("mission_execution_outbox")
