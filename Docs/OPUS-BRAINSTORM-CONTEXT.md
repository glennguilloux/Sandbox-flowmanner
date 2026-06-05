# Flowmanner — Brainstorm Context for Opus

**Date:** June 5, 2026
**Purpose:** Compact context for strategic brainstorming. Keep responses opinionated and actionable.

---

## What Flowmanner Is

A **multi-agent AI workflow orchestration platform** with an event-sourced execution substrate. Think "Datadog for AI agents" — the value is in **observability, replay, and control**, not just running agents.

**10-second pitch:** "The only AI workflow platform where you can replay any agent run, debug every decision, and prove your workflows work — all on your own hardware."

---

## Current State (as of today)

### What's Built
- **Event-sourced substrate** — 80% built, append-only event log with 20+ event types, ReplayEngine for time-travel debugging
- **7 execution strategies** — Solo, DAG, Swarm, Pipeline, Graph, LangGraph, Meta (recursive)
- **50+ predefined agents** across 10 domains (Software, Finance, Healthcare, Legal, etc.)
- **Chat-centric UI** — SSE streaming, canvas, code sandbox, branching threads
- **Cost attribution engine** — tracks LLM costs per agent/mission/user/workspace
- **BYOK** — users bring their own API keys (DeepSeek, OpenAI, Anthropic)
- **Local LLM** — Qwen3.6-27B on dual RTX 5060 Ti (~38 tok/s), sovereign deployment
- **Self-improvement subsystem** — error taxonomy (16 types), causal decomposition, hypothesis testing
- **HITL primitives** — backend built (raise/resolve/poll, approval gates), frontend inbox not wired
- **Circuit breakers** — per-mission cost/time/iteration budgets, prevents runaway agents
- **Blueprint+Run migration** — dual-write active, new tables exist, cutover pending

### What's NOT Built / Broken
- **Zero users** — functional but no one is using it
- **Substrate tests** — 186 tests exist and pass, but coverage gaps remain
- **Broken frontend pages** — some pages fail to render (triage needed)
- **No production monitoring** — no ntfy, no backup cron, no CI pipeline
- **HITL frontend** — backend works, inbox UI doesn't exist
- **Marketplace** — listed as a pillar but empty
- **Blueprint+Run cutover** — not completed (reads still on old tables)

### Infrastructure
- **Homelab** (172.16.1.1): Backend (FastAPI), PostgreSQL, Redis, Qdrant, RabbitMQ, Celery, Jaeger, llama.cpp
- **VPS** (74.208.115.142): Frontend (Next.js 16), Nginx, SSL — connected via WireGuard
- **Stack:** FastAPI + Next.js + PostgreSQL + Redis + Qdrant + RabbitMQ + Celery

---

## Strategic Questions for Brainstorming

### 1. The Moat Question
The event-sourced substrate with time-travel replay is genuinely novel — no competitor has it. But it's 80% built and invisible to users. **How do we make the substrate the product, not just infrastructure?**

Key angle: "Replay Assertions" — auto-generating expected behaviors from successful runs and validating future runs against them. This turns testing from a developer task into a product feature.

### 2. The One-Demo Question
We need one mission type that's so compelling it makes someone say "I can't go back." Candidates:
- **Code Review Agent** — paste GitHub PR URL, get structured review
- **Runaway Agent Simulator** — shows circuit breaker stopping a cost spiral, then replays it
- **Research Agent** — multi-source research with full audit trail

**Which demo has the highest "wow factor" per hour of investment?**

### 3. The Kill List
We're drowning in surface area (48 ORM models, 79 page files, 26 component dirs) with zero users. What should we explicitly NOT build?
- Federation protocol (0 instances)
- Neo4j graph DB (Postgres + Qdrant suffice)
- YAML agent DSL (Python is fine)
- Blog, Partner dashboard, Marketplace commission (premature)
- Multi-modal input (text-only is fine for now)

**Is this the right kill list? What's missing? What shouldn't be killed?**

### 4. The Positioning Question
Competitors: n8n (visual workflows), LangChain (framework), CrewAI (multi-agent), AutoGen (research). None have event sourcing, replay, or local inference.

**Should Flowmanner position as:**
- A) "Git for AI workflows" (version, diff, replay) — developer-focused
- B) "The safety net for AI agents" (circuit breakers, cost caps, audit trails) — enterprise-focused
- C) "Sovereign AI on your own hardware" (local inference, data never leaves) — privacy-focused
- D) Something else entirely?

### 5. The Open Source Question
The substrate is our hardest-to-replicate asset. Should we:
- Open-source the replay engine to build community?
- Keep everything closed for competitive advantage?
- Open-core model (open substrate, closed enterprise features)?

### 6. The "iPhone Moment" Question
What specific scenario would make agent orchestration go from "useful for experts" to "everyone needs this"? Is it:
- A UX breakthrough (agent orchestration as intuitive as a spreadsheet)?
- A killer integration (agent workflows inside Slack/Notion/GitHub)?
- A viral use case that demos itself?

### 7. The 90-Day Question
Given everything above, what's the single most important thing to accomplish in the next 90 days? The existing strategic plan says: "Make one flow work end-to-end, then make the substrate visible." Is this right, or is there a bolder bet?

---

## Constraints
- **Solo developer** (Glenn) — no team, limited time
- **Sovereign infrastructure** — homelab-first, no cloud dependency
- **Local LLM available** — Qwen3.6-27B at ~38 tok/s (free inference)
- **Budget-conscious** — cost attribution is a first-class feature, not an afterthought

---

---

## Technical Reference

### API Surface (817 endpoint functions across 2 versions)

**V1 — 70+ route modules:**
admin, agent, agent_capabilities, agent_personalities, agent_registry, analytics, api_keys, audit_log, auth, blog, browser, byok, changelog, chat, circuit_breaker, community, cost_attribution, dashboard, data_export, delegations, domain_agents, evaluation, extensions, feature_flags, feedback, file, flow_compat, graph, health, hitl, integrations, io, linear, llm, llm_advanced, marketplace, memory, mission, mission_advanced, mission_decomposition, newsletter, observability, oidc, onboarding, orchestration, partner, plugins, presence, rag, rate_limits, reliability, roadmap, roles, sandbox, search, sessions, stats, subscription, substrate, swarm, swarm_protocol, templates, tools, triggers, two_fa, usage, users, votes, webhooks, workspace, workspace_activity, workspace_messages, workspace_shares

**V2 — 15 modules:**
agents, auth, blueprints, chat, dashboard, integrations, integrations_actions, integrations_oauth, missions, openapi, rate_limit, regression, runs, search, tier_rate_limit

### Database Schema (48 model files, 60+ ORM classes)

**Core Domain Models:**
```
Users & Auth:      users, auth_sessions, api_keys, oidc_providers, user_oidc_accounts, user_api_keys
Workspaces:        workspaces, workspace_members, workspace_activity_log, workspace_shares
Agents:            agents, agent_templates, agent_versions, agent_registrations, agent_capabilities,
                   agent_memories, agent_messages, agent_tool_bindings
Missions:          missions, mission_tasks, mission_logs, mission_improvements, mission_templates,
                   mission_versions
Blueprints/Runs:   blueprints, runs, blueprint_versions  (new — migration in progress)
Chat:              chat_threads, chat_messages, chat_folders
Graphs:            graphs, graph_executions, graph_states
Swarm:             swarms, swarm_pipelines, swarm_models
Substrate:         substrate_events  (append-only event log with DB trigger)
Capabilities:      capabilities, capability_versions, capability_dependencies, capability_tokens
Tools:             tools, tool_catalog, tool_registrations, tool_analytics
Memory:            memories, knowledge_graph, learning_rules, adaptation_rules
Notifications:     notifications, notification_settings, push_subscriptions
Subscriptions:     subscriptions, partner_revenue
Other:             webhooks, triggers, idempotency_keys, llm_call_records,
                   eval_runs, golden_datasets, eval_test_cases, hitl_records,
                   circuit_breakers, feature_flags, roles, role_permissions,
                   delegations, analytics_events, community_templates,
                   marketplace_listings, blog_posts, feedback, roadmap_items
```

**Key Relationships:**
- User → Workspaces (many-to-many via workspace_members)
- Workspace → Agents, Missions, Chat, Blueprints (all workspace-scoped)
- Mission → MissionTasks (one-to-many, DAG dependencies via `dependencies` JSONB)
- Mission → SubstrateEvents (append-only, keyed by `run_id`)
- Blueprint → Runs (one-to-many, immutable execution instances)
- Agent → CapabilityTokens (unforgeable, attenuable authorization)

### Key Tables (Event-Sourced Substrate)

**`substrate_events`** — The core of the platform:
- `id`, `sequence` (auto-increment), `run_id`, `mission_id`, `task_id`
- `type` (20+ event types: RUN_STARTED, NODE_COMPLETED, LLM_CALL, TOOL_CALL, HUMAN_INTERRUPT, etc.)
- `payload` (JSONB — full context of each event)
- `causal_parent` (links events in causal chains)
- `actor` (who triggered: agent, user, system)
- `timestamp`
- PostgreSQL trigger prevents UPDATE/DELETE (append-only invariant)
- ReplayEngine reads in batches of 1,000 to rebuild state

### Execution Pipeline

```
User Input → ExecutionRouter (keyword analysis)
  → Strategy Selection (Solo|DAG|Swarm|Pipeline|Graph|LangGraph|Meta)
    → UnifiedExecutor.execute()
      → BudgetEnforcer.check_budget() (pre-call)
      → ModelRouter.route_request() (LLM selection: DeepSeek | llama.cpp)
      → BudgetEnforcer.call() (the ONLY path to LLM calls)
      → SubstrateEventLog.append() (immutable event)
      → Node handlers (12 types)
    → Result aggregation
  → MissionStatus update
→ SSE stream to frontend
```

### Self-Improvement Pipeline

```
Execution failure → FailureType.classify() (16 types)
  → FailureRepository.persist()
  → CausalDecomposer.analyze()
  → HypothesisTester.test()
  → KnobManager.apply() (if hypothesis confirmed)
  → KnowledgeGraph.update()
```

### Key Service Files
| Service | Path | Purpose |
|---------|------|---------|
| BudgetEnforcer | `services/budget_enforcer.py` | ONLY path to LLM calls, cost tracking |
| ModelRouter | `services/llm_router.py` | Routes between DeepSeek API + local llama.cpp |
| UnifiedExecutor | `services/substrate/executor.py` | Single executor with 7 pluggable strategies |
| ReplayEngine | `services/substrate/replay_engine.py` | Rebuilds state from event log at any sequence |
| AssertionEngine | `services/substrate/assertion_engine.py` | Validates runs against expected behaviors |
| FailureAnalyzer | `services/nexus/failure_analyzer.py` | 9 error classes with budget-bounded recovery |
| MetaLoopOrchestrator | `services/nexus/meta_loop_orchestrator.py` | Recursive plan-execute-observe loop |
| ImprovementLoopV2 | `services/improvement/improvement_loop_v2.py` | Self-improvement via hypothesis testing |
| HumanInterrupt | `orchestration/human_interrupt.py` | HITL approval/clarification/escalation |
| ChatService | `services/chat_service.py` | Thread/message management, LLM streaming |
| MissionExecutor | `services/mission_executor.py` | Mission lifecycle orchestration |
| CostEngine | `observability/cost_engine.py` | Cost attribution by agent/user/workspace |

### Frontend Structure (Next.js 16 + React 19)
```
src/app/[locale]/(app)/
  dashboard/       — Mission overview, analytics
  chat/            — Primary interface (SSE streaming, branching)
  missions/        — Mission list, detail, execution
  agents/          — Agent catalog, configuration
  flows/           — Visual graph editor (@xyflow/react + elkjs)
  settings/        — User/workspace config, BYOK keys
  marketplace/     — Template browsing (scaffolded, empty)
```

**State Management:** Zustand stores (auth, chat, notification, workspace)
**Data Fetching:** SWR with optimistic updates
**i18n:** next-intl (EN, FR, ES, DE, NL)

---

*Condensed from: CANONICAL-KNOWLEDGE.md, ROADMAP.md, STRATEGIC-90DAY-PLAN.md, BRAINSTORM-DEEP-QUESTIONS-FOR-OPUS.md, OpenAPI schema, model files, backend source*
