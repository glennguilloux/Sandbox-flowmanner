"""Add integration_config and approval_required columns.

Revision ID: next_level_growth_wave1
Revises: f637dac6c054
Create Date: 2026-06-03 12:00:00.000000

Add:
- missions.integration_config (JSONB, nullable) — for HTTP outbound integration config
- mission_tasks.approval_required (Boolean, default False) — for human approval gating
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "next_level_growth_wave1"
down_revision: Union[str, Sequence[str], None] = "f637dac6c054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "missions",
        sa.Column(
            "integration_config",
            postgresql.JSONB(),
            nullable=True,
        ),
    )
    op.add_column(
        "mission_tasks",
        sa.Column(
            "approval_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("mission_tasks", "approval_required")
    op.drop_column("missions", "integration_config")
