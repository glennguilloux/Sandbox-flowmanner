"""GOV-1.4 — add 'review' memory-correction event type (C3 audit fix)

Extends the ``memory_correction_events`` CHECK constraint
(``ck_memory_correction_event_event_type_valid``) to allow the ``"review"``
event type. A ``review`` event records a memory-write approval decision
(human approve/reject, or the audited HITL expiry auto-reject) taken on a
``PendingWrite`` drained through the memory inbox.

Why: GOV-1.4's C3 acceptance criterion requires the audit write path to
actually persist. Before this, memory-approval expiry emitted a substrate
``HUMAN_INTERRUPT_RESOLVED`` event ONLY when ``run_id`` was set, but memory
inbox items carry ``run_id=None`` — so their expiry wrote no memory-domain
audit row. The drain now records a ``review`` event in the durable
``memory_correction_events`` trail regardless of run_id, satisfying C3.

Pairs with the model tuple change in
``app/models/memory_correction_models.py`` (same commit per AGENTS.md ritual
rule 6: migration + model change must ship together).

Revision ID: 20260709_gov14_memory_review_audit_event
Revises: gov11_merge_blog_gov11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260709_gov14_memory_review_audit_event"
down_revision: str | Sequence[str] | None = "gov11_merge_blog_gov11"
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
)

CONSTRAINT_NAME = "ck_memory_correction_event_event_type_valid"


def upgrade() -> None:
    op.execute(f"ALTER TABLE memory_correction_events DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME}")
    op.execute(
        f"ALTER TABLE memory_correction_events ADD CONSTRAINT {CONSTRAINT_NAME} CHECK (event_type IN {ALL_EVENT_TYPES})"
    )


def downgrade() -> None:
    # Roll back to the pre-1.4 type set (drop "review").
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
    )
    op.execute(f"ALTER TABLE memory_correction_events DROP CONSTRAINT IF EXISTS {CONSTRAINT_NAME}")
    op.execute(f"ALTER TABLE memory_correction_events ADD CONSTRAINT {CONSTRAINT_NAME} CHECK (event_type IN {legacy})")
