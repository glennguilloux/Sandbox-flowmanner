"""add mission_id to runs

Revision ID: 501e7de40d00
Revises: a1outbox00
Create Date: 2026-07-19 17:02:03.815311

Links a blueprint `Run` to the `Mission` it backs, so the Chat
MissionStatusTile can poll the mission a run was created from. The column is
nullable: legacy runs and any caller-supplied run that predates the link stay
valid, and the FK is SET NULL on mission deletion (a run outliving its mission
is harmless).

No backfill, no data mutation: every existing row is already nullable-compatible
(NULL), so no sentinel or UPDATE is required.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "501e7de40d00"
down_revision: Union[str, Sequence[str], None] = "a1outbox00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "mission_id",
                sa.UUID(),
                sa.ForeignKey("missions.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
        batch_op.create_index("ix_runs_mission_id", ["mission_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("runs", schema=None) as batch_op:
        batch_op.drop_index("ix_runs_mission_id")
        batch_op.drop_column("mission_id")
