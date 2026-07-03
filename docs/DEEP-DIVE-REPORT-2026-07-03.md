# FlowManner Deep Dive Report — July 3, 2026

---

## Executive Summary

**1. The substrate is GA but the cleanup is unfinished.** `UnifiedExecutor` is the sole execution path (Phase 8.1 GA confirmed in `test_event_sourced_state.py`). The 7 old executors still sit in the tree and are still imported by 6 v1 routers (`flow_compat.py`, `graph.py`, `swarm.py`, `swarm_protocol.py`, `orchestration.py`, `mission_decomposition_routes.py`). This is the single biggest source of architectural confusion. **Delete the old executors and migrate the 6 routers to substrate strategies.** Effort: L. Impact: High. Risk if not done: High (two execution paths diverge over time).

**2. The frontend ↔ backend gap is the biggest product opportunity.** ~70 of ~139 backend endpoint modules have zero frontend. The three features in `.sisyphus/plans/frontend-wiring-roadmap.md` (Reliability Center, Tool Routing Inspector, Plugin Manager) require zero new API work — just build the UI. The data-fetching strategy is fragmented (59 files use `apiClient`, 58 use raw `fetch`, 12 use React Query, 5 use SWR). **Pick one fetching strategy, build the 3 wired features, then prioritize the next 5–7 highest-value unwired endpoints.** Effort: M per feature. Impact: High. Risk if not done: Medium (the platform looks hollow).

**3. The improvement loop and LLM-as-judge bypass the substrate's own rules.** `llm_judge.py` and `eval_runner.py` call `httpx.AsyncClient` directly to hit the LLM API, violating the substrate guarantee that all LLM calls go through `BudgetEnforcer.call()`. The improvement loop's `STRATEGY_MAP` in `causal_decomposer.py` references cloud models (`gpt-4`, `claude-3-opus`, `gpt-3.5-turbo`) in knob values — these can never execute on a self-hosted llama.cpp setup. **Fix the LLM call path and replace cloud model references with local model identifiers.** Effort: S. Impact: Medium. Risk if not done: Medium (silent failures, wrong recommendations).

**4. The `/inbox` auth gap is real and may have siblings.** Confirmed: `/inbox` is not in `middleware.ts`'s protected paths. The inbox page is publicly accessible. The middleware protects `/dashboard`, `/chat`, `/settings`, `/admin` but uses a hardcoded path list — any new page added without updating the list is automatically unprotected. **Fix the `/inbox` gap and switch to an opt-out model (protect everything except explicit public routes).** Effort: S. Impact: High. Risk if not done: High (security vulnerability).

**5. Dependency pins are creating a ticking clock.** LangChain 0.1.20 and langgraph 0.0.40 are ancient. The `langchain/` subpackage is legacy and the `langgraph/` strategy has been substrate-ified. **Delete the `langchain/` legacy wrappers, upgrade langgraph to current, and remove the langgraph 0.0.40 pin.** Effort: M. Impact: Medium. Risk if not done: Medium (increasingly difficult to upgrade, security patches stop).

---

## Section A: Architecture

### What exists

**v1/v2/v3 API split:** v1 (104 modules, legacy, no envelope, forward-compatible forever), v2 (27 modules, standardized `{data, meta, error}` envelope, CQRS for missions + blueprints), v3 (12 modules, auth/workspace specialty, cookie+Bearer). v1 mission routes carry deprecation headers (`Sunset: 2026-09-01`). GraphQL was removed 2026-07-09.

**Substrate (H5.1 GA):** `UnifiedExecutor` (`executor.py`) is the sole execution entry point. 7 strategies in `strategies/`: `SoloStrategy`, `DAGStrategy`, `GraphStrategy`, `SwarmStrategy`, `PipelineStrategy`, `MetaStrategy`, `LangGraphStrategy`. 4 guarantees enforced: durable (append-only `substrate_events` table with DB-level BEFORE-UPDATE-OR-DELETE trigger), type-checked (Pydantic), capability-bounded (`CapabilityToken`), bounded (`BudgetEnforcer.call()`). Event log → replay engine → assertion engine → baseline extractor form the regression-testing loop.

**CQRS:** Mission routes fully delegated (14 commands + 14 queries in `_mission_cqrs/`). Blueprint + Run routes use `_blueprint_cqrs/`. The v1 `mission.py` router is a thin DI shell — the reference implementation.

**Dual-write (Mission → Blueprint/Run):** Active. `dual_write_sync_run_status` and `dual_write_sync_blueprint` in `compat.py` fire-and-forget. `reconcile_dual_write.py` script exists for reconciliation. Prometheus counter `dual_write_failures_total` tracks failures. Tests cover failure logging (B4), deterministic IDs (B6), retry behavior, and run-with-retry scenarios.

### What's wrong

1. **7 old executors still in the tree.** `mission_executor.py` (1,387 LOC), `dag_executor.py` (179 LOC), `graph_executor.py` (293 LOC), `swarm/orchestrator.py` (331 LOC), `swarm_pipeline/orchestrator.py` (~1,700 LOC), `nexus/meta_loop_orchestrator.py` (225 LOC), `langgraph/agent.py` (~900 LOC). Still imported by: `decomposition_service.py` (imports `dag_executor`), `graph_node_handlers.py` (imports `GraphInterpreter`), `graph_service.py` (imports `GraphInterpreter`), `flow_compat.py` (imports `GraphInterpreter`), `plugins.py` (imports `ExecutionContext` from `graph_executor`). The substrate AGENTS.md says "before deleting, confirm `FLOWMANNER_UNIFIED_EXECUTOR=all` has been on for ≥2 weeks" — but `test_event_sourced_state.py` confirms the flag was already removed and UnifiedExecutor is always used. The old executors are dead code that's still imported.

2. **6 v1 routers inline old executor logic.** Per the v1 AGENTS.md audit: `mission_decomposition_routes.py` (uses `dag_executor`), `flow_compat.py` (uses `GraphInterpreter`), `graph.py` (uses `graph_executor`), `swarm.py` (uses `SwarmOrchestrator`), `swarm_protocol.py` (uses debate/escalation/handoff protocols), `orchestration.py` (uses nexus orchestrator). These routes bypass the substrate entirely — no event log, no budget enforcement, no capability tokens.

3. **CQRS is only applied to 2 domains.** Missions and blueprints have CQRS. The other ~70 v1 CRUD routers are raw service calls. The v1 AGENTS.md says these "don't need executor migration" but they also don't have the v2 envelope, idempotency, or rate limiting. The migration path is unclear — there's no v2 router for most domains.

4. **Dual-write is accumulating complexity.** The dual-write has 5 sites (create, execute, update, delete, abort), each fire-and-forget. There are 4+ dedicated scripts (`reconcile_dual_write.py`, `exercise_dual_write.py`, `backfill_blueprints_runs.py`, `prove_dual_write_complete.py`). The `compat.py` module has retry logic with ERROR-level logging on final failure. This is a transition pattern — the question is when it ends and Mission is fully replaced by Blueprint+Run.

5. **LangChain 0.1.20 and langgraph 0.0.40 are ancient pins.** The `langchain/` subpackage (`simple_agent.py`, `unified_agent.py`) is explicitly marked "legacy" in the services AGENTS.md. The `langgraph/` subpackage has been substrate-ified via `strategies/langgraph.py`. Yet the old `langgraph/agent.py` (~900 LOC) still exists and is still imported. The pinned versions make it impossible to use current langgraph features (checkpointing, human-in-the-loop primitives, subgraphs).

### Concrete recommendations

| # | Recommendation | Effort | Impact | Risk if NOT done |
|---|---|---|---|---|
| A1 | **Delete the 7 old executors.** Remove `mission_executor.py`, `dag_executor.py`, `graph_executor.py`, `swarm/orchestrator.py`, `swarm_pipeline/orchestrator.py`, `nexus/meta_loop_orchestrator.py`. Update the 5 files that import them to use substrate equivalents. Run `test_event_sourced_state.py` + chaos suite to verify. | L | High | High — two execution paths diverge |
| A2 | **Migrate the 6 v1 routers off inline executor logic.** Follow the priority queue in v1 AGENTS.md: `mission_advanced_routes.py` → `mission_decomposition_routes.py` → `flow_compat.py` + `graph.py` → `swarm.py` + `swarm_protocol.py` → `orchestration.py`. | L | High | Medium — these routes have no durability |
| A3 | **Delete the `langchain/` legacy subpackage.** Mark it deprecated, verify no production code imports it (only `simple_agent.py` and `unified_agent.py`), then remove. | S | Medium | Low — it's already marked legacy |
| A4 | **Upgrade langgraph to current (0.2+).** The substrate `LangGraphStrategy` wraps the old `langgraph/agent.py`. Upgrading enables native checkpointing and HITL primitives. Test with `test_langgraph_strategy.py`. | M | Medium | Medium — security patches, feature gap |
| A5 | **Set a timeline for ending the dual-write.** Either commit to Blueprint+Run as the canonical model (and make Mission a view) or keep Mission as canonical (and make Blueprint+Run optional). The current "both are canonical" state adds complexity to every mission operation. | M | High | Medium — perpetual sync overhead |

### Risks and trade-offs

- Deleting old executors risks breaking the 6 v1 routers that import them. Mitigation: migrate routers first (A2), then delete (A1).
- Ending dual-write requires a cutover that could lose data if not tested. Mitigation: the `reconcile_dual_write.py` script + `exercise_dual_write.py` already exist for verification.
- Upgrading langgraph could break the `LangGraphStrategy` adapter. Mitigation: the strategy is thin (wraps the agent), so the adapter surface is small.

---

## Section B: Frontend ↔ Backend Gap

### What exists

- **114 pages** (`page.tsx`), **272 components**, 487 TSX + 403 TS files
- **230 SDK generated files** (TypeScript + Python), but only **113 unique files** make API calls
- **Data fetching mix:** 59 files use `apiClient` (from `@/lib/api-client.ts`), 58 use raw `fetch()`, 12 use React Query (`@tanstack/react-query` v5), 5 use SWR
- **i18n:** 5 locales (de, en, es, fr, ja) via `next-intl` v4.12
- **19 E2E test files** in `e2e/` (Playwright v1.60) — but the prompt says "zero Playwright tests"; the 19 files exist but coverage of the 114 pages is thin
- **72 unit/component test files** (Vitest v4.1)
- Frontend stack: Next.js 16.2.6, React 19.2.4, Tailwind v3.4, Radix UI + shadcn v4.11

### What's wrong

1. **Data fetching is fragmented across 4 strategies.** `apiClient` (59 files) and raw `fetch()` (58 files) are tied. React Query (12 files) and SWR (5 files) are minority patterns. This means: no consistent caching strategy, no consistent error handling, no consistent loading states, and the SDK generated files (230 of them) are underused. The `apiClient` approach auto-injects JWT from NextAuth session — raw `fetch()` calls don't get this for free.

2. **~70 backend endpoint modules have zero frontend.** The frontend-wiring-roadmap identifies 3 Tier 1 features (Reliability Center, Tool Routing Inspector, Plugin Manager) that need zero new API work. Beyond those, the highest-value unwired endpoints likely include: HITL governance inbox (exists as a page but not wired), evaluation runner (LLM-as-judge), regression/baseline comparison, integration action execution, workspace team management, and analytics dashboards.

3. **The extensions page is a dead path.** `/extensions` exists but makes zero API calls. The backend `plugins.py` (853 lines) has full CRUD + health monitoring + test execution. The roadmap recommends replacing the static extensions page with a live plugin manager.

4. **i18n sustainability is questionable.** 5 locales × every new feature = 5 translation files to update. The roadmap specifies "i18n keys under namespace in all 5 locales" for each feature. For a 1-person team, this is a tax on every UI change. The question is whether German, French, Spanish, and Japanese are actually used by real users.

5. **E2E coverage is thin.** 19 E2E test files for 114 pages = ~17% page coverage. And the Playwright config exists but the tests may not be running in CI (the `test-e2e` Makefile target exists but no GitHub Actions workflow runs it).

6. **SDK generation pipeline produces dead code.** 230 generated SDK files, 113 files make API calls. That's ~50% utilization. The generated SDK is a flat service-per-endpoint pattern — it's not ergonomic enough to replace `apiClient` for most developers.

### Concrete recommendations

| # | Recommendation | Effort | Impact | Risk if NOT done |
|---|---|---|---|---|
| B1 | **Standardize on React Query + apiClient.** Migrate the 58 raw `fetch()` calls to use `apiClient` (for auth token injection) wrapped in React Query (for caching/loading/error states). Drop SWR (5 files — small migration). | M | High | Medium — inconsistent auth, no caching |
| B2 | **Build the 3 Tier 1 features from the wiring roadmap.** Reliability Center (~½ day), Tool Routing Inspector (~1 day), Plugin Manager (~1.5 days). Zero new API needed. Follow the patterns in the roadmap doc. | M | High | Low — missed opportunity |
| B3 | **Fix the `/inbox` page wiring.** The HITL inbox page exists but isn't wired to the backend. The backend `hitl.py` router has the endpoints. This is a security-adjacent feature (human approval workflows) that should be visible. | S | High | Medium — HITL is invisible to users |
| B4 | **Audit i18n usage.** Check if non-English locales have real users. If not, drop to English-only and remove the i18n tax. If yes, invest in a translation pipeline (e.g., LLM-assisted translation with human review). | S | Medium | Low — ongoing maintenance tax |
| B5 | **Add E2E tests for critical paths.** Login → dashboard, create mission → execute → view results, chat → tool calling. 3–5 Playwright tests covering the core user journey. Run them in CI. | S | Medium | Medium — regressions slip through |

### Risks and trade-offs

- Migrating 58 `fetch()` calls to React Query is tedious but low-risk. Each migration is mechanical.
- Dropping locales could alienate early international users. But if there are no real users in those locales, the maintenance cost is pure waste.
- The SDK generation pipeline is valuable for the Python SDK (published to TestPyPI). The TypeScript SDK is less valuable since the frontend uses `apiClient` directly.

---

## Section C: AI/LLM Pipeline & Agent Quality

### What exists

**Agent execution loop:** `SoloStrategy` (replaces `mission_executor.py`) handles single-agent task loops with LLM tool-calling. `NodeExecutor` handles per-node dispatch: LLM, tool, code, RAG, web search, file, browser, sandbox, HITL, sub-workflow. All LLM calls go through `BudgetEnforcer.call()` (substrate guarantee #4). All tool calls require `CapabilityToken` (guarantee #3).

**7 strategies:** solo, dag, graph, swarm, pipeline, meta, langgraph. Each implements `ExecutionStrategy` ABC from `strategies/base.py`. The substrate AGENTS.md documents that "the deletion is the value" — when a strategy grows past its target LOC, extract to the base.

**RAG pipeline:** `rag_service.py` delegates to `rag/` subpackage: `chunking_service`, `embedding_service`, `prompt_synthesizer`, `retrieval_service`, `vector_store`. SearXNG sidecar for live web search. Multi-provider reranking in `web_search/`.

**Memory flywheel:** `memory_service.py` (conversation + episodic memory, Postgres + Qdrant). `memory_bridge/memory_bridge.py` connects to RAG for knowledge sharing. `inject_context()` pulls memory context into agent prompts. `episodic_memory_worker.py` (Celery) consolidates short-term → long-term.

**Improvement loop (Phases 1–6):** 10,570-line subsystem. `causal_decomposer.py` maps 14 failure types to constrained intervention strategies (knobs, not code). `hypothesis_tester.py` runs A/B/before-after/canary tests with safety constraints and auto-rollback. `improvement_loop_v2.py` orchestrates: failure telemetry → causal decomposition → hypothesis testing → improvement application. `ImprovementKnowledge` tracks strategy effectiveness.

**Plan selection:** `plan_scorer.py` scores candidates deterministically (<10ms, no LLM). `plan_selector.py` picks winner by policy (min_cost, max_quality, balanced, auto).

**LLM-as-judge:** `llm_judge.py` — rubric-based scoring (accuracy, completeness, relevance, safety; 1–5 scale). `eval_runner.py` — runs golden datasets against models, scores with LLM judge, records Prometheus metrics, pushes to Langfuse.

**Domain agents:** 3 agents (biotech, finance, legal) extending `BaseDomainAgent`. Each has system prompts, tool schemas, and `process_response()`. LLM calls go through `BudgetEnforcer.call()`.

### What's wrong

1. **`llm_judge.py` and `eval_runner.py` bypass `BudgetEnforcer`.** Both use `httpx.AsyncClient` directly to call the LLM API:
   ```python
   # llm_judge.py line ~80
   async with httpx.AsyncClient(timeout=60.0) as client:
       resp = await client.post(f"{self.api_base}/chat/completions", ...)
   ```
   This violates substrate guarantee #4 ("all LLM calls go through `BudgetEnforcer.call()`"). These calls are untracked, unbounded, and bypass the circuit breaker. The `eval_runner.py` also uses `settings.LLM_API_KEY` directly instead of the BYOK resolution path.

2. **The improvement loop's `STRATEGY_MAP` references cloud models.** In `causal_decomposer.py`, the `SWITCH_TO_CAPABLE_MODEL` strategies have knob values like `{"model": "gpt-4"}`, `{"model": "claude-3-opus"}`, `{"model": "gpt-3.5-turbo"}`, `{"model": "gpt-4-32k"}`. These models don't exist in the self-hosted setup. When the improvement loop tries to apply these strategies, the model routing will fail silently (or fall back to the local model, making the "switch" a no-op). This is AI-for-AI's-sake — the system recommends improvements it can't execute.

3. **The 7 strategies may be over-engineered for a 27B model.** The substrate AGENTS.md notes "agent protocols with more than 3 phases confuse [the 27B model]." The `PipelineStrategy` has 7 phases. The `SwarmStrategy` has debate/escalation/handoff protocols. The `MetaStrategy` does recursive self-improvement. For a 27B model, `solo` and `dag` are likely the only strategies that work well. The others may produce degraded output or consume excessive context.

4. **The memory bridge uses in-memory storage.** `MemoryBridge.share_memory()` accesses `self.memory_service._memories.get(memory_id)` — this is an in-memory dict, not a DB lookup. If `MemoryService` is backed by Postgres+Qdrant, this attribute may not exist or may be stale. The memory bridge's sharing mechanism is likely broken in production.

5. **Plan selection's cost model doesn't match a free local LLM.** `plan_scorer.py` penalizes `estimated_cost_usd` — but with a self-hosted llama.cpp, the cost is ~$0. The scorer's cost penalty (−0.30 max) is essentially a no-op. The real cost is VRAM time and context window consumption. The scorer should use estimated token count and latency instead of dollar cost.

6. **Domain agents define tools that aren't implemented.** Each domain agent (`biotech/agent.py`, `finance/agent.py`, `legal/agent.py`) defines tool schemas (e.g., `trial_designer`, `financial_analyzer`, `contract_analyzer`) but these tools have no implementations — they're just parameter dictionaries. The agent's `run()` method calls `BudgetEnforcer.call()` with the system prompt but never dispatches to tools. These are prompt-only agents wearing tool costumes.

7. **The replay assertion engine is untested in production.** The `ReplayAssertionEngine` and `BaselineExtractor` are implemented and have unit tests, but there's no evidence they're running against real mission executions. The v2 `/regression` endpoints exist but have no frontend. This is a "built but not used" feature.

### Concrete recommendations

| # | Recommendation | Effort | Impact | Risk if NOT done |
|---|---|---|---|---|
| C1 | **Route LLM judge + eval runner through BudgetEnforcer.** Replace `httpx.AsyncClient` calls in `llm_judge.py` and `eval_runner.py` with `BudgetEnforcer.call()`. This adds cost tracking, circuit breaking, and budget enforcement to eval runs. | S | Medium | Medium — unbounded LLM calls |
| C2 | **Replace cloud model references in STRATEGY_MAP.** In `causal_decomposer.py`, replace `gpt-4`/`claude-3-opus`/`gpt-3.5-turbo` with local model identifiers from `config/llm-models.yaml` (e.g., `qwen3.6-27b-mtp`, `ornith-1.0-35b`, `qwopus3.6-35b-a3b-coder-mtp`). | S | Medium | Medium — silent strategy failures |
| C3 | **Profile which strategies work with the 27B model.** Run 5 missions per strategy type with identical prompts. Measure: success rate, token usage, latency, output quality (via LLM judge). Publish results. Cut or downgrade strategies that degrade. | M | High | Medium — user-facing quality issues |
| C4 | **Fix the memory bridge's share_memory().** Replace `self.memory_service._memories.get(memory_id)` with a proper DB lookup. Or remove the sharing feature if it's not used in production. | S | Low | Low — feature is likely broken already |
| C5 | **Replace plan_scorer's dollar-cost with token/latency cost.** Change `estimated_cost_usd` to `estimated_tokens` + `estimated_latency_ms`. Adjust the scoring weights accordingly. | S | Medium | Low — cost selection is a no-op |
| C6 | **Implement or remove domain agent tools.** Either wire the tool schemas to actual tool implementations in `app/tools/`, or remove the tool definitions and make the agents prompt-only (honest about what they are). | S | Low | Low — misleading UI/metadata |

### Risks and trade-offs

- Profiling strategies (C3) could reveal that 4 of 7 strategies don't work well with the 27B model. That's valuable information — better to know than to guess. The strategies can remain in the codebase as "available for larger models" but default to `solo` for the current hardware.
- Routing eval through BudgetEnforcer (C1) adds overhead to eval runs. But eval runs should be tracked like any other LLM call.
- The improvement loop is a 10,570-line subsystem that may be generating more noise than signal. The hypothesis tester's p-value calculation is hardcoded (`0.05 if is_significant else 0.3`) — this is not real statistics. Consider whether the full 6-phase improvement loop is worth maintaining for a 1-person team.

---

## Section D: Performance & Scalability

### What exists

- **Async-first:** SQLAlchemy 2.0 async (`AsyncSession`) throughout services. Uvicorn + FastAPI async event loop.
- **Redis caching:** Used for rate limiting (`auth_rate_limiter.py`), mission caching (`mission_cache.py`), langgraph persistence (`langgraph/persistence.py`), web search cache (`web_search/cache`), RAG embedding cache (`rag/embedding_service.py`), in-process cache (`cache/inprocess.py` for feature flags, agent templates, configuration), workflow cache (`cache/workflow_cache.py`).
- **PostgreSQL 15:** 62 ORM models, 120 Alembic migrations, 38 `Index()` definitions across models. Named volumes for persistence.
- **Celery:** 4 concurrency workers, 100 max-tasks-per-child. Beat schedule: HITL expiry (every 5 min), integration health check (every 15 min). `LeaseReclaimer` started on worker_ready signal.
- **WebSocket:** Socket.IO via `websocket/mission_ws.py` + `websocket/presence.py`. JWT-authenticated. Falls back to SSE (`/api/v1/missions/{id}/stream`).
- **Docker:** No volume mounts on backend container (code baked into image). Memory limits set per service (backend: 4g, postgres: 2g, celery-worker: 2g, redis: 512m).
- **WireGuard:** VPS → homelab tunnel for API proxy. Watchdog script deployed (`wg-watchdog.sh`).

### What's wrong

1. **120 Alembic migrations is a lot.** Each migration adds up + down paths. The migration chain is linear (no branches detected). Compaction (squashing early migrations into a baseline) would reduce startup time and simplify the chain. But it's risky — once compacted, you can't downgrade past the squash point.

2. **Redis caching is broad but unmeasured.** Redis is used in 6+ subsystems but there's no evidence of cache hit rate monitoring. The `inprocess.py` cache (in-process, TTL-based) duplicates some Redis concerns (feature flags, agent templates). The split between in-process and Redis caching is not clearly documented.

3. **WebSocket through WireGuard is a potential latency bottleneck.** The VPS proxies `/ws` through WireGuard to the homelab. Socket.IO's long-polling fallback adds latency. The presence system (`presence.py`) broadcasts via Redis pubsub — if the WebSocket connection drops, presence state may become stale.

4. **No k6 load test files found in the backend.** The CI has a `load-test.yml` workflow, but no actual k6 test scripts were found in the backend directory. The load testing may be defined in the CI workflow itself or in a different location. Either way, load testing is not part of the local development workflow.

5. **Docker image bake with no volume mounts is correct for production but painful for development.** Every code change requires a 2-minute rebuild. The `Dockerfile.dev` with volume mounts exists, and `make dev-up` starts a standalone dev environment, but the primary dev workflow still goes through the production compose. The `dev` Makefile target uses `docker-compose.dev.yml` which overlays the production compose — but the backend still has no volume mount in production compose.

6. **38 indexes across 62 models may be insufficient.** That's ~0.6 indexes per model. For a 237K LOC backend with 104 API modules, many query patterns likely lack index coverage. Common missing indexes: foreign key columns (PostgreSQL doesn't auto-index FKs), composite indexes for common filter combinations, partial indexes for soft-delete queries.

### Concrete recommendations

| # | Recommendation | Effort | Impact | Risk if NOT done |
|---|---|---|---|---|
| D1 | **Add cache hit rate monitoring.** Instrument Redis cache gets/sets/misses with Prometheus counters. Add a dashboard panel. Identify which caches have low hit rates and tune TTLs. | S | Medium | Low — suboptimal performance |
| D2 | **Audit database indexes.** Run `EXPLAIN ANALYZE` on the top 20 most-used queries (mission list, chat threads, dashboard stats, analytics rollups). Add missing indexes. | M | Medium | Medium — slow queries at scale |
| D3 | **Write 3–5 k6 load test scripts.** Cover: mission create+execute, chat streaming, dashboard load. Run locally before deploy, not just in CI. | S | Medium | Medium — unknown performance ceiling |
| D4 | **Squash the first 80 Alembic migrations into a baseline.** Keep the last 40 for downgrade capability. This reduces migration chain complexity. | S | Low | Low — mostly cosmetic |
| D5 | **Consolidate in-process + Redis caching.** Document which data goes where. Rule of thumb: per-request data = in-process, cross-request data = Redis. Remove duplication. | S | Low | Low — confusion, double-caching |

### Risks and trade-offs

- Squashing migrations is irreversible (can't downgrade past the squash point). Mitigation: only squash the oldest 80, keep recent 40 intact. Nobody downgrades 80 migrations anyway.
- Adding indexes locks the table during creation (in PostgreSQL < 12). PostgreSQL 15 supports `CREATE INDEX CONCURRENTLY` — use it.
- WebSocket latency through WireGuard may be unavoidable given the 2-machine architecture. The alternative (running the backend on the VPS) would require moving all data stores, which is a larger change.

---

## Section E: Security & Reliability

### What exists

- **Auth:** JWT (PyJWT 2.8) + refresh tokens, 2FA (TOTP via pyotp), OIDC SSO, account lockout after failed attempts, session management (v3).
- **Rate limiting:** `GlobalRateLimitMiddleware` (IP-based) + per-user `rate_limit()` (Redis sliding window) + tier-aware `tier_rate_limit()` (free/starter/pro/business/enterprise multipliers). Headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.
- **Webhook signatures:** All 21 webhook endpoints verify signatures. Verifiers in `webhook_handler/signature.py`: HMAC-SHA256, SHA1, Stripe (timestamped), Slack, Twilio, Shopify. Each webhook router has its own verify function (github, gitlab, slack, stripe, twilio, shopify, asana, clickup, airtable, datadog, figma, hubspot, intercom, jira, monday, pagerduty, sentry, vercel, zendesk, confluence, linear).
- **BYOK encryption:** Fernet symmetric encryption (`cryptography.fernet`). Key derived via `PBKDF2HMAC` (SHA256, 100,000 iterations) from `ENCRYPTION_KEY` or `SECRET_KEY`. Hardcoded salt: `flowmanner-salt-`.
- **RBAC:** `permission_service.py` — role-based + custom roles + delegations.
- **PII redaction:** `pii_redactor.py` for logs and tool outputs.
- **Audit:** `audit.py` middleware logs auth events. `_mission_cqrs.audit.AuditService` for mission mutations.
- **Circuit breaker:** Per-mission (Phase 6.4). Checked before LLM and tool calls. Updated after each call.
- **Sentry:** Integrated with DNS validation (recently fixed to prevent urllib3 log spam).
- **WireGuard watchdog:** Auto-restarts on stale handshake.

### What's wrong

1. **🚨 `/inbox` is publicly accessible.** Confirmed: `/inbox` is NOT in the middleware's protected paths list. The middleware protects `/dashboard`, `/chat`, `/settings`, `/admin` but `/inbox` is missing. The HITL inbox contains human approval workflows — potentially sensitive mission data. This was flagged in a commit message (`501c821`) but the diff was empty (the fix was never applied).

2. **The middleware uses an opt-in protection model.** Routes must be explicitly added to the protected paths list. Any new page created without updating the list is automatically unprotected. This is a systemic vulnerability — the `/inbox` gap is a symptom, not a one-off.

3. **BYOK encryption uses a hardcoded salt.** `flowmanner-salt-` in `encryption.py`. PBKDF2 with a hardcoded salt means an attacker who knows the codebase can precompute rainbow tables for common API keys. The salt should be random per-key (stored alongside the ciphertext) or at minimum per-deployment.

4. **Sentry is not integrated in `main_fastapi.py` or `app/core/`.** The grep found no Sentry imports in these files. The Sentry integration may be in a different location (e.g., a separate initialization script or the Docker entrypoint). If Sentry isn't actually initializing, errors are going unreported.

5. **21 webhook endpoints each implement their own signature verification.** While `webhook_handler/signature.py` has shared verifiers, each webhook router (`github_webhook.py`, `slack_webhook.py`, etc.) has its own verify function with its own error handling. Inconsistency risk: one webhook might use `hmac.compare_digest` (constant-time) while another uses `==` (timing-attack vulnerable). The Sentry webhook explicitly notes "Sentry webhooks do NOT include HMAC signatures by default" — this means the Sentry webhook may accept unsigned payloads.

6. **Secret management is `.env` files.** The `.env` file contains `REDIS_PASSWORD`, `JWT_SECRET_KEY`, `ENCRYPTION_KEY`, etc. For a homelab this is acceptable, but there's no secret rotation strategy and the `.env` is committed to Docker via `env_file: .env` in docker-compose.yml.

7. **The circuit breaker is per-mission, not per-strategy or per-provider.** If the LLM provider goes down, every mission using that provider will independently trip its circuit breaker — there's no shared state. A per-provider breaker would propagate failure faster and reduce wasted calls.

### Concrete recommendations

| # | Recommendation | Effort | Impact | Risk if NOT done |
|---|---|---|---|---|
| E1 | **🚨 Fix `/inbox` auth gap immediately.** Add `/inbox` to the middleware protected paths list. One line change. | S | High | High — security vulnerability |
| E2 | **Switch middleware to opt-out model.** Protect all routes except an explicit public list (`/`, `/login`, `/register`, `/api/auth/*`). This prevents future gaps. | S | High | High — systemic vulnerability |
| E3 | **Randomize BYOK encryption salt.** Generate a random salt per key, store it alongside the ciphertext. Keep PBKDF2 iterations at 100k+. | S | Medium | Medium — weakened encryption |
| E4 | **Verify Sentry is actually initializing.** Check the Docker entrypoint or startup script. If not, add `sentry_sdk.init()` to `main_fastapi.py` with the DNS validation check. | S | Medium | Medium — silent errors |
| E5 | **Audit all 21 webhook verifiers for constant-time comparison.** Ensure every verifier uses `hmac.compare_digest()`. The Sentry webhook should require a shared secret or reject unsigned payloads in production. | S | Medium | Medium — timing attacks |
| E6 | **Add a per-provider circuit breaker.** Share circuit breaker state across missions using the same LLM provider. Redis-backed. | M | Medium | Low — wasted calls on provider outage |

### Risks and trade-offs

- Switching to opt-out middleware could break public pages if the public list is incomplete. Mitigation: audit all current public routes before switching.
- Randomizing the salt requires a migration (re-encrypting all stored BYOK keys). Mitigation: decrypt with old salt, re-encrypt with new random salt, store salt prefix.
- Per-provider circuit breaker adds Redis dependency to the LLM call path. Mitigation: fall back to per-mission breaker if Redis is unavailable.

---

## Section F: Developer Experience & Operations

### What exists

- **Deploy scripts:** `deploy-frontend.sh` (159 lines, ~4 min: rsync + docker build + restart + health checks), `deploy-backend.sh` (508 lines, ~2 min: backup + build + restart + health checks + auto-rollback), `deploy-all.sh` (320 lines).
- **CI:** 6 GitHub Actions workflows: `ci.yml`, `cli.yml`, `deploy.yml`, `load-test.yml`, `pr-check.yml`, `publish-sdk-testpypi.yml`.
- **Makefile:** ~30 targets: dev (homelab + standalone), test (backend + frontend + e2e), deploy (backend + frontend + all), database (migrate, upgrade, downgrade, backup, seed), Docker (build, ps, logs, restart), SDK (generate-ts, generate-python, check-sdk), utilities (clean, lint, format, health, shells).
- **AGENTS.md system:** Nested per-directory: root → `AGENTS.homelab.md` / `AGENTS.vps.md` / `AGENTS.ops.md` → `backend/AGENTS.md` → `backend/app/services/AGENTS.md` → `backend/app/services/substrate/AGENTS.md` → `backend/app/api/v1/AGENTS.md` → `backend/app/api/v2/AGENTS.md`. Detailed, well-maintained.
- **.sisyphus/ system:** Session continuity via plans, analysis, notepads, exit-audits. `boulder.json` tracks state. `SESSION-RITUAL.md` defines end-of-session process.
- **Observability:** structlog (structured logging, f-string ban enforced by ruff G003/G004), Jaeger (OpenTelemetry tracing), prometheus-client (metrics), Sentry (error tracking), Langfuse (LLM tracing + chaos testing). `cost_engine.py` for cost attribution. `intervention_distance.py` for autonomy measurement.
- **Pre-commit:** ruff (lint + format), mypy (scoped to `backend/app/`).

### What's wrong

1. **Deploy times are acceptable but not great.** 4 minutes for frontend, 2 minutes for backend. The backend deploy has auto-rollback which is excellent. The frontend deploy could be faster with Docker layer caching (currently rebuilds the full image). But for a 1-person team, 4 minutes is tolerable.

2. **CI may be burning free-tier minutes without proportional value.** 6 workflows on GitHub Actions free tier (2,000 min/month for private repos). The `load-test.yml` workflow runs k6 tests — but no k6 test scripts were found in the backend. The `publish-sdk-testpypi.yml` publishes the Python SDK on every push — is this needed on every push? The `pr-check.yml` may duplicate `ci.yml`. Audit which workflows actually catch bugs.

3. **The AGENTS.md documentation is extensive but may be stale.** The root AGENTS.md still references the sandbox preview auth chain as "RESOLVED" with detailed commit hashes — useful as a changelog but adds noise. The `docs/REBUILD-ROADMAP.md` is archived but still in the tree. The `.sisyphus/plans/OLD/` directory accumulates old plans. Documentation hygiene is a recurring tax.

4. **Observability has overlap.** structlog + Jaeger + Prometheus + Sentry + Langfuse = 5 observability systems. Jaeger and Langfuse both trace LLM calls. Prometheus and Sentry both track errors. The query experience is fragmented — you need to check 5 different tools to understand a single issue. For a 1-person team, this is too many dashboards.

5. **The Makefile is the right abstraction but some targets are stale.** `make reproduce` prints "Reproducer artifacts not yet available." `make dev` depends on the production compose (homelab-only). The standalone dev (`make dev-up`) is a better experience but may not be the default.

### Concrete recommendations

| # | Recommendation | Effort | Impact | Risk if NOT done |
|---|---|---|---|---|
| F1 | **Audit CI workflows.** Remove `load-test.yml` if no k6 scripts exist. Gate `publish-sdk-testpypi.yml` to tags/releases only. Merge `pr-check.yml` into `ci.yml` if they overlap. | S | Medium | Low — wasted CI minutes |
| F2 | **Consolidate observability.** Pick 3: structlog (logging), Prometheus (metrics), Sentry (errors). Drop Jaeger if OpenTelemetry traces aren't actively queried. Drop Langfuse if LLM tracing isn't actively used. Or: keep all 5 but create a single "investigation dashboard" that correlates logs → traces → metrics → errors. | M | Medium | Low — tool fatigue |
| F3 | **Clean up stale documentation.** Move archived roadmaps to a single `docs/archive/` directory. Remove resolved warning sections from AGENTS.md (keep the resolution note as a one-liner). Prune `.sisyphus/plans/OLD/` periodically. | S | Low | Low — onboarding noise |
| F4 | **Make `make dev-up` the default dev command.** The standalone dev environment is self-contained and doesn't depend on production compose. Update `make dev` to call `dev-up`. | S | Low | Low — developer confusion |

### Risks and trade-offs

- Dropping Jaeger means losing distributed tracing. If the WireGuard tunnel has latency issues, traces are the best diagnostic. Mitigation: keep Jaeger but only enable it when debugging.
- Dropping Langfuse means losing LLM call traces. Mitigation: structlog can capture LLM call metadata if the log events are structured properly.
- Consolidating CI workflows could miss edge cases. Mitigation: run both old and new workflows in parallel for one sprint before removing the old ones.

---

## Section G: Product Vision & Feature Prioritization

### What exists

FlowManner is a self-hosted, AI-native workflow orchestration platform. Think "LangChain + n8n + Linear, self-hosted, running on consumer GPUs."

**Unique value proposition:** Self-hosted AI workflow orchestration on consumer GPUs. No cloud API dependencies. Data sovereignty. Cost-zero inference. Privacy.

**Feature breadth:**
- 7 execution strategies (solo, dag, graph, swarm, pipeline, meta, langgraph)
- 21 webhook integrations
- Memory flywheel (conversation + episodic + RAG)
- Plan selection (cost-aware K-plan scoring)
- Improvement loop (6-phase autonomous self-improvement)
- HITL governance (human approval workflows)
- Replay assertion engine (regression testing)
- LLM-as-judge evaluation
- 3 domain agents (biotech, finance, legal)
- BYOK (bring your own key)
- MCP gateway (codegraph, filesystem, github)
- Marketplace, community, changelog, roadmap features

### What's wrong

1. **The product tries to be everything.** 7 strategies, 21 integrations, 3 domain agents, marketplace, community, changelog, roadmap, billing (PayPal), subscriptions — all for a 1-person team. The breadth is impressive but the depth is uneven. The 21 webhooks all have signature verification but none have deep integration (e.g., the GitHub webhook receives events but doesn't create issues or PRs). The marketplace exists as a backend module but has no frontend.

2. **The ~70 unwired endpoints suggest a "build everything" approach.** The backend has 139 endpoint modules; the frontend uses ~20. The platform has more capability than it exposes. This is either a goldmine (features waiting for UI) or a graveyard (features nobody uses).

3. **AI-for-AI's-sake features.** The improvement loop (10,570 lines) generates strategies that reference cloud models it can't use. The plan selection scores on dollar cost when the LLM is free. The LLM-as-judge bypasses the substrate's own rules. The replay assertion engine has no frontend and no evidence of production use. These are sophisticated features that may not be solving real user problems.

4. **The 27B model constraint limits which features are genuinely useful.** Multi-agent swarm debate, 7-phase pipelines, and recursive meta-improvement are features that shine with frontier models (GPT-4, Claude). A 27B model at 32K context handles up to ~3-phase protocols. The product should lean into what the 27B model does well (single-agent tool calling, RAG-augmented chat, structured output) rather than what it struggles with (multi-agent reasoning, long-context synthesis).

5. **No clear target user.** Is FlowManner for developers (self-hosted LangChain alternative)? For teams (self-hosted n8n with AI)? For individuals (personal AI assistant)? The domain agents (biotech, finance, legal) suggest vertical markets, but these are thin wrappers. The marketplace suggests a platform play, but who's building plugins?

### What 3–5 features, if built next, would make FlowManner genuinely more useful?

1. **Wire the HITL inbox** (S, High) — The approval workflow is the bridge between autonomous AI and human oversight. Without a UI, it's invisible. This is the most important missing piece for real workflow usage.

2. **Build the 3 Tier 1 frontend features** (M, High) — Reliability Center, Tool Routing Inspector, Plugin Manager. Zero new API. These make the platform feel complete.

3. **Workflow templates gallery** (M, High) — The backend has `templates.py` with template CRUD. A frontend gallery of pre-built workflow templates (e.g., "Summarize GitHub issues", "Research a topic with RAG", "Monitor Sentry and create Linear issues") would make the platform immediately useful to new users. No new API needed — just UI + seed data.

4. **Integration action picker** (M, Medium) — The v2 `integrations_actions.py` endpoint discovers available actions across OAuth connections. A UI that lets users browse "send Slack message", "create Linear issue", "search Notion" and drag them into a workflow would make the 21 integrations feel real.

5. **Eval results dashboard** (S, Medium) — The eval runner produces scored results with per-category breakdowns. A frontend page that shows eval run history, score trends, and model comparisons would make the LLM-as-judge visible and actionable.

### What 3–5 features, if cut, would reduce maintenance burden?

1. **Domain agents (biotech, finance, legal)** — 3 agents × ~200 LOC each = 600 LOC of thin wrappers with unimplemented tools. Cut to reduce surface area. The system prompts could be offered as "agent templates" instead.

2. **Marketplace + community + changelog + roadmap + votes** — 5 backend modules with no frontend and no evidence of usage. These are platform-as-a-product features that a 1-person team can't maintain. Cut to reduce API surface and test burden.

3. **The 6-phase improvement loop** — 10,570 LOC. The hypothesis tester has fake p-values. The strategy map references cloud models. The knowledge graph is in-memory. Consider keeping Phases 1–2 (failure telemetry + causal decomposition) and cutting Phases 3–6 (hypothesis testing, knowledge graph, strategy evolution, temporal analysis, proactive scheduling).

4. **PayPal billing + subscriptions** — If the product is self-hosted and free, billing is unnecessary. If the product will have paid tiers, Stripe (already integrated) is a better choice than PayPal.

5. **A2A (agent-to-agent) protocol server** — `a2a/a2a_server.py` + `a2a/a2a_agent_wrapper.py`. Cross-agent communication is a future feature that adds complexity now. Cut until there's a concrete use case.

---

## Section H: The "Next Level" Vision

### What makes self-hosted AI workflow platforms better than cloud alternatives?

1. **Privacy and data sovereignty.** All data stays on your hardware. No API calls to third parties. This is FlowManner's strongest differentiator. For users in regulated industries (healthcare, finance, legal), this is non-negotiable.

2. **Cost-zero inference.** Once the hardware is paid for, every LLM call is free. Cloud platforms charge per-token; FlowManner charges per-watt. At scale, this is dramatically cheaper.

3. **Offline operation.** The platform works without internet (except for web search and external integrations). This enables air-gapped deployments, field research, and environments with unreliable connectivity.

4. **Custom fine-tuning.** The GGUF model can be swapped or fine-tuned. Cloud platforms lock you into their model versions. FlowManner can run any GGUF that fits in VRAM.

5. **Full control over the stack.** No vendor lock-in, no API deprecations, no rate limits imposed by others. The user owns the entire execution path.

### What unique features does the local LLM constraint enable?

1. **Workflow version control.** The substrate's replay engine + assertion engine + baseline extractor could become a "git for workflows." Every run is an append-only event log. Every run can be replayed. Every run can be diffed against a baseline. This is something cloud platforms can't offer because they don't expose the event log. **Build a "Workflow Diff" UI** that shows what changed between two runs of the same workflow — different tool calls, different outputs, different costs. This turns the replay engine from a testing tool into a debugging tool.

2. **Personal knowledge graph.** The memory flywheel + Qdrant + RAG could become a personal knowledge graph that competitors can't match. Every conversation, every mission, every tool call contributes to a persistent, searchable, private knowledge base. The user owns their data and can export it, search it, and reason over it. **Build a "Memory Explorer" UI** that lets users browse, search, and manage their accumulated memories. Show which memories were recalled during which conversations.

3. **Self-hosted Zapier replacement.** The 21 integrations + event bus + trigger system could become a self-hosted automation platform powered by local AI. Instead of "when X happens, do Y" (Zapier), it's "when X happens, ask the AI what to do, then do it." The trigger bridge (`substrate/trigger_bridge.py`) already wires webhooks → substrate execution. **Build a "Trigger Builder" UI** that lets users create triggers from any of the 21 integrations and route them to AI-powered workflows.

4. **Zero-cost eval-driven development.** Because LLM calls are free, FlowManner can run eval suites on every model change, every prompt change, every workflow change — automatically. The eval runner + LLM-as-judge + golden datasets already exist. **Wire eval runs into the deploy pipeline** — every backend deploy that touches agent code runs the eval suite and blocks if scores regress. This is CI for AI, and it's only practical when inference is free.

5. **Local-first agent observability.** The combination of structlog + Jaeger + cost_engine + intervention_distance could produce a "mission replay" view that shows exactly what the agent did, why it made each decision, how much it cost, and where it needed human intervention. **Build a "Mission Timeline" UI** that visualizes the substrate event log as an interactive timeline — tool calls, LLM calls, HITL pauses, circuit breaker trips, cost accumulation. This makes the agent's behavior transparent and debuggable.

### What would make a developer choose FlowManner over LangChain + custom orchestration?

1. **The substrate guarantees.** Durable execution, type-checked I/O, capability-bounded tools, budget enforcement. LangChain doesn't offer any of these. FlowManner's substrate is a production-grade execution engine, not a library of chains.

2. **The replay engine.** Crash recovery, deterministic replay, regression testing. LangChain has no equivalent. This is the difference between "it worked on my machine" and "it will work again."

3. **The UI.** LangChain is code-only. FlowManner has a frontend (114 pages, 272 components). A visual workflow builder + mission dashboard + agent management UI makes the platform accessible to non-developers.

4. **The integrations.** 21 webhook integrations + OAuth flows + MCP gateway. LangChain requires you to build each integration yourself.

5. **The memory flywheel.** Persistent, searchable, private memory across conversations and missions. LangChain has no built-in memory system (you build it yourself with vector stores).

The pitch: **"FlowManner is the self-hosted alternative to LangChain + n8n + Linear, with durable execution, replay-based debugging, and a local LLM. Your data never leaves your hardware."**

---

## Prioritized Action Plan

| Priority | Item | Category | Effort | Impact | Risk if NOT done | Dependencies |
|----------|------|----------|--------|--------|------------------|--------------|
| P0 | Fix `/inbox` auth gap (E1) | Security | S | High | High | None |
| P0 | Switch middleware to opt-out model (E2) | Security | S | High | High | E1 |
| P1 | Route LLM judge + eval through BudgetEnforcer (C1) | AI Quality | S | Medium | Medium | None |
| P1 | Replace cloud model refs in STRATEGY_MAP (C2) | AI Quality | S | Medium | Medium | None |
| P1 | Wire HITL inbox frontend (B3) | Frontend | S | High | Medium | None |
| P1 | Build Reliability Center UI (B2a) | Frontend | S | High | Low | None |
| P2 | Build Tool Routing Inspector UI (B2b) | Frontend | M | High | Low | None |
| P2 | Standardize on React Query + apiClient (B1) | Frontend | M | High | Medium | None |
| P2 | Delete old `langchain/` subpackage (A3) | Architecture | S | Medium | Low | None |
| P2 | Build Plugin Manager UI (B2c) | Frontend | M | High | Low | Resolve extensions-vs-plugins question |
| P2 | Migrate 6 v1 routers off old executors (A2) | Architecture | L | High | Medium | None |
| P3 | Delete 7 old executors (A1) | Architecture | L | High | High | A2 |
| P3 | Profile strategies with 27B model (C3) | AI Quality | M | High | Medium | None |
| P3 | Build workflow templates gallery (G3) | Product | M | High | Low | None |
| P3 | Audit DB indexes (D2) | Performance | M | Medium | Medium | None |
| P3 | Verify Sentry initialization (E4) | Security | S | Medium | Medium | None |
| P3 | Audit webhook verifiers for constant-time (E5) | Security | S | Medium | Medium | None |
| P3 | Randomize BYOK encryption salt (E3) | Security | S | Medium | Medium | None |
| P4 | Set dual-write end timeline (A5) | Architecture | M | High | Medium | A2 |
| P4 | Upgrade langgraph (A4) | Architecture | M | Medium | Medium | A3 |
| P4 | Build Eval Results Dashboard (G5) | Product | S | Medium | Low | C1 |
| P4 | Consolidate observability (F2) | DevOps | M | Medium | Low | None |
| P4 | Add E2E tests for critical paths (B5) | Frontend | S | Medium | Medium | None |
| P4 | Audit CI workflows (F1) | DevOps | S | Medium | Low | None |
| P4 | Add cache hit rate monitoring (D1) | Performance | S | Medium | Low | None |
| P5 | Replace plan_scorer cost model (C5) | AI Quality | S | Medium | Low | None |
| P5 | Build Mission Timeline UI (H5) | Product | M | High | Low | P3 (A1) |
| P5 | Build Workflow Diff UI (H1) | Product | M | High | Low | P3 (A1) |
| P5 | Build Memory Explorer UI (H2) | Product | M | Medium | Low | None |
| P5 | Wire eval runs into deploy pipeline (H4) | DevOps | M | Medium | Low | C1 |
| P5 | Write k6 load test scripts (D3) | Performance | S | Medium | Medium | None |
| P5 | Add per-provider circuit breaker (E6) | Security | M | Medium | Low | None |
| P5 | Audit i18n usage (B4) | Frontend | S | Medium | Low | None |
| P5 | Cut domain agents (G-cut-1) | Product | S | Medium | Low | None |
| P5 | Cut marketplace/community/changelog/roadmap (G-cut-2) | Product | S | Medium | Low | None |

---

## What to Cut

| Module | LOC (est.) | Justification |
|--------|-----------|---------------|
| `domain_agents/` (biotech, finance, legal) | ~600 | Thin wrappers with unimplemented tools. System prompts could be agent templates instead. |
| `marketplace.py`, `community.py`, `changelog.py`, `roadmap.py`, `votes.py` | ~2,000 | No frontend, no evidence of usage. Platform-as-a-product features a 1-person team can't maintain. |
| Improvement loop Phases 3–6 (`hypothesis_tester.py`, `improvement_loop_v2.py`, `success_learner.py`, `knowledge_graph.py`, `strategy_evolution.py`, `knowledge_transfer.py`, `temporal_analyzer.py`, `proactive_scheduler.py`) | ~7,000 | Fake p-values, cloud model refs, in-memory knowledge graph. Keep Phases 1–2 (failure telemetry + causal decomposition). Cut the rest. |
| `paypal_service.py` + `subscription_service.py` | ~500 | Self-hosted product doesn't need billing. Stripe already integrated if needed later. |
| `a2a/` (agent-to-agent protocol) | ~300 | No concrete use case. Cross-agent communication is a future feature. |
| `langchain/` legacy subpackage (`simple_agent.py`, `unified_agent.py`) | ~400 | Explicitly marked legacy in services AGENTS.md. Substrate replaces it. |
| 7 old executors (after A2 migration) | ~5,000 | Dead code. Substrate is GA. |
| **Total** | **~15,800 LOC** | **~6.7% of backend codebase** |

---

## Open Questions for Glenn

1. **Is the Blueprint+Run model intended to fully replace Mission?** If yes, when do you want to end the dual-write? If no, what's the long-term role of each model?

2. **Do you have real users in non-English locales (de, es, fr, ja)?** If not, dropping to English-only would remove a significant maintenance tax on every UI change.

3. **Are the 21 webhook integrations actually receiving traffic?** Or are they "available but unused"? If unused, consider keeping signature verification but removing the per-integration routers (use a generic webhook router instead).

4. **Is the improvement loop actually running in production?** The `on_mission_complete` hook fires `improvement_loop_v2.on_mission_complete()` — is this enabled? If it's generating noise without signal, cutting Phases 3–6 would save ~7,000 LOC.

5. **What's the target user for FlowManner?** Developer (self-hosted LangChain alternative)? Team (AI-powered n8n)? Individual (personal AI assistant)? The answer determines which of the ~70 unwired endpoints to prioritize.

6. **Are extensions and plugins the same thing?** The roadmap flags this as an open question. `plugins.py` (853 lines) and `extensions.py` are separate backend systems. The frontend has a static extensions page. Decide: merge or keep separate?

7. **Do you want to keep Jaeger and Langfuse, or consolidate to structlog + Prometheus + Sentry?** Five observability systems is a lot for one person. If you're actively using Jaeger traces and Langfuse LLM traces, keep them. If not, they're overhead.

8. **Should the Sentry webhook accept unsigned payloads?** Sentry webhooks don't include HMAC signatures by default. In production, this means anyone who knows the webhook URL can send fake Sentry alerts. Is this acceptable, or should you configure a Sentry webhook signing secret?

---

## Implementation Status

### P0 Items — COMPLETED (2026-07-03)

Both P0 security items have been implemented:

- **E1 (Fix `/inbox` auth gap):** ✅ Fixed — `/inbox` is now protected by default under the opt-out model.
- **E2 (Switch middleware to opt-out model):** ✅ Implemented — `/home/glenn/FlowmannerV2-frontend/src/middleware.ts` rewritten from opt-in (`protectedPaths` array, ~20 paths) to opt-out (`publicPaths` array, ~25 public paths). All routes not in the public list now require authentication by default. This fixed `/inbox` plus ~20 other previously-unprotected authenticated routes (`/extensions`, `/playground`, `/tools`, `/workflows`, `/programs`, `/swarm`, `/runs`, `/blueprints`, `/circuit-breaker`, `/costs`, `/reliability`, `/tool-routing`, `/plugins`, `/templates`, etc.). TypeScript passes clean. 878 vitest tests pass. Code review completed.

---

*This report is a working document. It should be read alongside `.sisyphus/plans/frontend-wiring-roadmap.md` and the AGENTS.md documentation system. No code was changed in the production of this report (P0 items excepted — those were implemented separately).*
