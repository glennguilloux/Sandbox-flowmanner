# DEEP DIVE: FlowManner — Take It To The Next Level

You are a frontier model with deep architecture and product instincts. Your job
is to produce a comprehensive, brutally honest, deeply specific report on what
FlowManner should do next to level up — what to finish, what to cut, what to
build, what to refactor, and in what order. This is a working document that will
drive the next 4–8 weeks of development.

---

## 0. WHAT FLOWMANNER IS

FlowManner is a self-hosted, AI-native workflow orchestration platform. Think
"LangChain + n8n + Linear, self-hosted, running on consumer GPUs." It lets users
define missions (multi-step AI tasks), execute them through a unified substrate
(solo agent, DAG, graph, swarm, pipeline, meta, or LangGraph strategy), connect
to 21 external integrations via webhooks, and manage everything through a
Next.js frontend served behind an Nginx reverse proxy on a VPS with a WireGuard
tunnel to the homelab backend.

The platform is built and run by ONE person on a homelab with:

- **2x RTX 5060 Ti (16GB each = 32GB VRAM)** serving llama.cpp (Q5_K_M quantized
  models, ~27B–35B parameters, 32K context)
- **One VPS** (74.208.115.142) running Nginx, SSL, and the Next.js frontend
- **One homelab** running FastAPI backend, PostgreSQL, Redis, Qdrant, RabbitMQ,
  Celery, Jaeger, SearXNG
- **One ops/dev machine** (172.16.1.2) for triggering deploys and dev work
- Total infra budget: ~$400/month (self-hosted, no cloud APIs)

The LLM constraint is real: a 27B model at 32K context is the ceiling. It
handles up to ~3-phase agent protocols well; beyond that it degrades. All AI
recommendations must respect this constraint.

---

## 1. CODEBASE SCALE (hard numbers)

### Backend (FastAPI, Python 3.11)

| Metric | Count |
|--------|-------|
| Python files | 913 |
| Lines of code | 237,164 |
| API v1 endpoint modules | 104 |
| API v2 endpoint modules | 35 |
| API v3 (auth/workspace) modules | 12 |
| ORM models | 62 |
| Service files | 348 |
| Alembic migrations | 120 |
| Test functions | 3,967 (84 integration) |
| Dependencies (requirements.txt) | 128 packages |
| Integration webhooks | 21 (airtable, asana, clickup, confluence, datadog, figma, github, gitlab, hubspot, intercom, jira, monday, pagerduty, sentry, shopify, slack, stripe, telegram, twilio, vercel, zendesk) |

### Frontend (Next.js 16, React 19, TypeScript)

| Metric | Count |
|--------|-------|
| Pages (page.tsx) | 114 |
| Components | 272 |
| TSX files | 487 |
| TS files | 403 |
| SDK generated service files | 226 |
| Files making API calls | 116 |
| Frontend test files | 72 |
| i18n locales | 5 (de, en, es, fr, ja) |

### Infrastructure

| Component | Technology |
|-----------|-----------|
| Web server | Nginx (VPS) |
| Frontend | Next.js 16, served in Docker on VPS |
| Backend | FastAPI 0.115 + Uvicorn 0.34 |
| Database | PostgreSQL 15 |
| Cache | Redis 7 |
| Vector DB | Qdrant 1.12 |
| Message Queue | RabbitMQ 3 |
| Task Queue | Celery 5.3 |
| Tracing | Jaeger (OpenTelemetry) |
| Search | SearXNG sidecar |
| LLM | llama.cpp (2x RTX 5060 Ti, tensor split) |
| Observability | structlog + prometheus-client + Sentry |

### API consumption gap (CRITICAL)

The backend exposes 104 v1 + 35 v2 = ~139 endpoint modules. The frontend
consumes ~20 of them. **~70 backend endpoint modules have ZERO frontend.** There
are 226 generated SDK service files but only 116 files actually call APIs. The
gap between what the backend can do and what the user can see is enormous.

### v1 → v2 migration

The codebase is mid-migration:
- **v1**: Legacy, no envelope, ~80% of endpoints, will be supported forever
  (backward compatible)
- **v2**: Current default, standardized envelope `{data, meta, error}`, 35
  modules, includes CQRS split for missions + blueprints
- **v3**: Auth/workspace specialty, cookie+Bearer auth, `trace_id` in errors

The mission execution layer has been fully CQRS-delegated (14 commands + 14
queries). The substrate (H5.1 unified executor) replaced 7 separate executors
with typed strategies. Old executors still exist in the tree but new code must
target the substrate.

### Deployment

Two-machine split deploy:
- `deploy-frontend.sh` — rsync + Docker build + restart on VPS (~4 min)
- `deploy-backend.sh` — backup + Docker build + restart + health checks +
  auto-rollback (~2 min)
- Docker images have NO volume mounts — all code baked into image
- CI: GitHub Actions with 6 workflows (ci, cli, deploy, load-test, pr-check,
  publish-sdk-testpypi)

---

## 2. THE SUBSTRATE (execution engine — H5.1 GA)

This is the heart of FlowManner. The `UnifiedExecutor` is the single entry point
for all workflow execution, dispatching to 7 typed strategies:

| Strategy | Replaces | Purpose |
|----------|----------|---------|
| `solo.py` | `mission_executor.py` (1,387 LOC) | Single-agent task loop with LLM tool-calling |
| `dag.py` | `dag_executor.py` (179 LOC) | Dependency-ordered parallel task dispatch |
| `graph.py` | `graph_executor.py` (293 LOC) | Conditional edges, `{{node.output.field}}` interpolation |
| `swarm.py` | `swarm/orchestrator.py` (331 LOC) | Multi-agent LLM collaboration |
| `pipeline.py` | `swarm_pipeline/orchestrator.py` (~1,700 LOC) | 7-phase orchestrated pipeline |
| `meta.py` | `nexus/meta_loop_orchestrator.py` (225 LOC) | Budget-bounded recursive improvement |
| `langgraph.py` | `langgraph/agent.py` (~900 LOC) | Stateful LangGraph agent workflows |

4 substrate guarantees:
1. **Durable** — append-only event log (`substrate_events` table)
2. **Type-checked** — Pydantic models for all I/O
3. **Capability-bounded** — tool calls require `CapabilityToken`
4. **Bounded** — all LLM calls through `BudgetEnforcer.call()`

The old executors are still in the tree and still wired by legacy routes, but
all new code targets the substrate. The deletion of old executors is pending
verification that `FLOWMANNER_UNIFIED_EXECUTOR=all` is stable in production.

---

## 3. KEY SUBSYSTEMS

### Memory & Learning
- `memory_service.py` + `memory_bridge/` — personal memory flywheel wired into
  chat (extraction + recall + citations)
- `episodic_memory.py` — episodic memory API
- v2 `personal_memory.py` — 10 endpoints for personal memory CRUD
- Qdrant-backed semantic search for memory recall

### RAG Pipeline
- `rag_service.py` → delegates to `rag/` subpackage (chunking, embedding,
  prompt synthesis, retrieval, vector store)
- SearXNG sidecar for live web search
- Multi-provider reranking in `web_search/`

### Plan Selection
- `plan_selection/` — cost-aware K-plan scored pick
- `mission_planner.py` — LLM-driven plan generation
- Plan candidate round-trip (select-plan endpoint + inline hooks)
- Mission plan candidates endpoint for frontend comparison UI

### Reliability & Governance
- Circuit breaker (per-mission, Phase 6.4)
- Reliability center (chaos mode toggle, Langfuse health)
- HITL governance (human-in-the-loop approval workflows)
- Replay assertion engine (regression checks against known-good runs)
- Baseline extractor (auto-generate expected behaviors from successful runs)

### Integrations
- 21 webhook endpoints for external services
- OAuth flows for: Stripe, Jira, Confluence
- Event bus with 18 integration webhooks wired
- BYOK (bring your own key) for external LLM providers
- MCP gateway (codegraph-ai, filesystem, github)

### Self-Improvement Loop
- Phases 1–6 in `improvement/` subpackage
- LLM-as-judge evaluation in `evaluation/`
- Domain agents in `domain_agents/`

---

## 4. WHAT'S IN-FLIGHT / KNOWN ISSUES

### Open bugs (GitHub Issues)
1. **Issue #25** — `playground_sandboxes.workspace_id` is UUID but
   `workspaces.id` is VARCHAR(36). FK constraint fails on fresh DB (breaks k6
   load tests on CI). Fix: 1 migration + 1 model line change.
2. **Issue #20** — CLI binary needs a smoke test step in CI. Blocked until GH
   Actions free tier resets.
3. **`/inbox` auth gap** — Commit `501c821` claims to add `/inbox` to middleware
   `protectedPaths` but the diff was empty. The inbox page is publicly accessible.
   Fix: 1 line in `src/middleware.ts`.

### Frontend wiring roadmap (3 features, zero new API needed)
1. **Reliability Center** (~½ day) — partial (field-name fix committed)
2. **Tool Routing Inspector** (~1 day) — not started
3. **Plugin Manager** (~1.5 days) — partial frontend exists

### v1 → v2 migration
Multiple v1 routers still inline old executor logic (graph, swarm,
orchestration, flow_compat, mission_decomposition). These need to be migrated
to the substrate strategies or CQRS handlers.

### LLM model swap
A daemon on port 9723 allows runtime model swapping (Qwen3.6-27B ↔ Ornith-35B ↔
Qwopus-35B). Dashboard UI exists but had 3 data-shape mismatches. Those were
fixed in the HIL dashboard repo. The daemon is fully functional via API.

### Known tech debt
- 7 old executors still in tree (substitute for substrate is GA, but old code
  not deleted)
- ~70 endpoints with no frontend
- 120 Alembic migrations (compaction opportunity)
- No E2E test suite (Playwright installed but no tests written)
- Frontend tests only cover 72 files out of ~900
- No API contract testing between frontend SDK and backend
- LangChain 0.1 pinned (2+ major versions behind current)
- langgraph 0.0.40 pinned (massively behind)

---

## 5. YOUR ASSIGNMENT

Produce a comprehensive report organized into these sections. For each section,
provide:
- **What exists** (be specific — cite file paths, module names, architecture
  patterns)
- **What's wrong or missing** (be brutally honest)
- **Concrete recommendations** (actionable, prioritized, with effort estimates
  suitable for a single developer on a homelab)
- **Risks and trade-offs** (what could go wrong, what's the cost of NOT doing it)

### SECTION A: Architecture Deep Dive

Analyze the overall system architecture. Consider:
- Is the v1/v2/v3 split healthy, or is it creating complexity debt?
- The substrate is GA but 7 old executors remain — what's the cleanup path?
- Is the CQRS pattern for missions the right model? Should it extend to all
  domains?
- The dual-write pattern (Mission → Blueprint/Run) — is this transition well-
  managed or accumulating risk?
- The event log as source of truth — are there consistency gaps?
- The memory flywheel — how well is it integrated into the chat/mission flow?
- Microservice vs monolith trade-offs for a 1-person team
- Dependency health (LangChain 0.1, langgraph 0.0.40 — ancient pins)

### SECTION B: Frontend ↔ Backend Gap

This is the biggest opportunity. ~70 backend endpoint modules have zero
frontend. Analyze:
- Which of the ~70 unwired endpoints would deliver the most user value if they
  had a UI?
- The frontend uses a mix of `apiClient`, `fetch`, `swr`, and
  `@tanstack/react-query` — is the data-fetching strategy consistent?
- 226 SDK service files are generated but only 116 files use them — is the SDK
  generation pipeline working or is it producing dead code?
- i18n: 5 locales — is the translation pipeline sustainable?
- The frontend is on Next.js 16 with React 19 + React Compiler — are there
  patterns that need modernization?
- Component library: Radix + shadcn + custom — is this consistent?
- E2E tests: zero Playwright tests despite the dependency being installed

### SECTION C: AI/LLM Pipeline & Agent Quality

The LLM is a Q5_K_M quantized 27B model on 32GB VRAM. Analyze:
- How well does the current agent execution loop (solo strategy + tool calling)
  work with a 27B local model?
- The 7 strategies (solo, dag, graph, swarm, pipeline, meta, langgraph) — are
  they all genuinely useful, or are some over-engineered for a 27B model?
- The tool routing inspector — does the scoring/selection mechanism make sense
  for local LLMs?
- RAG pipeline quality — is the chunking, embedding, and retrieval strategy
  optimal?
- Memory flywheel — extraction + recall + citations — how well does this work
  in practice?
- The improvement loop (Phases 1–6) — is this actually improving agent quality
  or just generating noise?
- Cost-aware plan selection — does the K-plan scoring work well with a free
  local LLM (where "cost" is VRAM/time, not dollars)?
- The replay assertion engine + baseline extractor — is regression testing of
  agent workflows actually catching real bugs?

### SECTION D: Performance & Scalability

- The backend is async-first (SQLAlchemy 2.0 async) — are there sync bottlenecks?
- Redis caching strategy — is it aggressive enough? What's the hit rate?
- Database: 120 migrations — any performance debt? Index coverage?
- Docker image bake + no volume mounts — is this the right model for dev velocity?
- The 2-machine WireGuard split — is this a latency bottleneck for API calls?
- Celery worker utilization — is the task queue being used effectively?
- WebSocket connections for real-time — how well does this work through the
  WireGuard tunnel?
- k6 load testing exists but is it revealing real bottlenecks?

### SECTION E: Security & Reliability

- The `/inbox` auth gap is a symptom — what other routes might be unprotected?
- BYOK key storage — is the encryption adequate?
- The 21 webhook endpoints — are they all validating signatures correctly?
- Rate limiting: per-user + tier-aware — is the coverage complete?
- Circuit breaker: per-mission — should it be per-strategy or per-provider?
- Sentry integration: DNS check was just added — what else is fragile?
- WireGuard watchdog: just deployed — are there other SPOFs?
- Secret management: `.env` files — is there a better path for a homelab?
- Dependency vulnerabilities: LangChain 0.1, etc.

### SECTION F: Developer Experience & Operations

- Deploy scripts (deploy-frontend.sh ~4min, deploy-backend.sh ~2min) — can this
  be faster?
- The Docker bake model means no hot reload in production — is there a dev mode
  that works well?
- CI: 6 GitHub Actions workflows — are they providing value or just burning
  free-tier minutes?
- The AGENTS.md documentation system (nested, per-directory) — is it helping
  agents land quickly, or is it stale?
- The handoff/exit-ritual system (.sisyphus/) — is this working well for session
  continuity?
- Observability: structlog + Jaeger + Prometheus + Sentry — is there overlap?
  What's the query experience like?
- The Makefile targets — are they the right abstraction for a 1-person team?

### SECTION G: Product Vision & Feature Prioritization

Step back and think about FlowManner as a product. Analyze:
- What is FlowManner's unique value proposition? (self-hosted AI workflow
  orchestration on consumer GPUs — who is the target user?)
- The 70 unwired endpoints suggest a "build everything" approach — should the
  product narrow its focus?
- The integration breadth (21 webhooks) vs depth — is breadth-without-depth a
  trap?
- Marketplace, community, changelog, roadmap — are these features that a
  1-person team can maintain?
- The plan selection / cost-aware / mission comparison features — are these
  solving real user problems or are they AI-for-AI's-sake?
- What 3-5 features, if built next, would make FlowManner genuinely more useful?
- What 3-5 features, if cut, would reduce maintenance burden without losing
  value?

### SECTION H: The "Next Level" Vision

This is the creative section. If you had 8 weeks with this codebase and a
frontier model's brain, what would you build that would make FlowManner
genuinely impressive? Think about:
- What makes self-hosted AI workflow platforms better than cloud alternatives?
- The local LLM constraint (27B) — what unique features does this enable that
  cloud API-dependent platforms can't do? (privacy, cost-zero inference,
  custom fine-tuning, offline operation, data sovereignty)
- The substrate's replay engine + assertion engine — could this become a
  "workflow version control" system?
- The memory flywheel — could this become a personal knowledge graph that
  competitors can't match?
- The 21 integrations + event bus — could this become a self-hosted Zapier
  replacement powered by local AI?
- What would make a developer choose FlowManner over LangChain + custom
  orchestration?

---

## 6. OUTPUT FORMAT

Write your report as a single markdown document. Use this structure:

```
# FlowManner Deep Dive Report — [Date]

## Executive Summary (1 page max)
[The 5 most important takeaways, prioritized]

## Section A: Architecture
[analysis + recommendations]

## Section B: Frontend ↔ Backend Gap
[analysis + recommendations]

[... C through H ...]

## Prioritized Action Plan
[A single table: Priority | Item | Category | Effort | Impact | Dependencies]

## What to Cut
[A list of features/modules that should be deprecated or deleted to reduce
complexity, with justification]

## Open Questions for Glenn
[Things you need human input on before proceeding]
```

For every recommendation, include:
- **Effort** estimate (S/M/L) for a single developer
- **Impact** estimate (Low/Medium/High)
- **Risk** if NOT done (Low/Medium/High)
- **Dependencies** on other work

Be specific. Don't say "improve test coverage." Say "add integration tests for
the 7 substrate strategies in `backend/app/tests/test_substrate_*.py` — currently
only 3 of 7 strategies have dedicated test files, and the pipeline strategy
(1,700 LOC of migrated code) has zero tests."

Don't hedge. If something is over-engineered, say so. If something is missing,
say what it is. If something is good, acknowledge it and explain why.

---

## 7. KEY FILES TO READ (if you have filesystem access)

If you are running on the homelab with filesystem access, read these for context:

- `/opt/flowmanner/AGENTS.md` — top-level agent instructions
- `/opt/flowmanner/backend/AGENTS.md` — backend contract (framework versions, Docker, deploy)
- `/opt/flowmanner/backend/app/services/AGENTS.md` — services layer contract (23K chars, all clusters)
- `/opt/flowmanner/backend/app/api/v1/AGENTS.md` — v1 router inventory + migration status
- `/opt/flowmanner/backend/app/api/v2/AGENTS.md` — v2 router inventory + envelope specs
- `/opt/flowmanner/backend/app/services/substrate/AGENTS.md` — substrate contract (H5.1)
- `/opt/flowmanner/docker-compose.yml` — infra topology
- `/opt/flowmanner/Makefile` — build/test/deploy targets
- `/opt/flowmanner/backend/requirements.txt` — Python dependencies (128 packages)
- `/opt/flowmanner/.sisyphus/plans/frontend-wiring-roadmap.md` — frontend feature plan
- `/opt/flowmanner/.sisyphus/analysis/codex-plugins-adoption-plan-2026-06-28.md` — behavioral guardrails analysis
- `/opt/flowmanner/.sisyphus/analysis/hubble.md` — spec pipeline ideas
- `/opt/flowmanner/config/llm-models.yaml` — LLM model configuration
- `/opt/flowmanner/scripts/llm-model-daemon.py` — runtime model swap daemon
- `/opt/flowmanner/scripts/llm-model-manager.sh` — model manager bash core

If you do NOT have filesystem access, use the data in sections 1–4 above. It was
gathered live from the codebase on 2026-07-03.

---

## 8. CONSTRAINTS

1. **Self-hosted LLM only.** Never recommend OpenAI/Google/Anthropic/DeepSeek as
   primary or fallback LLM. The primary is llama.cpp on 2x RTX 5060 Ti.
2. **1-person team.** Recommendations must be achievable by one developer. No
   "hire a team" or "dedicate a sprint" suggestions.
3. **$400/month infra.** Don't recommend cloud services that would blow the
   budget. Self-hosted solutions preferred.
4. **No deploy without human review.** Glenn deploys himself. Don't include
   auto-deploy steps.
5. **The local LLM is a 27B model.** Agent protocols with more than 3 phases
   confuse it. Keep recommendations within this constraint.
6. **Respect what exists.** Don't recommend rewriting from scratch. FlowManner
   has 237K LOC of backend + ~900 frontend files. Refactor and improve, don't
   burn it down.

---

## 9. STOP RULES

1. **DO NOT** produce code changes. This is an analysis/report task only.
2. **DO NOT** edit any files. Write the report as output text.
3. **DO NOT** commit anything. The human (Glenn) reviews the report and decides
   what to act on.
4. **DO NOT** hedge or soften criticisms. If something is broken, over-engineered,
   or unnecessary, say so with evidence.
5. **DO NOT** ignore the constraints in section 8.
6. If you find something you believe is a genuine security vulnerability, flag
   it prominently at the top of the report.

---

## SUMMARY

FlowManner is a 237K-LOC backend + large Next.js frontend self-hosted AI
workflow platform running on consumer GPUs. It has a unified substrate execution
engine (GA), 21 integrations, a memory flywheel, and plan selection — but ~70
endpoints have no UI, several old executors haven't been cleaned up, testing has
significant gaps, and the product needs focus.

Your job: tell us what to do next, in what order, and why. Be specific, be
honest, be useful. The report should be long enough to be genuinely valuable
and short enough that a 27B model can summarize it without losing the key
recommendations.
