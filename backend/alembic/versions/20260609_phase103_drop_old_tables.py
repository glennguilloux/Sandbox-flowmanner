"""Phase 10.3: Drop old execution tables (point of no return).

⚠️  THIS MIGRATION HAS NO DOWNGRADE — rollback requires DB backup restore.

Pre-conditions:
1. All reads switched to new tables (via compat views)
2. Compat views verified working
3. Full database backup taken immediately before running
4. 2-week soak period with no issues

Drops in dependency order: children first, then parents.

Revision ID: phase103_drop_old_tables
Revises: phase102_compat_views
Create Date: 2026-06-09
"""

import os

from alembic import context, op

revision = "phase103_drop_old_tables"
down_revision = "phase102_compat_views"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if os.environ.get("PHASE10_SOAK_COMPLETE") != "1" and not context.is_offline_mode():
        raise RuntimeError(
            "Phase 10.3 is on HOLD — 2-week soak period not yet complete. "
            "Set PHASE10_SOAK_COMPLETE=1 to override. "
            "Target apply date: 2026-06-23."
        )

    # Drop compat views first
    op.execute("DROP VIEW IF EXISTS workflow_executions_compat")
    op.execute("DROP VIEW IF EXISTS workflows_compat")
    op.execute("DROP VIEW IF EXISTS missions_compat")

    # Drop external FK constraints from active tables that reference tables
    # being retired. These active tables keep their data — only the FK is
    # removed so the old parent tables can be dropped.
    op.execute("ALTER TABLE feedback_reports DROP CONSTRAINT IF EXISTS feedback_reports_mission_id_fkey")
    op.execute("ALTER TABLE http_integration_logs DROP CONSTRAINT IF EXISTS http_integration_logs_mission_id_fkey")
    op.execute("ALTER TABLE human_interrupts DROP CONSTRAINT IF EXISTS human_interrupts_mission_id_fkey")
    op.execute("ALTER TABLE inbox_items DROP CONSTRAINT IF EXISTS inbox_items_mission_id_fkey")
    op.execute(
        "ALTER TABLE mission_circuit_breakers DROP CONSTRAINT IF EXISTS mission_circuit_breakers_mission_id_fkey"
    )
    op.execute("ALTER TABLE mission_runs DROP CONSTRAINT IF EXISTS mission_runs_mission_id_fkey")
    op.execute("ALTER TABLE mission_triggers DROP CONSTRAINT IF EXISTS mission_triggers_mission_id_fkey")

    # Drop in dependency order (children first)
    op.drop_table("mission_logs")
    op.drop_table("mission_tasks")
    op.drop_table("execution_events")
    op.drop_table("workflow_states")
    op.drop_table("workflow_executions")
    op.drop_table("workflow_versions")
    op.drop_table("orchestrator_tasks")
    op.drop_table("orchestrator_executions")
    # Drop swarm child tables that have FKs to swarm_pipelines
    op.drop_table("swarm_consensus_rounds")
    op.drop_table("swarm_tasks")
    op.drop_table("swarm_agents")
    op.drop_table("swarm_pipelines")
    op.drop_table("mission_versions")
    op.drop_table("mission_templates")
    op.drop_table("mission_improvements")

    # Parent tables last
    op.drop_table("missions")
    op.drop_table("workflows")


def downgrade() -> None:
    # ⚠️ NO DOWNGRADE — restore from backup if rollback needed
    raise NotImplementedError(
        "Phase 10.3 drop migration has no downgrade. Restore from the database backup taken before this migration."
    )
