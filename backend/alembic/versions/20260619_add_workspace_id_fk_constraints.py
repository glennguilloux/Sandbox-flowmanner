"""Add workspace_id FK constraints to 15 tables that were missing them.

Revision ID: fk_workspace_id_constraints_001
Revises: fk_user_id_constraints_001
Create Date: 2026-06-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "fk_workspace_id_constraints_001"
down_revision: str | Sequence[str] | None = "fk_user_id_constraints_001"
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


def upgrade() -> None:
    # Nullable workspace_id → ON DELETE SET NULL
    nullable_tables = [
        "capabilities_catalog",
        "chat_threads",
        "custom_roles",
        "extensions",
        "llm_call_records",
        "memory_entries",
        "mission_circuit_breakers",
        "role_delegations",
        "tools_catalog",
        "user_api_keys",
    ]

    # NOT NULL workspace_id → RESTRICT (prevent deleting workspaces with records)
    not_null_tables = [
        "cost_records",
        "installed_plugins",
        "spending_limits",
        "user_custom_roles",
        "user_tenants",
    ]

    for table in nullable_tables:
        if _fk_exists(table, "workspace_id", "workspaces"):
            continue
        constraint_name = f"fk_{table}_workspace_id"
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD CONSTRAINT {constraint_name} "
            f"FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE SET NULL"
        )

    for table in not_null_tables:
        if _fk_exists(table, "workspace_id", "workspaces"):
            continue
        constraint_name = f"fk_{table}_workspace_id"
        op.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {constraint_name} FOREIGN KEY (workspace_id) REFERENCES workspaces(id)"
        )


def downgrade() -> None:
    all_tables = [
        "capabilities_catalog",
        "chat_threads",
        "custom_roles",
        "extensions",
        "llm_call_records",
        "memory_entries",
        "mission_circuit_breakers",
        "role_delegations",
        "tools_catalog",
        "user_api_keys",
        "cost_records",
        "installed_plugins",
        "spending_limits",
        "user_custom_roles",
        "user_tenants",
    ]
    for table in all_tables:
        constraint_name = f"fk_{table}_workspace_id"
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint_name}")
