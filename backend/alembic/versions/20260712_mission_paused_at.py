# mypy: disable-error-code=attr-defined
"""Add paused_at timestamp to missions for the pause-timeout auto-fail.

Revision ID: 20260712_mission_paused_at
Revises: 20260711_governance_poison_scan
Create Date: 2026-07-12 12:00:00

Adds two nullable columns to ``missions``:
  - ``paused_at``     — timestamp the mission was paused (for the 7-day window).
  - ``compensated_at``— set in its own durable session before compensation
                       runs, so a Celery retry cannot double-refund.

NULL ``paused_at`` means "paused before this column existed" and is treated
as infinity (exempt from auto-fail) — no backfill required.

Also adds a composite index (status, paused_at) to keep the periodic
sweep index-only and avoid a sequential scan over the missions table.

NOTE on multi-head: the alembic tree currently has many heads. This
migration intentionally chains off a single head
(20260711_governance_poison_scan). Because it only adds nullable columns
+ index (no cross-head dependency), ``alembic upgrade head`` will still
apply it. The pre-existing multi-head condition itself is a separate
tech-debt item and is OUT OF SCOPE for this change.
"""

from alembic import op
from alembic import context
import sqlalchemy as sa

revision = "20260712_mission_paused_at"
down_revision = "20260711_governance_poison_scan"
branch_labels = None
depends_on = None

_COLUMNS = ("paused_at", "compensated_at")


def _column_exists(name: str) -> bool:
    """True if ``missions.<name>`` already exists (live-DB only)."""
    if context.is_offline_mode():
        return False
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        return bool(
            conn.execute(
                sa.text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name='missions' AND column_name=:col"
                ).bindparams(col=name)
            ).scalar()
        )


def upgrade() -> None:
    if not _column_exists("paused_at"):
        op.add_column(
            "missions",
            sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        )
    if not _column_exists("compensated_at"):
        op.add_column(
            "missions",
            sa.Column("compensated_at", sa.DateTime(timezone=True), nullable=True),
        )
    # Composite index for the index-only pause-timeout sweep.
    op.create_index(
        "ix_missions_status_paused_at",
        "missions",
        ["status", "paused_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_missions_status_paused_at", table_name="missions")
    if _column_exists("compensated_at"):
        op.drop_column("missions", "compensated_at")
    if _column_exists("paused_at"):
        op.drop_column("missions", "paused_at")
