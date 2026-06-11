"""Phase 10.4: Retarget auxiliary tables to blueprints + runs.

Adds new FK columns to mission_improvements, mission_triggers, and
mission_circuit_breakers pointing to the new blueprints and runs tables.

These columns are populated during dual-write (Phase 5) and the old
FK columns are dropped in the Phase 10.3 cleanup migration.

Revision ID: phase104_retarget_aux_tables
Revises: phase103_drop_old_tables
Create Date: 2026-06-09
"""

import os

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "phase104_retarget_aux_tables"
down_revision = "phase103_drop_old_tables"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    """Check if a table exists in the public schema."""
    bind = op.get_bind()
    return bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=:tname)"
        ),
        {"tname": table_name},
    ).scalar()


def _column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists on a table."""
    bind = op.get_bind()
    return bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=:tname AND column_name=:cname)"
        ),
        {"tname": table_name, "cname": column_name},
    ).scalar()


def _index_exists(index_name: str) -> bool:
    """Check if an index exists in the public schema."""
    bind = op.get_bind()
    return bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname='public' AND indexname=:iname)"),
        {"iname": index_name},
    ).scalar()


def _constraint_exists(constraint_name: str, table_name: str) -> bool:
    """Check if a constraint exists on a table."""
    bind = op.get_bind()
    return bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.table_constraints "
            "WHERE table_schema='public' AND constraint_name=:cname AND table_name=:tname)"
        ),
        {"cname": constraint_name, "tname": table_name},
    ).scalar()


def upgrade() -> None:
    # ── SAFETY GUARD ────────────────────────────────────────────────
    # ⛔ HOLD: Remove this guard only after 2-week soak is verified.
    if os.environ.get("PHASE10_SOAK_COMPLETE") != "1":
        raise RuntimeError(
            "Phase 10.4 is on HOLD — 2-week soak period not yet complete. "
            "Set PHASE10_SOAK_COMPLETE=1 to override. "
            "Target apply date: 2026-06-23."
        )

    # ── mission_improvements: add run_id FK ──────────────────────────
    # Table may have been dropped in phase 10.3 — skip if absent.
    if _table_exists("mission_improvements"):
        if not _column_exists("mission_improvements", "run_id"):
            op.add_column(
                "mission_improvements",
                sa.Column(
                    "run_id",
                    postgresql.UUID(as_uuid=True),
                    nullable=True,
                ),
            )
        if not _index_exists("ix_mission_improvements_run_id"):
            op.create_index("ix_mission_improvements_run_id", "mission_improvements", ["run_id"])
        if not _constraint_exists("fk_mission_improvements_run_id", "mission_improvements"):
            op.create_foreign_key(
                "fk_mission_improvements_run_id",
                "mission_improvements",
                "runs",
                ["run_id"],
                ["id"],
            )

    # ── mission_triggers: add blueprint_id FK ────────────────────────
    if _table_exists("mission_triggers"):
        if not _column_exists("mission_triggers", "blueprint_id"):
            op.add_column(
                "mission_triggers",
                sa.Column(
                    "blueprint_id",
                    postgresql.UUID(as_uuid=True),
                    nullable=True,
                ),
            )
        if not _index_exists("ix_mission_triggers_blueprint_id"):
            op.create_index("ix_mission_triggers_blueprint_id", "mission_triggers", ["blueprint_id"])
        if not _constraint_exists("fk_mission_triggers_blueprint_id", "mission_triggers"):
            op.create_foreign_key(
                "fk_mission_triggers_blueprint_id",
                "mission_triggers",
                "blueprints",
                ["blueprint_id"],
                ["id"],
            )

    # ── mission_circuit_breakers: add run_id FK ──────────────────────
    if _table_exists("mission_circuit_breakers"):
        if not _column_exists("mission_circuit_breakers", "run_id"):
            op.add_column(
                "mission_circuit_breakers",
                sa.Column(
                    "run_id",
                    postgresql.UUID(as_uuid=True),
                    nullable=True,
                ),
            )
        if not _index_exists("ix_mission_circuit_breakers_run_id"):
            op.create_index(
                "ix_mission_circuit_breakers_run_id",
                "mission_circuit_breakers",
                ["run_id"],
            )
        if not _constraint_exists("fk_mission_circuit_breakers_run_id", "mission_circuit_breakers"):
            op.create_foreign_key(
                "fk_mission_circuit_breakers_run_id",
                "mission_circuit_breakers",
                "runs",
                ["run_id"],
                ["id"],
            )


def downgrade() -> None:
    op.drop_constraint(
        "fk_mission_circuit_breakers_run_id",
        "mission_circuit_breakers",
        type_="foreignkey",
    )
    op.drop_index("ix_mission_circuit_breakers_run_id", table_name="mission_circuit_breakers")
    op.drop_column("mission_circuit_breakers", "run_id")

    op.drop_constraint("fk_mission_triggers_blueprint_id", "mission_triggers", type_="foreignkey")
    op.drop_index("ix_mission_triggers_blueprint_id", table_name="mission_triggers")
    op.drop_column("mission_triggers", "blueprint_id")

    op.drop_constraint("fk_mission_improvements_run_id", "mission_improvements", type_="foreignkey")
    op.drop_index("ix_mission_improvements_run_id", table_name="mission_improvements")
    op.drop_column("mission_improvements", "run_id")
