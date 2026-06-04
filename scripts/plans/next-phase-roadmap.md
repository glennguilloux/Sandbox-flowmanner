# Flowmanner Next-Phase Roadmap: Phases 26-35

**Date:** 2025-07-21
**Status:** Approved — Phase 27 → Phase 26 execution priority
**Architecture:** Two-machine (homelab + VPS), FastAPI, Next.js, PostgreSQL, Redis, Qdrant, Celery+RabbitMQ, llama.cpp

---

## Context: What We've Built (Phases 1-25 Complete)

### Architecture
- **VPS (74.208.115.142):** Next.js 16 frontend, Nginx SSL, WireGuard tunnel
- **Homelab (10.99.0.3):** FastAPI backend, PostgreSQL 15, Redis 7, Qdrant, Jaeger, Celery+RabbitMQ, llama.cpp (Qwen3.6-27B)

### Completed Capabilities
- ✅ Core API (98 tables, 273 paths, 357 operations)
- ✅ CI/CD pipeline, Docker hardening, automated backups
- ✅ Sentry error tracking (frontend + backend)
- ✅ Learning service (Qdrant + sentence-transformers)
- ✅ Email delivery (Resend + SMTP, 9 templates)
- ✅ Full-text search (PostgreSQL FTS + semantic)
- ✅ Data export/GDPR compliance
- ✅ Feature flags + changelog system
- ✅ Celery async infrastructure + idempotency middleware
- ✅ Real-time WebSocket (Socket.IO) + React Query data fetching
- ✅ In-process caching layer + Redis optimization
- ✅ TypeScript SDK (53 services) + Python SDK (54 modules) + developer portal
- ✅ Webhook guarantees (exponential backoff, DLQ, HMAC signing)
- ✅ Observability (33 Prometheus metrics, 4 circuit breakers, alerting)
- ✅ Load testing (k6) + chaos engineering (4 experiments)
- ✅ Per-endpoint rate limiting (8 categories, tier-aware)
- ✅ PWA + offline support + push notifications

### Known Remaining Gaps
- Billing/subscription (excluded for now)
- Full SDK migration (frontend still uses apiClient directly)
- LLM circuit breaker wrapping (partial)
- Redis centralized wrapper (direct connections everywhere)
- Push notification delivery (VAPID ready, needs backend sender)

---

## Execution Decision

**Start with Phase 27 (LLM Quality & Evaluation) → Phase 26 (Multi-Agent Orchestration)**

Rationale:
- Phase 27 is self-contained, 3 weeks, and produces immediate value (you'll know if your current prompts are good)
- Phase 26 depends on Phase 27 for quality scoring of agent outputs
- Together, they form the core differentiator
- Phase 33 (Enterprise Security) is the revenue unlock — parallel after Wave A

---

# Phase 26: Multi-Agent Orchestration Framework

- **Goal:** Enable autonomous agent teams that decompose goals, delegate tasks, negotiate, and synthesize results — the core differentiator vs n8n/LangChain/AutoGen/CrewAI.
- **Problem it solves:** Current missions are single-agent, linear task sequences. No agent-to-agent delegation, no parallel execution with consensus, no multi-perspective reasoning.
- **Key deliverables:**
  1. Agent registry with capability profiles (what each agent can do, confidence scores)
  2. Orchestration engine: task decomposition → agent matching → parallel dispatch → result synthesis
  3. Inter-agent communication protocol (structured messages, handoffs, escalations)
  4. Consensus mechanisms (majority vote, debate-then-synthesize, role-based weighting)
  5. Swarm execution: fan-out to N agents, merge outputs with conflict resolution
- **Success criteria:** Submit "Research competitors, analyze market, write strategy doc" → 4 agents collaborate in parallel → output coherent 5-page document with citations in < 60s
- **Primary agents:** engineering-ai-engineer, engineering-software-architect, engineering-event-driven-architect
- **Supporting agents:** qa-verifier, engineering-llm-evaluation-harness
- **Effort:** 4 weeks
- **Impact:** 🔴 Critical
- **Dependencies:** Phase 27 (evaluation framework), existing mission/task system, Celery infra, WebSocket
- **Risks:** Agent coordination overhead could degrade latency; token costs multiply with N agents; consensus deadlocks possible
- **Technical approach:** Extend `mission_executor.py` with a `SwarmOrchestrator` class. Add `agent_registry` table with capability embeddings. Use Celery chords/groups for fan-out execution. Build a `debate_protocol.py` for multi-agent consensus. Leverage existing WebSocket to stream per-agent progress to frontend.

## Phase 26: Execution Plan

| Week | Deliverable | Agent |
|------|------------|-------|
| **1** | Agent registry with capability embeddings | engineering-ai-engineer + engineering-software-architect |
| **2** | SwarmOrchestrator (fan-out, consensus, synthesis) | engineering-ai-engineer + engineering-event-driven-architect |
| **3** | Inter-agent protocol + debate mechanism | engineering-ai-engineer |
| **4** | Frontend swarm dashboard + WebSocket streaming | engineering-frontend-developer + qa-verifier |

### Week 1 Detail: Agent Registry
- `AgentCapability` model: name, description, embedding, supported task types, tool set, confidence score
- `AgentRegistry` service: register, discover (semantic search via Qdrant), match (find best agent for task)
- Admin UI: list agents, view capabilities, test with sample tasks
- API: `POST /api/v1/agents/register`, `GET /api/v1/agents`, `POST /api/v1/agents/match`

### Week 2 Detail: SwarmOrchestrator
- `SwarmOrchestrator` class in `app/services/swarm/orchestrator.py`
- Task decomposition: LLM breaks goal into subtasks with dependency graph
- Agent matching: for each subtask, find best agent from registry
- Parallel dispatch: Celery chord for fan-out, callback for result aggregation
- Synthesis: LLM merges agent outputs with conflict resolution markers
- `SwarmExecution` model tracking orchestrator runs

### Week 3 Detail: Agent Protocol
- `AgentMessage` schema: sender, recipient, type (task/query/response/error/handoff), payload, priority
- `DebateProtocol`: round-by-round debate, judge agent evaluates positions, consensus scoring
- `HandoffProtocol`: agent can delegate subtask with structured context
- `EscalationChain`: if agent fails, escalate to specialized agent or human

### Week 4 Detail: Frontend
- Swarm execution view: visualize agent dependency graph, streaming progress per agent
- Agent chat: see inter-agent messages in real time
- Result panel: synthesized output with per-agent contributions highlighted
- Controls: pause/resume swarm, override agent assignment, inject human input

---

# Phase 27: LLM Quality & Evaluation Platform

- **Goal:** Golden datasets, regression suites, and automated model-graded evaluation so every LLM change is measured, not guessed.
- **Problem it solves:** No systematic way to know if model changes improve or degrade quality. Currently using DeepSeek + llama.cpp with manual fallback — zero quality measurement.
- **Key deliverables:**
  1. Golden dataset builder (curated prompt→expected_answer pairs, categorized by task type)
  2. Automated regression test suite: on every model/config change, run golden dataset, compare scores
  3. Model-graded evaluation (LLM-as-judge using rubric scoring)
  4. Quality dashboard: per-model accuracy, latency, cost, user satisfaction correlation
  5. CI/CD integration: block deployment if eval scores drop below threshold
- **Success criteria:** Change system prompt → CI runs 200 golden tests → see exact quality delta in 5 minutes → promote/reject automatically
- **Primary agents:** engineering-llm-evaluation-harness, engineering-ai-engineer, engineering-inference-economics-optimizer
- **Supporting agents:** qa-verifier, testing-evidence-collector
- **Effort:** 3 weeks
- **Impact:** 🔴 Critical
- **Dependencies:** Langfuse integration (already exists), Phase 26 depends on this
- **Risks:** Golden dataset bias (overfitting); LLM-as-judge has its own biases; need sufficient prompt diversity
- **Technical approach:** Create `evaluation/` module with `GoldenDataset` model, `EvaluationRunner` service, and `LLMJudge` class. Store eval results in PostgreSQL with Langfuse trace correlation. Add pre-commit hooks to mission-gate.sh. Build admin UI panel in frontend.

## Phase 27: Execution Plan

| Week | Deliverable | Agent |
|------|------------|-------|
| **1** | Golden dataset schema + 50 test cases | engineering-llm-evaluation-harness + engineering-ai-engineer |
| **2** | EvaluationRunner + LLM-as-judge integration | engineering-ai-engineer + kieran-python-reviewer |
| **3** | Quality dashboard + CI/CD gate | engineering-frontend-developer + qa-verifier |

### Week 1 Detail: Golden Dataset
- `GoldenDataset` model: id, name, category (code/review/rag/agent/creative), version, created_at
- `GoldenTestCase` model: dataset_id, input_prompt, expected_output (flexible — exact match or rubric), task_type, difficulty, tags
- Builder UI: paste prompt→response pairs, tag by task type, set expected behavior
- Seed 50 test cases across: code generation (20), RAG accuracy (15), agent reasoning (10), creative tasks (5)
- Import from existing Langfuse traces where users marked quality

### Week 2 Detail: EvaluationRunner
- `EvaluationRunner` service: load dataset → run all test cases → collect outputs → score → aggregate
- `LLMJudge` class: rubric-based scoring (1-5 scale) on: accuracy, completeness, relevance, safety
- Comparison mode: run same prompts against two model/config variants → statistical significance test
- `EvalRun` model: tracks each run with scores per test case, aggregate metrics, model version, config hash
- Integration with Langfuse: each eval run creates a Langfuse trace

### Week 3 Detail: Dashboard + CI Gate
- Quality dashboard: per-model trend charts, degradation alerts, top failing test cases
- CI integration: add `npm run eval:regression` to mission-gate.sh pre-deploy phase
- Threshold: if overall score drops > 5%, block deployment with detailed report
- Quick-eval mode: run 20 "smoke test" cases in < 30s for pre-commit hook

---

# Phase 28: Advanced RAG Pipeline v2

- **Goal:** Hybrid dense-sparse retrieval with reranking, query decomposition, and agentic RAG — turning the knowledge base into a reasoning engine.
- **Problem it solves:** Current RAG is basic: embed query → Qdrant search → return chunks. No hybrid search, no reranking, no multi-hop reasoning.
- **Key deliverables:**
  1. Hybrid search combining Qdrant dense vectors + PostgreSQL FTS (BM25) with fusion ranking
  2. Cross-encoder reranking layer (sentence-transformers or API-based)
  3. Query decomposition: break complex queries into sub-queries, retrieve separately, synthesize
  4. Agentic RAG: LLM decides when to search, reformulates queries, verifies retrieved context
  5. Source attribution with confidence scores and hallucination detection
- **Success criteria:** Complex question like "How does retry logic work in mission execution and what are the failure modes?" → decomposed into 3 sub-queries → hybrid retrieval → reranked top-10 chunks → LLM synthesizes with inline citations → hallucination score < 5%
- **Primary agents:** engineering-rag-pipeline-architect, engineering-ai-engineer, engineering-database-optimizer
- **Supporting agents:** engineering-llm-evaluation-harness, qa-verifier
- **Effort:** 3 weeks
- **Impact:** 🟡 High
- **Dependencies:** Phase 27 (evaluation), existing Qdrant + PostgreSQL FTS
- **Risks:** Reranking adds latency (100-500ms); hybrid fusion tuning is empirical; hallucination detection is imperfect
- **Technical approach:** Add `HybridRetriever` class. Add `RerankerService`. Build `QueryDecomposer` using LLM structured output. Implement `AgenticRAGLoop` with tool-calling pattern.

---

# Phase 29: Autonomous Long-Running Agents

- **Goal:** Agents that persist across sessions, maintain memory, replan on failure, and execute background workflows without user supervision.
- **Problem it solves:** Current missions are fire-and-forget with no persistent agent state. No memory, no replanning, no long-running capability.
- **Key deliverables:**
  1. Persistent agent memory: conversation history + vector memory + key-value episodic store
  2. Goal decomposition & dynamic replanning: agent detects dead end → rewinds → tries alternative approach
  3. Human-in-the-loop gates: agent pauses at critical decisions, requests approval, resumes
  4. Background agent workers: Celery tasks that run agents for hours with heartbeat + progress streaming
  5. Agent dashboard: list all running agents, view progress, inspect memory, pause/resume/kill
- **Success criteria:** "Monitor Hacker News for AI workflow tools, compile weekly report" → agent runs for 7 days → delivers structured report every Monday at 9AM
- **Primary agents:** engineering-ai-engineer, engineering-event-driven-architect, engineering-autonomous-optimization-architect
- **Supporting agents:** engineering-sre, qa-verifier
- **Effort:** 4 weeks
- **Impact:** 🟡 High
- **Dependencies:** Phase 26 (multi-agent), Phase 28 (RAG for memory), Celery infra (exists)
- **Risks:** Token cost accumulation; memory pollution; replanning loops; tool-access sandboxing
- **Technical approach:** Add `AgentMemory` model (PostgreSQL + Qdrant hybrid). Build `GoalPlanner` with ToT replanning. `HumanGate` callback system. Extend Celery with `LongRunningAgentTask`.

---

# Phase 30: Developer Experience & SDK Unification

- **Goal:** Migrate frontend to SDK, add API versioning with zero-downtime deprecation, auto-generated docs, and interactive playground.
- **Problem it solves:** Frontend still uses `apiClient` directly. No API versioning. SDK parity gaps. Developer portal is basic.
- **Key deliverables:**
  1. Frontend migration: replace all `apiClient` calls with TypeScript SDK
  2. API versioning: `/api/v2/` namespace with header-based negotiation, deprecation timeline
  3. Auto-generated OpenAPI docs from FastAPI type hints, published to developer portal
  4. Interactive API playground (branded Swagger) with auth token injection
  5. SDK code generation pipeline: OpenAPI spec → auto-generate TS + Python SDK updates on CI
- **Success criteria:** Frontend makes zero direct API calls (100% SDK). New endpoint auto-generates SDK methods, docs, and playground entry in one CI run.
- **Primary agents:** engineering-frontend-developer, engineering-graphql-grpc-architect, engineering-migration-engineer
- **Supporting agents:** qa-verifier, design-ui-designer
- **Effort:** 3 weeks
- **Impact:** 🟡 High
- **Dependencies:** None (standalone), unblocks all future frontend work
- **Risks:** High-touch migration (273 paths); regression risk; codegen edge cases
- **Technical approach:** Strangler-fig migration. FastAPI versioning middleware. Custom FastAPI → SDK codegen. React playground component.

---

# Phase 31: AI Workflow Marketplace & Templates

- **Goal:** Shareable, discoverable, one-click-importable workflow templates — turning user creations into a network-effect growth engine.
- **Problem it solves:** Every user starts from scratch. No sharing, discovery, or remixing. No community flywheel.
- **Key deliverables:**
  1. Template packaging: export workflow as versioned template with metadata, schema, example outputs
  2. Marketplace UI: browse, search (semantic), filter by category/task-type, ratings, install count
  3. One-click import: instantiate template into user's workspace with guided configuration wizard
  4. Creator profiles: track contributions, ratings, fork chains
  5. Template quality scoring: automated testing against golden datasets before publication
- **Success criteria:** Browse marketplace → find "Competitor Analysis Agent" → one-click import → configure API keys → running in 2 minutes
- **Primary agents:** engineering-frontend-developer, design-ux-architect, product-manager
- **Supporting agents:** design-ui-designer, product-feedback-synthesizer
- **Effort:** 3 weeks
- **Impact:** 🟡 High
- **Dependencies:** Phase 27 (quality scoring), Phase 30 (SDK for validation)
- **Risks:** Chicken-and-egg (no content); template security (malicious code); IP/licensing complexity
- **Technical approach:** `Template` model with JSON schema versioning. Template validation sandbox (restricted Celery worker). Marketplace search with PostgreSQL FTS + Qdrant semantic.

---

# Phase 32: Real-Time Multi-User Collaboration

- **Goal:** Google Docs-level real-time collaboration for workflow editing — multiple users editing the same workflow simultaneously.
- **Problem it solves:** Single-user only. No presence, no commenting, no conflict resolution. Hard requirement for team adoption.
- **Key deliverables:**
  1. CRDT or operational transform for workflow graph editing (Yjs/ShareDB)
  2. Real-time presence: who's editing, what node they're on, cursor positions
  3. Inline commenting & resolution on workflow nodes
  4. Version history with visual diff (before/after) and one-click rollback
  5. Permissioned collaboration: view-only, comment, edit roles per workflow
- **Success criteria:** Two users open same workflow → both see each other's cursors → user A adds node → appears on user B's screen in < 200ms → no merge conflicts
- **Primary agents:** engineering-frontend-developer, engineering-software-architect, engineering-event-driven-architect
- **Supporting agents:** design-ux-architect, qa-verifier
- **Effort:** 4 weeks
- **Impact:** 🟡 High
- **Dependencies:** Phase 30 (SDK for clean API), existing WebSocket infra
- **Risks:** CRDT/OT is famously complex; scaling to many concurrent editors; bandwidth; offline editing conflicts
- **Technical approach:** Yjs (CRDT) over existing WebSocket. `CollaborationSession` model. Presence via Redis pub/sub. Visual diff using graph isomorphism. Threaded comment model.

---

# Phase 33: Enterprise Security & Compliance

- **Goal:** SOC 2 Type II readiness, SSO (OIDC/SAML), fine-grained RBAC, and hardened audit logging — unblocking enterprise sales.
- **Problem it solves:** No SSO, basic RBAC (user/admin). Enterprise customers require these before procurement. Revenue gatekeeper.
- **Key deliverables:**
  1. SSO integration: OIDC (Google, Okta) + SAML (Azure AD, OneLogin) with JIT provisioning
  2. Fine-grained RBAC: custom roles with per-endpoint, per-workflow, per-resource permissions
  3. SOC 2-aligned audit logging: every CRUD operation, auth event, permission change with immutable storage
  4. Data residency controls: per-tenant data isolation, retention policies, export/deletion automation
  5. Security posture dashboard: compliance score, open vulnerabilities, access review status
- **Success criteria:** Enterprise security questionnaire completed in < 1 hour (all answers pre-populated). SOC 2 Type II achievable within 3 months.
- **Primary agents:** engineering-security-engineer, compliance-auditor, engineering-software-architect
- **Supporting agents:** engineering-threat-detection-engineer, security-engineer
- **Effort:** 4 weeks
- **Impact:** 🔴 Critical (revenue unlock)
- **Dependencies:** Phase 30 (API versioning for RBAC), existing audit_log module
- **Risks:** SSO provider edge cases; RBAC migration can break permissions; SOC 2 requires org processes beyond code
- **Technical approach:** `python-saml` + `python-oidc` integration. Granular permission matrix (JSONB). Append-only audit log + optional S3 immutable. Compliance dashboard from Sentry, Prometheus, audit logs.

---

# Phase 34: AI-Powered Analytics & Insights

- **Goal:** Per-workflow cost attribution, performance analytics, bottleneck detection, and AI-generated optimization suggestions.
- **Problem it solves:** No visibility into workflow performance or cost. No feedback loop from analytics to optimization.
- **Key deliverables:**
  1. Workflow performance dashboard: execution time, success rate, token usage, cost per run
  2. Cost attribution: LLM tokens, CPU time, API calls per user/workspace/workflow
  3. AI-driven bottleneck detection: automatically identify slow/error-prone nodes and suggest fixes
  4. Trend analysis: anomaly detection on execution patterns, predictive alerts
  5. Weekly automated insights report: "Your top 3 optimization opportunities this week"
- **Success criteria:** User sees "Workflow X costs $4.32/day, 3x more than similar workflows → suggested optimization: cache LLM responses → estimated savings: $2.80/day"
- **Primary agents:** support-analytics-reporter, engineering-data-engineer, engineering-analytical-olap-engineer
- **Supporting agents:** engineering-ai-engineer, design-ux-architect
- **Effort:** 3 weeks
- **Impact:** 🟢 Medium
- **Dependencies:** Phase 27 (cost data), Phase 28 (RAG-powered insights)
- **Risks:** OLAP infrastructure complexity; per-call tracking overhead; insights quality depends on data volume
- **Technical approach:** `ExecutionMetrics` model. PostgreSQL materialized views. `InsightGenerator` weekly Celery task. Analytics dashboard with time-series charts.

---

# Phase 35: Self-Healing & Autonomous Operations

- **Goal:** Automated failover, predictive scaling, incident auto-remediation, and chaos engineering in production.
- **Problem it solves:** Operations require manual intervention. Two-machine architecture has single points of failure. No self-healing.
- **Key deliverables:**
  1. Automated failover: health check fails 3x → auto-restart container → if still fails, alert
  2. Predictive scaling hooks: monitor queue depth, p99 latency, pre-warm resources
  3. Incident auto-remediation playbooks: known failure patterns → automatic fix
  4. Chaos engineering in production: controlled fault injection with automatic rollback
  5. Operational health SLI dashboard: SLO tracking, error budget burn rate, MTTR trending
- **Success criteria:** Backend container crashes at 3AM → auto-restarted in < 30s → user never notices → Slack notification with root cause analysis by 3:05AM
- **Primary agents:** engineering-sre, engineering-devops-automator, engineering-autonomous-optimization-architect
- **Supporting agents:** engineering-cloud-finops, engineering-threat-detection-engineer
- **Effort:** 3 weeks
- **Impact:** 🟢 Medium
- **Dependencies:** Phase 29 (long-running agent infra for playbooks), existing Prometheus + health-monitor.sh
- **Risks:** Auto-remediation cascading failures; chaos engineering in production is scary; two-machine limits true HA
- **Technical approach:** Extend `health-monitor.sh` with remediation. `PlaybookEngine` — YAML runbooks via Celery. Chaos engineering with existing k6 tooling. SLO dashboard from Prometheus. Slack webhook notifications.

---

# Execution Priority Matrix

| Priority | Phase | Name | Why |
|----------|-------|------|-----|
| **P0** | 27 | LLM Quality & Evaluation | Foundation — every AI feature needs measurement. Build first. |
| **P0** | 26 | Multi-Agent Orchestration | Core differentiator. The north star. |
| **P0** | 33 | Enterprise Security | Revenue gatekeeper. SSO → enterprise sales. |
| **P1** | 28 | Advanced RAG Pipeline | Amplifies Phases 26, 27, 29. Better retrieval → better agents. |
| **P1** | 30 | Developer Experience & SDK | Unblocks all frontend work. Platform adoption table stakes. |
| **P1** | 29 | Autonomous Long-Running Agents | Differentiator. Depends on 26 + 28. |
| **P2** | 31 | Workflow Marketplace | Growth flywheel. Can start small. |
| **P2** | 32 | Real-Time Collaboration | Team adoption enabler. Complex implementation. |
| **P3** | 34 | AI Analytics & Insights | Value increases as usage grows. |
| **P3** | 35 | Self-Healing Operations | Internal ops improvement. Less user-visible. |

---

# Phase Grouping (Parallel Execution)

| Wave | Phases | Rationale |
|------|--------|-----------|
| **Wave A** | 27 + 30 | Independent. Evaluation framework + SDK migration run simultaneously. |
| **Wave B** | 26 + 28 | Orchestration + RAG synergistic. RAG makes agents smarter; agents stress-test RAG. |
| **Wave C** | 29 + 33 | Autonomous agents + enterprise security. Different concerns, parallel execution. |
| **Wave D** | 31 + 32 | Marketplace + collaboration share user-facing patterns. |
| **Wave E** | 34 + 35 | Analytics + self-healing share observability data. |

**Critical path:** 27 → 26 → 29 → 31 (eval → orchestration → autonomous → marketplace)

---

# Agent Utilization Plan

### Most Utilized (4+ phases)
- `engineering-ai-engineer`: Phases 26, 27, 28, 29 (core AI workhorse)
- `engineering-software-architect`: Phases 26, 29, 32, 33 (system design)
- `qa-verifier`: Phases 26-32 (quality gate for everything)

### Potential Bottlenecks
- `engineering-ai-engineer` is on the critical path for 4 phases → consider splitting into sub-agents
- `engineering-llm-evaluation-harness` needed for 26, 27, 28 → front-load Phase 27 to establish eval framework early

---

# Biggest Missing Piece

**Multi-Agent Orchestration (Phase 26)** unlocks the most value. It transforms Flowmanner from "a tool that runs task sequences" into "a platform where AI agents collaborate autonomously." Every other phase amplifies this: RAG gives agents knowledge, evaluation ensures quality, marketplace distributes agent teams, collaboration lets humans steer agent swarms.

Without it, Flowmanner competes with n8n and Zapier. With it, Flowmanner competes with AutoGen, CrewAI, and the future of work itself.

---

# Competitive Differentiation

| Capability | n8n | LangChain | AutoGen | CrewAI | **Flowmanner (post-Phase 35)** |
|---|---|---|---|---|---|
| Visual workflow builder | ✅ | ❌ | ❌ | ❌ | ✅ (with real-time collab) |
| Multi-agent orchestration | ❌ | ❌ | ✅ | ✅ | ✅ (with marketplace + evals) |
| Built-in RAG | ❌ | ✅ | ❌ | ❌ | ✅ (hybrid + agentic) |
| Enterprise SSO/RBAC | ✅ (cloud) | ❌ | ❌ | ❌ | ✅ (self-hosted) |
| LLM evaluation platform | ❌ | ✅ (LangSmith) | ❌ | ❌ | ✅ (integrated) |
| Self-hosted | ✅ | ❌ | ❌ | ❌ | ✅ (two-machine) |
| Workflow marketplace | ✅ | ❌ | ❌ | ❌ | ✅ |
| Long-running autonomous agents | ❌ | ❌ | ❌ | ❌ | ✅ |
| Real-time collaboration | ❌ | ❌ | ❌ | ❌ | ✅ |

**Flowmanner's unique position:** The only platform that combines visual workflow building with multi-agent AI orchestration, running on self-hosted infrastructure with enterprise security — a category of one.

---

# Immediate Next Step: Phase 27 Week 1

**Goal:** Golden dataset schema + 50 test cases

### Models to Create
```python
# /opt/flowmanner/backend/app/models/evaluation_models.py

class GoldenDataset(Base):
    id: UUID
    name: str
    category: str  # code, review, rag, agent, creative
    version: int
    description: str
    created_at: datetime
    updated_at: datetime

class GoldenTestCase(Base):
    id: UUID
    dataset_id: UUID -> GoldenDataset
    input_prompt: str
    expected_behavior: str  # description of what good output looks like
    task_type: str
    difficulty: str  # easy, medium, hard
    tags: list[str]
    rubric: JSONB  # scoring criteria: accuracy, completeness, relevance, safety (weighted)
    created_at: datetime

class EvalRun(Base):
    id: UUID
    dataset_id: UUID -> GoldenDataset
    model_name: str
    model_config_hash: str  # hash of system prompt, temperature, etc.
    started_at: datetime
    completed_at: datetime
    aggregate_score: float
    scores_by_category: JSONB
    langfuse_trace_id: str
```

### Files to Create
- `/opt/flowmanner/backend/app/models/evaluation_models.py`
- `/opt/flowmanner/backend/app/services/evaluation/dataset_builder.py`
- `/opt/flowmanner/backend/app/services/evaluation/eval_runner.py`
- `/opt/flowmanner/backend/app/services/evaluation/llm_judge.py`
- `/opt/flowmanner/backend/app/api/v1/evaluation.py`
- `/opt/flowmanner/backend/alembic/versions/xxxx_add_evaluation_tables.py`
- `/opt/flowmanner/backend/tests/test_evaluation.py`
