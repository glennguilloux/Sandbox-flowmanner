"""Fix orphaned search_vector trigger on chat_messages.

The reconcile_schema_001_additions migration dropped the ``search_vector`` column
(and its GIN index) but left behind the BEFORE INSERT/UPDATE trigger and its
trigger function, which still references ``NEW.search_vector``. Every subsequent
INSERT/UPDATE on ``chat_messages`` crashes with::

    asyncpg.exceptions.UndefinedColumnError: record "new" has no field "search_vector"

This migration drops the orphaned trigger and function. The original trigger
was created by ``phase3_20260601_0603_fulltext_search_and_sharing.py``; the
reconciliation migration that removed the column missed the corresponding
trigger + function cleanup.

Revision ID: fix_search_vector_trigger_001
Revises: integration_onboarding_flag_001_enable
Create Date: 2026-06-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "fix_search_vector_trigger_001"
down_revision: str | Sequence[str] | None = "integration_onboarding_flag_001_enable"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Drop the orphaned trigger and function.

    Drop order: trigger first, then function. Both depend on
    ``NEW.search_vector`` -- a column the reconciliation migration removed.
    ``IF EXISTS`` keeps the migration idempotent if Phase 6 has already
    cleaned these up via some other path.
    """
    op.execute("DROP TRIGGER IF EXISTS trg_chat_messages_search_vector ON chat_messages")
    op.execute("DROP FUNCTION IF EXISTS chat_messages_search_update()")


def downgrade() -> None:
    """Recreate the function and trigger.

    The column was intentionally removed by ``reconcile_schema_001_additions``;
    we do NOT recreate it. The recreated function guards on column existence
    so it is harmless if the column stays gone, but the recreated trigger will
    still fire BEFORE INSERT/UPDATE.

    NOTE: If the column is genuinely absent, the recreated trigger references
    ``NEW.search_vector`` and will break inserts again. This downgrade is
    intended for chain-integrity rollback only (e.g. dev environments). In
    production, do not downgrade past this point until either the column is
    re-added or the trigger is dropped again.
    """
    op.execute(
        """
        CREATE OR REPLACE FUNCTION chat_messages_search_update()
        RETURNS trigger AS $$
        BEGIN
            -- Only update if the column exists (it was dropped in
            -- reconcile_schema_001_additions and is intentionally not
            -- re-added in this migration).
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'chat_messages' AND column_name = 'search_vector'
            ) THEN
                NEW.search_vector := to_tsvector('english', COALESCE(NEW.content, ''));
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_chat_messages_search_vector
        BEFORE INSERT OR UPDATE ON chat_messages
        FOR EACH ROW EXECUTE FUNCTION chat_messages_search_update()
        """
    )
