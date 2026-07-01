# FlowManner — Complete System Specification for AI Brainstorming

**Generated:** 2026-06-03
**Purpose:** Feed this entire document to GPT-5.6 (or any AI) for a fully-informed brainstorming session about the Flowmanner platform.
**Source material:** Live codebase reconnaissance + 10+ reference documents + ARCHITECTURAL_ANALYSIS + ROADMAP + H1/H2 audits + Docker audit + all ADRs.

---

## TABLE OF CONTENTS

1. SYSTEM IDENTITY & PHILOSOPHY
2. INFRASTRUCTURE & TOPOLOGY
3. BACKEND ARCHITECTURE
4. FRONTEND ARCHITECTURE
5. API VERSIONING (V1/V2/V3)
6. CORE DATA MODEL (44 SQLAlchemy models)
7. AUTH & SECURITY
8. EXECUTION ENGINES (7 strategies)
9. AGENT SYSTEM
10. OBSERVABILITY & MONITORING
11. LLM ROUTING (3-Layer Architecture)
12. SELF-IMPROVEMENT & LEARNING
13. NEXUS META-ORCHESTRATION
14. SWARM ORCHESTRATION
15. SUBSTRATE (Event-Sourced Engine — V2)
16. RAG PIPELINE
17. INTEGRATIONS & CONNECTORS
18. DEPLOYMENT & CI/CD
19. TEST COVERAGE
20. CURRENT ROADMAP STATUS (P1-P6, H1-H2)
21. KNOWN WEAKNESSES & OPEN QUESTIONS
22. FRONTEND COMPONENT CATALOG
23. FRONTEND ZUSTAND STORES
24. FRONTEND DASHBOARD ROUTES (19+ pages)

---

## 1. SYSTEM IDENTITY & PHILOSOPHY

**Flowmanner** is a multi-agent AI workflow automation platform. It orchestrates complex tasks through AI agents, visual flow definitions, persistent memory, and a marketplace for sharing. It positions itself as an "Agentic OS."

### Five Pillars
1. **Missions** — Task definitions with decomposition, execution tracking, results
2. **Agents** — Specialized AI entities (50+ predefined) that execute work
3. **Chat** — Primary human interface; all system functions are chat-accessible
4. **Graphs/Flows** — Visual workflow definitions via node-and-edge editor
5. **Marketplace** — Sharing economy for agent templates, workflows, and tools

### Ten Implicit Architectural Principles (from code analysis)
1. **Sovereign Infrastructure** — Homelab-first, all state on owned hardware, VPS is thin presentation layer. Inverts cloud-native orthodoxy.
2. **Agent as Atomic Unit** — Not a chatbot with RAG; agents are discoverable, composable, marketplace-published entities with persistent identity.
3. **Mission as Composable Work Unit** — Complex work is inherently hierarchical and decomposable. Rejects "one big prompt."
4. **Immutable Deployment** — No volume mounts. Every change requires full Docker rebuild. Cost of correctness.
5. **Observability as Infrastructure** — Jaeger + OpenTelemetry + Langfuse + Sentry + structlog + Prometheus. Trace from Nginx → Next.js → WireGuard → FastAPI → Celery → LLM.
6. **Multi-Tenancy from Inception** — Workspace isolation, RBAC, API keys, subscription tiers. Designed as SaaS platform business model from day one.
7. **Integration Hub** — 6 native OAuth integrations (Linear, Discord, Slack, Notion, GitHub, Google). Agents must act, not just think.
8. **Graceful Degradation** — Local llama.cpp (Qwen3.6-27B) alongside DeepSeek API. If API is down, local model takes over. If WireGuard fails, VPS serves static content.
9. **Chat-Centric UI** — Everything accessible through conversation.
10. **BYOK** — User-supplied LLM API keys prevent vendor lock-in.

### Dual Vision
- **Flowmanner Classic** — The running system; accretion-driven, feature-rich but architecturally fragmented
- **Flowmanner Ω (Omega)** — Proposed re-architecture as "durable, type-safe, formally auditable agentic OS" with event sourcing, capability-based security, bounded execution guarantees

---

## 2. INFRASTRUCTURE & TOPOLOGY

### Three-Machine Architecture

| Machine | Public IP | LAN IP | Role | Specs |
|---------|-----------|--------|------|-------|
| **Homelab** | 176.141.9.146 | 10.99.0.3 / 172.16.1.1 | Backend, DBs, LLM | Arch, i7-11700K, 62GB RAM, 2×RTX 5060 Ti (32GB VRAM), 1.9TB disk |
| **VPS** | 74.208.115.142 | 10.99.0.1 (WG) | Frontend, Nginx, SSL | IONOS US, Debian 13 |
| **Ops/Dev** | — | 172.16.1.2 | Dev workstation, deploy trigger | ✅ Reachable |

### Network Flow
```
Internet → VPS (Nginx :443) → frontend:3000 (Next.js)
                            ─→ /api/* → WireGuard → Homelab:8000 (FastAPI)
                            ─→ /api/auth/* → frontend:3000 (NextAuth)
                            ─→ /ws → WireGuard → Homelab:8000 (WebSocket)
```

### Docker Compose (12 containers on Homelab)
| Service | Image | IP | Ports | Mem Limit |
|---------|-------|----|-------|-----------|
| backend | workflows-backend:restored | 10.0.4.6 | 8000 | 4GB |
| celery-worker | (same image) | — | — | 2GB |
| celery-beat | (same image) | — | — | 512MB |
| postgres | postgres:15-alpine | 10.0.4.10 | 5432 | 2GB |
| qdrant | qdrant/qdrant:v1.12.0 | 10.0.4.3 | 6333,6334 | 1GB |
| redis | redis:7-alpine | 10.0.4.5 | 6379 | 512MB |
| rabbitmq | rabbitmq:3-management-alpine | 10.0.4.9 | 5672,15672 | 512MB |
| jaeger | jaegertracing/all-in-one | 10.0.4.7 | 16686,4318 | — |
| static | nginxinc/nginx-unprivileged:1.27-alpine | 10.0.4.8 | 8080 | 128MB |
| searxng | searxng/searxng:latest | 10.0.4.11 | 55510 | — |

Also running: 2× `ghcr.io/github/github-mcp-server` (MCP containers on homelab).

### llama.cpp (Bare Metal via systemd)
- **Model:** Qwen3.6-27B-Q5_K_M-mtp.gguf (19.7GB)
- **Binary:** `/mnt/apps/llama.cpp-mtp/build/bin/llama-server`
- **Config:** `--spec-type draft-mtp --spec-draft-n-max 3 --ctx-size 32768 --gpu-layers 99 --flash-attn on`
- **Performance:** ~38 tok/s (Q5 MTP), ~44 tok/s (Q4 MTP)
- **Access:** `http://10.0.4.1:11434` (Docker gateway), OpenAI-compatible `/v1/chat/completions`
- **Hardware:** 2× RTX 5060 Ti (16GB each), CUDA 13.2, Blackwell SM 12.0

### WireGuard
- Connects VPS (10.99.0.1) ↔ Homelab (10.99.0.3)
- All `/api/*` traffic from VPS Nginx routes through this tunnel
- **Single point of failure** — no documented fallback routing

---

## 3. BACKEND ARCHITECTURE

### Stack
- **Framework:** FastAPI 0.115 + Uvicorn 0.34, 4 workers
- **Python:** 3.11 slim-bookworm
- **ORM:** SQLAlchemy 2.0 (async) + Alembic 1.13
- **Task Queue:** Celery 5.3 + RabbitMQ, 4 concurrency, 100 max-tasks-per-child
- **Cache:** Redis 4.5 (password-protected, append-only persistence)
- **Vector DB:** Qdrant 1.12
- **LLM:** LangChain 0.1 + OpenAI 1.68
- **Tracing:** OpenTelemetry → Jaeger
- **Validation:** Pydantic 2.10
- **Auth:** PyJWT 2.8 + passlib + pyotp (2FA)
- **Logging:** structlog
- **Metrics:** prometheus-client

### Directory Structure (45 top-level dirs)
```
backend/app/
├── main_fastapi.py          # Entry point
├── api/                     # API layer
│   ├── v1/                  # 74 endpoint modules (legacy)
│   ├── v2/                  # 23 route files (next-gen)
│   ├── v3/                  # 13 route files (workspace-scoped, cookie auth)
│   ├── middleware/          # Audit, metrics, rate limit, security, versioning
│   └── deps.py              # FastAPI dependencies
├── models/                  # 44 SQLAlchemy model files
├── schemas/                 # Pydantic request/response schemas
├── services/                # 77 service files + 15 subdirectories
├── core/                    # Config, security, database connections
├── middleware/               # FastAPI middleware
├── tasks/                   # Celery tasks
│   └── celery_app.py        # Celery app definition
├── workers/                 # Background workers
├── websocket/               # WebSocket handlers
├── tools/                   # Tool implementations
├── integrations/            # External service integrations
├── agent_definitions/       # Agent configuration
├── governance/              # Governance/approval workflows
├── substrate/               # Event-sourced execution engine (V2)
├── orchestrator/            # Meta-orchestration
├── memory/                  # Memory subsystem
├── utils/                   # Utility functions
├── cli/                     # CLI commands
├── cache/                   # Caching layer
├── tests/                   # 52 test files
└── scripts/                 # Utility scripts
```

### Service Subdirectories
- `a2a/` — Agent-to-Agent protocol
- `connectors/` — Third-party integrations (Slack, GitHub, Google, Notion, Discord, Linear, Email, Webhook)
- `domain_agents/` — Specialized domains (biotech, finance, legal)
- `evaluation/` — Eval runner, LLM judge, dataset builder
- `flow/` — Execution router, flow service
- `improvement/` — 16 files: autonomous improvement loop, causal decomposition, strategy evolution
- `langchain/`, `langgraph/` — LangChain/LangGraph integration
- `nexus/` — 22 files: meta-orchestration, capability registry, cost optimizer, distributed executor
- `providers/` — LLM provider adapters (DeepSeek, OpenRouter)
- `rag/` — Chunking, embedding, vector store, retrieval, prompt synthesis
- `runtime/` — Self-healing, predictive scaler, health monitor, anomaly detector
- `substrate/` — Event-sourced engine, replay, executor V2
- `swarm/`, `swarm_pipeline/` — Swarm orchestration
- `unified_tools/` — Tool registry, chain executor
- `web_search/` — DuckDuckGo + SearXNG dual provider

### Backend Dockerfile
```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app/
CMD ["uvicorn", "app.main_fastapi:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1
```
**Note:** This is a single-stage build (not multi-stage). The Dockerfile from AGENTS.homelab.md references a multi-stage build but the actual file is single-stage.

---

## 4. FRONTEND ARCHITECTURE

### Stack
- **Framework:** Next.js 16.2.6 App Router, TypeScript
- **UI:** React 19.2.4, Tailwind CSS
- **i18n:** `next-intl` 4.12, `[locale]` route prefix
- **State:** Zustand 5 (auth, chat, inbox, notification, workspace stores)
- **Server State:** TanStack React Query 5
- **Forms/UI:** `react-dropzone`, `sonner` (toasts), `lucide-react` (icons), `@xyflow/react` (flow graphs)
- **Auth Client:** `next-auth` 5 beta, Zustand auth-store wrapping `getSession()`
- **Virtualization:** `@tanstack/react-virtual` 3
- **Testing:** Vitest (unit), Playwright (E2E)

### Frontend Source Location
`/home/glenn/FlowmannerV2-frontend/` (on homelab)
- rsync'd to VPS for deploy
- Built on VPS via `docker compose build`
- Dev server: `http://172.16.1.1:3000` (systemd user service, HMR)

### API Client Pattern (Dual)
1. **`apiClient`** — Thin fetch wrapper, uses `localStorage("fm_tokens")`. Used by: files, marketplace, usage, triggers, integrations
2. **`sdk-client.ts`** — Auto-generated OpenAPI SDK (87 lines, 53 service classes), uses `getAuthToken()` → NextAuth session. Used by: graphs, missions, agents, notifications, teams, tools, users, admin. **Preferred path.**

### Frontend Directory Structure
```
src/
├── app/[locale]/
│   ├── (auth)/signin, signup
│   ├── (dashboard)/admin, analytics, chat, costs, developer, feedback, files, graphs,
│   │   integrations, marketplace, missions, notifications, nps, onboarding, rag,
│   │   settings, team, templates, triggers
│   ├── about, agents, blog, browser, case-studies, dashboard, docs, developers,
│   │   inbox, invite, maintenance, mission-dashboard, models, pricing, privacy,
│   │   profile, register, roadmap, server-auth, terms, tools, topology
│   └── page.tsx (homepage)
├── components/        # 28 component directories
│   ├── chat/          # SSEChat.tsx (core streaming chat)
│   ├── auth/          # Credentials form, sign-in components
│   ├── mission-builder/ # Visual flow editor with nodes/
│   ├── rag/           # SearchBar, document viewers
│   ├── layout/        # Navbar, sidebar, footer
│   ├── ui/            # Base UI components
│   ├── shared/        # Shared patterns
│   ├── settings/      # API keys, billing, danger zone
│   ├── marketplace/   # Listing cards, detail views
│   ├── triggers/      # Trigger configuration
│   ├── workspace/     # Workspace management
│   └── ... (blog, analytics, dashboard, evaluation, inbox, etc.)
├── stores/            # 5 Zustand stores
├── lib/               # Utilities, API helpers, types
│   ├── sdk-client.ts  # 53 service classes
│   ├── chat-types.ts  # Core chat type definitions
│   ├── provider-models.ts  # LLM provider model maps
│   ├── workspace-api.ts    # Workspace CRUD helpers
│   └── file-api.ts         # File API helpers
└── hooks/             # React hooks (use-documents, etc.)
```

---

## 5. API VERSIONING (V1 / V2 / V3)

Three parallel API tiers in the same FastAPI app:

| Aspect | V1 | V2 | V3 |
|--------|----|----|----|
| **Routes** | 74 endpoint modules | 23 route files | 13 route files |
| **Tag** | None (legacy) | v2-* tags | v3-* tags |
| **Auth** | Mixed | Bearer tokens | httpOnly cookie sessions |
| **Middleware** | Shared app middleware | Own v2 middleware | Feature-flag gated |
| **Status** | Production, fragmented | Active development | Migration in progress |
| **GraphQL** | No | `/api/v2/graphql` | No |

### V1 Categories (74 modules)
- Auth: admin, api_keys, auth, oidc, two_fa
- Core: chat, agent, mission, graph, file, browser
- Workspace: workspace, tenant, users, roles
- Intelligence: llm, llm_advanced, search, rag, memory
- Operations: dashboard, analytics, usage, stats, observability
- Platform: marketplace, community, changelog, roadmap
- Integration: integrations, linear, byok, webhooks
- Quality: evaluation, feedback, reliability
- Admin: admin, audit_log, rate_limits, feature_flags

### V2 Routes
- `/api/v2/auth` — register, login, login/2fa, refresh, logout, me
- `/api/v2/chat` — folders CRUD, threads CRUD, messages, branches, chat, chat/stream
- `/api/v2/agents` — CRUD, templates CRUD
- `/api/v2/missions` — CRUD, tasks, logs, execute, execute-async, status, stream, analytics
- `/api/v2/workspaces` — CRUD, members, teams
- `/api/v2/search` — search, suggestions
- `/api/v2/graphql` — GraphQL endpoint

### V3 Routes (feature-flag gated)
- `/api/v3/auth/users`, `/api/v3/auth/sessions` — httpOnly cookie auth
- `/api/v3/workspaces` — + invitations, activity log, billing stub, teams
- `/api/v3/teams` — top-level team CRUD
- `/api/v3/auth/oidc` — OIDC login stub
- `/api/v3/auth/webhooks` — Webhook CRUD

**V3 Key Design Changes from V2:**
- httpOnly cookies instead of Bearer tokens
- Scoped `fm_*` API keys with granular permissions
- Feature-flag gating (`is_auth_v3_enabled`, `is_workspaces_v3_enabled`)
- Middleware scope enforcement (`scope_validator.py`)
- Rate limiting (same as V2: `auth_rate_limiter.py`)

---

## 6. CORE DATA MODEL (44 SQLAlchemy Models)

| Category | Models |
|----------|--------|
| **User/Identity** | users, auth_sessions, auth_api_keys, oidc_provider_configs |
| **Organization** | workspaces, workspace_activity_log, teams, subscriptions |
| **Agent** | agents, agent_templates, agent_registry, capability_tokens, capability_catalog |
| **Mission** | missions, mission_tasks, mission_logs, mission_advanced, mission_improvements |
| **Chat** | chat_threads, chat_messages, chat_folders |
| **Graph/Flow** | graphs, graph_executions, graph_states |
| **Swarm** | swarms, swarm_pipelines |
| **Memory/Learning** | memories, learning_rules, adaptation_rules |
| **Marketplace** | marketplace_listings, community_templates |
| **Business** | subscriptions, partner_revenue, analytics_events, idempotency_keys |
| **Notification** | notifications, push_subscriptions, webhook_subscriptions |
| **Tool** | tools, tool_registrations |
| **Infrastructure** | feature_flags, audit_log, feedback, evaluation |
| **Auth V3** | auth_v3_models (auth_cookies, auth_sessions_v3) |
| **BYOK** | byok_models (user_api_keys) |
| **Plugin** | plugin_models, binding_models |
| **HITL** | hitl_models, circuit_breaker_models |
| **I/O** | io_models, materialization_models, phase4_models |

### Migration Chain
- Alembic in `/opt/flowmanner/backend/alembic/`
- Current head includes `workspaces_v3_001` (applied after `auth_v3_001`)
- Migration state: `docker compose exec backend alembic current`

---

## 7. AUTH & SECURITY

### Auth Stack
- **NextAuth.js v5** (auth.js) — JWT session strategy, server-side
- **Dual auth** (now unified): NextAuth JWT cookie (primary) + historical `fm_tokens` localStorage (removed)
- **Zustand auth store** wraps NextAuth with polling + exponential backoff

### Providers
| Provider | Condition | Endpoint |
|----------|-----------|----------|
| GitHub OAuth | `AUTH_GITHUB_ID` + `AUTH_GITHUB_SECRET` | GitHub OAuth flow (primary) |
| Credentials | Always | `POST /api/auth/login` (email/pw) |
| OIDC | V3 feature flag | `/api/v3/auth/oidc` (stub) |

### Middleware Protection
- 23+ protected routes: `/dashboard`, `/chat`, `/agents`, `/models`, `/knowledge`, `/settings`, `/profile`, `/team`, `/missions`, `/analytics`, `/marketplace`, `/browser`, `/admin`, etc.
- Unauthenticated → redirect to `/{locale}/signin?from={path}`
- Order: auth check runs BEFORE intlMiddleware

### Custom NextAuth Routes
| Route | File | Purpose |
|-------|------|---------|
| `GET /api/auth/session` | `session/route.ts` | Returns `{authenticated, accessToken, user}` |
| `GET/PATCH/DELETE /api/auth/me` | `me/route.ts` | Proxies user profile to backend |
| `POST /api/auth/register` | `[...nextauth]/route.ts` | Registration before NextAuth |
| `GET/POST /api/auth/*` | `[...nextauth]/route.ts` | NextAuth built-in handlers |

### Backend Auth
- `POST /api/auth/login` → returns `{access_token, refresh_token, user?}`
- `GET /api/auth/me` → user profile with Bearer token
- JWT tokens, PyJWT 2.8 + passlib
- 2FA support (pyotp)

### Known Auth Issues (Fixed)
- **401 infinite loop** — H1 exit gate MET (2026-06-01). `/api/auth/session` returns 200+null for unauth.
- **Field name mismatch** — `access_token` vs `accessToken` caused months-long navbar bug.
- **Stale NextAuth session** — Must pair `authApi.logout()` with `await signOut({redirect: false})`.
- **Polling concern** — 14 calls to `/api/auth/session` per page load. Deferred to P5.

### V3 Auth Migration
- httpOnly cookie sessions replacing Bearer tokens
- Scoped `fm_*` API keys with granular permissions (Phase 1)
- Feature-flag gated behind `is_auth_v3_enabled`
- Rate limiting: `auth_rate_limiter.py`

---

## 8. EXECUTION ENGINES (7 strategies)

| Strategy | Pattern | File | When Used |
|----------|---------|------|-----------|
| **Solo** | Serial task loop | `mission_executor.py` | Simple single-agent missions |
| **DAG** | Topological layers (Kahn's algorithm) | `dag_executor.py` (179 LOC) | Dependency-ordered parallel tasks |
| **Swarm** | Hub-and-spoke (decompose → dispatch → synthesize) | `swarm/orchestrator.py` (331 LOC) | Parallelizable sub-tasks |
| **Swarm Pipeline** | State machine with debate | `swarm_pipeline/orchestrator.py` (199 LOC) | Multi-agent coordination with consensus |
| **Graph** | Visual node-and-edge execution | `graph_executor.py` | User-defined workflows |
| **LangGraph** | StateGraph with human-in-the-loop | `langgraph/agent.py` | Complex stateful workflows |
| **Nexus (Meta)** | Recursive planning/execution/self-correction | `nexus/orchestrator.py` (460 LOC) | Self-healing meta-orchestration |

### Mission Executor Architecture (after Phase 3 refactor)
The `MissionExecutor` was decomposed into 5 modules (ADR-001):
| Module | LOC | Responsibility |
|--------|-----|----------------|
| `cost_tracker.py` | 82 | LLM cost estimation and call recording |
| `llm_executor.py` | 165 | LLM-based task execution with agent prompts |
| `browser_task_runner.py` | 97 | Browser automation tool dispatch |
| `mission_planner.py` | 395 | LLM-driven plan generation |
| `task_executor.py` | 506 | Task execution across all backends |

`MissionExecutor` itself is now ~580 LOC as a pure orchestrator.

### Execution Router
- `flow/execution_router.py` (287 LOC)
- Keyword-based goal routing → dispatches to Mission, Workflow, or General AI executor

---

## 9. AGENT SYSTEM

### Architecture
- **Agent Registry** (`agent_registry_service.py`) — Capability matching, discoverability
- **Agent Templates** — Predefined agent configurations
- **Agent Personalities** — Behavioral configuration per agent
- **Agent Capabilities** — `capability_tokens`, `capability_catalog`, OCap security model
- **Domain Agents** — Specialized: biotech, finance, legal (each with `base_domain_agent.py` pattern)
- **A2A Protocol** — Agent-to-Agent communication (`a2a/a2a_server.py`)
- **Marketplace** — 50+ agents across 10 categories

### Agent Catalog (50 predefined personalities)
10 domains × 5 agents each:
- Customer Service, Finance, Healthcare, HR, Legal, Marketing, Media/Creative, Operations, Sales, Software/IT

Each agent has: `id`, `domain`, `name`, `description`, `color`, core competencies, behavioral rules.

### Agent Capability Lattice (H2.3 ✅ COMPLETE)
- `capability_lattice.py` — max_depth invariant on every composition
- Static analysis detects loops that exit on string match
- Loop composition requires `termination_condition` in 3 acceptable categories
- Halting proof sketches for all 4 composition types
- String-based exit conditions rejected at composition time

### Agent Identity Model
- 🔴 WEAKNESS IDENTIFIED: No unforgeable agent IDs
- Not addressed in V3/V4 migrations yet

---

## 10. OBSERVABILITY & MONITORING

### Stack
- **Jaeger** — Distributed tracing (all-in-one container)
- **OpenTelemetry** — Instrumentation (OTLP endpoint → Jaeger)
- **Langfuse** — LLM observability (cloud or self-hosted)
- **Sentry** — Error tracking
- **Prometheus** — Metrics (4 SLO gauges with 60s periodic refresh)
- **structlog** — Structured logging

### SLO Dashboard (4 panels)
| Panel | Metric | Target | Alert Threshold |
|-------|--------|--------|----------------|
| Mission success rate | `flowmanner_slo_compliance_ratio{slo_name="mission_success_rate"}` | > 95% | < 85% |
| p99 SSE latency | `sse_token_latency_p99` | p99 < 300ms | > 500ms |
| Model fallback success | `model_fallback_success` | > 99% | < 95% |
| Deploy success rate | `deploy_success_rate` | > 99% | < 95% |

### Alert Channels
- Configurable via `NOTIFY_CHANNELS` env var (csv)
- Supported: webhook (Slack/Discord), ntfy, email (placeholder), PagerDuty (placeholder)
- Debounce via `ALERT_COOLDOWN_SECONDS` (default 300s)
- Per-channel failure is non-fatal

### Gaps
- ntfy integration incomplete (P4.1 planned)
- Langfuse dashboard deployment status unconfirmed (P4.2 planned)
- Zero production monitoring detected across all 3 machines (H1.5 audit)

---

## 11. LLM ROUTING (3-Layer Architecture)

### Layer 1: LLM Router (`llm_router.py` — 316 LOC)
- AsyncOpenAI-based
- BYOK override
- Provider resolution (`PROVIDER_MAP` in `chat_service.py`)

### Layer 2: Model Router (`model_router.py` — 617 LOC)
- Local-first / cost-optimized / performance strategies
- Health tracking
- Provider availability checks
- Silent failure bug (H1.1 — ✅ FIXED)

### Layer 3: Cost-Aware Router (`cost_aware_router.py` — 702 LOC)
- Task complexity classification: SIMPLE / MEDIUM / COMPLEX / CRITICAL
- Per-model cost tracking
- Budget enforcement

### BYOK Providers (V1 API)
| Provider | Supported |
|----------|-----------|
| DeepSeek | ✅ |
| OpenAI | ✅ |
| Anthropic | ✅ |
| OpenRouter | ✅ |
| Google AI | ✅ |
| Groq | ✅ |
| Together AI | ✅ |
| Fireworks AI | ✅ |
| DeepInfra | ✅ |
| xAI | ✅ |
| OpenAI Compatible (Custom) | ✅ (configurable base URL) |

### Provider Resolution (`chat_service.py`)
- `PROVIDER_MAP` maps provider → (base_url, default_key)
- `_normalize_provider()`: hyphens → underscores, lowercase
- `_get_upstream_model_name()`: strips provider prefix
- `OPENAI_PROVIDER_FAMILIES = frozenset(("openai", "openai_compatible"))`

---

## 12. SELF-IMPROVEMENT & LEARNING (16 files)

### Architecture
| Service | File | Lines | Purpose |
|---------|------|-------|---------|
| `improvement_loop_v2` | `services/improvement/improvement_loop_v2.py` | 866 | Autonomous improvement: failure → causal decomposition → hypothesis → test → apply |
| `causal_decomposer` | `services/improvement/causal_decomposer.py` | — | Root cause analysis from failure telemetry |
| `hypothesis_tester` | `services/improvement/hypothesis_tester.py` | — | Verify improvement strategies before applying |
| `knob_manager` | `services/improvement/knob_manager.py` | — | Configurable parameter tracking with rollback |
| `knowledge_graph` | `services/improvement/knowledge_graph.py` | — | Persistent what-works graph |
| `strategy_evolution` | `services/improvement/strategy_evolution.py` | — | Strategy mutation and selection |
| `success_learner` | `services/improvement/success_learner.py` | — | Learn from successes, not just failures |
| `temporal_analyzer` | `services/improvement/temporal_analyzer.py` | — | Time-pattern detection in failures |
| `proactive_scheduler` | `services/improvement/proactive_scheduler.py` | — | Schedule improvement cycles |

### Error Taxonomy (Two Parallel Systems)
1. **Nexus ErrorClass** (9 types, budget-bounded): TIMEOUT, VALIDATION, RESOURCE, LOGIC, NETWORK, PERMISSION, NOT_FOUND, RATE_LIMIT, UNKNOWN
2. **Improvement FailureType** (16 types, heuristic): TOOL_API_ERROR, TOOL_TIMEOUT, RESOURCE_EXHAUSTION, CONNECTION_FAILURE, RATE_LIMITED, SERVICE_UNAVAILABLE, TOOL_INVALID_INPUT, TOOL_INVALID_OUTPUT, LLM_HALLUCINATION, LLM_REFUSAL, LLM_INSTRUCTION_DRIFT, CONTEXT_OVERFLOW, RETRIEVAL_MISS, WORKFLOW_DEPENDENCY_FAIL, AGENT_COORDINATION_FAIL, UNKNOWN

### Error Class Budgets (H2.2 ✅ DEFINED, ⚠️ UNWIRED)
| Error Class | Max Retries | Wall-Clock | Max Cost |
|-------------|-------------|------------|----------|
| TIMEOUT | 5 | 600s | $0.50 |
| VALIDATION | 1 | 60s | $0.10 |
| RESOURCE | 3 | 120s | $0.25 |
| LOGIC | 1 | 30s | $0.10 |
| NETWORK | 5 | 300s | $0.50 |
| PERMISSION | 0 | 0s | $0.00 |
| NOT_FOUND | 2 | 60s | $0.10 |
| RATE_LIMIT | 5 | 600s | $0.50 |
| UNKNOWN | 1 | 120s | $0.25 |

**Gap:** `MetaLoopOrchestrator` does not call `can_retry`/`check_budget` — budgets exist but unwired.

---

## 13. NEXUS META-ORCHESTRATION (22 files)

Central coordination, capability discovery, cross-system chaining.

### Key Services
| Service | Lines | Purpose |
|---------|-------|---------|
| `orchestrator.py` | 460 | Central orchestration, capability discovery |
| `meta_loop_orchestrator.py` | — | Meta-level orchestration loop |
| `capability_registry.py` | — | Everything registers what it can do |
| `capability_composer.py` | — | Composition of capabilities |
| `capability_lattice.py` | — | Depth invariants, halting proofs |
| `execution_planner.py` | — | AI execution planning |
| `ai_execution_planner.py` | — | AI-driven execution planning |
| `distributed_executor.py` | — | Multi-service execution |
| `cost_optimizer.py` | — | Cross-system cost optimization |
| `failure_analyzer.py` | — | Error classification with budgets |
| `marketplace.py` | — | Tool/agent marketplace |
| `security.py` | — | Capability security model |
| `tracing.py` | — | Distributed tracing |
| `context_builder.py` | — | Knowledge integration |
| `memory_integration.py` | — | Memory integration |
| `observability.py` | — | Monitoring |

---

## 14. SWARM ORCHESTRATION

### Swarm Services
| Service | Lines | Purpose |
|---------|-------|---------|
| `orchestrator.py` | 331 | Goal → Decompose → Match → Dispatch → Synthesize |
| `debate_protocol.py` | — | Two-agent argument rounds (max 5) |
| `handoff_protocol.py` | — | Task delegation (priority, accept/complete/reject) |
| `escalation_chain.py` | — | Failure escalation (default/aggressive/conservative/never) |

### Swarm Pipeline (7-phase)
`swarm_pipeline/orchestrator.py` (199 LOC):
Dispatch → Research → Draft → Debate → Review → Consensus → Synthesis

---

## 15. SUBSTRATE (Event-Sourced Engine — V2)

**Status: IMPLEMENTED BUT UNTESTED.** Full module exists but zero tests, DB-level trigger unverified.

### Components
- `SubstrateEvent` model — sequence, run_id, timestamp, type, payload, causal_parent, actor
- `EventLog` — append-only, SERIALIZABLE isolation, claims DB-level trigger
- `RunState` (SubstrateRunState) — projection for ReplayEngine
- `ReplayEngine` — deterministic replay from any checkpoint with same model+seed
- `ExecutorV2` — runs alongside mission_executor.py, writes events per state transition
- All 7 strategies ported (solo, dag, swarm, pipeline, graph, langgraph, meta)
- Feature flag: `FLOWMANNER_SUBSTRATE_V2=run` (gates TriggerBridge vs legacy TriggerScheduler)

### Gaps (H2.1)
- DB-level `BEFORE UPDATE OR DELETE` trigger NOT verified — claimed in `event_log.py:10` comment but no migration found
- Zero substrate tests
- No 1000-node performance benchmark
- No chaos test (`test_kill_worker_mid_mission` does not exist)
- `_resume_run()` exists but unverified

---

## 16. RAG PIPELINE

| Service | File | Purpose |
|---------|------|---------|
| Chunking | `rag/chunking_service.py` | Document → chunks with metadata |
| Embedding | `rag/embedding_service.py` | Vector embedding generation |
| Vector Store | `rag/vector_store.py` | Qdrant upsert/search per-user isolation |
| Retrieval | `rag/retrieval_service.py` | Semantic search |
| Prompt Synthesis | `rag/prompt_synthesizer.py` | Context-augmented prompt generation |
| Coordination | `rag_service.py` | High-level RAG coordination |
| Memory | `memory_service.py` | Semantic memory, episodic memory |

---

## 17. INTEGRATIONS & CONNECTORS

### Native Connectors (6)
| Connector | File | Auth | Capabilities |
|-----------|------|------|-------------|
| Linear | `connectors/linear_connector.py` | OAuth | Full bidirectional sync, webhooks |
| Discord | `connectors/discord_connector.py` | Bot Token | Server/channel operations |
| Slack | `connectors/slack_connector.py` | OAuth | Message posting, channel monitoring |
| GitHub | `connectors/github_connector.py` | OAuth | Repo access, issues, PRs |
| Google | `connectors/google_connector.py` | OAuth | Drive, Docs |
| Notion | `connectors/notion_connector.py` | Integration Key | Pages, databases |
| Email | `connectors/email_connector.py` | SMTP/IMAP | Email sending/receiving |
| Webhook | `connectors/webhook_connector.py` | — | Outgoing webhook delivery |

**Manager:** `connectors/manager.py` — connector lifecycle, registration

### Other Integrations
- **Stripe** — Payment processing
- **Resend** — Email delivery
- **SearXNG** — Self-hosted web search (DuckDuckGo + SearXNG dual provider in web_search/)

---

## 18. DEPLOYMENT & CI/CD

### Deployment Workflow (Manual)
```
Developer edits on Homelab →
  Frontend: `bash /opt/flowmanner/deploy-frontend.sh` (~4 min)
    → rsync to VPS → docker compose build → docker compose up → nginx restart
  Backend: `bash /opt/flowmanner/deploy-backend.sh` (~2 min)
    → pre-deploy health → image backup → build → restart → health check → auto-rollback
  All: `bash /opt/flowmanner/deploy-all.sh`
```

### Three Local Commands (`~/.local/bin/`)
| Command | What it does |
|---------|-------------|
| `dev` | Start Next.js dev server (systemd user service) |
| `wip` | Silent local save-point (no push, no deploy) |
| `ship` | Only way to prod — commits dirty files, pushes origin, deploys frontend |

### CI/CD Gaps
- ❌ **No CI pipeline** — no GitHub Actions, no automated testing before deploy
- ❌ **No automated security updates** — pacman not automated, no fail2ban (until P5.4)
- ❌ **Single backup cron** — only langfuse-backup.sh (P4.3 planned)
- ❌ **Backend Dockerfile is single-stage** (not multi-stage as documented in AGENTS.homelab.md)

### Docker Hygiene (After P5.1)
- **Before:** 35 images, 527.1GB, 80% disk
- **After:** 11 images, 48.45GB, 57% disk (**+418GB reclaimed**)
- Remaining orphaned volumes: 219.8GB (not yet pruned)
- Build cache: 545.1GB (not yet pruned)

---

## 19. TEST COVERAGE

### Backend Tests (52 test files)
Location: `/opt/flowmanner/backend/app/tests/`

**Test counts by category (from directory listing):**
- Auth: test_auth_api.py, test_auth_v3_integration.py, test_auth_v3_unit.py
- Model Router: test_model_router.py, test_h1_1_model_router_silent_failure.py, test_wave1_model_router_error_chain.py, test_integration_model_router.py
- Mission: test_mission_api.py, test_mission_advanced_api.py, test_mission_executor.py, test_mission_execution_api.py, test_mission_lifecycle.py, test_mission_planner.py, test_mission_handlers.py, test_mission_active.py, test_mission_code_sandbox.py, test_mission_cqrs.py
- Connectors: test_slack_adapter.py, test_github_connector.py, test_google_connector.py, test_notion_adapter.py, test_linear_adapter.py, test_discord_connector.py, test_github_adapter.py, test_google_drive_adapter.py
- DAG: test_dag_executor.py, test_dag_executor.py
- Health: test_health.py, test_health.py
- Chat: test_chat_service_byok.py, test_chat_streaming.py, test_integration_byok_streaming.py
- Graph: test_graph_executor.py
- Evaluation: test_evaluation.py
- Phase: test_p1_p2_fixes.py, test_phase3_finalize.py, test_phase4_finalize.py, test_phase5_finalize.py
- Others: test_agent_api.py, test_agent_memory.py, test_agent_protocol.py, test_alerting_channels.py, test_audio_*, test_bootstrap.py, test_byok_api.py, test_classify_route_workflow.py, test_close_missions.py, test_cost_engine.py, test_cross_workspace_shares.py, test_cqrs_integration.py, test_dashboard.py, test_disaster_recovery.py, test_edge_cases.py, test_entity_versioning.py, test_entity_versioning_integration_pg.py, test_event_sourced_state.py, test_failure_analyzer_budgets.py, test_h1_3_observability_abort.py, test_human_interrupt_primitives.py, test_import_bindings.py, test_importers.py, test_integration_bridge.py, test_llm_config.py, test_llm_executor.py, test_partner.py, test_proxy_chain.py, test_social_token.py, test_subscription.py, test_task_executor.py, test_usage_api.py, test_usage_middleware.py, test_usage_service.py, test_validation_middleware.py, test_workspace_v3_unit.py, test_wave3_comprehensive.py

**Major gaps:**
- ❌ **Zero substrate tests** — no `test_substrate*`, `test_event*`, `test_executor*` files
- ❌ **Zero chaos tests** — no `test_kill_worker_mid_mission`
- ❌ No CI pipeline to run tests automatically
- Test count is large but spread unevenly
- `test_h1_3_observability_abort.py` exists (from H1 work)

### Frontend Tests
- **Unit/Component:** Vitest, jsdom, in `src/**/*.test.{ts,tsx}`
- **E2E:** Playwright, in `e2e/`, runs against localhost:3000
- **Known state (2026-06-01):** 49 tests, 14 pass, 32 pre-existing failures

---

## 20. CURRENT ROADMAP STATUS (P1-P6 + H1/H2)

### Sequencing Principle
> Fix what blocks → Test what exists → Build what's missing

### H1 (Q3 2026) — ✅ Mostly Complete
| Item | Status | Detail |
|------|--------|--------|
| H1.1 — ModelRouter silent failure | ✅ FIXED | `user_id` param, error handling, E2E tests |
| H1.2 — Unify dual auth | ✅ COMPLETE | `fm_tokens` eliminated (3 archival refs remain) |
| H1.3 — Mission executor observability + abort | ✅ COMPLETE | State transitions logged, LLMCallRecord, Mission.abort |
| H1.4 — Browser agent hardening | ✅ COMPLETE | Iteration budget, cost budget, screenshot persistence |
| H1.5 — SLOs + observability | ⚠️ PARTIAL | 4 SLOs defined, Prometheus gauges, Langfuse dashboards unclear |
| H1.6 — Single-machine dev | ✅ COMPLETE | `dev/docker-compose.dev.yml` — self-contained |

**H1 exit gate: MET at HTTP level** (401 loop fixed, but 14 calls/page polling remains)

### H2 (Q4 2026–Q1 2027) — Partial
| Item | Status | Remaining Work |
|------|--------|---------------|
| H2.1 — Event-sourced substrate | ⚠️ Implemented, untested | DB trigger migration + full test suite |
| H2.2 — Error class budgets | ✅ Defined, ⚠️ unwired | Wire MetaLoopOrchestrator → budget checks |
| H2.3 — Capability depth proof | ✅ Complete | — |
| H2.4 — Trigger scheduler event-driven | ⚠️ 2s polling | Implement PG LISTEN/NOTIFY or Redis pubsub |

### P1 (Unblock H1 Exit Gate)
- P1.1 — `/api/auth/session` 401 fix ✅ DONE
- P1.1b — Reduce session polling 14→2 calls ⏳ DEFERRED to P5
- P1.2 — Diagnose 6 broken pages 📋 OPEN
- P1.3 — Remove `fm_tokens` cleanup 📋 OPEN

### P2 (Test the Substrate) 📋 OPEN
- P2.1-P2.6 — Substrate event log, replay engine, executor V2, chaos, capability, budget tests
- P2.7 — CI pipeline

### P3 (Wire & Harden Substrate) 📋 OPEN
- P3.1 — DB trigger migration for append-only
- P3.2 — Wire MetaLoopOrchestrator → failure_analyzer budgets
- P3.3 — Replace 2s polling with PG LISTEN/NOTIFY

### P4 (Observability) 📋 OPEN
- P4.1 — ntfy integration
- P4.2 — Langfuse dashboard verification
- P4.3 — Backup cron jobs

### P5 (V1 Polish) — ✅ Mostly Complete (P5.3 BLOCKED)
- P5.1 — Docker image hygiene ✅ DONE (+418GB reclaimed)
- P5.2 — nginx-static health ✅ ALREADY HEALTHY
- P5.3 — Ops machine failed units ✅ DONE (machine reachable, 3 failed units cleared, 0 remaining)
- P5.4 — fail2ban ✅ RUNNING

### P6 (V2: Memory + HITL + Cost) 📋 OPEN
- P6.1 — Episodic memory consolidation worker
- P6.2 — Human-in-the-loop primitives
- P6.3 — Cost attribution engine
- P6.4 — Circuit breaker wiring

### Deferred (V3+ / Never)
- Federation protocol ❌ YAGNI
- Neo4j graph DB ❌ Postgres + Qdrant suffice
- YAML agent DSL ❌ Python is fine
- Procedural memory ❌ agent capability registry works
- Multi-modal agent input ❌ text-only for V1

---

## 21. KNOWN WEAKNESSES & OPEN QUESTIONS

### Critical (from DeepSeek Architecture Audit)
| # | Weakness | Status |
|---|----------|--------|
| W1 | Session management broken (401 loop) | ✅ FIXED |
| W2 | 31% page failure rate (6/19 pages) | ❌ OPEN |
| W3 | Zero production monitoring | ⚠️ PARTIAL |
| W4 | Single backup cron job | ⚠️ PARTIAL |
| W5 | No CI/CD pipeline | ❌ OPEN |
| W6 | No automated security updates | ⚠️ PARTIAL (fail2ban running) |
| W7 | 14 idle Docker services (50GB+) | ✅ 418GB RECLAIMED |
| W8 | 3,000+ failed systemd units on ops | ✅ RESOLVED (3 units cleared: chromium-cdp masked, drkonqi masked, krfb disabled) |
| W9 | nginx-static unhealthy | ✅ ALREADY HEALTHY |
| W10 | WireGuard as single point of failure | ❌ OPEN |

### Architectural Weaknesses
| # | Weakness | Status |
|---|----------|--------|
| W11 | No event sourcing / execution replay | ⚠️ Built, untested (substrate exists) |
| W12 | No deterministic LLM testing | ❌ OPEN |
| W13 | No agent output evaluation framework | ❌ OPEN |
| W14 | Flow vs Graph consolidation | ❌ OPEN |
| W15 | Workspace vs Tenant redundancy | ❌ OPEN |
| W16 | No unforgeable agent IDs | ❌ OPEN |
| W17 | Marketplace viability | ❌ OPEN |
| W18 | Learning loop is write-only | ❌ OPEN |

### Open Questions for Brainstorming
1. How much of the Omega spec (18 invariants, 5-horizon roadmap) has been implemented vs designed?
2. Nexus ErrorClass (9 types) vs Improvement FailureType (16 types) — unified, bridged, or siloed?
3. Flow vs Graph — has any consolidation begun?
4. Workspace vs Tenant — migration status?
5. Marketplace — partially implemented; current operational status?
6. Learning loop — decay-weighting and A/B validation status?
7. Auth v3 rollout — percentage deployed?
8. Chaos test harness — does test suite exist?

---

## 22. FRONTEND COMPONENT CATALOG (28 directories)

| Component Dir | Purpose |
|--------------|---------|
| `analytics/` | Usage analytics charts and dashboards |
| `approvals/` | Workspace approval flows |
| `auth/` | Sign-in, credentials form |
| `blog/` | Blog page components |
| `chat/` | SSEChat.tsx (core streaming), FilePreview, ChatMessage components |
| `costs/` | Cost/usage visualization |
| `dashboard/` | Main dashboard widgets |
| `evaluation/` | Evaluation UI |
| `inbox/` | HITL inbox for pending human approvals |
| `integrations/` | Connected services UI |
| `layout/` | Navbar, sidebar, footer |
| `marketplace/` | Agent/flow marketplace cards and detail |
| `mission-builder/` | Visual flow editor with `nodes/` subdirectory |
| `notifications/` | Notification preferences and list |
| `observatory/` | System observability dashboard |
| `onboarding/` | New user onboarding flow |
| `rag/` | SearchBar, document list, knowledge base |
| `seo/` | SEO-related meta components |
| `settings/` | API keys, billing, danger zone |
| `shared/` | Reusable patterns shared across pages |
| `swarm/` | Swarm visualization |
| `templates/` | Template gallery cards |
| `triggers/` | Event trigger configuration |
| `ui/` | Base UI components (buttons, cards, inputs, badges, loader) |
| `workspace/` | Workspace settings and management |

### Chat Architecture
- **Files:** `page.tsx` (SSR) → `page-client.tsx` (state manager, ~243 LOC) → `SSEChat.tsx` (core UI + streaming, ~299 LOC)
- **Streaming:** SSE via `POST /api/chat/threads/{id}/chat/stream` → `data:` events
- **Slash commands:** Flat `if/else` chain in SSEChat.tsx:93-115 — currently only `/integrations` exists
- **No command registry** — no `/help`, no argument parsing

### Browser Feature
- `/browser` (~500 LOC) — Manual browser controls (navigate, snapshot, click, type, scroll)
- `/tools/browser` (~1300 LOC) — Full AI chat-driven browser agent + manual controls + settings panel
- Backend: Playwright-based, self-healing clicks (coordinate fallback)
- Agent loop: 15 iterations, max_tokens=1000, 300s session timeout

---

## 23. FRONTEND ZUSTAND STORES (5 stores)

| Store | File | Purpose |
|-------|------|---------|
| `auth-store.ts` | Wraps NextAuth, polls `getSession()` with exponential backoff | Auth state, user profile |
| `chat-store.ts` | Chat state management | Messages, threads, streaming state |
| `inbox-store.ts` | Pending HITL interrupts | Approve/deny actions |
| `notification-store.ts` | Real-time notifications via SSE | Unread count, notification list |
| `workspace-store.ts` | Active workspace state | Workspace CRUD, member list |

---

## 24. FRONTEND DASHBOARD ROUTES (19+ pages)

| Route | Feature | Key API | Status |
|-------|---------|---------|--------|
| `/chat` | AI Chat (hub) | `POST /api/chat/threads/{id}/chat/stream` | ✅ Working |
| `/rag` | RAG Knowledge Base | `POST /api/memory/search` | ✅ Working |
| `/files` | File Manager | `GET /api/files`, `GET /api/files/{id}/download` | ✅ Working |
| `/graphs` | Graph Workflows | `GET /api/graphs`, `POST /api/graphs/{id}/execute` | ✅ Working |
| `/graphs/{id}/executions` | Execution History | `GET /api/graphs/{workflow_id}/executions` | ✅ Working |
| `/missions` | Missions List | `GET /api/missions`, `POST /api/missions/{id}/execute` | ✅ Working |
| `/missions/builder` | Visual Flow Editor | Internal SDK | ✅ Working |
| `/templates` | Template Gallery | `GET /api/templates` | ❌ Broken |
| `/triggers` | Triggers | `GET /api/triggers`, `PATCH /api/triggers/{id}` | ✅ Working |
| `/analytics` | Usage Analytics | `GET /api/v1/usage/summary` | ❌ Broken |
| `/agents` | Agent Catalog | `GET /api/agents` | ✅ Working |
| `/marketplace` | Marketplace | `GET /api/marketplace/listings` | ✅ Working |
| `/notifications` | Notifications | `GET /api/users/me/notifications` + SSE | ✅ Working |
| `/team` | Team Management | SDK: TeamsService, MembershipsService, InvitationsService, WorkspaceService | ✅ Working |
| `/feedback` | Feedback | FeedbackService | ✅ Working |
| `/settings/*` | Settings | `GET/PATCH /api/users/me` | ✅ Working |
| `/admin/*` | Admin Panel | AdminService | ❌ Broken (6 pages broken) |
| `/models` | Models/BYOK | — | ❌ Broken |
| `/profile` | Profile | — | ❌ Broken |
| `/blog` | Blog | — | ❌ Broken |
| `/dashboard` | Dashboard | — | ✅ Working |
| `/browser` | Browser | BrowserApi | ✅ Working |
| `/tools/browser` | AI Browser | BrowserApi + Chat | ✅ Working |

**6 broken pages per DeepSeek audit:** Models, Templates, Analytics, Blog, Profile, Admin.

---

## END OF SPECIFICATION

*This document was compiled from live reconnaissance of all 3 machines, 10+ reference documents, 52 test files, 44 model files, 74 V1 route modules, 77 service files, 19 dashboard pages, 5 Zustand stores, 28 component directories, Docker infrastructure, deploy scripts, Makefile, ADR-001, and all 3 AGENTS files.*
