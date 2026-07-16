# mypy: disable-error-code=attr-defined
"""Allow blueprint/substrate-run sandboxes via run_id (c2 FK fix).

Revision ID: 20260715_sandbox_run_context
Revises: 20260712_substrate_idem_unique
Create Date: 2026-07-15 17:00:00

mission_sandboxes.mission_id was NOT NULL with FK -> missions(id). Blueprint
runs (and substrate runs generally) create no missions row, so inserting the
sandbox mapping raised ForeignKeyViolation. This makes mission_id nullable and
adds an optional run_id (unique, indexed, no FK) so blueprint runs can key the
mapping on the run id instead. The legacy Mission path is untouched:
mission_id keeps its FK + unique, and is populated for mission-scoped sandboxes.

Existing rows all have a non-null mission_id, so making the column nullable is
a safe no-data-mutation ALTER.
"""

import sqlalchemy as sa

from alembic import op

revision = "20260715_sandbox_run_context"
down_revision = "20260712_substrate_idem_unique"
branch_labels = None
depends_on = None

_TABLE = "mission_sandboxes"
_MISSION_FK = "mission_sandboxes_mission_id_fkey"
_RUN_UQ = "uq_mission_sandboxes_run_id"
_RUN_IX = "ix_mission_sandboxes_run_id"


def upgrade() -> None:
    # 1. mission_id becomes optional (legacy Mission path keeps the FK + unique).
    op.alter_column(
        _TABLE,
        "mission_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
    # 2. run_id carries blueprint/substrate-run context (no FK: runs may be
    #    recreated, we only need it for lookup/reaping).
    op.add_column(_TABLE, sa.Column("run_id", sa.UUID(), nullable=True))
    op.create_unique_constraint(_RUN_UQ, _TABLE, ["run_id"])
    op.create_index(_RUN_IX, _TABLE, ["run_id"])


def downgrade() -> None:
    op.drop_index(_RUN_IX, table_name=_TABLE)
    op.drop_constraint(_RUN_UQ, _TABLE, type_="unique")
    op.drop_column(_TABLE, "run_id")
    op.alter_column(
        _TABLE,
        "mission_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
