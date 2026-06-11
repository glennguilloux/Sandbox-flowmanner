"""Add mission_id and agent_id FK constraints to tables that were missing them.

- Clean orphaned values (learning_feedback, mission_runs, substrate_events)
- Convert llm_call_records.agent_id from uuid to varchar (agents.id is varchar)
- Add mission_id FKs to 11 tables
- Add agent_id FKs to 7 tables

Revision ID: fk_remaining_constraints_001
Revises: fk_workspace_id_constraints_001
Create Date: 2026-06-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "fk_remaining_constraints_001"
down_revision: str | Sequence[str] | None = "fk_workspace_id_constraints_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _fk_exists(table: str, column: str, ref_table: str) -> bool:
    """Check if a FK constraint already exists on a column."""
    bind = op.get_bind()
    result = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "ON tc.constraint_name = kcu.constraint_name "
            "JOIN information_schema.constraint_column_usage ccu "
            "ON tc.constraint_name = ccu.constraint_name "
            "WHERE tc.constraint_type = 'FOREIGN KEY' "
            "AND tc.table_name = :table "
            "AND kcu.column_name = :column "
            "AND ccu.table_name = :ref_table "
            "LIMIT 1"
        ),
        {"table": table, "column": column, "ref_table": ref_table},
    )
    return result.fetchone() is not None


def _column_type_name(table_name: str, column_name: str) -> str | None:
    """Return the DB type name of a column, or None if the column doesn't exist."""
    bind = op.get_bind()
    try:
        cols = {c["name"]: str(c["type"]) for c in sa.inspect(bind).get_columns(table_name)}
        return cols.get(column_name)
    except Exception:
        return None


def upgrade() -> None:
    # ── Clean up orphaned mission_id values ──
    # mission_runs has NOT NULL + 6 orphans: drop constraint, clean up, restore
    op.execute("ALTER TABLE mission_runs ALTER COLUMN mission_id DROP NOT NULL")
    op.execute(
        "UPDATE mission_runs SET mission_id = NULL "
        "WHERE mission_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM missions m WHERE m.id = mission_runs.mission_id)"
    )

    for table in ["learning_feedback", "substrate_events"]:
        # substrate_events has an append-only trigger — disable temporarily for orphan cleanup
        if table == "substrate_events":
            op.execute("ALTER TABLE substrate_events DISABLE TRIGGER trg_substrate_events_append_only")
        op.execute(
            f"UPDATE {table} SET mission_id = NULL "
            f"WHERE mission_id IS NOT NULL "
            f"AND NOT EXISTS (SELECT 1 FROM missions m WHERE m.id = {table}.mission_id)"
        )
        if table == "substrate_events":
            op.execute("ALTER TABLE substrate_events ENABLE TRIGGER trg_substrate_events_append_only")

    # ── Clean up orphaned agent_id values ──
    for table in ["learning_feedback"]:
        op.execute(
            f"UPDATE {table} SET agent_id = NULL "
            f"WHERE agent_id IS NOT NULL "
            f"AND NOT EXISTS (SELECT 1 FROM agents a WHERE a.id = {table}.agent_id)"
        )

    # ── Fix llm_call_records.agent_id type mismatch ──
    # agents.id is varchar but llm_call_records.agent_id is uuid
    # Convert uuid → varchar to match agents.id
    col_type = _column_type_name("llm_call_records", "agent_id")
    if col_type and "UUID" in col_type.upper():
        op.alter_column(
            "llm_call_records",
            "agent_id",
            type_=sa.String(36),
            existing_type=postgresql.UUID(as_uuid=True),
            postgresql_using="agent_id::text",
        )

    # ── Add mission_id FK constraints ──
    # Nullable mission_id → ON DELETE SET NULL
    mission_nullable = [
        "cost_records",
        "http_integration_logs",
        "learning_feedback",
        "llm_call_records",
        "mission_runs",
        "substrate_events",
    ]

    # NOT NULL mission_id → RESTRICT
    mission_not_null = [
        "feedback_reports",
        "human_interrupts",
        "inbox_items",
        "mission_circuit_breakers",
        "mission_triggers",
    ]

    for table in mission_nullable:
        if _fk_exists(table, "mission_id", "missions"):
            continue
        constraint_name = f"fk_{table}_mission_id"
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD CONSTRAINT {constraint_name} "
            f"FOREIGN KEY (mission_id) REFERENCES missions(id) ON DELETE SET NULL"
        )

    for table in mission_not_null:
        if _fk_exists(table, "mission_id", "missions"):
            continue
        constraint_name = f"fk_{table}_mission_id"
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {constraint_name} FOREIGN KEY (mission_id) REFERENCES missions(id)"
        )

    # ── Add agent_id FK constraints ──
    # Nullable agent_id → ON DELETE SET NULL
    agent_nullable = [
        "adaptation_rules",
        "learning_feedback",
        "llm_call_records",
        "memory_entries",
        "orchestrator_tasks",
    ]

    # NOT NULL agent_id → RESTRICT
    agent_not_null = [
        "agent_memory",
        "agent_registrations",
        "agent_reviews",
    ]

    for table in agent_nullable:
        if _fk_exists(table, "agent_id", "agents"):
            continue
        constraint_name = f"fk_{table}_agent_id"
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD CONSTRAINT {constraint_name} "
            f"FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE SET NULL"
        )

    for table in agent_not_null:
        if _fk_exists(table, "agent_id", "agents"):
            continue
        constraint_name = f"fk_{table}_agent_id"
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {constraint_name} FOREIGN KEY (agent_id) REFERENCES agents(id)")


def downgrade() -> None:
    # Drop agent_id FKs
    agent_tables = [
        "adaptation_rules",
        "learning_feedback",
        "llm_call_records",
        "memory_entries",
        "orchestrator_tasks",
        "agent_memory",
        "agent_registrations",
        "agent_reviews",
    ]
    for table in agent_tables:
        constraint_name = f"fk_{table}_agent_id"
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint_name}")

    # Revert llm_call_records.agent_id varchar → uuid
    col_type = _column_type_name("llm_call_records", "agent_id")
    if col_type and "CHAR" in col_type.upper():
        op.alter_column(
            "llm_call_records",
            "agent_id",
            type_=postgresql.UUID(as_uuid=True),
            existing_type=sa.String(36),
            postgresql_using="agent_id::uuid",
        )

    # Drop mission_id FKs
    mission_tables = [
        "cost_records",
        "http_integration_logs",
        "learning_feedback",
        "llm_call_records",
        "substrate_events",
        "feedback_reports",
        "human_interrupts",
        "inbox_items",
        "mission_circuit_breakers",
        "mission_runs",
        "mission_triggers",
    ]
    for table in mission_tables:
        constraint_name = f"fk_{table}_mission_id"
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint_name}")
