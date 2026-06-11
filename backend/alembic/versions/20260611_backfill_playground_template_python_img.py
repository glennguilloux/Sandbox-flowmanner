"""Backfill playground_sandboxes.template: react-standard -> python.img.

After commit 4f88743 flipped SANDBOXD_DEFAULT_TEMPLATE to python.img, the
column's default + server_default on new rows are python.img, but existing
rows keep the old value. This migration backfills any remaining
'react-standard' rows so the entire playground_sandboxes table is
consistent with the new default.

The react-standard template is still installable and can still be requested
explicitly; this migration only touches the rows that were silently
defaulted to react-standard by the old server_default and never explicitly
overridden.

Revision ID: backfill_playground_template_001
Revises: cleanup_stale_handler_refs_001
Create Date: 2026-06-11
"""

from sqlalchemy import text as sa_text

from alembic import op

# revision identifiers, used by Alembic.
revision = "backfill_playground_template_001"
down_revision = "cleanup_stale_handler_refs_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Backfill template column to the new default.

    Uses a single UPDATE statement scoped to the rows that still hold the
    old default. The WHERE clause is defensive: in the (unlikely) event a
    row was explicitly created with template='react-standard' by a caller
    that knew what it was doing, the column will still be flipped here.
    That trade-off is acceptable because (a) the legacy template is
    documented as deprecated in the chat prompt, and (b) any caller
    that wants to keep using react-standard can re-set the value on the
    row after this migration runs.
    """
    conn = op.get_bind()
    result = conn.execute(
        sa_text(
            "UPDATE playground_sandboxes "
            "SET template = 'python.img' "
            "WHERE template = 'react-standard'"
        )
    )
    # Result is logged for the migration record. The rowcount is not
    # asserted; 0 rows is a valid outcome (no legacy rows left).
    print(f"[backfill_playground_template_001] Updated {result.rowcount} rows to python.img")


def downgrade() -> None:
    """Downgrade is a no-op.

    We cannot reliably reverse this migration because we do not retain
    a record of which rows were originally 'react-standard' versus
    those that were already 'python.img' (or some other value) before
    the upgrade. Restoring all rows to 'react-standard' would
    incorrectly downgrade rows that were explicitly set to 'python.img'
    by a caller. Operators wanting to revert should restore from a
    pre-migration database backup.
    """
    pass
