# mypy: disable-error-code=attr-defined
"""Drop the ForeignKey on mission_logs.mission_id (soft reference).

Revision ID: 20260712_mission_log_soft_ref
Revises: 20260711_governance_poison_scan
Create Date: 2026-07-12 12:00:00.000000

GC4 / FM-2: audit MUST survive a rolled-back handler transaction and
``MissionLog.mission_id`` MUST be a SOFT reference (no FK). With a hard
FK, a forensic audit row can be constrained by the mission row's isolation,
and (worse) an audit written in the handler's single session is rolled
back WITH the business mutation on ``PermanentMissionError`` — exactly
when the trace is needed. ``AuditService.record_async`` now writes in its
own ``fresh_session()``; the FK must not exist so the write never
depends on the mission row.

We keep the ``mission_id`` column (indexed) and only DROP the FK
constraint. Rows are preserved (no DELETE — see migration convention).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "20260712_mission_log_soft_ref"
down_revision = "20260711_governance_poison_scan"
branch_labels = None
depends_on = None

_TABLE = "mission_logs"
_COLUMN = "mission_id"
_REFERENCED = "missions"


def _fk_constraint_name() -> str | None:
    """Find the existing FK constraint name on mission_logs.mission_id.

    Returns None if no such FK exists (idempotent safety).
    """
    bind = op.get_bind()
    inspector = inspect(bind)
    for fk in inspector.get_foreign_keys(_TABLE):
        # Postgres: constrained_columns holds the local column(s).
        if _COLUMN in (fk.get("constrained_columns") or []):
            return fk.get("name")
    return None


def upgrade() -> None:
    fk_name = _fk_constraint_name()
    if fk_name is None:
        # Idempotent: already dropped (or never present).
        return
    with op.get_context().autocommit_block():
        op.drop_constraint(fk_name, _TABLE, type_="foreignkey")


def downgrade() -> None:
    # Re-add the FK (kept for rollback safety only; GC4 prefers it gone).
    with op.get_context().autocommit_block():
        op.create_foreign_key(
            "fk_mission_logs_mission_id",
            _TABLE,
            _REFERENCED,
            ["mission_id"],
            ["id"],
            ondelete="CASCADE",
        )
