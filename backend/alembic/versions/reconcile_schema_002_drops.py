"""Reconciliation migration — drop 28 legacy tables (Part 2 of 2).

Drops tables that exist in the DB but have no SQLAlchemy model classes.
Separated from Part 1 so schema additions can be deployed and verified
before destructive operations.

Tables dropped (23 empty + 5 with data approved for dropping):

Empty (0 rows):
  circuit_breaker_state, comments, cost_records, cursor_positions,
  digest_queue, file_shares, files, flows, human_interrupts, mentions,
  notification_log, orchestration_agents, orchestration_tasks,
  orchestration_teams, presence_states, projects, provider_fallbacks,
  spending_limits, substrate_worker_leases, swarm_executions,
  tool_routing_decisions, user_model_preferences, workflow_runs

With data (approved for dropping):
  agent_template_versions (245 rows), mission_runs (6), onboarding_state (6),
  changelog_entries (1)

NOT dropped:
  alembic_version — Alembic uses this to track revision state
  audit_logs (1765 rows) — model class in legacy_models.py
  refresh_tokens (801 rows) — model class in auth_service.py
"""

from alembic import op

# revision identifiers
revision = "reconcile_schema_002"
down_revision = "reconcile_schema_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Drop 28 legacy tables that have no corresponding model classes."""

    # All drops use IF EXISTS for idempotency.
    # CASCADE is needed because some tables may have residual FK references.
    legacy_tables = [
        # Empty tables (0 rows)
        "circuit_breaker_state",
        "comments",
        "cost_records",
        "cursor_positions",
        "digest_queue",
        "file_shares",
        "files",
        "flows",
        "human_interrupts",
        "mentions",
        "notification_log",
        "orchestration_agents",
        "orchestration_tasks",
        "orchestration_teams",
        "presence_states",
        "projects",
        "provider_fallbacks",
        "spending_limits",
        "substrate_worker_leases",
        "swarm_executions",
        "tool_routing_decisions",
        "user_model_preferences",
        "workflow_runs",
        # With data (approved for dropping)
        "agent_template_versions",
        "mission_runs",
        "onboarding_state",
        "changelog_entries",
        # NOTE: alembic_version is NOT dropped — Alembic uses it to track state
    ]

    for table in legacy_tables:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")


def downgrade() -> None:
    """Re-creating dropped tables is not supported.

    These tables were legacy and had no model classes.  If you need to
    reverse this migration, restore from a database backup taken before
    running the upgrade.
    """
    pass
