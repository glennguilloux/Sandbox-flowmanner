# FLOWMANNER — CANONICAL KNOWLEDGE REPRESENTATION

*Extracted: 2026-06-01*

---

## 1. CORE CONCEPTS

### 1.1 Fundamental Identity
**Flowmanner** is a **multi-agent AI workflow automation platform**. It orchestrates complex tasks through AI agents, visual flow definitions, persistent memory, and a marketplace for sharing. It positions itself as an "Agentic OS" — an operating system for AI agents.

### 1.2 The Five Pillars
1. **Missions** — Task definitions with decomposition, execution tracking, and results
2. **Agents** — Specialized AI entities (50+ predefined) that execute work
3. **Chat** — Primary human interface; all system functions are chat-accessible
4. **Graphs/Flows** — Visual workflow definitions via node-and-edge editor
5. **Marketplace** — Sharing economy for agent templates, workflows, and tools

### 1.3 Dual Vision (Classic vs. Omega)
- **Flowmanner Classic** — The running system; accretion-driven, feature-rich but architecturally fragmented
- **Flowmanner Ω (Omega)** — A proposed re-architecture as a "durable, type-safe, formally auditable agentic OS" with event sourcing, capability-based security, and bounded execution guarantees

---

## 2. DIMENSIONS

### 2.1 Execution Models (7 strategies)
| Strategy | Pattern | When Used |
|---|---|---|
| **Solo** | Serial task loop | Simple single-agent missions |
| **DAG** | Topological layers (Kahn's algorithm) | Dependency-ordered parallel tasks |
| **Swarm** | Hub-and-spoke (decompose → dispatch → synthesize) | Parallelizable sub-tasks |
| **Swarm Pipeline** | State machine with debate | Multi-agent coordination with consensus |
| **Graph** | Visual node-and-edge execution | User-defined workflows |
| **LangGraph** | StateGraph with human-in-the-loop | Complex stateful workflows |
| **Nexus (Meta)** | Recursive planning/execution/self-correction | Self-healing meta-orchestration |

### 2.2 Environment Dimension (3-machine topology)
| Environment | Role |
|---|---|
| **Homelab** (172.16.1.1 / 10.99.0.3) | Backend, databases, LLM inference |
| **VPS** (74.208.115.142 / 10.99.0.1) | Frontend, Nginx, SSL termination |
| **Ops/Dev** (172.16.1.2) | Development workstation, deployment control |

### 2.3 API Versioning Dimension
- **v1** — Legacy endpoints (46+ route files)
- **v2** — Refactored base, auth, agents, workspaces, search
- **v3** — Workspace-scoped entities, httpOnly cookies, OIDC, scoped RBAC (in migration)
- **v4** — Planned: UUIDv7, JSON:API, cookie-only auth, unified protocol (28-week roadmap)

### 2.4 Error Taxonomy Dimension (two parallel systems)
**Nexus ErrorClass (9 types, budget-bounded):**
`TIMEOUT` | `VALIDATION` | `RESOURCE` | `LOGIC` | `NETWORK` | `PERMISSION` | `NOT_FOUND` | `RATE_LIMIT` | `UNKNOWN`

**Improvement FailureType (16 types, heuristic classification):**
- *Infrastructure:* `TOOL_API_ERROR`, `TOOL_TIMEOUT`, `RESOURCE_EXHAUSTION`, `CONNECTION_FAILURE`, `RATE_LIMITED`, `SERVICE_UNAVAILABLE`
- *Application:* `TOOL_INVALID_INPUT`, `TOOL_INVALID_OUTPUT`, `LLM_HALLUCINATION`, `LLM_REFUSAL`, `LLM_INSTRUCTION_DRIFT`, `CONTEXT_OVERFLOW`, `RETRIEVAL_MISS`, `WORKFLOW_DEPENDENCY_FAIL`, `AGENT_COORDINATION_FAIL`, `UNKNOWN`

### 2.5 Domain Dimension (10 agent categories)
Customer Service | Finance | Healthcare | HR | Legal | Marketing | Media/Creative | Operations | Sales | Software/IT

---

## 3. ENTITIES

### 3.1 Infrastructure Components
- **Nginx** — SSL termination, reverse proxy routing (`/api/*` → WireGuard → backend, `/*` → Next.js)
- **Next.js 16** — Frontend (App Router, React 19, standalone output)
- **FastAPI** — Backend (uvicorn, 4 workers)
- **PostgreSQL 15** — Primary relational database (asyncpg)
- **Redis 7** — Cache, pub/sub for SSE broadcasts
- **Qdrant v1.12** — Vector store for RAG and semantic memory
- **RabbitMQ** — Message broker for Celery tasks
- **Celery** — Background task workers
- **Jaeger** — Distributed tracing
- **llama.cpp** — Local LLM inference (Qwen3.6-27B, ~38 tok/s, 2x RTX 5060 Ti)
- **WireGuard** — VPN tunnel linking VPS ↔ Homelab

### 3.2 Core Data Entities (34+ SQLAlchemy models)
- **User/Identity:** `users`, `auth_sessions`, `auth_api_keys`, `oidc_provider_configs`
- **Organization:** `workspaces`, `teams`, `workspace_activity_log`, `subscriptions`
- **Agent:** `agents`, `agent_templates`, `agent_registry`, `capability_tokens`
- **Mission:** `missions`, `mission_tasks`, `mission_logs`, `mission_improvements`
- **Chat:** `chat_threads`, `chat_messages`, `chat_folders`
- **Graph/Flow:** `graphs`, `graph_executions`, `graph_states`
- **Swarm:** `swarms`, `swarm_pipelines`
- **Memory/Learning:** `memories`, `learning_rules`, `adaptation_rules`
- **Marketplace:** `marketplace_listings`, `community_templates`
- **Business:** `subscriptions`, `partner_revenue`, `analytics_events`, `idempotency_keys`
- **Notification:** `notifications`, `push_subscriptions`, `webhook_subscriptions`
- **Tool:** `tools`, `tool_registrations`

### 3.3 Agent Catalog (50 predefined personalities)
All agents have: `id`, `domain`, `name`, `description`, `color`, core competencies, and behavioral rules. Domains span 10 industries with 5 agents each.

### 3.4 Nexus Subsystem (22 files)
The meta-orchestration layer:
- `orchestrator.py`, `meta_loop_orchestrator.py` — Core orchestration
- `capability_composer.py`, `capability_lattice.py`, `capability_registry.py` — Capability management
- `execution_planner.py`, `ai_execution_planner.py` — Planning
- `failure_analyzer.py` — Error classification with budget-bounded recovery
- `context_builder.py`, `memory_integration.py` — Knowledge integration
- `marketplace.py`, `marketplace_db.py` — Marketplace logic
- `observability.py`, `tracing.py` — Monitoring
- `security.py`, `tool_versioning.py`, `cost_optimizer.py`, `distributed_executor.py`, `agent_capability_registrar.py`, `agent_templates.py`

### 3.5 Self-Improvement Subsystem (16 files)
- `improvement_loop_v2.py` — Core learning loop
- `failure_types.py`, `failure_repository.py` — Error taxonomy and persistence
- `causal_decomposer.py`, `hypothesis_tester.py` — Root cause analysis
- `success_learner.py`, `temporal_analyzer.py`, `strategy_evolution.py` — Learning from success
- `knowledge_graph.py`, `knowledge_transfer.py` — Knowledge propagation
- `metrics_collector.py`, `knob_manager.py`, `alerting.py`, `proactive_scheduler.py`

### 3.6 Evaluation Subsystem (4 files)
`dataset_builder.py`, `eval_runner.py`, `llm_judge.py` — LLM-as-judge evaluation pipeline

### 3.7 Domain Agents (3 specialized domains)
`biotech/`, `finance/`, `legal/` — Each with `base_domain_agent.py` pattern

### 3.8 A2A (Agent-to-Agent)
`a2a_server.py`, `a2a_agent_wrapper.py` — Inter-agent communication protocol

### 3.9 Graphify Knowledge Graph
2,059 nodes, 4,152 edges — codebase knowledge graph with hash-cached JSON artifacts

---

## 4. RELATIONSHIPS

### 4.1 Ownership & Scoping
- User → Workspaces (many-to-many via membership)
- Workspace → Agents, Missions, Chat Threads, Graphs (all workspace-scoped in v3+)
- Workspace → Teams (one-to-many)
- Mission → MissionTasks (one-to-many, hierarchical via `parent_task_id`)
- Mission → Sub-Missions (self-referential via `parent_mission_id`)
- MissionTask → MissionTasks (DAG dependencies)

### 4.2 Execution Pathways
- Chat message → ExecutionRouter (keyword analysis) → determines dispatch: Mission | Workflow | General AI
- Trigger (30s tick or webhook) → Mission launch
- Mission → Executor strategy selection → Task dispatch → Result aggregation
- Graph → GraphExecutor → Node handlers (12 types) → State management

### 4.3 Learning & Feedback
- Execution outcome → FailureContext persisted → FailureType classification → improvement_loop_v2 → adaptation rules → Qdrant vectors
- Success → success_learner → strategy_evolution → knowledge_graph
- Feedback → feedback_synthesizer → learning rules (decay-bounded)

### 4.4 Agent Relationships
- Agent ↔ ToolRegistry (via CapabilityTokens)
- Agent ↔ Agent (via A2A protocol)
- Agent ↔ Domain (via base_domain_agent.py inheritance)
- Agent ↔ Nexus (via capability_composer for meta-orchestration)

---

## 5. KNOWLEDGE FLOWS

### 5.1 Request Flow
```
User (Browser) → Nginx (VPS) → Next.js (VPS) → /api/* → WireGuard → FastAPI (Homelab) → Services → DB/Redis/Qdrant
```

### 5.2 Chat/Streaming Flow
```
User Input → ExecutionRouter → [Mission|Workflow|Chat] → SSE stream → Client (RAF-batched updates)
```

### 5.3 Mission Execution Flow
```
Trigger/Manual → ExecutionRouter → Strategy selection → DAG topological sort → Task dispatch → Node handlers → Result collection → MissionLog
```

### 5.4 Self-Improvement Flow
```
Execution failure → failure_types.classify_failure() → failure_repository persistence →
causal_decomposer → hypothesis_tester → adaptation rules → knowledge_graph propagation
```

### 5.5 Deployment Flow
```
Dev edits (Homelab) → rsync to VPS → docker compose build → docker compose up -d --force-recreate → Nginx reload
```

### 5.6 Notification Flow
```
Backend event → Redis pub/sub → SSE stream → Browser push notification
```

---

## 6. DESIGN PRINCIPLES

### 6.1 Explicit Principles
1. **Chat-Centric** — Chat is the universal interface; everything is accessible through conversation
2. **BYOK (Bring Your Own Key)** — User-supplied LLM API keys prevent vendor lock-in
3. **Observable Execution** — Deep observability via OTel, Jaeger, Langfuse on every execution path
4. **Self-Service Agents** — Users define and configure agents directly
5. **Build over Buy** — Local llama.cpp inference on bare metal; no volume mounts (code baked into images)
6. **Dual-Machine Separation** — Public frontend (VPS) isolated from private backend (Homelab) via WireGuard
7. **No Volume Mounts** — Code changes require full Docker image rebuild
8. **Never Edit on VPS** — All source edits happen on Homelab; VPS is deployment target only

### 6.2 Implicit Principles (from Omega spec)
9. **Durable Execution** — Event-sourced substrate for replayability and crash recovery
10. **Type-Safe Composition** — Compile-time validation of inter-agent contracts
11. **Capability-Bounded** — OCap security model; no ambient authority
12. **Budget-Bounded** — Every execution has cost, time, iteration budgets
13. **Bounded Learning** — Decay-weighted learning rules with A/B validation requirements
14. **Single Executor** — One engine with pluggable strategies (vs. 7 separate executors)

---

## 7. REPEATED TERMINOLOGY

| Term | Definition |
|---|---|
| **Mission** | A user-defined task that is decomposed, executed, and tracked |
| **Agent** | A specialized AI entity with defined competencies and behavioral rules |
| **Flow / Graph** | Visual workflow definition (nodes + edges); terms used interchangeably despite being separate models |
| **Nexus** | Meta-orchestration layer for recursive planning and self-correction |
| **Substrate** | The execution engine layer (in Omega: the event-sourced durable core) |
| **Capability Token** | Unforgeable, attenuable authorization token (OCap security model) |
| **Workspace** | Organizational container scoping agents, missions, chat, and members |
| **Execution Router** | Keyword-based dispatcher determining how user input should be handled |
| **Tool Registry** | Centralized catalog of executable tools with metadata |
| **Graphify** | Codebase-to-knowledge-graph extraction tool (2,059 nodes) |
| **Sisyphus** | Code name for the Omega re-architecture architect/process |
| **Hermes** | Planning/orchestration subsystem for browser harness and RAG flows |
| **BYOK** | "Bring Your Own Key" — user-supplied LLM API keys |
| **SSE** | Server-Sent Events for real-time streaming |
| **OCap** | Object-Capability security model |

---

## 8. OPEN QUESTIONS

1. **Omega Implementation Status** — How much of the 18 invariants and 5-horizon roadmap has actually been implemented vs. designed?
2. **Nexus ErrorClass vs. Improvement FailureType** — Two parallel error taxonomies exist (9 Nexus classes vs. 16 Improvement types). Are they unified, bridged, or siloed?
3. **Flow vs. Graph Consolidation** — Identified as architectural weakness #8. Has any consolidation begun?
4. **Workspace vs. Tenant** — Redundant route definitions identified as weakness #7. Migration status?
5. **Agent Identity Model** — Weakness #11 notes no unforgeable agent IDs. Is this addressed in v3/v4 migrations?
6. **Marketplace Viability** — The marketplace is listed as a pillar but flagged as partially implemented. What's the current operational status?
7. **Learning Loop Status** — Identified as "write-only" (weakness #10). Has the decay-weighting and A/B validation been implemented?
8. **ModelRouter Silent Failure** — Critical bug causing empty mission results. Is this now fixed?
9. **Auth v3 Rollout** — What percentage of the 6-week Phase 1 (Auth + Workspaces) has been deployed?
10. **Chaos Test Harness** — Invariant I.19 requires chaos tests on every PR. Does the test suite exist?

---

## 9. EVOLUTION

### 9.1 Phase Timeline
| Phase | Scope |
|---|---|
| **V1/V2** | Initial platform — 46+ API routes, core mission/agent/chat models |
| **V3** (in progress) | Structural integrity — workspace scoping, httpOnly cookies, OIDC, scoped RBAC |
| **V4** (planned) | Protocol unification — UUIDv7, JSON:API, cookie-only auth |
| **H1** (Q3 2026) | Harden chat frontier — fix ModelRouter, unify auth, add observability |
| **H2** (Q4 2026-Q1 2027) | Durable substrate — event sourcing, budgets, depth invariants |
| **H3** (Q2-Q3 2027) | Type-safe composition + OCap — Pydantic scaling, chaos test suite |
| **H4** (Q4 2027) | Model consolidation — canonical models for org/workflow |
| **H5** (Q1-Q2 2028) | Single executor + replay UI + multimodal I/O |

### 9.2 Architectural Shifts Documented
- User-owned → Workspace-owned entities
- JWT Bearer → httpOnly cookies + session tracking
- Raw dicts → Pydantic-validated inter-agent contracts
- 7 executors → 1 executor with pluggable strategies
- RBAC → OCap capability tokens
- Mutable DB rows → Append-only event log
- In-memory notifications → DB-backed + SSE + Web Push
- string-based LLM routing → typed model routing

---

## 10. HIDDEN ASSUMPTIONS

1. **Single Developer** — All credentials reference `glenn`; no team onboarding patterns documented outside workspace invitations
2. **Chat Is Sufficient** — The assumption that all platform functions are accessible through chat implies a conversational completeness that the deep-dive analysis questions (many features are frontend-only or not wired to chat)
3. **Homelab Always Available** — The dual-machine architecture assumes 100% homelab uptime; no documented fallback if the homelab goes down
4. **WireGuard Is Reliable** — All VPS→backend traffic depends on a single WireGuard tunnel with no documented redundancy
5. **LLM Availability** — The system assumes both DeepSeek API and local llama.cpp are available; fallback behavior is not documented
6. **Docker Compose Is Sufficient** — No orchestration layer (Kubernetes, Nomad); assumes single-host deployment per environment
7. **Token Budgets Are Sufficient** — Context window management exists (32K ctx for llama.cpp) but no dynamic window sizing documented
8. **Knowledge Graph Completeness** — Graphify's 2,059 nodes and 4,152 edges are assumed to represent complete codebase knowledge
9. **Omega Is the Future** — All strategic planning assumes Flowmanner Ω will replace Classic; no contingency for maintaining Classic long-term
10. **Credentials in AGENTS.md** — Secrets are documented in plaintext markdown files shared with AI coding agents

---

*Extracted from: AGENTS.md, flowmanner skill, ARCHITECTURE.md, FLOWMANNER-OMEGA-SPEC.md, 50 agent personality definitions, v3-v4-migration-roadmap, DEEP-DIVE-ANALYSIS.md, auth-v3-implementation.md, workspaces-v3-implementation.md, observable-transformation-canvas.md, FLOWMANNER-UNIFIED-TOOLS-PLAN.md, graph-execution-engine.md, flowmanner-omega-roadmap.md, failure_types.py, failure_analyzer.py, failure_repository.py, mission_models.py, graphify-out/graph.json, wireguard.txt, SECRETS-ROTATION.md, IMPROVEMENTS-LOG.md, REBUILD-BACKEND.md, AGENTS.homelab.md, AGENTS.vps.md, AGENTS.ops.md, openapi.json, and 34+ model files.*
