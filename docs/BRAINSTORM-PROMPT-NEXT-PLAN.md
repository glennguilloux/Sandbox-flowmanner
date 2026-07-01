# Flowmanner — Next Plan Brainstorm Prompt

> **Instructions:** Copy everything below the `---` line into your frontier LLM. This prompt contains full context about the project's architecture, current state, completed work, known issues, and strategic options. The LLM should produce a detailed, prioritized execution plan for the next 2-4 weeks of work.

---

## ROLE

You are a senior platform architect and technical strategist. I need you to produce a detailed, prioritized execution plan for the next phase of my product, **Flowmanner** — an agentic AI workflow automation platform. I've spent 4 months building it and I'm at a critical inflection point: V1 is production-stable, and I need to decide what to build next to reach product-market fit.

I'm a solo founder/bootstrapper. I have limited time (10-15 hours/week) and need to maximize impact. Every hour spent on the wrong feature is a week of runway lost.

**Produce a plan that is:**
1. Prioritized by user value (not technical elegance)
2. Realistic for a solo developer (no "hire a team" suggestions)
3. Honest about what's worth building vs. what's premature
4. Specific enough to execute immediately (file paths, API designs, implementation order)
5. Critical — tell me what NOT to build and why

---

## WHAT IS FLOWMANNER?

Flowmanner is a **multi-agent AI workflow automation platform** — think "Zapier meets LangChain, but agents are first-class citizens that can be published, monetized, and composed into visual workflows."

### Core Value Proposition
Users create **Missions** (complex tasks) that are decomposed and executed by specialized **Agents**. Agents are composable, shareable via a **Marketplace**, and their execution is fully observable through a **Mission Observatory** with event sourcing and replay.

### Key Differentiators (planned)
1. **Sovereign Infrastructure** — runs on self-hosted hardware (not cloud-dependent)
2. **Cost-Aware Plan Selection** — generates K plan candidates, scores them, auto-selects best value
3. **Full Observability** — every agent action is traced, logged, and replayable
4. **Marketplace** — third-party developers publish agents/tools that users can install
5. **Human-in-the-Loop** — agents can pause and ask for human approval before destructive actions

---

## CURRENT ARCHITECTURE

### Infrastructure (2 machines)

```
Internet → VPS (IONOS, 74.208.115.142) → Nginx :443
  ├── /* → frontend:3000 (Next.js 16.2.6)
  ├── /api/* → WireGuard → Homelab:8000 (FastAPI)
  └── /api/auth/* → frontend:3000 (NextAuth)

Homelab (Arch Linux, i7-11700K, 62GB RAM, 2×RTX 5060 Ti 32GB VRAM):
  - FastAPI backend (Python 3.12)
  - PostgreSQL 16
  - Redis 7
  - Qdrant (vector search)
  - RabbitMQ + Celery workers
  - Jaeger (distributed tracing)
  - llama.cpp (Qwen3.6-27B local LLM)
```

### Tech Stack
- **Frontend:** Next.js 16.2.6, React 19, TypeScript, Tailwind CSS, TanStack Query, React Flow
- **Backend:** FastAPI, SQLAlchemy, Alembic, Pydantic v2, Celery
- **Databases:** PostgreSQL (primary), Redis (cache), Qdrant (vectors), RabbitMQ (message broker)
- **Auth:** NextAuth JWT + v3 cookie-based auth (dual strategy)
- **Observability:** OpenTelemetry, Jaeger, Langfuse, Sentry
- **Deployment:** Docker Compose, bash scripts, no CI/CD

### API Surface
- **812 total routes** across v1 (legacy), v2 (public API), v3 (auth)
- **177 v2 routes** with cursor pagination, tier-based rate limiting, OpenAPI 3.1 spec
- **18 webhook integrations** (GitHub, Slack, Stripe, Jira, Asana, etc.)

### Frontend Pages (~100+ routes)
Dashboard, Missions, Agents, Chat, Marketplace, Costs, Analytics, Blueprints (with CRUD + executions), Mission Builder (React Flow), Mission Observatory (event timeline + plan comparison), Integrations, Developer portal, Admin panel, etc.

---

## WHAT'S BEEN BUILT (completed)

### V1 Phases 1-5 (COMPLETE)
- **P1:** Fixed auth infinite loop, broken pages, cleaned up fm_tokens
- **P2:** Substrate test suite (event log, replay, executor, chaos tests)
- **P3:** DB append-only trigger, orchestrator budget wiring, LISTEN/NOTIFY triggers
- **P4:** Observability (ntfy alerts, Langfuse dashboards, backup crons)
- **P5:** Docker hygiene (446GB reclaimed), fail2ban, ops machine cleanup, nginx health

### Recent Features (June 29 - July 1, 2026)
- **Cost-Aware Plan Selection:** K=3 plan candidates generated (heuristic + 2 LLM personas), scored, auto-selected. `BUDGET_AWARE_PLAN_SELECTION=auto` active in production.
- **Plan Comparison UI:** Frontend component showing candidates side-by-side with quality bars, cost/latency metrics, risk flags. Click-to-select with per-card loading states.
- **Event Bus:** Full pipeline with failure alerts (Slack), analytics endpoint, 18 integration webhooks wired.
- **Trigger Pipeline:** Cron-based triggers with proper cron matching, routed through UnifiedExecutor.
- **My Blueprints CRUD:** Tabbed Browse/Manage interface with create, edit, publish, delete, execute, execution history.
- **Pydantic v2 Migration:** Fixed 235 test failures (forward reference resolution).
- **Test Infrastructure:** 1016 tests passing (was 3553 failed + 79 errors at one point).

### Production Health (as of 2026-07-01)
- 10/10 Docker containers healthy
- Frontend: HTTP 200
- Backend: HTTP 200 (db ok, redis ok, langfuse healthy, LLM healthy)
- Alembic: `20260630_plan_candidates` (head)
- Tests: 1012 passed, 4 failed (plan selection mode edge cases), 3 skipped
- Disk: 47% used (965 GB free of 1.9 TB)

---

## KNOWN ISSUES & WEAKNESSES

### Open Weaknesses (from architecture audit)

| ID | Issue | Severity | Status |
|----|-------|----------|--------|
| W5 | No CI/CD pipeline | HIGH | Open — manual `deploy-backend.sh` / `deploy-frontend.sh` |
| W10 | WireGuard SPOF | MEDIUM | Open — if tunnel drops, entire API surface unreachable |
| W11 | Event sourcing untested | MEDIUM | Partial — built but no replay tests in production |
| W12 | No deterministic LLM testing | MEDIUM | Open — can't reproduce agent decisions |
| W13 | No agent evaluation framework | MEDIUM | Open — no systematic quality measurement |
| W14 | No execution sandbox isolation | HIGH | Open — agents run in-process, not sandboxed |
| W15 | No semantic caching | LOW | Open — repeated similar prompts re-call LLM |
| W16 | No prompt management | LOW | Open — prompts hardcoded in Python |
| W17 | No HITL primitives | MEDIUM | Open — no approval gates for destructive actions |

### Immediate Technical Debt
1. **4 test failures** — caused by `BUDGET_AWARE_PLAN_SELECTION=auto` changing planner code path
2. **No CI/CD** — all deploys are manual bash scripts
3. **WireGuard SPOF** — watchdog script + nginx graceful degradation recommended (25 min fix)
4. **100+ frontend routes** — many are stub pages with no real functionality
5. **v1 API surface** — 634 routes on v1 lack role-based access control

---

## WHAT'S PLANNED BUT NOT BUILT (V2 roadmap)

### Phase 6: Memory + HITL + Cost (4-6 weeks estimated)
1. **P6.1 Episodic Memory** — consolidation worker, Qdrant embeddings, forget policy
2. **P6.2 Human-in-the-Loop** — approval gates, Inbox UI, WebSocket push
3. **P6.3 Cost Attribution** — per-agent billing, workspace-level cost queries
4. **P6.4 Circuit Breakers** — per-mission limits, destructive action policy

### Phase 7: Plugin System (already partially built)
- Plugin runtime + sandbox (9.1-9.6 in NEXT-SESSION.md are marked COMPLETE)
- Custom Node SDK (Python)
- Marketplace integration
- Plugin security scanner
- Visual workflow builder integration (React Flow nodes)

### Explicitly Deferred (V3 / Never)
- ❌ Federation protocol — YAGNI
- ❌ Neo4j — Postgres + Qdrant suffice
- ❌ YAML agent DSL — Python is fine
- ❌ Multi-modal input — text-only for now
- ❌ Agent-to-human rich output — chat is fine for V1

---

## MY CONSTRAINTS

1. **Solo founder** — 10-15 hours/week of focused development time
2. **Bootstrapped** — no external funding, need to reach revenue or break-even
3. **Homelab-first** — can't afford cloud infrastructure, running on personal hardware
4. **No users yet** — the product is built but hasn't been marketed or launched
5. **Technical debt is real** — 634 v1 routes lack RBAC, no CI/CD, manual deploys
6. **Marketplace is empty** — no third-party publishers yet

---

## WHAT I NEED FROM YOU

Produce a detailed plan that answers these questions:

### 1. Strategic Direction
- Should I focus on getting users first (marketing/launch) or build more features first?
- What's the minimum feature set needed to attract early adopters?
- Is the current architecture over-engineered for a product with zero users?

### 2. Prioritized Next Steps (2-4 weeks)
- What are the 3-5 highest-impact things I should build next?
- For each item: what files to modify, estimated effort, expected impact, and success criteria
- What should I absolutely NOT build yet?

### 3. Go-to-Market Strategy
- Who is the ideal first user? (developer? ops team? AI researcher?)
- What's the distribution channel? (Hacker News? Product Hunt? GitHub?)
- Should I open-source it? Freemium? Paid-only?

### 4. Revenue Model
- What's the most realistic path to first dollar?
- Marketplace commission? SaaS subscription? Self-hosted license?
- What pricing tier structure makes sense?

### 5. Technical Priorities
- Should I fix the test failures and WireGuard SPOF first, or ignore them and ship features?
- Is CI/CD worth investing in before having users?
- Should I consolidate the 100+ frontend routes into fewer, polished pages?

### 6. Risk Assessment
- What are the biggest risks to this project succeeding?
- What would make me shut it down?
- What pivot options exist if the current approach doesn't work?

---

## ADDITIONAL CONTEXT

### Competitive Landscape
- **LangChain/LangGraph** — open-source, developer-focused, no visual builder
- **CrewAI** — multi-agent, but no marketplace or observability
- **Zapier** — no-code, but no AI agents, no self-hosting
- **n8n** — open-source workflow automation, but no agent-native design
- **Dify** — open-source LLM app builder, closest competitor but cloud-first

### My Strengths
- Deep technical execution (4 months, 812 API routes, 100+ pages, full observability stack)
- Sovereign infrastructure story (privacy-conscious enterprises)
- Cost-aware plan selection (unique feature)
- Full event sourcing + replay (debugging superpower)
- 18 pre-built integrations (GitHub, Slack, Jira, Stripe, etc.)

### My Weaknesses
- Zero users, zero revenue
- Over-engineered for current stage
- No marketing or distribution
- Technical debt in auth, testing, deployment
- Solo founder = bus factor of 1

---

## OUTPUT FORMAT

Please structure your response as:

1. **Executive Summary** (3-5 sentences: what to do, why, in what order)
2. **Strategic Assessment** (honest evaluation of where I am)
3. **Prioritized Plan** (numbered list, each item with: what, why, effort, impact, files)
4. **What NOT to Build** (explicit list with reasoning)
5. **Go-to-Market Recommendation** (specific, actionable)
6. **Revenue Path** (first dollar timeline and method)
7. **Risk Matrix** (top 5 risks with mitigations)
8. **30-60-90 Day Milestones** (concrete checkpoints)

Be brutally honest. I'd rather hear "this is over-engineered, simplify" than "great work, keep building."
