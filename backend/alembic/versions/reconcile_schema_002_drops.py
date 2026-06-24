"""Reconciliation migration — drop 23 legacy tables (Part 2 of 2).

Drops tables that exist in the DB but have no SQLAlchemy model classes AND
are not queried via raw SQL from application code.
Separated from Part 1 so schema additions can be deployed and verified
before destructive operations.

Tables dropped (all 0 rows, no code references):

Empty (0 rows):
  circuit_breaker_state, comments, cost_records, cursor_positions,
  digest_queue, file_shares, files, flows, human_interrupts, mentions,
  notification_log, orchestration_agents, orchestration_tasks,
  orchestration_teams, presence_states, projects, provider_fallbacks,
  spending_limits, substrate_worker_leases, swarm_executions,
  tool_routing_decisions, user_model_preferences, workflow_runs

NOT dropped (queried via raw SQL — would cause runtime 500s):

  agent_template_versions (245 rows) — queried in data_export.py,
    workflow_version_models.py
  mission_runs (6 rows) — queried in learning_service.py
    (_get_model_from_runs raw SQL SELECT)
  onboarding_state (6 rows) — queried in onboarding.py
    (5 raw SQL ops: SELECT, INSERT, UPDATE)
  changelog_entries (1 row) — queried in changelog.py
    (6 raw SQL ops: SELECT, INSERT, UPDATE, DELETE)

NOT dropped (have model classes or are Alembic-managed):
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
    """Drop 23 legacy tables that have no corresponding model classes.

    These tables are all empty (0 rows) and have no raw SQL references in
    application code. The 4 tables that did have data or code references
    (agent_template_versions, mission_runs, onboarding_state, changelog_entries)
    have been excluded — see module docstring for details.
    """

    # All drops use IF EXISTS for idempotency.
    # CASCADE is needed because some tables may have residual FK references.
    #
    # NOTE: Tables with active raw SQL references have been removed from this
    # list. The migration author saw "no ORM model" and assumed "unused", but
    # the app queries them via text("SELECT ... FROM <table>"). Dropping them
    # would cause 500s on /api/v1/changelog, /api/v1/onboarding, learning
    # service, and data export. See docstring above for the full list.
    legacy_tables = [
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
