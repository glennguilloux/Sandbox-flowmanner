"""Reconciliation migration 001 — fix structural drift between models and live DB.

Generated automatically from live DB audit on 2026-06-24 (v2 — corrected).

Scope:
- Create 10 missing tables (correct dependency order)
- Add 32 missing columns (with server_default for NOT NULL)
- Fix 23 real type mismatches (all with explicit USING clauses)
- Create 70 missing indexes
- Drop 129 stale DB indexes
- Drop 45 stale DB FK constraints (actual names from pg_catalog)

Cosmetic mismatches (TIMESTAMP/DATETIME, DOUBLE PRECISION/FLOAT, BIGINT/INTEGER)
are NOT altered — they map to the same PostgreSQL type.

Tables preserved: audit_logs (1765 rows), refresh_tokens (801 rows)
Tables dropped: 27 legacy tables (in reconcile_schema_002)
"""

import sqlalchemy as sa

from alembic import op

# revision identifiers
revision = "reconcile_schema_001"
down_revision = "20260617_pending_writes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── STEP 1: Drop stale FK constraints (45) ──────────────────
    op.execute("ALTER TABLE adaptation_rules DROP CONSTRAINT IF EXISTS fk_adaptation_rules_agent_id")
    op.execute("ALTER TABLE agent_memory DROP CONSTRAINT IF EXISTS agent_memory_user_id_fkey")
    op.execute("ALTER TABLE agent_memory DROP CONSTRAINT IF EXISTS fk_agent_memory_agent_id")
    op.execute("ALTER TABLE agent_registrations DROP CONSTRAINT IF EXISTS fk_agent_registrations_agent_id")
    op.execute("ALTER TABLE agent_reviews DROP CONSTRAINT IF EXISTS fk_agent_reviews_agent_id")
    op.execute("ALTER TABLE agent_reviews DROP CONSTRAINT IF EXISTS fk_agent_reviews_user_id")
    op.execute("ALTER TABLE analytics_events DROP CONSTRAINT IF EXISTS fk_analytics_events_user_id")
    op.execute("ALTER TABLE capabilities_catalog DROP CONSTRAINT IF EXISTS fk_capabilities_catalog_workspace_id")
    op.execute("ALTER TABLE chat_folders DROP CONSTRAINT IF EXISTS chat_folders_parent_id_fkey")
    op.execute("ALTER TABLE chat_threads DROP CONSTRAINT IF EXISTS fk_chat_threads_workspace_id")
    op.execute("ALTER TABLE custom_roles DROP CONSTRAINT IF EXISTS fk_custom_roles_workspace_id")
    op.execute("ALTER TABLE extensions DROP CONSTRAINT IF EXISTS fk_extensions_workspace_id")
    op.execute("ALTER TABLE idempotency_keys DROP CONSTRAINT IF EXISTS fk_idempotency_keys_user_id")
    op.execute("ALTER TABLE idempotency_request_logs DROP CONSTRAINT IF EXISTS fk_idempotency_request_logs_user_id")
    op.execute("ALTER TABLE installed_plugins DROP CONSTRAINT IF EXISTS fk_installed_plugins_workspace_id")
    op.execute("ALTER TABLE learning_feedback DROP CONSTRAINT IF EXISTS fk_learning_feedback_agent_id")
    op.execute("ALTER TABLE learning_feedback DROP CONSTRAINT IF EXISTS fk_learning_feedback_mission_id")
    op.execute("ALTER TABLE llm_call_records DROP CONSTRAINT IF EXISTS fk_llm_call_records_agent_id")
    op.execute("ALTER TABLE llm_call_records DROP CONSTRAINT IF EXISTS fk_llm_call_records_mission_id")
    op.execute("ALTER TABLE llm_call_records DROP CONSTRAINT IF EXISTS fk_llm_call_records_workspace_id")
    op.execute("ALTER TABLE log_entries DROP CONSTRAINT IF EXISTS fk_log_entries_user_id")
    op.execute("ALTER TABLE marketplace_listings DROP CONSTRAINT IF EXISTS fk_ml_category")
    op.execute("ALTER TABLE marketplace_listings DROP CONSTRAINT IF EXISTS fk_ml_workspace")
    op.execute("ALTER TABLE marketplace_reviews DROP CONSTRAINT IF EXISTS fk_marketplace_reviews_user_id")
    op.execute("ALTER TABLE marketplace_reviews DROP CONSTRAINT IF EXISTS marketplace_reviews_listing_id_fkey")
    op.execute("ALTER TABLE memory_entries DROP CONSTRAINT IF EXISTS fk_memory_entries_agent_id")
    op.execute("ALTER TABLE memory_entries DROP CONSTRAINT IF EXISTS fk_memory_entries_workspace_id")
    op.execute("ALTER TABLE mission_circuit_breakers DROP CONSTRAINT IF EXISTS fk_mission_circuit_breakers_run_id")
    op.execute(
        "ALTER TABLE mission_circuit_breakers DROP CONSTRAINT IF EXISTS fk_mission_circuit_breakers_workspace_id"
    )
    op.execute("ALTER TABLE mission_triggers DROP CONSTRAINT IF EXISTS fk_mission_triggers_blueprint_id")
    op.execute("ALTER TABLE orchestrator_tasks DROP CONSTRAINT IF EXISTS fk_orchestrator_tasks_agent_id")
    op.execute("ALTER TABLE partners DROP CONSTRAINT IF EXISTS partners_owner_id_fkey")
    op.execute("ALTER TABLE roadmap_comments DROP CONSTRAINT IF EXISTS fk_roadmap_comments_user_id")
    op.execute("ALTER TABLE roadmap_votes DROP CONSTRAINT IF EXISTS fk_roadmap_votes_user_id")
    op.execute("ALTER TABLE role_delegations DROP CONSTRAINT IF EXISTS fk_role_delegations_workspace_id")
    op.execute("ALTER TABLE substrate_events DROP CONSTRAINT IF EXISTS fk_substrate_events_blueprint_id")
    op.execute("ALTER TABLE substrate_events DROP CONSTRAINT IF EXISTS fk_substrate_events_mission_id")
    op.execute("ALTER TABLE tool_analytics DROP CONSTRAINT IF EXISTS fk_tool_analytics_user_id")
    op.execute("ALTER TABLE tool_permissions DROP CONSTRAINT IF EXISTS fk_tool_permissions_user_id")
    op.execute("ALTER TABLE tools_catalog DROP CONSTRAINT IF EXISTS fk_tools_catalog_workspace_id")
    op.execute("ALTER TABLE user_api_keys DROP CONSTRAINT IF EXISTS fk_user_api_keys_workspace_id")
    op.execute("ALTER TABLE user_custom_roles DROP CONSTRAINT IF EXISTS fk_user_custom_roles_workspace_id")
    op.execute("ALTER TABLE user_installations DROP CONSTRAINT IF EXISTS fk_user_installations_user_id")
    op.execute("ALTER TABLE user_installations DROP CONSTRAINT IF EXISTS user_installations_listing_id_fkey")
    op.execute("ALTER TABLE user_tenants DROP CONSTRAINT IF EXISTS fk_user_tenants_workspace_id")

    # ── STEP 2: Drop stale indexes (129) ────────────────────────
    op.execute("DROP INDEX IF EXISTS adaptation_rules_rule_id_key")
    op.execute("DROP INDEX IF EXISTS ix_acb_agent_cap_unique")
    op.execute("DROP INDEX IF EXISTS ix_acb_agent_id")
    op.execute("DROP INDEX IF EXISTS ix_acb_capability_id")
    op.execute("DROP INDEX IF EXISTS agent_registrations_agent_id_key")
    op.execute("DROP INDEX IF EXISTS agent_templates_slug_key")
    op.execute("DROP INDEX IF EXISTS idx_agent_templates_is_active")
    op.execute("DROP INDEX IF EXISTS idx_agent_templates_model_config_division")
    op.execute("DROP INDEX IF EXISTS idx_agent_templates_model_config_slug")
    op.execute("DROP INDEX IF EXISTS ix_agent_templates_slug")
    op.execute("DROP INDEX IF EXISTS ix_atb_agent_id")
    op.execute("DROP INDEX IF EXISTS ix_atb_agent_tool_unique")
    op.execute("DROP INDEX IF EXISTS ix_atb_tool_id")
    op.execute("DROP INDEX IF EXISTS ix_agent_versions_agent_version")
    op.execute("DROP INDEX IF EXISTS ix_agents_owner_id")
    op.execute("DROP INDEX IF EXISTS idx_analytics_event_type")
    op.execute("DROP INDEX IF EXISTS idx_analytics_timestamp")
    op.execute("DROP INDEX IF EXISTS idx_analytics_user_type")
    op.execute("DROP INDEX IF EXISTS auth_api_keys_key_hash_key")
    op.execute("DROP INDEX IF EXISTS capabilities_catalog_slug_key")
    op.execute("DROP INDEX IF EXISTS ix_cd_cap_dep_unique")
    op.execute("DROP INDEX IF EXISTS ix_cd_capability_id")
    op.execute("DROP INDEX IF EXISTS ix_cd_depends_on_id")
    op.execute("DROP INDEX IF EXISTS ix_chat_files_chat_id")
    op.execute("DROP INDEX IF EXISTS ix_chat_messages_search_vector")
    op.execute("DROP INDEX IF EXISTS ix_custom_roles_tenant")
    op.execute("DROP INDEX IF EXISTS uq_custom_role_tenant_name")
    op.execute("DROP INDEX IF EXISTS ix_eval_runs_model_name")
    op.execute("DROP INDEX IF EXISTS ix_extensions_status")
    op.execute("DROP INDEX IF EXISTS ix_extensions_workspace_id")
    op.execute("DROP INDEX IF EXISTS ix_idempotency_keys_scoped")
    op.execute("DROP INDEX IF EXISTS ix_improvement_knowledge_edges_source_type")
    op.execute("DROP INDEX IF EXISTS ix_improvement_knowledge_edges_target_type")
    op.execute("DROP INDEX IF EXISTS ix_improvement_knowledge_nodes_type_key")
    op.execute("DROP INDEX IF EXISTS ix_inbox_mission")
    op.execute("DROP INDEX IF EXISTS ix_inbox_run")
    op.execute("DROP INDEX IF EXISTS ix_inbox_status")
    op.execute("DROP INDEX IF EXISTS ix_inbox_type")
    op.execute("DROP INDEX IF EXISTS ix_inbox_user")
    op.execute("DROP INDEX IF EXISTS ix_inbox_workspace")
    op.execute("DROP INDEX IF EXISTS ix_installed_plugins_workspace_name")
    op.execute("DROP INDEX IF EXISTS ix_llmcr_agent")
    op.execute("DROP INDEX IF EXISTS ix_llmcr_cost_category")
    op.execute("DROP INDEX IF EXISTS ix_llmcr_workspace")
    op.execute("DROP INDEX IF EXISTS idx_log_entries_level")
    op.execute("DROP INDEX IF EXISTS idx_log_entries_user_id")
    op.execute("DROP INDEX IF EXISTS marketplace_categories_name_key")
    op.execute("DROP INDEX IF EXISTS uq_mc_slug")
    op.execute("DROP INDEX IF EXISTS idx_marketplace_listings_category_id")
    op.execute("DROP INDEX IF EXISTS idx_marketplace_listings_owner_id")
    op.execute("DROP INDEX IF EXISTS ix_ml_artifact_id")
    op.execute("DROP INDEX IF EXISTS ix_ml_artifact_type")
    op.execute("DROP INDEX IF EXISTS ix_ml_status")
    op.execute("DROP INDEX IF EXISTS ix_ml_workspace")
    op.execute("DROP INDEX IF EXISTS idx_marketplace_reviews_listing_id")
    op.execute("DROP INDEX IF EXISTS idx_marketplace_reviews_user_id")
    op.execute("DROP INDEX IF EXISTS ix_memory_correction_events_user_id")
    op.execute("DROP INDEX IF EXISTS ix_memory_correction_events_workspace_id")
    op.execute("DROP INDEX IF EXISTS ix_mcb_mission")
    op.execute("DROP INDEX IF EXISTS ix_mcb_state")
    op.execute("DROP INDEX IF EXISTS ix_mcb_workspace")
    op.execute("DROP INDEX IF EXISTS ix_mission_circuit_breakers_run_id")
    op.execute("DROP INDEX IF EXISTS mission_sandboxes_mission_id_key")
    op.execute("DROP INDEX IF EXISTS mission_sandboxes_sandbox_id_key")
    op.execute("DROP INDEX IF EXISTS ix_mission_triggers_blueprint_id")
    op.execute("DROP INDEX IF EXISTS mission_triggers_webhook_path_key")
    op.execute("DROP INDEX IF EXISTS idx_node_groups_category")
    op.execute("DROP INDEX IF EXISTS idx_node_groups_user")
    op.execute("DROP INDEX IF EXISTS notification_settings_user_id_key")
    op.execute("DROP INDEX IF EXISTS idx_notifications_user_id")
    op.execute("DROP INDEX IF EXISTS idx_notifications_user_unread")
    op.execute("DROP INDEX IF EXISTS oidc_providers_name_key")
    op.execute("DROP INDEX IF EXISTS ix_onboarding_emails_user_type")
    op.execute("DROP INDEX IF EXISTS partners_slug_key")
    op.execute("DROP INDEX IF EXISTS ix_playground_status_expires")
    op.execute("DROP INDEX IF EXISTS playground_sandboxes_sandbox_id_key")
    op.execute("DROP INDEX IF EXISTS playground_sandboxes_session_token_key")
    op.execute("DROP INDEX IF EXISTS push_subscriptions_endpoint_key")
    op.execute("DROP INDEX IF EXISTS ix_roadmap_comments_roadmap_item_id")
    op.execute("DROP INDEX IF EXISTS ix_roadmap_items_status")
    op.execute("DROP INDEX IF EXISTS ix_roadmap_votes_item_user")
    op.execute("DROP INDEX IF EXISTS ix_delegations_delegatee")
    op.execute("DROP INDEX IF EXISTS ix_delegations_delegator")
    op.execute("DROP INDEX IF EXISTS ix_delegations_role")
    op.execute("DROP INDEX IF EXISTS ix_role_permissions_role")
    op.execute("DROP INDEX IF EXISTS uq_role_permission")
    op.execute("DROP INDEX IF EXISTS ix_runs_created_at")
    op.execute("DROP INDEX IF EXISTS ix_runs_user_id")
    op.execute("DROP INDEX IF EXISTS shared_links_token_key")
    op.execute("DROP INDEX IF EXISTS subscription_tiers_name_key")
    op.execute("DROP INDEX IF EXISTS ix_substrate_events_run_id_seq")
    op.execute("DROP INDEX IF EXISTS uq_team_member")
    op.execute("DROP INDEX IF EXISTS ix_tools_catalog_enabled")
    op.execute("DROP INDEX IF EXISTS tools_catalog_slug_key")
    op.execute("DROP INDEX IF EXISTS ix_usage_records_created_at")
    op.execute("DROP INDEX IF EXISTS idx_byok_user_provider")
    op.execute("DROP INDEX IF EXISTS idx_user_api_keys_provider")
    op.execute("DROP INDEX IF EXISTS idx_user_api_keys_user_id")
    op.execute("DROP INDEX IF EXISTS ix_user_api_keys_workspace")
    op.execute("DROP INDEX IF EXISTS ix_user_custom_roles_tenant")
    op.execute("DROP INDEX IF EXISTS ix_user_custom_roles_tenant_id")
    op.execute("DROP INDEX IF EXISTS uq_user_custom_role")
    op.execute("DROP INDEX IF EXISTS idx_user_installations_listing_id")
    op.execute("DROP INDEX IF EXISTS idx_user_installations_user_id")
    op.execute("DROP INDEX IF EXISTS ix_user_oidc_provider_id")
    op.execute("DROP INDEX IF EXISTS ix_user_oidc_user_id")
    op.execute("DROP INDEX IF EXISTS uq_oidc_provider_subject")
    op.execute("DROP INDEX IF EXISTS idx_user_subscriptions_user_id")
    op.execute("DROP INDEX IF EXISTS ix_user_tenants_tenant")
    op.execute("DROP INDEX IF EXISTS ix_user_tenants_user")
    op.execute("DROP INDEX IF EXISTS uq_user_tenant")
    op.execute("DROP INDEX IF EXISTS users_email_key")
    op.execute("DROP INDEX IF EXISTS users_username_key")
    op.execute("DROP INDEX IF EXISTS webhook_endpoints_name_key")
    op.execute("DROP INDEX IF EXISTS webhook_endpoints_path_key")
    op.execute("DROP INDEX IF EXISTS ix_webhook_logs_delivered_at")
    op.execute("DROP INDEX IF EXISTS ix_webhook_logs_next_retry_at")
    op.execute("DROP INDEX IF EXISTS ix_webhook_logs_status")
    op.execute("DROP INDEX IF EXISTS uq_workspace_hitl_config")
    op.execute("DROP INDEX IF EXISTS uq_workspace_member")
    op.execute("DROP INDEX IF EXISTS idx_workspace_messages_conv")
    op.execute("DROP INDEX IF EXISTS idx_workspace_messages_recipient_id")
    op.execute("DROP INDEX IF EXISTS idx_workspace_messages_sender_id")
    op.execute("DROP INDEX IF EXISTS idx_workspace_messages_workspace_id")
    op.execute("DROP INDEX IF EXISTS ix_ws_share_entity")
    op.execute("DROP INDEX IF EXISTS ix_ws_share_target")
    op.execute("DROP INDEX IF EXISTS uq_workspace_share")
    op.execute("DROP INDEX IF EXISTS ix_workspace_versions_ws_version")
    op.execute("DROP INDEX IF EXISTS ix_workspaces_subscription_tier")

    # ── STEP 2.5: Add columns needed by new tables BEFORE creation ──
    # swarm_agents, swarm_consensus_rounds, swarm_tasks all FK-reference
    # swarm_profiles.swarm_id, which doesn't exist yet.  Add it now.
    op.add_column("swarm_profiles", sa.Column("swarm_id", sa.String(64), server_default=""))
    op.add_column("swarm_profiles", sa.Column("swarm_name", sa.String(255), server_default=""))

    # ── STEP 3: Create missing tables (10) ──────────────────────
    # Order: workflows first (no deps on missing tables), then dependents.

    op.create_table(
        "workflows",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("graph_definition", sa.JSON()),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("user_id", sa.Integer()),
        sa.Column("workspace_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
    )
    op.create_index("ix_workflows_workspace_id", "workflows", ["workspace_id"])

    op.create_table(
        "workflow_executions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workflow_id", sa.String(36)),
        sa.Column("user_id", sa.Integer()),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("input_data", sa.JSON()),
        sa.Column("output_data", sa.JSON()),
        sa.Column("error_message", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("workspace_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
    )
    op.create_index("ix_workflow_executions_workspace_id", "workflow_executions", ["workspace_id"])

    op.create_table(
        "workflow_states",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("execution_id", sa.String(36)),
        sa.Column("workflow_id", sa.String(36)),
        sa.Column("state_data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["execution_id"], ["workflow_executions.id"]),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"]),
    )

    op.create_table(
        "workflow_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workflow_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"]),
    )
    op.create_index("ix_workflow_versions_workflow_id", "workflow_versions", ["workflow_id"])

    op.create_table(
        "execution_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("execution_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("node_id", sa.String(255)),
        sa.Column("message", sa.Text()),
        sa.Column("payload", sa.JSON()),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["execution_id"], ["workflow_executions.id"]),
    )
    op.create_index("ix_execution_events_execution_id", "execution_events", ["execution_id"])
    op.create_index("ix_execution_events_event_type", "execution_events", ["event_type"])

    op.create_table(
        "chat_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("system_prompt", sa.Text()),
        sa.Column("model", sa.String(100)),
        sa.Column("temperature", sa.Float()),
        sa.Column("max_tokens", sa.Integer()),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
    )
    op.create_index("ix_chat_templates_workspace_id", "chat_templates", ["workspace_id"])

    op.create_table(
        "mission_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mission_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255)),
        sa.Column("description", sa.Text()),
        sa.Column("mission_type", sa.String(50)),
        sa.Column("priority", sa.String(20)),
        sa.Column("plan", sa.JSON()),
        sa.Column("tasks_snapshot", sa.JSON()),
        sa.Column("constraints", sa.JSON()),
        sa.Column("change_summary", sa.Text()),
        sa.Column("created_by", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["mission_id"], ["missions.id"]),
    )
    op.create_index("ix_mission_versions_mission_id", "mission_versions", ["mission_id"])

    op.create_table(
        "swarm_agents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("agent_instance_id", sa.String(64), nullable=False),
        sa.Column("swarm_id", sa.String(64), nullable=False),
        sa.Column("agent_template_id", sa.String(36)),
        sa.Column("role", sa.String(50)),
        sa.Column("display_name", sa.String(255)),
        sa.Column("capabilities", sa.JSON()),
        sa.Column("specializations", sa.JSON()),
        sa.Column("config", sa.JSON()),
        sa.Column("assigned_model", sa.String(100)),
        sa.Column("model_config", sa.JSON()),
        sa.Column("status", sa.String(50)),
        sa.Column("load", sa.Integer()),
        sa.Column("max_concurrent_tasks", sa.Integer()),
        sa.Column("rating_avg", sa.Float()),
        sa.Column("rating_count", sa.Integer()),
        sa.Column("last_active_at", sa.DateTime(timezone=True)),
        sa.Column("joined_at", sa.DateTime(timezone=True)),
        sa.Column("cost_tracking", sa.JSON()),
        sa.Column("performance_metrics", sa.JSON()),
        sa.ForeignKeyConstraint(["swarm_id"], ["swarm_profiles.swarm_id"]),
        sa.ForeignKeyConstraint(["agent_template_id"], ["agent_templates.template_id"]),
    )

    op.create_table(
        "swarm_consensus_rounds",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("swarm_id", sa.String(64), nullable=False),
        sa.Column("proposal", sa.JSON(), nullable=False),
        sa.Column("initiator_agent_id", sa.String(64)),
        sa.Column("votes", sa.JSON()),
        sa.Column("result", sa.String(50)),
        sa.Column("strategy_used", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["swarm_id"], ["swarm_profiles.swarm_id"]),
    )

    op.create_table(
        "swarm_tasks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("swarm_id", sa.String(64), nullable=False),
        sa.Column("parent_task_id", sa.String(64)),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("priority", sa.Integer()),
        sa.Column("payload", sa.JSON()),
        sa.Column("assigned_agent_id", sa.String(64)),
        sa.Column("status", sa.String(50)),
        sa.Column("progress", sa.Integer()),
        sa.Column("result", sa.JSON()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("assigned_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("retry_count", sa.Integer()),
        sa.Column("max_retries", sa.Integer()),
        sa.Column("dependencies", sa.JSON()),
        sa.ForeignKeyConstraint(["assigned_agent_id"], ["swarm_agents.agent_instance_id"]),
        sa.ForeignKeyConstraint(["swarm_id"], ["swarm_profiles.swarm_id"]),
        sa.ForeignKeyConstraint(["parent_task_id"], ["swarm_tasks.id"]),
    )

    # ── STEP 4: Add missing columns (32) ───────────────────────
    op.add_column("agent_registrations", sa.Column("state", sa.String(30), server_default=""))
    op.add_column("agent_reviews", sa.Column("comment", sa.Text()))
    op.add_column("agent_reviews", sa.Column("is_approved", sa.Boolean(), server_default="false"))
    op.add_column("marketplace_categories", sa.Column("parent_id", sa.String(36)))
    op.add_column("partner_revenues", sa.Column("is_paid", sa.Boolean(), server_default="false"))
    op.add_column("partner_revenues", sa.Column("mission_id", sa.String(36), server_default=""))
    op.add_column("partner_revenues", sa.Column("mission_volume", sa.Integer(), server_default="0"))
    op.add_column("partner_revenues", sa.Column("paid_at", sa.DateTime(timezone=True)))
    op.add_column("partner_revenues", sa.Column("period_month", sa.String(7), server_default=""))
    op.add_column("partner_revenues", sa.Column("revenue_amount", sa.Float(), server_default="0"))
    op.add_column("partner_revenues", sa.Column("updated_at", sa.DateTime(timezone=True), server_default="now()"))
    op.add_column("partners", sa.Column("contact_email", sa.String(255), server_default=""))
    op.add_column("partners", sa.Column("revenue_share_percent", sa.Float(), server_default="0"))
    op.add_column("partners", sa.Column("stripe_account_id", sa.String(100)))
    op.add_column("pending_writes", sa.Column("updated_at", sa.DateTime(timezone=True), server_default="now()"))
    op.add_column("push_subscriptions", sa.Column("is_active", sa.Boolean(), server_default="false"))
    op.add_column("push_subscriptions", sa.Column("user_agent", sa.String(255)))
    op.add_column("swarm_profiles", sa.Column("consensus_config", sa.JSON()))
    op.add_column("swarm_profiles", sa.Column("consensus_strategy", sa.String(50)))
    op.add_column("swarm_profiles", sa.Column("created_by", sa.Integer()))
    op.add_column("swarm_profiles", sa.Column("daily_limit", sa.Float()))
    op.add_column("swarm_profiles", sa.Column("dissolved_at", sa.DateTime(timezone=True)))
    op.add_column("swarm_profiles", sa.Column("monthly_limit", sa.Float()))
    op.add_column("swarm_profiles", sa.Column("status", sa.String(50)))
    op.add_column("swarm_profiles", sa.Column("task_description", sa.Text()))
    op.add_column("swarm_profiles", sa.Column("task_type", sa.String(100)))
    op.add_column("swarm_profiles", sa.Column("updated_at", sa.DateTime(timezone=True)))
    op.add_column("user_installations", sa.Column("config", sa.Text()))
    op.add_column("user_installations", sa.Column("created_at", sa.DateTime(timezone=True), server_default="now()"))
    op.add_column("user_installations", sa.Column("updated_at", sa.DateTime(timezone=True), server_default="now()"))

    # ── STEP 5: Fix real type mismatches (23) ────────────────────
    op.execute("ALTER TABLE agent_reviews ALTER COLUMN user_id TYPE VARCHAR(36) USING user_id::VARCHAR(36)")
    op.execute("ALTER TABLE analytics_events ALTER COLUMN user_id TYPE VARCHAR(255) USING user_id::VARCHAR(255)")
    op.execute("ALTER TABLE inbox_items ALTER COLUMN mission_id TYPE VARCHAR(36) USING mission_id::VARCHAR(36)")
    op.execute("ALTER TABLE learning_feedback ALTER COLUMN mission_id TYPE VARCHAR(36) USING mission_id::VARCHAR(36)")
    op.execute("ALTER TABLE llm_call_records ALTER COLUMN agent_id TYPE UUID USING agent_id::UUID")
    op.execute("ALTER TABLE log_entries ALTER COLUMN user_id TYPE VARCHAR(36) USING user_id::VARCHAR(36)")
    op.execute("ALTER TABLE marketplace_reviews ALTER COLUMN user_id TYPE VARCHAR(36) USING user_id::VARCHAR(36)")
    op.execute("ALTER TABLE memory_entries ALTER COLUMN id TYPE UUID USING id::UUID")
    op.execute("ALTER TABLE memory_entries ALTER COLUMN session_id TYPE UUID USING session_id::UUID")
    op.execute("ALTER TABLE memory_entries ALTER COLUMN supersedes_id TYPE UUID USING supersedes_id::UUID")
    op.execute("ALTER TABLE memory_entries ALTER COLUMN workspace_id TYPE UUID USING workspace_id::UUID")
    op.execute(
        "ALTER TABLE notification_settings ALTER COLUMN push_enabled_channels TYPE VARCHAR(255) USING push_enabled_channels::VARCHAR(255)"
    )
    # notifications table is empty (0 rows) so INTEGER conversion is safe
    op.execute("ALTER TABLE notifications ALTER COLUMN id TYPE INTEGER USING id::INTEGER")
    op.execute(
        "ALTER TABLE oidc_provider_configs ALTER COLUMN client_secret_encrypted TYPE BYTEA USING client_secret_encrypted::BYTEA"
    )
    op.execute("ALTER TABLE pending_writes ALTER COLUMN id TYPE UUID USING id::UUID")
    op.execute("ALTER TABLE pending_writes ALTER COLUMN mission_id TYPE UUID USING mission_id::UUID")
    op.execute("ALTER TABLE playground_sandboxes ALTER COLUMN workspace_id TYPE UUID USING workspace_id::UUID")
    op.execute("ALTER TABLE push_subscriptions ALTER COLUMN endpoint TYPE TEXT USING endpoint::TEXT")
    op.execute("ALTER TABLE roadmap_comments ALTER COLUMN user_id TYPE VARCHAR(36) USING user_id::VARCHAR(36)")
    op.execute("ALTER TABLE roadmap_votes ALTER COLUMN user_id TYPE VARCHAR(36) USING user_id::VARCHAR(36)")
    op.execute("ALTER TABLE tool_analytics ALTER COLUMN user_id TYPE VARCHAR(36) USING user_id::VARCHAR(36)")
    op.execute("ALTER TABLE tool_permissions ALTER COLUMN user_id TYPE VARCHAR(36) USING user_id::VARCHAR(36)")
    op.execute("ALTER TABLE user_installations ALTER COLUMN user_id TYPE VARCHAR(36) USING user_id::VARCHAR(36)")

    # ── STEP 6: Create missing indexes (70) ─────────────────────
    op.create_index("ix_agent_capability_bindings_agent_id", "agent_capability_bindings", ["agent_id"])
    op.create_index("ix_agent_capability_bindings_capability_id", "agent_capability_bindings", ["capability_id"])
    op.create_index("ix_agent_reviews_user_id", "agent_reviews", ["user_id"])
    op.create_index("ix_agent_tool_bindings_tool_id", "agent_tool_bindings", ["tool_id"])
    op.create_index("ix_agent_tool_bindings_agent_id", "agent_tool_bindings", ["agent_id"])
    op.create_index("ix_capability_dependencies_capability_id", "capability_dependencies", ["capability_id"])
    op.create_index("ix_capability_dependencies_depends_on_id", "capability_dependencies", ["depends_on_id"])
    op.create_index("ix_composed_capabilities_name", "composed_capabilities", ["name"])
    op.create_index("ix_custom_roles_workspace_id", "custom_roles", ["workspace_id"])
    op.create_index("ix_episodes_mission_id", "episodes", ["mission_id"])
    op.create_index("ix_episodes_workspace_id", "episodes", ["workspace_id"])
    op.create_index("ix_episodes_user_id", "episodes", ["user_id"])
    op.create_index("ix_idempotency_keys_idempotency_key", "idempotency_keys", ["idempotency_key"])
    op.create_index("ix_inbox_items_user_id", "inbox_items", ["user_id"])
    op.create_index("ix_inbox_items_run_id", "inbox_items", ["run_id"])
    op.create_index("ix_inbox_items_interrupt_type", "inbox_items", ["interrupt_type"])
    op.create_index("ix_inbox_items_mission_id", "inbox_items", ["mission_id"])
    op.create_index("ix_inbox_items_workspace_id", "inbox_items", ["workspace_id"])
    op.create_index("ix_inbox_items_status", "inbox_items", ["status"])
    op.create_index("ix_llm_call_records_agent_id", "llm_call_records", ["agent_id"])
    op.create_index("ix_llm_call_records_workspace_id", "llm_call_records", ["workspace_id"])
    op.create_index("ix_llm_call_records_cost_category", "llm_call_records", ["cost_category"])
    op.create_index("ix_log_entries_level", "log_entries", ["level"])
    op.create_index("ix_log_entries_user_id", "log_entries", ["user_id"])
    op.create_index("ix_log_entries_session_id", "log_entries", ["session_id"])
    op.create_index("ix_marketplace_listings_name", "marketplace_listings", ["name"])
    op.create_index("ix_marketplace_listings_owner_id", "marketplace_listings", ["owner_id"])
    op.create_index("ix_marketplace_reviews_listing_id", "marketplace_reviews", ["listing_id"])
    op.create_index("ix_marketplace_reviews_user_id", "marketplace_reviews", ["user_id"])
    op.create_index("ix_mission_circuit_breakers_mission_id", "mission_circuit_breakers", ["mission_id"], unique=True)
    op.create_index("ix_mission_circuit_breakers_state", "mission_circuit_breakers", ["state"])
    op.create_index("ix_mission_circuit_breakers_workspace_id", "mission_circuit_breakers", ["workspace_id"])
    op.create_index("ix_mission_sandboxes_sandbox_id", "mission_sandboxes", ["sandbox_id"], unique=True)
    op.create_index("ix_mission_sandboxes_mission_id", "mission_sandboxes", ["mission_id"], unique=True)
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_partner_revenues_mission_id", "partner_revenues", ["mission_id"])
    op.create_index("ix_partner_revenues_period_month", "partner_revenues", ["period_month"])
    op.create_index("ix_partners_contact_email", "partners", ["contact_email"])
    op.create_index("ix_pending_writes_status", "pending_writes", ["status"])
    op.create_index("ix_role_delegations_workspace_id", "role_delegations", ["workspace_id"])
    op.create_index("ix_role_delegations_delegatee_id", "role_delegations", ["delegatee_id"])
    op.create_index("ix_role_delegations_role_id", "role_delegations", ["role_id"])
    op.create_index("ix_role_delegations_delegator_id", "role_delegations", ["delegator_id"])
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])
    op.create_index("ix_subscription_tiers_name", "subscription_tiers", ["name"], unique=True)
    op.create_index("ix_substrate_events_run_id", "substrate_events", ["run_id"])
    op.create_index("ix_substrate_events_sequence", "substrate_events", ["sequence"])
    op.create_index("ix_topology_edges_snapshot_id", "topology_edges", ["snapshot_id"])
    op.create_index("ix_topology_nodes_snapshot_id", "topology_nodes", ["snapshot_id"])
    op.create_index("ix_usage_records_model", "usage_records", ["model"])
    op.create_index("ix_usage_records_workspace_id", "usage_records", ["workspace_id"])
    op.create_index("ix_user_api_keys_user_id", "user_api_keys", ["user_id"])
    op.create_index("ix_user_api_keys_workspace_id", "user_api_keys", ["workspace_id"])
    op.create_index("ix_user_custom_roles_ws", "user_custom_roles", ["workspace_id"])
    op.create_index("ix_user_custom_roles_workspace_id", "user_custom_roles", ["workspace_id"])
    op.create_index("ix_user_installations_listing_id", "user_installations", ["listing_id"])
    op.create_index("ix_user_installations_user_id", "user_installations", ["user_id"])
    op.create_index("ix_user_oidc_accounts_provider_id", "user_oidc_accounts", ["provider_id"])
    op.create_index("ix_user_oidc_accounts_user_id", "user_oidc_accounts", ["user_id"])
    op.create_index("ix_user_subscriptions_user_id", "user_subscriptions", ["user_id"])
    op.create_index("ix_user_tenants_ws", "user_tenants", ["workspace_id"])
    op.create_index("ix_user_tenants_user_id", "user_tenants", ["user_id"])
    op.create_index("ix_user_tenants_workspace_id", "user_tenants", ["workspace_id"])
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_index("ix_users_partner_id", "users", ["partner_id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_workspace_messages_sender_id", "workspace_messages", ["sender_id"])
    op.create_index("ix_workspace_messages_workspace_id", "workspace_messages", ["workspace_id"])
    op.create_index("ix_workspace_messages_recipient_id", "workspace_messages", ["recipient_id"])

    # ── STEP 7: Add missing FK constraints (3) ─────────────────
    op.create_foreign_key("fk_swarm_profiles_created_by", "swarm_profiles", "users", ["created_by"], ["id"])
    op.create_foreign_key(
        "fk_tool_chain_executions_chain_id", "tool_chain_executions", "tool_chains", ["chain_id"], ["id"]
    )
    op.create_foreign_key("fk_users_partner_id", "users", "partners", ["partner_id"], ["id"])


def downgrade() -> None:
    """Forward-only migration — downgrade is not supported.

    This migration reconciles schema drift from accumulated manual changes.
    To reverse, restore from a database backup taken before running upgrade.
    """
    op.drop_constraint("fk_users_partner_id", "users", type_="foreignkey")
    op.drop_constraint("fk_tool_chain_executions_chain_id", "tool_chain_executions", type_="foreignkey")
    op.drop_constraint("fk_swarm_profiles_created_by", "swarm_profiles", type_="foreignkey")
