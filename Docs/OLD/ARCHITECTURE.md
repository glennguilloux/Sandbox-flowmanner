# Flowmanner — Comprehensive Architecture

> Synthesized June 1, 2026 from 38 model files, 67+ route modules, 85+ frontend pages, 40+ service files, and dual-machine infrastructure.

---

## Table of Contents

1. [What Is Flowmanner?](#1-what-is-flowmanner)
2. [Infrastructure](#2-infrastructure)
3. [Backend Data Model](#3-backend-data-model)
4. [Chat UX Architecture](#4-chat-ux-architecture)
5. [Execution Engine](#5-execution-engine)
6. [Nexus — Advanced Execution](#6-nexus--advanced-execution)
7. [LangGraph Integration Layer](#7-langgraph-integration-layer)
8. [Knowledge Flows](#8-knowledge-flows)
9. [Design Principles](#9-design-principles)

---

## 1. What Is Flowmanner?

Flowmanner is a **multi-agent AI workflow automation platform** that lets users define, orchestrate, and execute complex tasks using AI agents — operating individually, in teams, or as coordinated swarms. The system combines a visual flow builder with LLM-powered execution, real-time chat, persistent memory, and a marketplace for sharing agent templates and tools.

### The Five Pillars

| Pillar | Description |
|--------|-------------|
| **Missions** | The unit of work — a goal decomposed into tasks, executed by agents |
| **Agents** | AI entities with personalities, tools, and capabilities that execute tasks |
| **Chat** | The primary human interface — real-time, streaming LLM chat with branching |
| **Graphs / Flows** | Visual workflow definitions (nodes + edges) that agents execute |
| **Marketplace** | A sharing economy for agents, tools, templates, and integrations |

### Secondary Concepts

Swarms, Orchestration, Workspaces/Tenants, Memory, RAG, BYOK, Delegations, Reliability, Learning, Tools, Triggers, Webhooks, Evaluations, Roadmap, Partners, Analytics.

---

## 2. Infrastructure

### Dual-Machine Architecture

```
Internet → VPS (74.208.115.142)
              ├── Nginx (:443, SSL termination)
              │   ├── /api/*  → WireGuard → Homelab (10.99.0.3:8000) FastAPI
              │   ├── /ws     → WireGuard → Homelab (10.99.0.3:8000) WebSocket
              │   ├── /api/auth/* → frontend:3000 (NextAuth)
              │   └── /*     → frontend:3000 (Next.js)

Homelab (172.16.1.1 / 10.99.0.3)
  ├── Backend (FastAPI) — container backend on 10.0.4.6:8000
  ├── PostgreSQL — container workflow-postgres on 10.0.4.2:5432
  ├── Redis — container workflow-redis on 10.0.4.5:6379
  ├── Qdrant — container workflow-qdrant on 10.0.4.3:6333
  ├── RabbitMQ — container workflow-rabbitmq on 10.0.4.9:5672
  ├── Celery Worker + Beat — background task processing
  ├── Jaeger — container jaeger on 10.0.4.7 (distributed tracing)
  ├── Static files — container workflows-static on 10.0.4.8
  └── llama.cpp — bare metal systemd on 0.0.0.0:11434 (Qwen3.6-27B, ~38 tok/s)
```

### Frontend Stack
- **Framework:** Next.js 16.2.6 (App Router, Turbopack)
- **React:** 19.2.4 with React Compiler
- **Auth:** NextAuth v5 + Zustand fm_tokens (dual auth)
- **Styling:** Tailwind CSS 3.4
- **State:** Zustand stores (chat, auth, notification, workspace)
- **Data:** SWR
- **i18n:** next-intl
- **Flow editor:** @xyflow/react + elkjs
- **Testing:** Vitest + Playwright

### Backend Stack
- **Framework:** FastAPI, uvicorn (4 workers)
- **DB:** PostgreSQL 15 (asyncpg), Alembic migrations
- **Cache:** Redis 7
- **Vector store:** Qdrant v1.12.0
- **Observability:** Jaeger + OpenTelemetry + Langfuse
- **LLM:** DeepSeek API (primary), llama.cpp local (Qwen3.6-27B)

### Deployment
```
Frontend: /home/glenn/FlowmannerV2-frontend/ (homelab)
  → rsync → VPS:/opt/flowmanner/frontend/
  → docker compose build frontend → restart nginx (~4 min)

Backend: /opt/flowmanner/backend/ (homelab)
  → docker build -t workflows-backend:restored
  → docker compose up -d --no-deps --force-recreate backend (~2 min)
```

---

## 3. Backend Data Model

### Entity Map (49 Models)

```
Users & Identity (4)
  User, UserAPIKey (BYOK), UserSettings, UserSubscription

Agents (5)
  Agent, AgentTemplate, AgentRegistration, AgentCapability, AgentProtocol

Missions (6)
  Mission, MissionTask, MissionLog, MissionImprovement, MissionTrigger, TriggerLog

Chat (7)
  ChatFolder, ChatThread, ChatMessage, ChatFile, ChatBranch, ChatTemplate, SharedLink

Swarm (5)
  SwarmProfile, SwarmAgent, SwarmTask, SwarmConsensusRound, SwarmPipeline

Graphs & Flows (5)
  Flow, WorkflowRun, GraphWorkflow, GraphExecution, GraphState

Memory & Learning (4)
  Memory, MemorySession, AdaptationRuleDB, LearningFeedbackDB

Tools (5)
  ToolChain, ToolChainExecution, CustomTool, ToolPermission, ToolAnalytics

Organization (9)
  Workspace, WorkspaceMember, Team, TeamMember, WorkspaceInvitation,
  WorkspaceMessage, Tenant, TenantMember, TenantInvitation

Marketplace (5)
  MarketplaceListing, MarketplaceCategory, MarketplaceReview,
  UserInstallation, AgentReview

Infrastructure (8)
  WebhookEndpoint, WebhookLog, IntegrationConnection, FeatureFlag,
  UsageRecord, Notification, NotificationSettings, PushSubscription

Evaluation & Quality (3)
  GoldenDataset, GoldenTestCase, EvalRun

Feedback & Roadmap (5)
  FeedbackReport, FeedbackPattern, RoadmapItem, RoadmapVote, RoadmapComment

Business (3)
  Partner, PartnerRevenue, SubscriptionTier

Other (3)
  UserFile, LogEntry, ComposedCapabilityModel
```

### Ownership Hierarchy

```
User
  ├── Missions → MissionTasks → MissionLogs
  ├── ChatFolders → ChatThreads → ChatMessages, ChatFiles, ChatBranches, SharedLinks
  ├── Agents, AgentTemplates
  ├── Flows → WorkflowRuns
  ├── GraphWorkflows → GraphExecutions → GraphStates
  ├── ToolChains, CustomTools
  ├── WebhookEndpoints → WebhookLogs
  ├── MemorySessions → Memories
  ├── Subscriptions, UserAPIKeys, Notifications, UserFiles
  └── Tenant/Workspace affiliations
```

---

## 4. Chat UX Architecture

### Component Hierarchy

```
ChatLayout.tsx (Shell: sidebars, overlays, responsive)
├── SSEChat.tsx (Orchestrator: wires hooks to components)
│   ├── MessageList.tsx (react-markdown + GFM + math + syntax highlighting)
│   ├── ChatInputArea (inline: textarea + file upload + slash commands)
│   └── Canvas.tsx (visual workspace: text/code nodes, drag positioning)
├── TokenBar.tsx (color-coded: green ≤60%, yellow 60-80%, red >80%)
├── ChatHeader.tsx (model switcher, export, copy all)
└── CodeSandboxPanel.tsx (Python/JS/TS sandbox, 30s default timeout)
```

### Hook Composition

```
SSEChat orchestrates:
  useChatMessages(threadId)  → messages CRUD + optimistic updates + rollback
  useStreaming(threadId)     → SSE stream, 60fps RAF batching, retry with jitter
  useAttachments()           → file selection, drag/drop, validation
  useToolEvents(streaming)   → tool event parsing, throttled 200ms
  useWebSearchToggle()       → web search status
  useCostTracker()           → cost display
  useChatKeyboard()          → keyboard shortcuts
```

### Streaming Engine

```
POST /api/chat/threads/:id/chat/stream
  → SSE (text/event-stream)
  → ReadableStreamDefaultReader + TextDecoder
  → Each token: RAF-batched updateMessage(id, accumulated)
  → Tool events: throttled 200ms, dedup via Set
  → [DONE]: finalize, parse tools, report token usage
  → Retry: max 3, exponential backoff with jitter
```

### Zustand Store (chat-store.ts)

| Domain | Fields |
|--------|--------|
| UI | activeThreadId, sidebarOpen, rightSidebarOpen, isZenMode, sandboxOpen, isMobile |
| Content | messages, threadTitle, branches, sessionStartTime |
| Settings | model, temperature, maxTokens, systemPrompt, BYOK keys (persisted to localStorage) |
| Connectivity | connectionState, isTyping, tokenUsage, connectingStage, runningCount |
| Tools | toolEvents, filesTouched |

### Chat Message Types

```typescript
ChatMessage {
  id, role (user|assistant|system|tool),
  content, timestamp, editedAt,
  streaming, isError,
  tokenCount, model, modelName,
  parentId, branchInfo,
  reactions, attachments[],
  toolEvents[]  // ToolType: read_file|edit_file|write_file|run_command|search|browse|other
}
```

---

## 5. Execution Engine

### Five-Layer Architecture

```
LAYER 1: ROUTING
  ExecutionRouter → keyword analysis → route: mission | workflow | AI

LAYER 2: PLANNING
  Mission: LLM decomposes goal → JSON task plan
  Swarm: LLM decomposes → subtasks with types/dependencies
  Graph: Pre-defined node graph (visual builder)
  Nexus: Q/K/V attention-based semantic agent matching

LAYER 3: ORCHESTRATION (7 execution models)
  Solo:    mission_executor.py — single-agent task loop
  DAG:     decomposition_service.py — topological sort, layer execution
  Swarm:   swarm/orchestrator.py — decompose→match→dispatch→execute→synthesize
  Pipeline: swarm_pipeline/ — 7-phase: DISPATCH→RESEARCH→DRAFT→DEBATE→CONSENSUS→SYNTHESIS→REVIEW
  Graph:   graph_executor.py — Kahn algorithm, parallel nodes per layer
  Nexus:   meta_loop_orchestrator.py — recursive plan-execute-observe-replan
  LangGraph: langgraph/agent.py — StateGraph with human-in-the-loop

LAYER 4: EXECUTION
  Tools: browser (LLM-driven interactive loop), terminal, search, RAG, code sandbox
  Agent resolution: system prompt from AgentTemplate
  Code sandbox: isolated subprocess, restricted builtins, 60s timeout, no network

LAYER 5: LEARNING & IMPROVEMENT
  Feedback: PostgreSQL + Qdrant embeddings (dual persistence)
  Self-improvement: failure analysis → 9 error classes → recovery strategies
  Learning: similarity-based context injection, model recommendation by success rate
  Self-healing: anomaly detection, predictive scaling, auto-recovery (runtime/)
```

### DAG Executor (Kahn's Algorithm)

```
validate_dag(tasks) → error list (reference check + cycle detection via DFS)
topological_sort(tasks) → execution layers (Layer 0 = roots, Layer N = deps satisfied)
get_ready_tasks(tasks) → task IDs with all deps completed
get_downstream(task_id) → transitive dependents (BFS)
```

Tasks within the same layer execute in parallel via `asyncio.gather`.

### Mission Executor

```
execute_mission(mission, db):
  plan = LLM plan_mission(mission)
  while not all_tasks_terminal():
    ready = get_ready_tasks(tasks)
    for task in ready:
      system_prompt = resolve_agent_prompt(task.assigned_agent_id)
      result = execute_task(task, system_prompt)
      if success: task.status = completed
      elif is_retryable: retry_count++, task.status = pending
      else: task.status = failed, apply_fallback(human_escalate | abort)
```

### Execution Models Compared

| Model | Planning | Execution | Consensus | Best For |
|-------|----------|-----------|-----------|----------|
| Solo Mission | LLM plan | Serial task loop | None | Simple goals |
| DAG Mission | Manual decomposition | Topological layers, parallel | None | Complex workflows |
| Swarm | LLM decompose | Hub-and-spoke | Synthesis-time conflict resolution | Multi-agent |
| Swarm Pipeline | 7-phase state machine | Sequential + debate loop | Consensus round + REVIEW→DEBATE retry | High-quality output |
| Graph Workflow | Visual builder | Kahn layers, parallel nodes | None | Pre-defined flows |
| Nexus | AI semantic matching | Distributed Celery DAG | Meta-cognitive replan | Cross-system |
| LangGraph | StateGraph definition | Checkpointed graph | Human-in-the-loop | Complex automations |

### Trigger Scheduler

Background asyncio task, ticks every 30 seconds. Processes due cron triggers and matches inbound webhook paths to registered endpoints.

### Browser Agent

LLM-driven interactive loop (max 15 iterations): build context (system prompt + request + page state) → LLM returns JSON action (navigate, snapshot, click, type, scroll, done) → execute on browser. Screenshot-based feedback.

---

## 6. Nexus — Advanced Execution

Nexus is the **meta-orchestration layer** that sits above all other execution models, providing dynamic capability composition, distributed execution, and meta-cognitive self-correction.

### Architecture

```
MetaLoopOrchestrator (recursive plan-execute-observe-replan)
  ├── AIExecutionPlanner (Q/K/V attention + rule-based)
  ├── DistributedExecutor (Celery with DAG orchestration)
  ├── FailureAnalyzer (9 error classes, pattern learning, alternatives)
  └── Replan: retry / alternative tools / abort

CapabilityComposer
  ├── sequential | parallel | conditional | loop
  └── Composed capabilities re-registered as first-class

CapabilityRegistry (singleton)
  └── All tools, agents, and composed capabilities registered here

ContextBuilder
  └── Concurrent multi-source context assembly (memory, RAG, history)

CostOptimizer
  └── Budget enforcement, model selection, proactive recommendations
```

### Meta-Cognitive Loop

```
_run_recursive_cycle(goal, context, depth=0, max_depth=3):
  1. PLAN: ai_planner.plan_and_execute(goal, context)
  2. OBSERVE: if failure → FailureAnalyzer.analyze(error, context, logs)
  3. REPLAN:
     if recoverable AND retry_recommended → retry at depth+1
     elif recoverable AND NOT retry → use alternative_tools, retry at depth+1
     else → terminate with failure
  4. SUCCESS → return result
```

### Nine Error Classes

| Class | Retry? | Strategy |
|-------|--------|----------|
| TIMEOUT | Yes | Increase timeout or faster alternative |
| VALIDATION | No | Fix params from schema |
| RESOURCE | Yes | Wait, use less intensive tool |
| NETWORK | Yes | Exponential backoff |
| RATE_LIMIT | Yes | Wait with exponential backoff |
| LOGIC | No | Alternative approach |
| NOT_FOUND | No | Alternative data source |
| PERMISSION | No | Check credentials |
| UNKNOWN | Yes | Retry with modified params (once) |

### Capability Composition

Four patterns enable building higher-order tools from primitives. Composed capabilities are re-registered, enabling recursive composition — creating an infinite capability lattice.

---

## 7. LangGraph Integration Layer

The layer that connects chat to n8n workflows, ComfyUI image generation, sandbox execution, and 30+ tools.

### StateGraph Pipeline

```
process_input → convert_to_tools → check_approval → execute_tools → generate_response → END
                                        │
                          approved → execute_tools
                          rejected → generate_response ("rejected")
                          pending  → END (waits for human)
```

### Tool Handler Registry

```
BaseToolHandler (abstract)
├── validate_parameters(params) → (bool, error)
├── execute(params, context) → Dict
├── get_tool_schema() → JSON schema
└── safe_execute() → standardized result

Registered handlers:
├── N8nToolHandler: POST /webhook/{id} → workflow execution with user isolation
├── ComfyUIHandler: POST /prompt → poll /history/{id} (120s timeout)
├── ListIntegrationsHandler: discover Slack, GitHub, Notion connections
├── ExecuteIntegrationHandler: dispatch actions to specific integrations
└── UnifiedToolHandler: bridge to 30+ unified tools
```

### N8n Integration

User-isolated workflow execution: each call injects user_id, user_workflow_id, user_config_path, and metadata into the webhook payload.

### ComfyUI Integration

Two-phase: submit prompt → poll 60× every 2s for completion. User-isolated output directories at /comfyui/output/users/{user_id}.

### Approval Workflow

```
Tool invocation → is_safe AND auto_approve → AUTO_APPROVED → execute
                  require_approval_for_all → PENDING → APPROVED / REJECTED / CANCELLED
Persisted via Redis: langgraph:approval:{request_id}, TTL 300s
```

### Cost-Aware Routing

TaskClassifier.classify(prompt) → SIMPLE | MEDIUM | COMPLEX | CRITICAL → CostAwareRouter selects optimal model balancing quality vs cost using combined_score = (tradeoff × quality) + ((1-tradeoff) × 1/cost). Local models treated as zero monetary cost.

---

## 8. Knowledge Flows

### Primary Flow: User Intent → Execution

```
User types in Chat → LLM processes → Tool calls invoked
                                → Mission created
                                → Mission decomposed into tasks
                                → Tasks assigned to agents (solo/swarm/team)
                                → Agents execute (browser, terminal, tools)
                                → Results, logs, costs tracked
                                → Memory extracted from outcomes
                                → Learning feedback applied
```

### Event-Driven

```
Cron Trigger (30s tick) → MissionTrigger evaluated → Mission launched
Webhook received → WebhookEndpoint matched → Handler invoked → Mission launched
```

### Knowledge Accumulation

```
Mission execution → MissionLog entries → FeedbackReport → FeedbackPattern
                  → Memory entries (content + embedding) → Qdrant vectors
                  → LearningFeedbackDB → AdaptationRuleDB
```

### Real-Time

```
Client ↔ WebSocket (/ws) ↔ Backend → real-time events
Client → REST API (/api/v1/*) → Backend → PostgreSQL/Redis/Qdrant
VPS (Nginx :443) → WireGuard → Homelab (FastAPI :8000)
```

---

## 9. Design Principles

### Explicit
1. **Self-service agents** — users create and configure their own AI agents
2. **Multi-agent by default** — solo, team, swarm, pipeline, nexus, langgraph execution models
3. **BYOK** — user-supplied LLM API keys, no vendor lock-in
4. **Observable execution** — logs, cost tracking, token counting, Jaeger traces, Langfuse metrics
5. **Persistent learning** — feedback from outcomes feeds back into adaptation rules
6. **Marketplace economy** — agents, tools, templates shared and monetized
7. **Chaos-tested reliability** — circuit breakers, fault isolation for LLM calls
8. **Dual-machine separation** — VPS (frontend) + homelab (backend) via WireGuard

### Implicit
1. **Build don't buy** — local llama.cpp inference runs on bare metal
2. **No volume mounts** — backend code baked into Docker images
3. **Incremental complexity** — Free tier → Pro → Enterprise
4. **Chat as universal interface** — everything flows through chat
5. **Extractable knowledge** — Memories + RAG ensure system gets smarter
6. **Recursive composition** — Nexus capabilities compose into new capabilities indefinitely
7. **Dual auth** — NextAuth JWT + Zustand fm_tokens must agree

---

## Appendix

### API Routes (67 modules)

auth, users, chat, mission, agent, agent_registry, analytics, api_keys, audit_log, blog, browser, byok, changelog, community, dashboard, data_export, delegations, domain_agents, evaluation, feature_flags, feedback, file, flow_compat, graph, health, integrations, linear, llm, llm_advanced, marketplace, memory, mission_advanced, mission_decomposition, newsletter, observability, oidc, onboarding, orchestration, partner, presence, rag, rate_limits, reliability, roadmap, roles, sandbox, search, sessions, stats, subscription, swarm, swarm_protocol, templates, tenant, tenants, tools, triggers, two_fa, usage, votes, webhooks, workspace, workspace_activity, workspace_messages.

### Frontend Pages (85+)

Landing, About, Agents, Blog, Browser, Case Studies, Dashboard (analytics, chat, developer, feedback, files, graphs, marketplace, missions, notifications, nps, onboarding, rag, settings, team, templates, triggers), Developers (changelog, docs, playground, SDK), Docs, Integrations, Knowledge, Mission Dashboard, Models, Pricing, Privacy, Profile, Register, Roadmap, Server Auth, Terms, Tools (Browser, Catalog, Terminal, Topology), Topology.

### Open Questions

1. Flow vs Graph — two models with overlapping concerns, converging or competing?
2. Agent pluralism — four different agent representations, canonical lifecycle?
3. Workspace vs Tenant — legacy or complementary org models?
4. Nexus — fully operational or partially implemented?
5. Phase 4 — what were Phases 1-3?
6. GraphQL v2 — conditional Strawberry router, future API direction?
7. API v1/v2/v3 — what differentiates them?

---

*Generated from systematic analysis of the Flowmanner codebase. Associated deep-dive documents: FLOWMANNER-ONTOLOGY.md, CHAT-UX-ARCHITECTURE.md, EXECUTION-ENGINE.md.*
ARCHEOF"
