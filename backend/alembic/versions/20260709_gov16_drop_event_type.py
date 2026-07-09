"""GOV-1.6 — add 'drop' memory-correction event type (C5 durable drop signal)

Extends the ``memory_correction_events`` CHECK constraint
(``ck_memory_correction_event_event_type_valid``) to allow the ``"drop"``
event type. A ``drop`` event records that a candidate claim extracted from
a conversation was dropped by the defensive filter (sensitive/restricted/
private scope) before it reached durable memory.

Why: GOV-1.5 added the confidence gate + made the drop observable via logs
and a ``dropped`` metrics disposition, but dropped candidates were not
durable or Inspector-visible — the GOV-1.6 (C5) acceptance gap. GOV-1.6
closes the loop by persisting each defensive drop as a ``drop`` audit row
so the drop rate the calibration gate tunes against becomes a durable,
queryable signal in the same privacy trail as every other memory event.

The ``drop`` event carries ``claim_id=NULL`` (the candidate never became a
``PersonalMemoryClaim``); its ``claim_type`` / ``scope`` / ``confidence``
live in ``details`` so the Inspector can still surface the drop.

Pairs with the model tuple change in
``app/models/memory_correction_models.py`` (same commit per AGENTS.md ritual
rule 6: migration + model change must ship together). Chains directly on
top of the GOV-1.4 ``review`` event migration.

Revision ID: 20260709_gov16_drop_event_type
Revises: 20260709_gov14_memory_review_audit_event
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260709_gov16_drop_event_type"
down_revision: str | Sequence[str] | None = "20260709_gov14_memory_review_audit_event"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Must match app/models/memory_correction_models.py ALL_EVENT_TYPES.
ALL_EVENT_TYPES = (
    "view",
    "edit",
    "delete",
    "forget",
    "create",
    "inspect",
    "export",
    "pause",
    "resume",
    "review",
    "drop",
)

CONSTRAINT_NAME = "ck_memory_correction_event_event_type_valid"


def upgrade() -> None:
    op.execute(f"ALTER TABLE memory_correction_events DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME}")
    op.execute(
        f"ALTER TABLE memory_correction_events ADD CONSTRAINT {CONSTRAINT_NAME} CHECK (event_type IN {ALL_EVENT_TYPES})"
    )


def downgrade() -> None:
    # Roll back to the pre-1.6 type set (drop "drop").
    legacy = (
        "view",
        "edit",
        "delete",
        "forget",
        "create",
        "inspect",
        "export",
        "pause",
        "resume",
        "review",
    )
    op.execute(f"ALTER TABLE memory_correction_events DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME}")
    op.execute(f"ALTER TABLE memory_correction_events ADD CONSTRAINT {CONSTRAINT_NAME} CHECK (event_type IN {legacy})")
