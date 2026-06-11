"""Add user_id FK constraints to 13 tables that were missing them.

- NULL orphaned user_id values (audit_logs has 7)
- Add FK constraints: SET NULL for nullable columns, RESTRICT for NOT NULL

Revision ID: fk_user_id_constraints_001
Revises: fk_type_alignment_001
Create Date: 2026-06-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "fk_user_id_constraints_001"
down_revision: str | Sequence[str] | None = "fk_type_alignment_001"
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
    # ── Clean up orphaned user_id values before adding FK constraints ──
    # audit_logs has 7 orphaned user_id values from deleted users
    op.execute(
        "UPDATE audit_logs SET user_id = NULL "
        "WHERE user_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id = audit_logs.user_id)"
    )

    # ── Add FK constraints ──
    # Nullable user_id columns → ON DELETE SET NULL
    nullable_tables = [
        "analytics_events",
        "audit_logs",
        "log_entries",
        "tool_analytics",
    ]

    # NOT NULL user_id columns → RESTRICT (prevent deleting users with records)
    not_null_tables = [
        "agent_reviews",
        "cost_records",
        "flows",
        "marketplace_reviews",
        "roadmap_comments",
        "roadmap_votes",
        "tool_permissions",
        "user_installations",
        "workflow_runs",
    ]

    for table in nullable_tables:
        if _fk_exists(table, "user_id", "users"):
            continue
        constraint_name = f"fk_{table}_user_id"
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD CONSTRAINT {constraint_name} "
            f"FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL"
        )

    for table in not_null_tables:
        if _fk_exists(table, "user_id", "users"):
            continue
        constraint_name = f"fk_{table}_user_id"
        op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {constraint_name} FOREIGN KEY (user_id) REFERENCES users(id)")

    # idempotency tables (nullable user_id, added after initial migration)
    idempotency_tables = ["idempotency_keys", "idempotency_request_logs"]
    for table in idempotency_tables:
        if _fk_exists(table, "user_id", "users"):
            continue
        constraint_name = f"fk_{table}_user_id"
        op.execute(
            f"ALTER TABLE {table} "
            f"ADD CONSTRAINT {constraint_name} "
            f"FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL"
        )


def downgrade() -> None:
    all_tables = [
        "analytics_events",
        "audit_logs",
        "log_entries",
        "tool_analytics",
        "agent_reviews",
        "cost_records",
        "flows",
        "marketplace_reviews",
        "roadmap_comments",
        "roadmap_votes",
        "tool_permissions",
        "user_installations",
        "workflow_runs",
        "idempotency_keys",
        "idempotency_request_logs",
    ]
    for table in all_tables:
        constraint_name = f"fk_{table}_user_id"
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint_name}")
