"""FK type alignment: fix column types to match referenced PK types.

- Create cost_records table (missing migration)
- Alter varchar user_id → integer (13 tables)
- Alter varchar mission_id → uuid (cost_records, learning_feedback)

Revision ID: fk_type_alignment_001
Revises: phase4_playground
Create Date: 2026-06-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "fk_type_alignment_001"
down_revision: str | Sequence[str] | None = "phase4_playground"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    bind = op.get_bind()
    return sa.inspect(bind).has_table(table_name)


def _column_type_name(table_name: str, column_name: str) -> str | None:
    """Return the DB type name of a column, or None if the column doesn't exist."""
    bind = op.get_bind()
    try:
        cols = {c["name"]: str(c["type"]) for c in sa.inspect(bind).get_columns(table_name)}
        return cols.get(column_name)
    except Exception:
        return None


def _alter_varchar_to_integer(table: str, column: str) -> None:
    """Safely alter a varchar column to integer, handling non-numeric values and defaults."""
    col_type = _column_type_name(table, column)
    if col_type is None:
        return  # table or column doesn't exist
    if "INT" in col_type.upper() or "INTEGER" in col_type.upper():
        return  # already integer — skip (e.g. freshly created cost_records)

    bind = op.get_bind()
    nullable = True
    col_default = None
    for col in sa.inspect(bind).get_columns(table):
        if col["name"] == column:
            nullable = col.get("nullable", True)
            col_default = col.get("default")
            break

    # Drop NOT NULL temporarily if present so we can NULL out bad values
    if not nullable:
        op.alter_column(table, column, nullable=True)

    # Drop the default before altering (e.g. audit_logs has default=NULL::character varying)
    if col_default is not None:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT"
        )

    # NULL out non-numeric values
    op.execute(
        f"UPDATE {table} SET {column} = NULL "
        f"WHERE {column} IS NOT NULL AND {column} !~ '^[0-9]+$'"
    )

    op.alter_column(
        table,
        column,
        type_=sa.Integer(),
        existing_type=sa.String(),
        postgresql_using=f"{column}::integer",
    )

    # Restore NOT NULL if it was originally set (only if no NULLs remain)
    if not nullable:
        remaining = bind.execute(
            sa.text(f"SELECT COUNT(*) FROM {table} WHERE {column} IS NULL")
        ).scalar()
        if remaining == 0:
            op.alter_column(table, column, nullable=False)


def _alter_varchar_to_uuid(table: str, column: str) -> None:
    """Safely alter a varchar column to uuid."""
    col_type = _column_type_name(table, column)
    if col_type is None:
        return
    if "UUID" in col_type.upper():
        return  # already uuid — skip

    # NULL out invalid UUIDs first
    op.execute(
        f"UPDATE {table} SET {column} = NULL "
        f"WHERE {column} IS NOT NULL AND {column} !~ "
        f"'^[0-9a-f]{{8}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{4}}-[0-9a-f]{{12}}$'"
    )
    op.alter_column(
        table,
        column,
        type_=postgresql.UUID(as_uuid=True),
        existing_type=sa.String(),
        postgresql_using=f"{column}::uuid",
    )


def upgrade() -> None:
    # ── Issue #1: Create cost_records table (was missing from migrations) ──
    if not _table_exists("cost_records"):
        op.create_table(
            "cost_records",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "user_id",
                sa.Integer(),
                sa.ForeignKey("users.id"),
                nullable=False,
            ),
            sa.Column(
                "workspace_id",
                sa.String(36),
                sa.ForeignKey("workspaces.id"),
                nullable=False,
            ),
            sa.Column(
                "mission_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
            sa.Column("model_id", sa.String(150), nullable=False),
            sa.Column("provider", sa.String(50), nullable=False),
            sa.Column(
                "prompt_tokens", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "completion_tokens", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0.0"),
            sa.Column(
                "timestamp",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column("metadata", sa.Text(), nullable=True),
        )

    # ── Issue #3: Alter varchar user_id → integer ──
    user_id_tables = [
        "agent_reviews",
        "analytics_events",
        "audit_logs",
        "cost_records",
        "flows",
        "log_entries",
        "marketplace_reviews",
        "roadmap_comments",
        "roadmap_votes",
        "tool_analytics",
        "tool_permissions",
        "user_installations",
        "workflow_runs",
    ]
    for table in user_id_tables:
        _alter_varchar_to_integer(table, "user_id")

    # ── Issue #4: Alter varchar mission_id → uuid ──
    mission_id_tables = [
        "cost_records",
        "learning_feedback",
    ]
    for table in mission_id_tables:
        _alter_varchar_to_uuid(table, "mission_id")


def downgrade() -> None:
    # Revert uuid → varchar
    for table in ["learning_feedback", "cost_records"]:
        col_type = _column_type_name(table, "mission_id")
        if col_type and "UUID" in col_type.upper():
            op.alter_column(
                table,
                "mission_id",
                type_=sa.String(),
                existing_type=postgresql.UUID(as_uuid=True),
                postgresql_using="mission_id::text",
            )

    # Revert integer → varchar
    user_id_tables = [
        "workflow_runs",
        "user_installations",
        "tool_permissions",
        "tool_analytics",
        "roadmap_votes",
        "roadmap_comments",
        "marketplace_reviews",
        "log_entries",
        "flows",
        "cost_records",
        "audit_logs",
        "analytics_events",
        "agent_reviews",
    ]
    for table in user_id_tables:
        col_type = _column_type_name(table, "user_id")
        if col_type and ("INT" in col_type.upper() or "INTEGER" in col_type.upper()):
            op.alter_column(
                table,
                "user_id",
                type_=sa.String(),
                existing_type=sa.Integer(),
                postgresql_using="user_id::text",
            )

    # Drop cost_records if we created it
    if _table_exists("cost_records"):
        op.drop_table("cost_records")
