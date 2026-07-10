# Flowmanner Platform Foundation — Engineering Brief for Opus

**Date:** 2026-07-07
**Purpose:** Ground Opus in what ACTUALLY exists (mechanism, not UI) before we write
the "build on the foundation" roadmap. The earlier Opus critique assumed a thin site;
this corrects that. The depth is real and intentional — it is the product.

---

## 0. TL;DR for Opus

Flowmanner is a **multi-agent AI mission platform**, not a landing-page-with-a-chatbox.
The backend is a genuine orchestration engine: 115 tool handlers, a computed 3-gate tool
allowlist, LLM-provider-agnostic routing across 14 providers, a mission planner/executor
with self-improvement, a swarm/consensus subsystem, a RAG layer (Qdrant), a multi-tier
personal + episodic memory system with citation/privacy audit trails, a marketplace of
workflow templates, HITL inbox, eval/critique loop, reliability/chaos tooling, and a
full SSE streaming chat with canvas tiles. The frontend is a real Next.js 15 app with i18n
(5 locales), dnd-kit reorderable nav, and a canvas. **The ONLY genuinely thin layer is the
public shopfront / first-impression (landing + nav branding + the leaked drag handle).
Everything underneath is deep.** So "strip the over-engineering" was the wrong read —
the right move is: keep the engine, finish the front door, and expose the arsenal.

---

## 1. Backend scale (measured)

- **115 tool handler files** (`backend/app/tools/*.py`, excl. `__init__`).
  - Visibility tags actually present: 8 `default_on`, 11 `opt_in`, 3 `hidden`.
  - **93 tools are untagged → fall back to `hidden`** (safety default at
    `chat_service.py:1478`). This is the "93 invisible tools" Opus flagged. It is
    intentional fail-safe, not a bug. Plan: tag the next 10–20 high-value READ tools,
    keep writes hidden. Do NOT flip default to opt_in (Opus's call — agreed).
- **96 service modules** (`backend/app/services/*.py`).
- **63 SQLAlchemy models**, **12 Alembic migrations**.
- **143 API files** under `api/`, ~33 versioned routers under `api/v1/`
  (chat, tools, tool_routing, swarm_protocol, memory, hitl, reliability, marketplace,
  agents, analytics, usage, cost_attribution, circuit_breaker, audit_log, oidc, 2fa,
  sessions, dashboard, search, plugins, episodic_memory, …).
- Subsystems: `orchestration/`, `workers/`, `websocket/`, `governance/`, `observability/`,
  `memory/`, `integrations/`, `cache/`, `sdk/`.

---

## 2. Tool system (the "arsenal")

**Source of truth:** `tools_catalog` Postgres table (`models/tool_catalog_models.py`).
`Tool` has: slug, name, description, category, `tool_type`, `handler_ref` (dotted Python
path resolved at startup), `input_schema`/`output_schema` (JSONB), `auth_policy`,
`visibility`, `enabled`, `version`, `tier`, `timeout_seconds`, `requires_auth`,
`workspace_id` (NULL = global/builtin). `ToolVersion` = immutable version snapshots
(prompt-versioning foundation).

**In-memory `ToolRegistry`** = hydrated projection of that table. `get_tool_registry()`.

### Computed 3-gate allowlist — ADR-001 (`chat_service._get_chat_openai_tools`, line 1430)
The exposed chat tool set = intersection of:
1. **Visibility gate (curation):** `tool.metadata.visibility != "hidden"`.
   - `default_on` = always exposed (core + sandboxd).
   - `opt_in` = exposed when available (read-only tools).
   - `hidden` = never in chat (writes, deferred).
2. **Workspace gate:** `workspace_tool_allowlist` table (Redis-cached, invalidated on PUT
   `/tools`). NULL allowlist = all permitted.
3. **Scope gate (security, enforced at execution):** `tool.metadata.required_scopes`
   checked against resolved user scopes in `_execute_tool_call`. Admin/owner roles bypass;
   missing scopes → `capability denied`; no cached scopes → deny (defense-in-depth).

Key design note: **visibility is curation, `required_scopes` is the security boundary.**
Adding a tool = tag it in-file, NOT edit a central set. (This replaced the old hardcoded
allowlist the original Opus critique complained about — that critique is now STALE.)

`sandboxd_*` tools gated behind `SANDBOXD_ENABLED` feature flag (preview/exec/file_read/
file_write/file_list/serve + browser_sandbox).

---

## 3. LLM provider layer (`services/llm_providers.py`, extracted leaf)

Pure resolution module. Supports **14 providers**: deepseek, zhipuai, llamacpp (self-host
27B), llamacpp_light (qwen2.5-1.5b), openrouter, openai, anthropic, groq, together,
fireworks, deepinfra, xai, google, openai_compatible, + `glennguilloux` (OmniRoute on
ai.glennguilloux.com:9443). Functions: `_normalize_provider`, `_resolve_provider`
→ (base_url, api_key, upstream_model), `_detect_provider_from_key` (BYOK key-prefix
detection across 11 families), `_providers_compatible`. Model IDs are `provider/model`
namespaced. This is why "never recommend OpenAI/Google/Anthropic as primary" holds —
DeepSeek V4 Flash is the default cloud model, llama.cpp is the fallback.

Companion: `services/llm_router.py`, `services/model_router.py` (routing/selection),
`services/llm_executor.py`.

---

## 4. Chat streaming engine (`services/chat_service.py` — 2171 lines)

The orchestrator. Recent Chat-Wiring Sprint (Round 2) extracted pure leaves:
- `services/llm_providers.py` (Phase 0.1) — provider resolution.
- `services/chat_context.py` (Phase 0.2) — `_prune_messages_to_budget` (token budget w/
  summary placeholder) + `_inject_memory_context` (pre-LLM memory injection at index 1,
  citations rendered from SSE metadata, not parsed from text).
- `services/sse_protocol.py` (Phase 0.3) — SSE event-type constants shared by generator
  + frontend `useStreaming`: `token`, `tool_call_start`, `tool_call_result`,
  `canvas_update`, `memory_recall_used`, `memory_citation`, `complete`, `error`,
  `save_failed`, `stream_start`. Plus `_build_canvas_update` (tool→tile mapping; currently
  `browser_sandbox` → opens a browser-sandbox tile).

Other chat primitives:
- `fresh_session()` (`database.py`, Task 2.8) — owns its own transaction (commit/rollback),
  boundary for fire-and-forget writes so they don't hold a txn across LLM stream/tool exec.
- `BackgroundTaskManager` (Task 3.3) — holds strong refs to `asyncio.Task`s, logs
  exceptions, drains on shutdown (replaces GC-risky raw `create_task`).
- `_safe_fire_and_forget` wrapper.

**Known gap (Phase 1.3):** SSE keepalive ping not yet emitted by the backend; Nginx side
is handled manually (`proxy_buffering off` + `proxy_read_timeout 300s`). Opus's Q3 call.

---

## 5. Mission engine (`services/mission_planner.py` 966 lines + `mission_service.py`)

`MissionPlanner`: LLM-generated execution plans → `MissionTask` records, lifecycle
`pending → planning → planned`. Late-bound deps to avoid circular imports. Integrates
`CostTracker`, `ModelRouter`, personal-memory service, log/transition callbacks.

`mission_service.py` = execution. `mission_models.py` has `Mission`, `MissionTask`,
status enums. `mission_program_models.py` = scheduled/cron missions (mirrors
`MissionTrigger.next_fire_at`). This is the "plan, execute, improve" core the landing page
*claims* but does not *show*.

Supporting: `mission_analytics`, `mission_cache`, `mission_code_sandbox`,
`mission_tools`, `mission_errors` (Permanent/Retryable), `run_service` (runs),
`improvement_generator`, `self_improvement`, `self_correction_loop`, `learning_service`,
`feedback_synthesizer`, `critique_service`, `critic`.

---

## 6. Swarm / multi-agent (`services/swarm_service.py` + `models/swarm.py` + `api/v1/swarm_protocol.py`)

`SwarmProfile` (consensus_strategy + consensus_config, daily/monthly limits),
`SwarmAgent`, `SwarmTask`. `create_swarm`, `get_swarm`, `list_swarms`. Consensus strategies
(configurable) + usage caps. This is the "agent orchestration" depth.

Companion agent services: `agent_service`, `agent_registry_service`, `agent_parser`,
`agent_capabilities` (router), `agent_personalities` (router), `delegation_service`,
`team_space`, `cross_workspace_service`.

---

## 7. Memory architecture (multi-tier, with privacy)

- `personal_memory_service.py` — CRUD + recall + forget for `PersonalMemoryClaim`.
- `personal_memory_extractor.py` — extracts claims from conversations.
- `episodic_memory_service.py` + `episodic_memory_worker.py` + `api/v1/episodic_memory.py`
  — episode tracing.
- `memory_action_service.py` — records memory actions for episode tracing.
- `memory_digest_service.py` — daily digest surface.
- `memory_correction_service.py` — **privacy audit trail** (correction/forget requests).
- `memory_extraction_pause_service.py` — per-conversation pause toggle.
- `memory_citation_service.py` — `format_memory_block` (injects recalled memory as a
  system message; citations rendered from SSE `memory_citation` events).
- `chat_context._inject_memory_context` — pre-LLM injection at index 1.

This is a serious, privacy-aware memory subsystem — far beyond "chat with memory."

---

## 8. RAG (`services/rag_service.py`)

`RAGService` over **Qdrant** vector store. Semantic retrieval for missions/agents/tools.
`relevance_score` column exists on chat messages (`migrations/...chat_phase2_multimodel`).
Retrieval is the backbone of "chat with your documents" marketplace template.

---

## 9. Marketplace (`services/marketplace_service.py`)

Seed listings of workflow templates (Lead Enrichment, Cold Email, Chat-with-Docs RAG,
Invoice Extraction, Social Cross-Post, Email Triage, …) across categories (Sales, AI,
Finance, Marketing, Support) with integration tags. `MarketplaceListingModel`. This is the
monetizable surface — currently seed data, not user-generated yet.

Companion: `integration_bridge`, `integration_manifest_service`, `integration_health_service`,
`integration_playground_service`, `integration_usage_service`, `http_integration_executor`,
`tool_discovery_service`, `unified_tool_bridge`, `action_registry`.

---

## 10. Governance / reliability / observability

- `reliability_assertions.py` + `api/v1/reliability.py` — reliability center + chaos toggle.
- `circuit_breaker_service.py` + `api/v1/circuit_breaker.py`.
- `chaos_langfuse.py`, `langfuse_service.py`, `langfuse_metrics.py` — tracing/metrics.
- `cost_tracker.py`, `cost_attribution_service.py`, `usage_service.py`, `budget_enforcer.py`,
  `analytics_service.py`, `dashboard_service.py`.
- `audit_log.py` (router) + `api/middleware/audit.py` — audit trail.
- `hitl_service.py` + `api/v1/hitl.py` — human-in-the-loop inbox.
- `permission_service`, `auth_service`/`auth_v3_service`, `oidc_service`, `totp_service`,
  `two_fa` (router), `auth_rate_limiter`, `account_lockout`, `auth_constants` (ADMIN_ROLES).
- `event_bus.py`, `event_bus_consumers.py`, `event_router.py` — internal eventing.
- `sse_service.py`, `sse_buffer.py` — SSE infra (buffer is the Phase 1.3 Redis buffer target).
- `capability_engine.py`, `depth_policy.py`, `recovery_policy.py`, `brand_voice.py`.

---

## 11. Frontend (`FlowmannerV2-frontend`, Next.js 15, app router)

- 5 locales (en/fr/de/es/ja) via next-intl.
- `floating-nav.tsx` — dnd-kit reorderable nav (NOW gated behind an `editMode` toggle as of
  this session; grip handles hidden by default, pencil toggle reveals them). Persists order
  in localStorage (`floating-nav-*-order`).
- Canvas with tile system (`canvas_update` SSE → tile opens).
- `useStreaming` hook consumes the SSE event taxonomy from `sse_protocol.py`.
- i18n metadata: `layout.tsx` title template (FIXED this session — was doubling
  "— FlowManner"; now `%s`).
- Decorative chrome Opus flagged (MatrixRain, TopographicBackground, 3-column/zen/LaunchPad)
  is real but SHOULD be defaulted to a focused two-pane + progressive-reveal (Opus Q3).

---

## 12. What is genuinely thin (the only real gap)

1. **Public shopfront / first impression:** landing page undersells the engine; nav had a
   leaked debug drag handle (FIXED this session, gated behind edit mode); brand name was
   inconsistent ("AI Workflow Consulting" vs "AI Mission Platform") + doubled title
   (FIXED this session).
2. **Tool reachability:** 93 untagged tools invisible by design. Need to tag 10–20
   high-value read tools (Phase 1.2).
3. **SSE keepalive** (Phase 1.3) — backend ping missing.
4. **Chat UI default** (Phase 1.4) — simplify to two-pane, progressive-reveal chrome.

Everything in §2–§10 is DEEP and WORKING. The foundation is built. We build ON it now.

---

## 13. Open architecture decisions (from prior Opus round, still standing)

- Tag the exposed batch, NOT all 117. (Q2)
- `BackgroundTaskManager` now + Celery for extraction. (decided)
- Keepalive + manual Nginx. (decided)
- Prompt-to-switch over auto-route. (decided)
- Dual-write: BLOCKED on `docs/DUAL-WRITE-DECISION.md` (still the only genuinely open item).
- Virtualization amendment: confirmed.

## 14. The through-line for the next roadmap

The wiring sprint fixed the *mechanism*. Phase 1 pivots to **perception + reach**, not
plumbing. Then Phase 2+ builds ON the foundation: expose missions/swarm/marketplace through
the shopfront, surface the arsenal in chat, and make the first 30 seconds match the depth
that's already there.
