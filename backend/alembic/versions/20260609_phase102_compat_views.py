"""Phase 10.2: Create compatibility views for zero-downtime cut-over.

⛔ HOLD — DO NOT APPLY until 2-week soak of Phase 10.1 is complete.
   Apply date target: 2026-06-23 (or later).
   See: Docs/BLUEPRINT-RUN-IMPLEMENTATION-PLAN.md for soak checklist.

Creates PostgreSQL views that map old table names to new tables,
allowing old API endpoints to read from the new unified tables.

CRITICAL: Uses LEFT JOIN LATERAL (not plain LEFT JOIN) to avoid
duplicate rows when a blueprint has multiple runs.

Revision ID: phase102_compat_views
Revises: phase101_blueprints_runs
Create Date: 2026-06-09
"""

import os

from alembic import op

revision = "phase102_compat_views"
down_revision = "phase101_blueprints_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── SAFETY GUARD ────────────────────────────────────────────────
    # ⛔ HOLD: Remove this guard only after 2-week soak is verified.
    if os.environ.get("PHASE10_SOAK_COMPLETE") != "1":
        raise RuntimeError(
            "Phase 10.2 is on HOLD — 2-week soak period not yet complete. "
            "Set PHASE10_SOAK_COMPLETE=1 to override. "
            "Target apply date: 2026-06-23."
        )

    # ── missions_compat view ─────────────────────────────────────────
    # Maps old mission columns to blueprints + latest run
    op.execute(
        """
        CREATE OR REPLACE VIEW missions_compat AS
        SELECT
            b.id,
            b.user_id,
            b.title,
            b.description,
            b.blueprint_type AS mission_type,
            b.status,
            b.version,
            b.workspace_id,
            b.deleted_at,
            b.deleted_by,
            latest_run.total_tokens AS tokens_used,
            latest_run.total_cost_usd AS actual_cost,
            latest_run.error_message,
            latest_run.started_at,
            latest_run.completed_at,
            b.created_at,
            b.updated_at
        FROM blueprints b
        LEFT JOIN LATERAL (
            SELECT r.total_tokens, r.total_cost_usd, r.error_message,
                   r.started_at, r.completed_at
            FROM runs r
            WHERE r.blueprint_id = b.id
            ORDER BY r.created_at DESC
            LIMIT 1
        ) latest_run ON true
    """
    )

    # ── workflows_compat view ────────────────────────────────────────
    # Maps old workflow columns to blueprints
    op.execute(
        """
        CREATE OR REPLACE VIEW workflows_compat AS
        SELECT
            b.id,
            b.title AS name,
            b.description,
            b.definition AS graph_definition,
            b.status,
            b.user_id,
            b.workspace_id,
            b.created_at,
            b.updated_at
        FROM blueprints b
        WHERE b.blueprint_type IN ('graph', 'dag')
    """
    )

    # ── workflow_executions_compat view ──────────────────────────────
    # Maps old execution columns to runs
    op.execute(
        """
        CREATE OR REPLACE VIEW workflow_executions_compat AS
        SELECT
            r.id,
            r.blueprint_id AS workflow_id,
            r.user_id,
            r.status,
            r.input_data,
            r.output_data,
            r.error_message,
            r.started_at,
            r.created_at,
            r.completed_at,
            r.workspace_id
        FROM runs r
    """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS workflow_executions_compat")
    op.execute("DROP VIEW IF EXISTS workflows_compat")
    op.execute("DROP VIEW IF EXISTS missions_compat")
