# Flowmanner — `app/services` Agent Instructions

## Purpose

This is the local contract for everything under `backend/app/services/`. The services layer is the **business-logic seam** between the HTTP/SSE/WebSocket routes in `app/api/` and the persistence + infra layer (DB, Redis, Qdrant, LLM providers, sandboxd, connectors). The mission of this file: let an agent land in this directory, identify the right cluster for the change, and not get lost in 100+ files spread across 25+ subpackages.

## Ownership

| Concern | Owner file/cluster |
|---------|--------------------|
| Mission lifecycle (plan → execute → settle) | `mission_executor.py` + the decomposed sub-modules (see §1) |
| Chat + LLM tool-calling loop | `chat_service.py` + the LLM router family (see §3) |
| RAG / semantic retrieval | `rag_service.py` + `rag/` (see §2) |
| Workflow substrate + unified execution | `substrate/` (see §5) |
| External app connectors | `connectors/` + `linear/` + `mcp/` (see §6) |
| Auth / sessions / 2FA / OIDC | `auth_*`, `oidc_service`, `session_management` (see §7) |
| Memory & learning | `memory_service`, `learning_service`, `memory_bridge/` (see §8) |
| Observability / cost / circuit breaking | `langfuse_*`, `cost_*`, `circuit_breaker_service`, `runtime/` (see §9) |
| Self-improvement loop (Phases 1–6) | `improvement/` (see §10) |
| Sandbox / playground / preview | `sandbox_service`, `playground_service` (see §11) |
| Browser automation | `browser_*` (see §12) |
| Plugin system | `plugin_*` (see §13) |
| Marketplace / templates / capabilities | `marketplace_service`, `capability_engine`, `agent_*` (see §14) |
| HITL / governance / reliability | `hitl_service`, `reliability_assertions`, `delegation_service` (see §15) |
| A2A (agent-to-agent) | `a2a/` (see §16) |
| Sentry (observability-driven auto-fix) | `sentry/` (see §17) |
| Domain agents | `domain_agents/` (see §18) |
| Evaluation / LLM-as-judge | `evaluation/` (see §19) |
| Billing / subscriptions | `paypal_service`, `subscription_service` (see §20) |
| LangGraph (stateful workflow agent) | `langgraph/` (see §21) |
| LangChain (shared tools) | `langchain/tools/` (see §22) |

## Local Contracts

These rules apply specifically to this subtree. They are **in addition to** the rules in the parent `backend/AGENTS.md` (no volume mounts, must rebuild image, alembic for schema changes, etc.).

1. **Async-first.** Services are written against `sqlalchemy.ext.asyncio.AsyncSession`. Do not introduce sync DB calls. The few sync entry points (e.g. `model_router.get_routing_info()`) must not call `db.execute()`.
2. **Constructor + late-bound callables.** Where a service depends on `ModelRouter` or `RAGService` (which initialize after app start), accept a `get_<thing>` callable, not the instance. See `MissionExecutor._get_model_router` for the pattern. Tests inject `lambda: mock`.
3. **No `db.commit()` inside a sub-module that doesn't own the transaction.** Top-level service functions (routes) own the transaction. Sub-modules do `db.add()` / `db.flush()` and let the parent commit. The `CostTracker` comment in `services/README.md` calls this out explicitly.
4. **BYOK (Bring Your Own Key) precedence is `kwargs override → stored user key → platform key`.** See `_lookup_stored_byok_key` in `chat_service.py`. Never default to the platform key if a user has a stored key for that provider.
5. **`llamacpp/*` models ignore BYOK keys.** llama.cpp does not use API keys. `_resolve_provider` + `chat_service.send_message_to_llm` both nullify the key for `llamacpp/`.
6. **Provider key-prefix detection is hint-only.** `_detect_provider_from_key` returns `None` for ambiguous prefixes (`sk-…` is shared by OpenAI/Together/DeepInfra). Do not raise on prefix mismatch; rely on `_providers_compatible`.
7. **Substrate event log is the source of truth for workflow state** (see `substrate/H5-1-DESIGN.md`). Anything that mutates `Mission` / `WorkflowRun` status must also write a substrate event.
8. **All LLM calls go through `BudgetEnforcer.call()`** (post-H5.1). Do not call `httpx` / `AsyncOpenAI` directly from a strategy. See `substrate/H5-1-DESIGN.md §3.1`.
9. **Tool calls require a `CapabilityToken`.** Issued by `CapabilityEngine.issue()` and verified before execution. Strategies that need tools must request attenuation for sub-workflows.
10. **Tests live in `backend/app/tests/`, not here.** One test file per service is the convention (e.g. `test_cost_tracker.py` ↔ `cost_tracker.py`). Run with `docker compose exec backend pytest app/tests/ -v`.

## Work Guidance

### 1. Mission execution cluster (read this first)

This is the most-edited cluster. The god-class `mission_executor.py` was decomposed (ADR 001) into 5 focused sub-modules. **Do not grow `mission_executor.py` again.** New mission-side logic goes in the appropriate sub-module:

| File | Responsibility | Typical edits |
|------|----------------|---------------|
| `mission_executor.py` | Orchestrator only — wires sub-modules, runs the dependency-ordered task loop, owns the transaction. | Top-level lifecycle, abort/pause handling, post-exec hooks (analytics, audit, Linear sync, learning). |
| `mission_planner.py` | LLM-driven plan generation (pending → planning → planned). | Plan prompt, LLM call, JSON extraction, fallback to a single default task. |
| `task_executor.py` | Task dispatch by `task_type` (LLM, tool, RAG, web_search, code, file, human_input, fallback). | Per-task-type handlers, `_apply_fallback` strategies, dependency resolution. |
| `llm_executor.py` | Single-LLM-task execution + agent system prompt resolution. | Prompt templates, retry classification, cost recording. |
| `browser_task_runner.py` | Browser tool dispatch (navigate/click/type/scroll/screenshot/snapshot/close). | `BROWSER_TASK_TYPES` list, lazy tool imports. |
| `cost_tracker.py` | Cost estimation + `LLMCallRecord` writes + Prometheus metrics. | `COST_PER_1M_TOKENS` table, `record_llm_call()`. **No `db.commit()`.** |
| `mission_service.py` | Mission CRUD (the HTTP layer delegates here for non-execution operations). | Create/update/delete, listing, status queries. |
| `mission_analytics.py` | Mission-level analytics rollups. | Aggregation queries, dashboard metrics. |
| `mission_cache.py` | Mission-scoped Redis caching. | Cache keys, TTLs, invalidation on write. |
| `mission_code_sandbox.py` | Code-execution sandboxing for mission tasks. | Sandbox lifecycle, resource limits. |
| `mission_errors.py` | Shared error hierarchy (`MissionError` → `Retryable` / `Permanent`). | New error subclasses must be `classify_error()`-friendly. |
| `mission_tools.py` | Mission-side tool registry and registration. | Tool definitions and binding to task types. |

Errors raised from this cluster should subclass `MissionError`. The orchestrator's `_classify_error` translates HTTP timeouts / status codes into the right subclass.

### 2. RAG & search cluster

- `rag_service.py` is the **public entry point** used by missions and the chat. Internally delegates to the `rag/` subpackage.
- `rag/` is split by concern: `chunking_service`, `embedding_service`, `prompt_synthesizer`, `retrieval_service`, `vector_store`. If you add a new retrieval technique, add a new file in `rag/` — do not grow `rag_service.py`.
- `search_service.py` is web search (SearXNG / DuckDuckGo / Brave) for live data injected into chat. Different concern from RAG.
- `web_search/` is the SearXNG-backed implementation with multi-provider reranking, query understanding, and content extraction. See `web_search/docker-compose.searxng.yml` for the searxng sidecar.
- `semantic/` is the **topology manager** for the substrate's semantic graph — not general search. Don't confuse the two.

### 3. LLM routing cluster

This cluster is where the most subtle bugs hide (BYOK edge cases, provider fallback, circuit breaking).

| File | Role |
|------|------|
| `llm_router.py` | `ModelRouter` class — async `route_request()` with BYOK + fallback chain. Used by mission_executor, chat, sandbox, eval. |
| `model_router.py` | Older sync `ModelRouter` with the same surface. Used by some legacy routes. **Prefer `llm_router.py` for new code.** |
| `chat_service.py` | The chat tool-calling loop (sandboxd tools), prompt building, BYOK key resolution, stream + non-stream paths, attachment processing, web-search injection, branch management, auto-title generation. |
| `providers/` | Thin per-provider wrappers. `provider_factory.py` is the registry. Add a new provider by adding a service + registering it here. |
| `llm_langgraph/` | Single-file LangGraph agent driver. Replaced by `langgraph/agent.py` for new code. |
| `langgraph/llm_config.py` | `LLMManager` — model catalog, BYOK-aware `get_model()`. Imported by `model_router.py`. |

When changing routing, **change `llm_router.py` and `chat_service.py` together**. The two BYOK key resolution paths (`_get_byok_key` in `llm_router` and `_lookup_stored_byok_key` in `chat_service`) MUST agree. See the unit tests in `tests/test_h1_1_model_router_silent_failure.py` for known-bug history.

### 4. Agent cluster

- `agent_service.py` — `Agent` and `AgentTemplate` CRUD, plus `seed_agent_templates()` which reads from `agent_definitions/` (loaded via `agent_parser.load_all_agents`).
- `agent_parser.py` — Parses the 15 domain tree files under `backend/agent_definitions/` into seed dicts.
- `agent_registry_service.py` — Runtime registry of available agents (separate from the DB templates). Used by swarm/nexus matching.
- `agent_capabilities.py` (in `api/v1/`) — HTTP layer for agent capabilities.

When adding a new domain agent tree, edit `backend/agent_definitions/<division>/agent.py` and the `load_all_agents` parser — do not hard-code seeds anywhere else.

### 5. Substrate / unified execution cluster

`substrate/` is the **destination** of H5.1 (the "collapse the executors" effort). It already has the design (`H5-1-DESIGN.md`), the strategy scaffold, the event log, the replay engine, and the adapters from old ORM models.

- `substrate/executor.py` — `UnifiedExecutor` (the only entry point post-H5.1).
- `substrate/strategies/` — 7 strategies (solo, dag, graph, langgraph, meta, pipeline, swarm). Each implements `ExecutionStrategy` ABC from `strategies/base.py`.
- `substrate/event_log.py` — Append-only event log (`substrate_events` table). Source of truth for crash recovery.
- `substrate/replay_engine.py` — Rebuilds workflow state from event log.
- `substrate/baseline_extractor.py` + `substrate/assertion_engine.py` — Compare replay against captured baseline for regression detection.
- `substrate/trigger_bridge.py` — Wires external triggers (webhooks, cron, Linear) into the substrate.
- `substrate/adapters.py` — Converts old `Mission` / `Flow` / `Graph` ORM models into the new `Workflow` model.
- `substrate/workflow_models.py` — `Workflow`, `WorkflowNode`, `WorkflowEdge`, `NodeType`, `WorkflowType`. **Read this first if you need to add a node type.**

Until H5.1 ships, the 7 old executors (mission_executor, dag_executor, graph_executor, swarm/orchestrator, swarm_pipeline/orchestrator, langgraph/agent, nexus/meta_loop_orchestrator) coexist behind the `FLOWMANNER_UNIFIED_EXECUTOR` feature flag. New code should target the substrate.

**Surrounding executors that delegate into the substrate or wrap it:**

- `dag_executor.py` — Topo-sort + parallel layer execution (DAG-only).
- `graph_executor.py` + `graph_service.py` + `graph_node_handlers.py` + `graph_analytics.py` — The "Graph" workflow type. Conditional edges, `{{node_id.output.field}}` interpolation.
- `flow/` — `flow_service.py`, `execution_router.py`, `project_resolver.py` — Flow workflows (H4 consolidation of Graph + Flow into Workflow).
- `unified_tools/` — `tool_registry`, `tool_executor`, `tool_adapter`, `chain_executor`, `unified_bridge`, `dependencies` — the cross-strategy tool dispatch layer.
- `swarm/` — `orchestrator.py` + `debate_protocol`, `escalation_chain`, `handoff_protocol` — multi-agent debate.
- `swarm_service.py` + `swarm_pipeline/` (in api/v1) — Higher-level swarm APIs.
- `nexus/` — The "agent + capability lattice" subsystem. 18 files covering capability registry, marketplace, agent templates, observability, security, cost optimizer, memory integration, meta loop orchestrator. Most are adapters; `capability_lattice.py` and `failure_analyzer.py` are shared utilities used by the substrate.
- `blueprint_service.py` — Blueprint-driven runs (Design-Blueprint-Run unified model — see `Docs/DESIGN-BLUEPRINT-RUN-UNIFIED-MODEL.md`).
- `run_service.py` — Generic run lifecycle.
- `versioning.py` — Entity versioning (workflow versions, agent versions).

### 6. Integrations & connectors cluster

- `connectors/` — External app adapters. Each connector is a class extending `connectors/base.py` with a sync/async client, a manager, and a webhook receiver. Active connectors: `github`, `notion`, `discord`, `email`, `google`, `linear`, `slack`, `webhook`. Add a new connector by adding a new file + registering it in `connectors/manager.py`.
- `linear/` — Dedicated subpackage (line-specific sync + client). Higher-fidelity than the generic connector.
- `mcp/sentry_mcp_instrumentation.py` — MCP instrumentation hooks for the Sentry integration. Not a server config (that lives at `backend/mcp_gateway/client_config.json`).
- `webhook_handler/` — Generic webhook delivery with retry (`retry.py`), signature verification (`signature.py`), and routing (`router.py`).
- `http_integration_executor.py` + `integration_bridge.py` + `unified_tool_bridge.py` — HTTP-driven integration execution and the unified tool bridge.
- `trigger_service.py` — DB-driven trigger model (separate from webhooks).

### 7. Auth & security cluster

- `auth_service.py` — v1 auth (legacy).
- `auth_v3_service.py` — v3 auth (current). Always prefer this for new routes.
- `oidc_service.py` — OIDC / OAuth2 flows.
- `totp_service.py` — 2FA (TOTP).
- `auth_rate_limiter.py` — Per-endpoint rate limits.
- `account_lockout.py` — Lockout after failed attempts.
- `session_management.py` — Session lifecycle.
- `permission_service.py` — RBAC / permission checks.
- `pii_redactor.py` — Redact PII in logs and tool outputs.
- `notification_service.py` + `email_service.py` + `onboarding_email_service.py` — User-facing notifications.

### 8. Memory & learning cluster

- `memory_service.py` — Conversation + episodic memory. Backed by Postgres + Qdrant.
- `memory_bridge/memory_service.py` — Bridge to external memory backends (legacy; prefer the main `memory_service`).
- `memory_bridge/memory_bridge.py` — Bridge orchestration.
- `episodic_memory_worker.py` — Celery worker that consolidates short-term → long-term memory.
- `learning_service.py` — Cross-mission learning (records executions, surfaces insights).
- `feedback_synthesizer.py` — Converts user feedback into model improvements.

### 9. Observability & operations cluster

- `langfuse_service.py` + `langfuse_metrics.py` + `chaos_langfuse.py` — Langfuse tracing + chaos-test instrumentation.
- `alerting.py` — Service-level alerting.
- `dashboard_service.py` + `analytics_service.py` — Dashboard rollups.
- `usage_service.py` + `usage_tracking_service.py` (elsewhere) — Per-user usage + cost tracking.
- `cost_tracker.py` + `cost_attribution_service.py` + `budget_enforcer.py` — Cost models, attribution, enforcement.
- `circuit_breaker_service.py` + `app/core/circuit_breaker.py` — Circuit breaker (one per provider).
- **Self-healing / auto-scaling is NOT operational.** The `runtime/` self-healing subsystem (Phase 4: `predictive_scaler`, `self_healing`, `health_monitor`, `anomaly_detector`, `recovery_strategies`, `runtime_sdk`) was **removed 2026-07-17** (R10) because it was fully orphaned — decorative `random.uniform` telemetry, `asyncio.sleep(0.5)` "recovery", in-memory-only history, and zero imports outside `runtime/`. No real scaling/self-healing exists in the backend yet. Do not claim 99.9% SLA from code that isn't there.

### 10. Self-improvement cluster

`improvement/` is a **10,570-line subsystem** (per `IMPLEMENTATION_PROGRESS.md`) with its own internal ADR. Read `IMPLEMENTATION_PROGRESS.md` before editing anything here. The phases are:

| Phase | Module | What it does |
|-------|--------|--------------|
| 1 | `failure_types.py` | 14 failure types, severity, telemetry capture. |
| 2 | `causal_decomposer.py`, `knob_manager.py`, `improvement_models.py` | Maps failures to strategies; CRUD for configuration knobs. |
| 3 | `hypothesis_tester.py` | A/B / before-after / canary testing with safety constraints and auto-rollback. |
| 4 | `improvement_loop_v2.py` | Session lifecycle orchestrator. |
| 5 | `metrics_collector.py`, `failure_repository.py`, `alerting.py` | Persistence + dashboard API. |
| 6A | `success_learner.py` | Learn from successes (not just failures). |
| 6B | `knowledge_graph.py` | Persistent knowledge graph over failure/strategy/knob/outcome nodes. |
| 6C | `strategy_evolution.py` | Strategy lifecycle (experimental → candidate → established → deprecated). |
| 6D | `knowledge_transfer.py` | Cross-agent knowledge sharing. |
| 6E | `temporal_analyzer.py` | Time-based failure patterns and predictions. |
| 6F | `proactive_scheduler.py` | Schedule preventive improvements in low-traffic windows. |

The `mission_executor.py` completion hook fires `improvement_loop_v2.on_mission_complete()` (fire-and-forget `asyncio.create_task`).

### 11. Sandbox / playground / preview cluster

- `sandbox_service.py` — Mission-scoped sandboxd lifecycle. See `mission_sandboxes` table and `sandbox_models.py`.
- `playground_service.py` — Workspace-scoped persistent sandboxes (`playground_sandboxes` table).
- `mission_code_sandbox.py` — Subprocess-based code sandbox for legacy missions.
- `mission_tools.py` — Mission-side tool wrappers (some call into sandbox).

The sandboxd HTTP client lives at `app/integrations/sandboxd_client.py`, not in services.

### 12. Browser automation cluster

`browser_service.py` + `browser_agent.py` + `browser_manager.py` + `browser_session.py` + `browser_task_runner.py`. Browser tools are registered as `BROWSER_TASK_TYPES` in `browser_task_runner.py` and dispatched to the lazy-imported tool classes in `app/tools/`.

### 13. Plugin cluster

`plugin_loader.py` + `plugin_runtime.py` + `plugin_scanner.py` — load third-party plugin manifests, sandbox their execution, and scan for known-bad patterns. Plugin security model is governed by `phase96_plugin_security` alembic migration + `app/models/plugin_models.py`.

### 14. Marketplace / templates / capabilities cluster

- `marketplace_service.py` + `nexus/marketplace.py` + `nexus/marketplace_db.py` — Marketplace listings.
- `team_space.py` — Workspace-as-team abstraction.
- `capability_engine.py` — Capability lattice (used by substrate for attenuation).
- `action_registry.py` — Action → handler registry.
- `tool_discovery_service.py` — Tool discovery for the agent runtime.
- `agent_parser.py` + `agent_registry_service.py` — Agent template parsing + runtime registry.

### 15. Governance / HITL / reliability cluster

- `hitl_service.py` — Human-in-the-loop interrupts (paired with `app/orchestration/human_interrupt.py`).
- `reliability_assertions.py` — Per-mission reliability assertions.
- `delegation_service.py` — Permission delegation.
- `brand_voice.py` — Brand voice guardrails for agent outputs.

### 16. A2A (agent-to-agent) cluster

`a2a/a2a_server.py` + `a2a/a2a_agent_wrapper.py` — A2A protocol server. Used for cross-agent calls.

### 17. Sentry cluster

`sentry/sentry_integration.py` + `sentry/sentry_capability.py` + `sentry/sentry_mcp_client.py` + `sentry/fix_recommender.py` — When Sentry fires an alert, this cluster classifies the failure and proposes a fix.

### 18. Domain agents cluster

`domain_agents/` — domain-specialized agent wrappers extending `base_domain_agent.py`. Currently has `biotech/`, `finance/`, `legal/`. These are thin wrappers around a model + system prompt + tool set; the actual agent configuration is loaded from `backend/agent_definitions/<division>/agent.py` (see §4).

### 19. Evaluation cluster

`evaluation/dataset_builder.py` + `evaluation/eval_runner.py` + `evaluation/llm_judge.py` — Build eval datasets, run evals, judge with LLM.

### 20. Billing cluster

`paypal_service.py` + `subscription_service.py` — Subscription lifecycle and PayPal checkout. Wired to `app/models/subscription_models.py` and `partner_revenue_models.py`.

### 21. LangGraph cluster

`langgraph/` — stateful workflow agent. See `langgraph/README.md` for the full design.

- `langgraph/agent.py` — `LangGraphAgent`, the main orchestrator.
- `langgraph/state.py` — `AgentState`, `ToolExecution`, `ConversationMessage`.
- `langgraph/tool_converter.py` — Natural language → structured tool calls.
- `langgraph/approval_workflow.py` — Human approval for unsafe tools.
- `langgraph/persistence.py` — Redis-backed session persistence.
- `langgraph/claude_tools.py` + `langgraph/unified_tool_handler.py` — Tool definitions.
- `langgraph/cost_aware_router.py` — Routing with cost awareness.
- `langgraph/auth.py` + `auth_fastapi.py` — Auth shim.
- `langgraph/tool_handlers/` — `base_handler.py`, `registry.py`, `integration_handler.py`, `comfyui_handler.py`, `n8n_handler.py`.

### 22. LangChain tools cluster

`langchain/tools/` — shared production tool definitions used by `langgraph/agent.py` and `governance/controlflow/agent.py`. Contains `comfyui_agent_tool_prod`, `n8n_agent_tool_prod`, `workflow_catalog_tool_prod`. The legacy `simple_agent.py` and `unified_agent.py` wrappers were removed (2026-07-04) as they had no external consumers.

## Verification

There is no per-cluster test runner — tests live in `backend/app/tests/`. To verify a change in this subtree:

```bash
# Run only the tests for the service you touched
docker compose exec backend pytest app/tests/test_<service_name>.py -v

# Run the mission executor tests (covers §1)
docker compose exec backend pytest app/tests/ -v -k "mission"

# Run the LLM/BYOK regression suite
docker compose exec backend pytest app/tests/test_h1_1_model_router_silent_failure.py \
                                 app/tests/test_chat_service_byok.py \
                                 app/tests/test_integration_byok_streaming.py -v

# Run the substrate tests
docker compose exec backend pytest app/tests/test_substrate_*.py -v

# Run the full suite
docker compose exec backend pytest app/tests/ -v --timeout=30
```

The Dockerfile (stage 3, `FROM runtime AS test`) builds a test image that runs `pytest` by default. Build and run it from homelab:

```bash
docker build --target test -t backend-test /opt/flowmanner/backend/
docker run --rm backend-test
```

Lint + format:

```bash
docker compose exec backend ruff check app/services/
docker compose exec backend ruff format app/services/
```

## Child DOX Index

The subpackages under `services/` that have their own readmes or significant internal structure and may one day need a dedicated child AGENTS.md:

| Path | Existing readme | Notes |
|------|-----------------|-------|
| `langgraph/` | ✅ `README.md` | Self-documenting; promote to `AGENTS.md` when next edited. |
| `substrate/` | ✅ `AGENTS.md` + `H5-1-DESIGN.md` | **Local contract for the unified executor (H5.1, GA).** Read this first when working on workflow execution. |
| `improvement/` | ✅ `IMPLEMENTATION_PROGRESS.md` | Internal ADR; promote to `AGENTS.md` on next phase. |
| `connectors/`, `linear/`, `mcp/`, `webhook_handler/` | ❌ | Shared "external adapters" contract worth a child doc. |
| `substrate/strategies/` | ❌ | New in H5.1; deserves a strategy-writing guide. |
| `runtime/` | ❌ | Self-healing + predictive scaling subsystem. |
| `evaluation/`, `sentry/`, `a2a/`, `domain_agents/` | ❌ | Cross-cutting subsystems that cross multiple clusters. |
| `connectors/` (concrete: per-connector) | ❌ | One child doc per connector (github, linear, slack, etc.) is the right granularity. |

When working in a subpackage for the first time, create a child `AGENTS.md` there following the DOX rules in the root `AGENTS.md` and link it from this index.
