"""H2.1 — Event-sourced substrate: events table + append-only trigger.

Creates:
- substrate_events table (append-only event log)
- BEFORE UPDATE OR DELETE trigger that raises on any modification
- Indexes for efficient querying by run_id, sequence, type, timestamp
"""

revision = "h2_substrate_init"
down_revision = "h13_observability"
branch_labels = None
depends_on = None

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    # ── substrate_events table ─────────────────────────────────────
    op.create_table(
        "substrate_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "sequence",
            sa.BigInteger(),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "mission_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "task_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "type",
            sa.String(64),
            nullable=False,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=True,
        ),
        sa.Column(
            "causal_parent",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.Column(
            "actor",
            sa.String(64),
            nullable=False,
            server_default="system",
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ── Indexes ─────────────────────────────────────────────────────
    op.create_index(
        "ix_substrate_events_run_id_seq",
        "substrate_events",
        ["run_id", "sequence"],
        unique=False,
    )
    op.create_index(
        "ix_substrate_events_mission_id",
        "substrate_events",
        ["mission_id"],
        unique=False,
    )
    op.create_index(
        "ix_substrate_events_type",
        "substrate_events",
        ["type"],
        unique=False,
    )
    op.create_index(
        "ix_substrate_events_timestamp",
        "substrate_events",
        ["timestamp"],
        unique=False,
    )

    # ── Append-only trigger (DB-level enforcement) ──────────────────
    # This trigger raises an exception on any UPDATE or DELETE to the
    # substrate_events table, guaranteeing append-only semantics at the
    # database level — not just application level.
    op.execute("""
        CREATE OR REPLACE FUNCTION enforce_substrate_events_append_only()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'substrate_events is append-only: UPDATE and DELETE are forbidden';
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_substrate_events_append_only
        BEFORE UPDATE OR DELETE ON substrate_events
        FOR EACH STATEMENT
        EXECUTE FUNCTION enforce_substrate_events_append_only();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_substrate_events_append_only ON substrate_events")
    op.execute("DROP FUNCTION IF EXISTS enforce_substrate_events_append_only()")
    op.drop_index("ix_substrate_events_timestamp", table_name="substrate_events")
    op.drop_index("ix_substrate_events_type", table_name="substrate_events")
    op.drop_index("ix_substrate_events_mission_id", table_name="substrate_events")
    op.drop_index("ix_substrate_events_run_id_seq", table_name="substrate_events")
    op.drop_table("substrate_events")
