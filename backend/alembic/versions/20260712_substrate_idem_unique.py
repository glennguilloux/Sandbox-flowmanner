# mypy: disable-error-code=attr-defined
"""Add unique constraint on substrate_events.idempotency_key (S2).

Revision ID: 20260712_substrate_idem_unique
Revises: 20260712_mission_paused_at
Create Date: 2026-07-12 12:30:00

Hardens EventLog dedup-on-write (Item #3): the soft read-then-write check in
event_log.append() can race between two concurrent Celery workers / a retried
task, both passing the SELECT and both INSERTing the same idempotency_key.
The unique constraint makes the dedup HARD at the database level.

idempotency_key is nullable, so Postgres permits multiple NULLs — only
non-null keys are unique-constrained, which is correct for an optional key.

Existing rows are clean (only NULL keys in practice), so no pre-dedupe is
required. The constraint is created WITHOUT NOT VALID-safe data mutation.
"""

from alembic import op

revision = "20260712_substrate_idem_unique"
down_revision = "20260712_mission_paused_at"
branch_labels = None
depends_on = None

_CONSTRAINT_NAME = "uq_substrate_events_idempotency_key"
_TABLE = "substrate_events"
_COLUMNS = ["idempotency_key"]


def upgrade() -> None:
    op.create_unique_constraint(_CONSTRAINT_NAME, _TABLE, _COLUMNS)


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT_NAME, _TABLE, type_="unique")
