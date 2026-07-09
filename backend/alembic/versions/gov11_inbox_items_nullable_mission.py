"""GOV-1.1: make inbox_items.mission_id nullable for memory-write approvals.

Memory write approvals (HumanInterruptType.MEMORY_APPROVAL) are drained into
the HITL inbox as a SEPARATE filter from mission action approvals and must
never pause/abort a mission, so they are not bound to one.  This migration
relaxes the NOT NULL constraint on inbox_items.mission_id (the FK is retained;
ondelete behaviour unchanged).

Revision ID: gov11_inbox_items_nullable_mission
Revises: h5_human_interrupts
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "gov11_inbox_items_nullable_mission"
down_revision: str | None = "h5_human_interrupts"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Relax inbox_items.mission_id to nullable."""
    with op.batch_alter_table("inbox_items", schema=None) as batch_op:
        batch_op.alter_column(
            "mission_id",
            existing_type=postgresql.UUID(as_uuid=False),
            nullable=True,
        )


def downgrade() -> None:
    """Restore NOT NULL (only safe when no orphan memory-approval rows exist)."""
    with op.batch_alter_table("inbox_items", schema=None) as batch_op:
        batch_op.alter_column(
            "mission_id",
            existing_type=postgresql.UUID(as_uuid=False),
            nullable=False,
        )
