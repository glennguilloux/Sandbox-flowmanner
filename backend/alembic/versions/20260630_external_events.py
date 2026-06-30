"""Create external_events table — durable event bus for inbound integration events.

Creates:
- ``external_events`` table (append-only, idempotent via delivery_id)
- PostgreSQL trigger that prevents UPDATE/DELETE (append-only enforcement)
- Indexes for efficient querying by source, event_type, status, user_id, received_at

The trigger exempts the ``status`` and ``processed_at`` columns so the EventBus
can update processing state without violating the append-only constraint.
"""

revision = "20260630_external_events"
down_revision = "20260629_prog_next_fire"
branch_labels = None
depends_on = None

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


def upgrade() -> None:
    # ── external_events table ──────────────────────────────────────
    op.create_table(
        "external_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("delivery_id", sa.String(255), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("raw_body", postgresql.JSONB(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "triggers_fired",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ── Indexes ─────────────────────────────────────────────────────
    # Unique index on (source, delivery_id) for idempotency.
    op.create_index(
        "ix_external_events_delivery_id",
        "external_events",
        ["source", "delivery_id"],
        unique=True,
    )
    op.create_index(
        "ix_external_events_status",
        "external_events",
        ["status"],
    )
    op.create_index(
        "ix_external_events_source_type",
        "external_events",
        ["source", "event_type"],
    )
    op.create_index(
        "ix_external_events_received_at",
        "external_events",
        ["received_at"],
    )
    op.create_index(
        "ix_external_events_user_id",
        "external_events",
        ["user_id"],
    )

    # ── Append-only trigger (DB-level enforcement) ──────────────────
    # Allows UPDATE only on status-tracking columns (status, processed_at,
    # error_message, triggers_fired, updated_at).  All other columns are
    # immutable after insert.  DELETE is always forbidden.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_external_events_append_only()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'external_events is append-only: DELETE is forbidden';
            END IF;

            IF TG_OP = 'UPDATE' THEN
                -- Allow updates to processing-status columns only
                IF NEW.source IS DISTINCT FROM OLD.source
                   OR NEW.event_type IS DISTINCT FROM OLD.event_type
                   OR NEW.delivery_id IS DISTINCT FROM OLD.delivery_id
                   OR NEW.payload IS DISTINCT FROM OLD.payload
                   OR NEW.raw_body IS DISTINCT FROM OLD.raw_body
                   OR NEW.user_id IS DISTINCT FROM OLD.user_id
                   OR NEW.received_at IS DISTINCT FROM OLD.received_at
                THEN
                    RAISE EXCEPTION 'external_events is append-only: only status columns may be updated';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """
    )

    op.execute(
        """
        CREATE TRIGGER trg_external_events_append_only
        BEFORE UPDATE OR DELETE ON external_events
        FOR EACH ROW
        EXECUTE FUNCTION enforce_external_events_append_only();
    """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_external_events_append_only ON external_events")
    op.execute("DROP FUNCTION IF EXISTS enforce_external_events_append_only()")
    op.drop_index("ix_external_events_user_id", table_name="external_events")
    op.drop_index("ix_external_events_received_at", table_name="external_events")
    op.drop_index("ix_external_events_source_type", table_name="external_events")
    op.drop_index("ix_external_events_status", table_name="external_events")
    op.drop_index("ix_external_events_delivery_id", table_name="external_events")
    op.drop_table("external_events")
