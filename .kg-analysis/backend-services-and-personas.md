# KG-ANALYSIS: Backend Services Layer + 216-Persona Platform Model

**Scope**: Read-only analysis of `/opt/flowmanner/backend/app/services/` (Scope A) and the
agent-definitions / persona platform (Scope B). No source was modified, committed, or deployed.

**Repo state**: branch `agent/20260720-kg/svc-personas`, worktree
`/opt/flowmanner/.worktrees/t_dddfe2c0`. All file:line anchors verified by reading the code.

---

## 1. SERVICES INVENTORY

The services layer is **109 modules** (`app/services/*.py` top-level + many subpackages) totalling
~43,300 lines. It is organised as: flat-functional services (`app/services/*.py`), domain
subpackages (`services/substrate/`, `services/web_search/`, `services/swarm/`, `services/nexus/`,
`services/providers/`, `services/rag/`, `services/semantic/`, `services/reviewer_guard/`,
`services/webhook_handler/`, `services/unified_tools/`, `services/evaluation/`, `services/flow/`,
`services/sentry/`, `services/integrative_memory/`, `services/skills/`), and CQRS command/query
helpers under `app/api/_*_cqrs/`.

| Module (top-level unless noted) | Responsibility | Key exports | Consumers (API) | Notes |
|---|---|---|---|---|
| `chat_service.py` (2885 ln) | Chat threads, message history, prompt versioning, system-prompt assembly | `ChatService`, system-prompt builder | `api/v1/chat.py:29`, `api/v2/chat.py:36`, `api/v2/prompts.py:16` | **God service** — largest in repo |
| `integration_bridge.py` (2630 ln) | External integration execution/runtime bridge | `IntegrationBridge` | `api/v1/integration_webhooks.py`, `integrations_actions.py:14` | **God service** — 2nd largest |
| `mission_service.py` (+ `_mission_cqrs/*`) | Mission CRUD, access control, lifecycle | `get_mission`, `require_mission_access` | `api/v1/circuit_breaker.py:21`, `api/v1/substrate.py:20`, `api/v1/replay_export.py:35`, `_mission_cqrs/*` | Central to substrate/run flows |
| `mission_planner.py` (1010 ln) | Mission decomposition/planning | `MissionPlanner` | `api/_mission_cqrs/commands.py:45` | |
| `mission_program_service.py` (995 ln) | Program (multi-mission) CQRS | `MissionProgramService` | `api/_program_cqrs/commands.py:24`, `api/v2/programs.py:48` | |
| `auth_service.py` | JWT decode, user lookup, password verify | `decode_access_token`, `get_user_by_id`, `verify_password` | `api/deps.py:14`, `api/v1/auth.py:38`, `api/v1/two_fa.py:20`, `api/v2/auth.py:29` | Cross-cutting auth |
| `auth_v3_service.py` (660 ln) | V3 auth (workspaces, invites, sessions) | token/session helpers | `api/deps.py:16`, `api/v1/auth.py:51`, `api/v2/auth.py:42`, `api/v3/auth.py:52`, `api/v3/workspace_invitations.py:20` | Cross-cutting auth |
| `agent_service.py` (275 ln) | Agent + AgentTemplate CRUD, **seeds personas** | `list_agents`, `seed_agent_templates`, `list_agent_templates` | `api/v1/agent.py:18`, `api/v2/agents.py:23`, `api/v1/agent_registry.py:22` | **Persona loader seam** — see §4 |
| `agent_parser.py` (101 ln) | Parse persona `.md` → dict | `load_all_agents`, `parse_agent_file` | `agent_service.py:14` only | Tiny, central to persona load |
| `agent_registry_service.py` | Semantic agent-capability registry (Qdrant) | `AgentRegistryService` | `api/v1/agent_capabilities.py:18`, `swarm/handoff_protocol.py:24`, `swarm/escalation_chain.py:18` | Cross-cutting (discovery) |
| `llm_executor.py` (228 ln) | LLM task execution **+ system-prompt injection** | `_resolve_agent_system_prompt` | invoked by task/run executors | **Runtime injection seam** — see §4 |
| `llm_router.py` / `model_router.py` (706 / 731 ln) | Model selection, cost-aware routing | `ModelRouter`, `LLMRouteResult` | `api/v1/llm.py:12`, `api/v1/llm_advanced.py:11` | Cross-cutting (every LLM call) |
| `chat_context.py`, `chat_service.py` | Chat context building | — | chat routes | |
| `budget_enforcer.py` (925 ln) | Cost/budget guardrails | `BudgetEnforcer` | run/mission paths | Cross-cutting (cost) |
| `cost_tracker.py`, `cost_attribution_service.py`, `cost_summary_service.py` | Token/cost accounting | `CostAttributionService`, `get_chat_cost_summary` | `api/v1/cost_attribution.py:20`, `api/v2/chat.py:57` | Cross-cutting (cost) |
| `tool_router.py` (658 ln), `tool_discovery_service.py` (572 ln) | Tool routing/discovery | `ToolRouter`, `get_tool_router` | `api/v1/tool_routing.py:20,161` | Cross-cutting (tools) |
| `memory_service.py`, `personal_memory_service.py` (1222 ln), `episodic_memory_service.py`, `memory_*_service.py` | Memory tiers (semantic/episodic/personal) | `MemoryService`, `PersonalMemoryService`, `EpisodicMemoryService` | `api/v2/personal_memory.py:60`, `api/v1/episodic_memory.py:18`, `api/v1/memory_actions.py:16` | Cross-cutting (memory) |
| `rag_service.py`, `rag/*` | RAG retrieval + vector store | `RAGService`, `prompt_synthesizer` | `api/v1/rag.py:18,23` | Cross-cutting (RAG) |
| `swarm_service.py`, `swarm/*` | Multi-agent orchestration (debate/escalation/handoff) | `DebateProtocol`, `EscalationChain`, `HandoffProtocol` | `api/v1/swarm_protocol.py:17-19` | Cross-cutting (orchestration) |
| `run_service.py` (454 ln) | Run records, execution status | `RunService` | `api/_blueprint_cqrs/queries.py:15`, `commands.py:9` | |
| `blueprint_service.py` | Blueprint (DAG) CRUD | `BlueprintService` | `api/_blueprint_cqrs/*` | |
| `substrate/*` (adapters, node_executor, assertion_engine, replay_engine, resilience_service, trigger_bridge, lease_reclaimer, harness_evolution, replay_query) | Workflow substrate execution + replay + resilience | `get_assertion_engine`, `get_replay_engine`, `ResilienceService`, `NodeExecutor` | `api/v1/substrate.py:21-23`, `api/v1/strategies.py:12`, `api/v2/regression.py:25`, `api/v2/resilience.py:26`, `api/v1/replay_export.py:36` | Cross-cutting (execution substrate) |
| `oidc_service.py` (786 ln) | OIDC/SAML identity | OIDC helpers | `api/v1/oidc.py:22` | Auth-adjacent |
| `totp_service.py` | TOTP / backup codes | `verify_code`, `consume_backup_code` | `api/v1/two_fa.py:21`, `api/v1/auth.py:57`, `api/v2/auth.py:48`, `api/v3/auth.py:73` | Auth-adjacent |
| `account_lockout.py`, `auth_rate_limiter.py` | Brute-force lockout + rate limits | `record_failed_login`, `check_rate_limit` | `api/v1/auth.py:36,37`, `api/v2/auth.py:27,28`, `api/v3/auth.py:51` | Security cross-cutting |
| `circuit_breaker_service.py`, `reliability_assertions.py`, `chaos_langfuse.py` | Resilience/chaos tooling | `CircuitBreakerService`, `get_reliability_monitor`, `get_chaos` | `api/v1/circuit_breaker.py:20`, `api/v1/reliability.py:13,14` | Reliability cross-cutting |
| `notification_service.py` (734 ln), `alerting.py` (539 ln) | Notify + alert dispatch | notify/alert fns | background/event paths | |
| `event_bus.py`, `event_bus_consumers.py`, `event_router.py` | Internal eventing | `get_event_bus` | `api/v1/integration_webhooks.py:28` | Cross-cutting (events) |
| `plugin_runtime.py` (445 ln), `plugin_loader.py`, `plugin_scanner.py` | Plugin sandbox/runtime | `PluginRuntime` | plugin routes | |
| `marketplace_service.py`, `nexus/*` | Marketplace + nexus capability composition | `get_marketplace_service` | `api/v2/marketplace.py:16` | |
| `sandbox_service.py`, `mission_code_sandbox.py` | Code-sandbox execution | — | sandbox routes | |
| `hitl_service.py` (607 ln) | Human-in-the-loop review | `HITLService` | `api/v1/hitl.py:25` | |
| `critic.py` (650 ln), `critique_service.py`, `self_correction_loop.py`, `self_improvement.py`, `improvement_generator.py`, `feedback_synthesizer.py` | Critique/self-improvement loop | `Critic`, `SelfImprovementEngine` | `api/v2/critiques.py:49`, `api/v1/feedback_routes.py:22`, `_mission_cqrs/*` | |
| `graph_service.py` (473 ln), `graph_analytics.py` | Knowledge-graph ops | graph fns | `api/v1/graph.py:23` | |
| `search_service.py` | Web/search service | `get_search_service` | `api/v1/search.py:14`, `api/v2/search.py:12` | |
| `usage_service.py`, `analytics_service.py` | Usage + analytics tracking | `UsageService`, `track_event` | `api/v1/usage.py:10`, `api/v1/analytics.py:14` | |
| `permission_service.py`, `workspace_tenancy.py`, `cross_workspace_service.py` | Tenancy/permissions | permission fns | `api/v1/workspace_shares.py:16` | Security/tenancy cross-cutting |
| `session_management.py`, `delegation_service.py`, `team_space.py` | Sessions/delegation/teams | session/delegation fns | `api/v1/sessions.py:10`, `api/v1/delegations.py:24` | |
| `brand_voice.py`, `skills_service.py` (444 ln), `playground_service.py` | Brand voice, skills, playground | `PlaygroundService` | `api/v1/playground.py:16`, `api/v1/admin_sandboxes.py:17` | |
| `trigger_service.py`, `sse_*` (sse_buffer/sse_protocol/sse_service) | Triggers + SSE streaming | trigger fns, `get_stream_buffer` | `api/v1/triggers.py:23`, `api/v1/chat.py:49`, `api/v2/chat.py:58` | Cross-cutting (streaming) |
| `versioning.py`, `mission_cache.py`, `mission_errors.py` | Versioning, cache, error types | `invalidate_mission_cache`, `MissionNotFoundError` | `_mission_cqrs/*`, `api/v1/substrate.py:19` | |
| `langfuse_service.py` (710 ln), `langfuse_metrics.py`, `chaos_langfuse.py` | Observability (Langfuse) | `LangfuseService` | lifespan, tracing | Cross-cutting (observability) |
| `web_search/*` (service, providers, cache, content_extractor, service_enhanced, web_search_routes_enhanced) | Web-search pipeline | `WebSearchService` | search routes | |
| `providers/*` (deepseek, openrouter, anthropic_adapter, provider_factory) | LLM provider adapters | provider clients | `llm_router` consumers | |
| `task_executor.py` (783 ln), `delegation_service.py` | Task execution + delegation | task executor | run/substrate paths | |
| `learning_service.py` (651 ln), `capability_engine.py`, `depth_policy.py`, `recovery_policy.py` | Learning/depth/recovery policy | policy fns | run paths | |

> Note: This is a representative inventory of the 109 modules; every module listed was confirmed by
> reading the file or its api-consumer import. Line counts from `wc -l app/services/*.py`.

---

## 2. SERVICE→ROUTE MAP

Compiled by grepping `app/api/**/*.py` for `from app.services` / `from app.services.*`.

| API router | Services imported |
|---|---|
| `api/deps.py` | `auth_service`, `auth_v3_service` |
| `api/v1/auth.py` | `account_lockout`, `auth_rate_limiter`, `auth_service`, `auth_v3_service`, `totp_service` |
| `api/v2/auth.py` | `account_lockout`, `auth_rate_limiter`, `auth_service`, `auth_v3_service`, `totp_service` |
| `api/v3/auth.py` | `auth_rate_limiter`, `auth_v3_service`, `totp_service` |
| `api/v3/workspace_invitations.py` | `auth_v3_service` |
| `api/v1/two_fa.py` | `auth_service`, `totp_service` |
| `api/v1/oidc.py` | `oidc_service` |
| `api/v1/agent.py` | `agent_service` |
| `api/v2/agents.py` | `agent_service` |
| `api/v1/agent_registry.py` | `agent_service` |
| `api/v1/agent_capabilities.py` | `agent_registry_service` |
| `api/v1/agent_personalities.py` | (reads `agent_definitions/` directly — NOT via a service) |
| `api/v1/chat.py` | `chat_service`, `sse_buffer` |
| `api/v2/chat.py` | `chat_service`, `cost_summary_service`, `sse_buffer` |
| `api/v2/prompts.py` | `chat_service` |
| `api/v1/rag.py` | `rag`, `rag_service`, `rag.prompt_synthesizer` |
| `api/v1/search.py` / `api/v2/search.py` | `search_service` |
| `api/v1/tool_routing.py` | `tool_router` |
| `api/v2/integrations_actions.py` | `action_registry` |
| `api/v1/triggers.py` | `trigger_service` |
| `api/v1/substrate.py` | `mission_errors`, `mission_service`, `substrate.assertion_engine`, `substrate.replay_engine`, `substrate.replay_query` |
| `api/v1/strategies.py` | `substrate.strategies` |
| `api/v2/regression.py` | `substrate.assertion_engine`, `substrate.baseline_extractor` |
| `api/v2/resilience.py` | `substrate.resilience_service` |
| `api/v1/replay_export.py` | `mission_errors`, `mission_service`, `substrate.event_log` |
| `api/v1/circuit_breaker.py` | `circuit_breaker_service`, `mission_service` |
| `api/v1/reliability.py` | `chaos_langfuse`, `reliability_assertions` |
| `api/v1/hitl.py` | `hitl_service` |
| `api/v1/cost_attribution.py` | `cost_attribution_service` |
| `api/v1/graph.py` | `graph_service`, `mission_errors` |
| `api/v1/dashboard.py` | `dashboard_service` |
| `api/v1/analytics.py` | `analytics_service` |
| `api/v1/usage.py` | `usage_service` |
| `api/v1/sessions.py` | `session_management` |
| `api/v1/delegations.py` | `delegation_service` |
| `api/v1/episodic_memory.py` | `episodic_memory_service` |
| `api/v2/personal_memory.py` | `memory_correction_service`, `personal_memory_service` |
| `api/v1/memory_actions.py` | `memory_action_service` |
| `api/v1/feedback_routes.py` | `feedback_synthesizer`, `mission_service` |
| `api/v1/swarm_protocol.py` | `swarm.debate_protocol`, `swarm.escalation_chain`, `swarm.handoff_protocol` |
| `api/v1/playground.py` / `api/v1/admin_sandboxes.py` | `playground_service` |
| `api/v1/workspace_shares.py` | `cross_workspace_service` |
| `api/v1/depth.py` | `depth_policy` |
| `api/v1/integration_webhooks.py` | `event_bus` |
| `api/v2/marketplace.py` | `nexus.marketplace_db` |
| `api/v2/critiques.py` | `critique_service` |
| `api/v1/llm.py` / `api/v1/llm_advanced.py` | `llm_router` |
| `api/v3/workspaces.py` | `background_task_manager` |
| `api/_mission_cqrs/commands.py` | `mission_cache`, `mission_errors`, `mission_planner`, `mission_service`, `self_improvement` |
| `api/_mission_cqrs/queries.py` | `mission_analytics`, `mission_cache`, `mission_errors`, `mission_service`, `self_improvement` |
| `api/_program_cqrs/commands.py` / `queries.py` | `mission_program_service` |
| `api/_blueprint_cqrs/commands.py` / `queries.py` | `blueprint_service`, `run_service` |
| `api/v1/evaluation.py` | `evaluation.dataset_builder`, `evaluation.eval_runner` |

**No v3 `/agents` or `/agent-templates` route exists** — persona/agent serving is v1 (`/api/agent`,
`/api/agent-registry`, `/api/agent-capabilities`, `/api/agent-personalities`) and v2
(`/api/agents`, `/api/agents/templates/list`).

---

## 3. CROSS-CUTTING SERVICES

Services that are depended on by many independent call paths (not just one feature area):

- **Auth**: `auth_service` + `auth_v3_service` + `totp_service` + `account_lockout` +
  `auth_rate_limiter` + `oidc_service` + `permission_service` + `workspace_tenancy`. Consumed by
  `api/deps.py` (the universal `get_current_user` dependency) and every authenticated route
  (`v1/auth.py:38`, `v2/auth.py:29`, `v3/auth.py:52`). This is the security backbone.
- **Cost/billing**: `budget_enforcer` (925 ln), `cost_tracker`, `cost_attribution_service`,
  `cost_summary_service`, `usage_service`. Enforced in run/mission execution and surfaced via
  `v1/cost_attribution.py` and `v2/chat.py:57`.
- **LLM execution + routing**: `llm_router`/`model_router` (every LLM call routes through here) and
  `llm_executor` (the system-prompt injection seam — §4).
- **Memory**: `memory_service`, `personal_memory_service` (1222 ln), `episodic_memory_service`,
  `memory_*_service` (citation, conflict, correction, snapshot, action, extraction_pause, attribution).
  Multi-tier memory is a first-class cross-cutting concern.
- **RAG**: `rag_service` + `rag/*` (vector_store, prompt_synthesizer).
- **Agent execution / substrate**: `substrate/*` (adapters, node_executor, assertion/replay/resilience
  engines, trigger_bridge, lease_reclaimer, harness_evolution) underpins mission/run execution and is
  consumed by `v1/substrate.py`, `v1/strategies.py`, `v2/regression.py`, `v2/resilience.py`,
  `v1/replay_export.py`.
- **Orchestration/swarm**: `swarm_service` + `swarm/*` (debate/escalation/handoff) + `agent_registry_service`
  (semantic discovery) — multi-agent coordination is cross-cutting.
- **Tooling**: `tool_router` + `tool_discovery_service` + `action_registry` + `unified_tool_bridge`.
- **Observability**: `langfuse_service` (710 ln) + `langfuse_metrics` + `chaos_langfuse` + `alerting` +
  `notification_service`.
- **Streaming/events**: `sse_buffer`/`sse_protocol`/`sse_service` + `event_bus`/`event_router`.

**God services (over-centralised, high change-risk):**
- `chat_service.py` — **2885 lines**, the single largest module. Owns chat threads, message history,
  prompt versioning, and system-prompt assembly (`chat_service.py:1826-1853`). Used by 3 API routers.
- `integration_bridge.py` — **2630 lines**, 2nd largest. Single point for all external integration
  execution; consumed by webhook + actions routes.
- `personal_memory_service.py` (1222) + `mission_planner.py` (1010) + `mission_program_service.py` (995)
  + `budget_enforcer.py` (925) are also very large and would benefit from decomposition.

**Duplication / overlap noted:**
- Two auth stacks coexist: `auth_service` (legacy JWT) and `auth_v3_service` (workspace/session model).
  v3 routes (`api/v3/auth.py`) use only `auth_v3_service`; v1/v2 use both. Migration is incomplete.
- Three web-search implementations: `web_search/service.py`, `web_search/service_enhanced.py`,
  `web_search/web_search_routes_enhanced.py` — overlapping responsibility.
- `cost_tracker` vs `cost_attribution_service` vs `cost_summary_service` — three cost modules with
  overlapping scope.
- `agent_registry_service` (Qdrant semantic registry) vs `agent_service`/`AgentTemplate` (PostgreSQL
  catalog) — two parallel "agent directories" with different backing stores and no obvious sync.

---

## 4. PERSONA PLATFORM MODEL

### 4.1 Loader mechanics (`app/services/agent_parser.py`)

- `AGENT_DEFINITIONS_DIR` is computed at `agent_parser.py:17` as
  `Path(__file__).resolve().parent.parent.parent / "agent_definitions"`.
  From `backend/app/services/agent_parser.py`, `parent.parent.parent` = `backend/`, so this resolves to
  **`/opt/flowmanner/backend/agent_definitions`** (the TOP-LEVEL dir — see §4.4 bug).
- `parse_agent_file(file_path)` (`agent_parser.py:20-71`): reads UTF-8, requires leading `---`
  frontmatter (`agent_parser.py:32`), splits on `---` into `[yaml_text, markdown_body]`
  (`agent_parser.py:36-42`), `yaml.safe_load`s the frontmatter (`agent_parser.py:45`), requires a
  `name` field (`agent_parser.py:54-57`), derives `slug = file_path.stem` and
  `division = file_path.parent.name` (`agent_parser.py:59-60`).
- **Persona fields**: `name`, `description`, `color` (default `#6B7280`), `emoji`, `vibe`
  (all with defaults), plus derived `slug`, `division`, and `system_prompt` = the markdown body
  (`agent_parser.py:62-71`). Frontmatter is flat only; nested structures are not supported.
- `load_all_agents(definitions_dir=None)` (`agent_parser.py:74-101`): `sorted(rglob("*.md"))`
  over the dir (`agent_parser.py:88`), calls `parse_agent_file` per file, logs
  `"Loaded %d agent definitions ... (%d parse errors)"` (`agent_parser.py:95-100`). Returns the list
  of successfully parsed dicts.

### 4.2 Divisions + counts

Two parallel on-disk stores exist (see §4.4). Counting the **canonical `app/agent_definitions/`** set
(216 files, verified by `find app/agent_definitions -name '*.md' | wc -l` = 216):

| Division (top-level dir) | Persona count | Notes |
|---|---|---|
| specialized | 41 | largest division |
| marketing | 30 | |
| engineering | 30 | |
| agent_personalities | 30 | **nested subdirs** (customer-service, finance, healthcare, hr, legal, marketing, media-creative, operations, sales, software_it) — 30 personas live one level deeper |
| game-development | 20 | **15 nested** under blender/godot/roblox-studio/unity/unreal-engine |
| design | 8 | |
| sales | 8 | |
| testing | 8 | |
| paid-media | 7 | |
| spatial-computing | 6 | |
| project-management | 6 | |
| support | 6 | |
| academic | 5 | |
| finance | 5 | |
| product | 5 | |
| browser | 1 | |
| **TOTAL** | **216** | |

`load_all_agents` derives `division` from `file_path.parent.name`, so a nested file like
`app/agent_definitions/agent_personalities/sales/deal-coach.md` is reported with
`division = "sales"` (its immediate parent), NOT `agent_personalities`. The 16 top-level divisions are
real directories; nested files inflate the apparent division count to ~20 logical buckets
(blender, godot, unity, unreal-engine, roblox-studio, customer-service, etc.).

### 4.3 Serving endpoints

Personas are **not** served directly from `.md` files at request time. The flow is:

1. **Seed (one-way copy)**: `agent_service.seed_agent_templates(db, definitions_dir)` (`agent_service.py:235`)
   calls `load_all_agents(definitions_dir)` (`agent_service.py:236`), then upserts each persona into the
   PostgreSQL `AgentTemplate` table (`agent_service.py:240-272`), setting
   `agent_type = agent_data["division"]` and `is_active=True` (`agent_service.py:256,267`).
2. **Seed is triggered at**: app startup via `lifespan._seed_agent_templates()` (`lifespan.py:481-488`,
   called at `lifespan.py:56`), the Alembic migration `2026_02_01_1400_seed_agent_templates.py:33`, the
   bootstrap CLI `cli/bootstrap.py:208`, and `scripts/import_agent_templates.py:59`.
3. **Serving**:
   - `GET /api/v2/agents/templates/list` → `list_agent_templates` (`api/v2/agents.py:163-177`,
     `agent_service.py:184-207`). **Filters `AgentTemplate.is_active.is_(True)`**
     (`agent_service.py:191-192`) and is **paginated** (default `limit=100`, but the v2 route defaults
     `per_page=20` via `Query(20)` at `api/v2/agents.py:166`).
   - `GET /api/v1/agents` / `/api/v2/agents` → user-owned `Agent` rows (CRUD on `Agent`, NOT the persona
     catalog) — `agent_service.list_agents` (`agent_service.py:83`).
   - `GET /api/agent-capabilities/*` → `AgentRegistryService` (Qdrant semantic registry, a SEPARATE store
     from `AgentTemplate`) — `api/v1/agent_capabilities.py:18`.
   - `GET /api/agent-personalities/*` → `app/api/v1/agent_personalities.py` reads `.md` files **directly
     from disk** (its own frontmatter parser, no PyYAML) — `agent_personalities.py:30-76`.

### 4.4 INVISIBLE-PERSONA BUG (root cause)

**`load_all_agents` reads the WRONG directory.** `agent_parser.py:17` resolves to
`/opt/flowmanner/backend/agent_definitions` (top-level), but the full 216-persona set lives in
`/opt/flowmanner/backend/app/agent_definitions/` (one level deeper, under `app/`).

Verified by direct execution:
- `backend/agent_definitions/` contains **185** `.md` files (`find backend/agent_definitions -name '*.md' | wc -l` = 185) and has **no `agent_personalities` subdir**.
- `backend/app/agent_definitions/` contains **216** `.md` files and **includes** `agent_personalities` (30 personas) + 30 extra personas spread across all divisions vs the top-level set.
- `load_all_agents()` returns **185** personas (`agent_parser.py` `rglob` over the top-level dir). The other **31 personas** (the entire `agent_personalities` division of 30, plus 1 more) are **never loaded, never seeded into `AgentTemplate`, and therefore never appear in `/api/v2/agents/templates/list`** — they are invisible.

Corroborating path-math errors in sibling code:
- `app/api/v1/agent_personalities.py:22` uses the SAME broken math
  (`Path(__file__).resolve().parent.parent.parent / "agent_definitions"`) and its docstring
  (`agent_personalities.py:4`) *claims* it reads `backend/app/agent_definitions/agent_personalities/`
  — but it actually reads the stale top-level dir, so it cannot even find its own division.
- `app/tasks/meta_review_tasks.py:169` hardcodes `/opt/flowmanner/backend/agent_definitions` (stale dir).
- `scripts/seed_marketplace.py:85` correctly uses
  `Path(__file__).resolve().parent.parent / "app" / "agent_definitions"` (the 216-set) — proving the
  `app/agent_definitions` path is the intended canonical source and the in-code `parent.parent.parent`
  math is wrong by one directory level.

**Secondary invisibility**: even among the 185 that ARE seeded, `/api/v2/agents/templates/list` only
returns `is_active=True` rows (`agent_service.py:191`) paginated `per_page=20` (`api/v2/agents.py:166`).
Since seeding sets `is_active=True` for all, all 185 seeded personas are reachable, but a client must
paginate to see beyond the first 20.

### 4.5 Persona → runtime injection seam

A chosen persona becomes a system prompt at execution via `llm_executor.py`:

- `LLMExecutor._build_llm_messages(task, prompt)` (`llm_executor.py:164-190`) calls
  `_resolve_agent_system_prompt(task)` and, if non-empty, prepends it as a `system` role message
  (`llm_executor.py:180-187`).
- `_resolve_agent_system_prompt(task)` (`llm_executor.py:192-226`): if `task.assigned_agent_id` is set
  (`llm_executor.py:205`), it opens a DB session and queries `AgentTemplate` **first by `template_id`**
  (`llm_executor.py:210-215`), falling back to a JSONB `slug` match
  (`llm_executor.py:217-220`), returning `template.system_prompt` (`llm_executor.py:214,223`).
- Separate path: chat threads resolve the system prompt in `chat_service.py:1826-1853`
  (active prompt content → thread `metadata_.system_prompt` → default "You are a helpful assistant."
  + optional Sandboxd guidance). This is the prompt-versioning seam, distinct from the
  `AgentTemplate` seam.

So the persona lifecycle is: **`.md` (frontmatter+body) → `load_all_agents` → `AgentTemplate.system_prompt`
(DB) → `llm_executor._resolve_agent_system_prompt` injects into the LLM `system` message at run time.**
Because loading reads the stale top-level dir (§4.4), any persona only present in `app/agent_definitions`
can never be assigned/injected — it is invisible end-to-end.

---

## 5. KEY FINDINGS

1. **Invisible-persona bug (CRITICAL)**: `agent_parser.py:17` resolves the definitions dir to
   `/opt/flowmanner/backend/agent_definitions` (185 files, stale, no `agent_personalities`), but the
   canonical set is `/opt/flowmanner/backend/app/agent_definitions` (216 files). `load_all_agents`
   therefore seeds only 185; the 31 personas absent from the top-level dir (the entire `agent_personalities`
   division of 30 + 1) are never loaded, never written to `AgentTemplate`, and never servable or
   injectable. `scripts/seed_marketplace.py:85` proves `app/agent_definitions` is the intended source.

2. **Sibling path bug**: `app/api/v1/agent_personalities.py:22` uses the identical broken
   `parent.parent.parent / "agent_definitions"` math; its docstring (`agent_personalities.py:4`) claims the
   `app/agent_definitions` path but it actually reads the stale top-level dir and cannot resolve its own
   division. `app/tasks/meta_review_tasks.py:169` hardcodes the same stale path.

3. **Two divergent persona stores, no sync**: `AgentTemplate` (PostgreSQL, seeded from `.md` via
   `agent_service.seed_agent_templates` `agent_service.py:235`) vs `AgentRegistryService` (Qdrant semantic
   registry, `agent_registry_service.py:24`). They back different endpoints
   (`/api/v2/agents/templates/list` vs `/api/agent-capabilities`) and there is no observed reconciliation.

4. **`load_all_agents` division derivation is lossy for nested files**: `division = file_path.parent.name`
   (`agent_parser.py:60`) means nested personas (e.g. `agent_personalities/sales/deal-coach.md`) report
   `division="sales"`, not `"agent_personalities"`, collapsing the intended 16-division taxonomy into ~20
   buckets once seeded into `AgentTemplate.agent_type`.

5. **Catalog pagination/filter hides personas even when seeded**: `list_agent_templates`
   (`agent_service.py:184-207`) filters `is_active.is_(True)` and the v2 route defaults `per_page=20`
   (`api/v2/agents.py:166`); a UI must paginate to surface all 185 seeded personas.

6. **God services**: `chat_service.py` (2885 ln) and `integration_bridge.py` (2630 ln) are the two largest
   modules and are single points of change for chat and integration execution respectively;
   `personal_memory_service.py` (1222), `mission_planner.py` (1010), `mission_program_service.py` (995),
   `budget_enforcer.py` (925) are also oversized.

7. **Auth stack is half-migrated**: `auth_service` (legacy JWT) and `auth_v3_service` (workspace/session
   model) coexist; v3 routes use only `auth_v3_service` (`api/v3/auth.py:52`) while v1/v2 import both
   (`api/v1/auth.py:38,51`). Incomplete v2→v3 auth migration.

8. **Redundant implementations**: three web-search modules (`web_search/service.py`,
   `web_search/service_enhanced.py`, `web_search/web_search_routes_enhanced.py`) and three cost modules
   (`cost_tracker`, `cost_attribution_service`, `cost_summary_service`) overlap in responsibility.

9. **Runtime injection is DB-backed, not file-backed**: the persona→system-prompt seam is
   `llm_executor._resolve_agent_system_prompt` (`llm_executor.py:192-226`), which reads `AgentTemplate`
   by `template_id` then `slug`. Because loading is broken (finding 1), the 31 invisible personas are also
   non-injectable at execution — the gap is end-to-end, not just catalog visibility.

10. **Seeding is idempotent and self-healing on fix**: `seed_agent_templates` upserts by slug
    (`agent_service.py:242`) and sets `is_active=True` for all (`agent_service.py:267`); it runs at lifespan
    (`lifespan.py:56,481`) and via migration/bootstrap. Fixing the path at `agent_parser.py:17` (and the two
    sibling sites) would, on next startup, auto-seed the missing 31 personas with no data migration required.
