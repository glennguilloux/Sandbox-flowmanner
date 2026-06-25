"""Fix playground_sandboxes.workspace_id type: UUID → VARCHAR(36).

The reconciliation migration (reconcile_schema_001_additions) inadvertently
changed workspace_id from VARCHAR(36) to UUID, creating a type mismatch with
the referenced workspaces.id PK (VARCHAR(36)).

Revision ID: fix_playground_ws_fk_type
Revises: reconcile_schema_001
Create Date: 2026-06-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import context, op

revision: str = "fix_playground_ws_fk_type"
down_revision: str | Sequence[str] | None = "reconcile_schema_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _column_type_name(table: str, column: str) -> str | None:
    """Return the DB type name of a column, or None if missing."""
    bind = op.get_bind()
    try:
        cols = {c["name"]: str(c["type"]) for c in sa.inspect(bind).get_columns(table)}
        return cols.get(column)
    except Exception:
        return None


def _fk_exists(table: str, column: str, ref_table: str) -> bool:
    """Check if a FK constraint already exists on a column."""
    if context.is_offline_mode():
        return False
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
    if context.is_offline_mode():
        return

    col_type = _column_type_name("playground_sandboxes", "workspace_id")
    if col_type is None:
        return  # table or column doesn't exist

    # Already VARCHAR/String — nothing to do
    if "CHAR" in col_type.upper() or "VARCHAR" in col_type.upper():
        return

    # Drop FK constraint before altering type (Postgres may reject the cast
    # while the constraint is active)
    has_fk = _fk_exists("playground_sandboxes", "workspace_id", "workspaces")
    if has_fk:
        op.drop_constraint(
            "playground_sandboxes_workspace_id_fkey",
            "playground_sandboxes",
            type_="foreignkey",
        )

    op.alter_column(
        "playground_sandboxes",
        "workspace_id",
        type_=sa.String(36),
        existing_type=postgresql.UUID(as_uuid=True),
        postgresql_using="workspace_id::text",
    )

    # Re-create the FK constraint
    if has_fk:
        op.create_foreign_key(
            "playground_sandboxes_workspace_id_fkey",
            "playground_sandboxes",
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    if context.is_offline_mode():
        return

    col_type = _column_type_name("playground_sandboxes", "workspace_id")
    if col_type is None:
        return

    # Already UUID — nothing to do
    if "UUID" in col_type.upper():
        return

    has_fk = _fk_exists("playground_sandboxes", "workspace_id", "workspaces")
    if has_fk:
        op.drop_constraint(
            "playground_sandboxes_workspace_id_fkey",
            "playground_sandboxes",
            type_="foreignkey",
        )

    op.alter_column(
        "playground_sandboxes",
        "workspace_id",
        type_=postgresql.UUID(as_uuid=True),
        existing_type=sa.String(36),
        postgresql_using="workspace_id::uuid",
    )

    if has_fk:
        op.create_foreign_key(
            "playground_sandboxes_workspace_id_fkey",
            "playground_sandboxes",
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="SET NULL",
        )
