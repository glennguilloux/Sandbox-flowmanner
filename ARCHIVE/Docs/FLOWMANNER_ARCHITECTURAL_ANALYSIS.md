# Flowmanner: Architectural Deconstruction & Next-Generation Specification

**Author:** Systems Architecture Analysis
**Date:** 2026-06-01
**Source Material:** AGENTS.md (all three machines), Flowmanner skill, docker-compose.yml, .env, backend models (30 files), API routes (68 files), frontend component tree (17 directories), package.json, Dockerfile, requirements.txt, investigation reports (v1 + v2), QA audit report

---

## PART I — REVERSE-ENGINEERED PHILOSOPHY

The architecture does not announce its philosophy. It must be inferred from its artifacts. Ten principles emerge from the concrete decisions embedded in the code, infrastructure, and operational patterns.

### 1. Sovereign Infrastructure as First Principle

The homelab-first design — bare-metal PostgreSQL, Redis, Qdrant, RabbitMQ, Jaeger, and llama.cpp running on local hardware behind a WireGuard tunnel — is not a cost-saving measure. It is a philosophical commitment to **data sovereignty and infra independence**. The VPS is a thin presentation layer. All state lives on owned hardware. This inverts the cloud-native orthodoxy: compute at the edge, state at the center, but the "center" is a basement, not us-east-1.

**Evidence:** Two GPUs (RTX 3070 + RTX 3060) running llama.cpp on bare metal via systemd while simultaneously pulling ollama, comfyui-3d, and anythingllm images. DeepSeek API as primary LLM with local llama.cpp as fallback. No AWS/GCP/Azure dependencies anywhere in .env.

### 2. The Agent as Atomic Unit, Not the Prompt

Flowmanner is not a prompt chainer. The backend has 30 model files, and `agent.py`, `agent_models.py`, `agent_registry.py`, `agent_personalities.py`, `agent_capabilities.py`, `domain_agents.py`, and `delegations.py` form a distinct subsystem. The frontend has an agents marketplace with 50 agents across 10 categories. Agents have personalities, capabilities, and can be delegated to. This is an **agent operating system**, not a chatbot with RAG.

**Contrast:** LangChain treats agents as chains with tool-calling. CrewAI treats agents as role-players. Flowmanner treats agents as **discoverable, composable, marketplace-published entities** with persistent identity.

### 3. Mission as the Composable Unit of Work

"Mission" is the most densely represented concept across the codebase. It spans `mission_models.py`, `mission_advanced_models.py`, `mission_decomposition_routes.py`, `mission_advanced_routes.py`, `mission.py` (API), and a dedicated `mission-builder/` frontend component with its own `nodes/` subdirectory and tests. Missions are not prompts. They are decomposable work units that get broken down by agents and executed as sub-tasks.

**Philosophical implication:** The system believes that complex work is inherently hierarchical and decomposable. This is a rejection of the "one big prompt" paradigm in favor of **recursive task decomposition**.

### 4. Immutable Deployment, Deterministic Reproducibility

The backend Docker image has no volume mounts for code. Every change requires a full `docker build` + `docker compose up -d --no-deps --force-recreate`. The Dockerfile is multi-stage, hardened (non-root user, no dev headers in runtime, explicit `chown`), and bakes Playwright browsers into the image. The frontend is rsync'd as source and rebuilt on the VPS.

**Philosophical implication:** This is DevOps rigor applied to AI infrastructure. No configuration drift. No "it works on my machine." Every deploy is a full, verifiable rebuild. The cost (~2-4 minutes per deploy) is accepted as the price of correctness.

### 5. Observability as Infrastructure, Not Afterthought

Jaeger (distributed tracing) + OpenTelemetry + Langfuse (LLM observability) + Sentry (error tracking) + structlog (structured logging) + Prometheus metrics. This is a comprehensive observability stack that most AI startups skip entirely. The system can trace a request from Nginx → Next.js → WireGuard → FastAPI → Celery worker → LLM API call → response.

**Philosophical implication:** AI agents are non-deterministic black boxes. Without observability, they are un-debuggable. Flowmanner treats observability as essential infrastructure, not a nice-to-have.

### 6. Multi-Tenancy from Inception

Tenant models, workspace isolation, RBAC (`roles.py`), API keys, subscription tiers (Free/Pro/Enterprise at €20/mo), and usage tracking. This is not a prototype that "will add multi-tenancy later." It was architected as a SaaS platform from day one, despite being self-hosted.

**Philosophical implication:** The platform is designed for a marketplace — many creators publishing agents, many consumers using them. This is a **platform business model** embedded in the architecture.

### 7. Integration Hub: Agents Must Act, Not Just Think

Six native OAuth integrations (Linear, Discord, Slack, Notion, GitHub, Google Drive) with webhook support. Linear has full bidirectional sync (`LINEAR_API_KEY`, `LINEAR_WEBHOOK_SECRET`, `LINEAR_TEAM_ID`). Discord has a bot token. Stripe handles payments. Resend handles email. This is not a demo — it's wired for production action.

**Philosophical implication:** Agents are worthless if they can only generate text. They must act on real tools. The integration surface is the agent's hands.

### 8. Two-Auth Redundancy (And Its Hidden Philosophy)

The system uses **two parallel auth systems**: NextAuth JWT cookies (server-side) AND Zustand localStorage key `"fm_tokens"` (client-side). Both must agree. The AGENTS.homelab.md explicitly calls this out: "Two auth systems: NextAuth JWT cookie + Zustand localStorage key 'fm_tokens'. Both must agree."

**Philosophical implication:** This reveals a deep anxiety about session reliability. The dual-auth pattern is a **defensive redundancy strategy** — if one auth layer fails, the other preserves the user's session. But it also creates race conditions and is the likely root cause of the pervasive 401 errors found in the QA audit.

### 9. Frontend as Compiled Artifact

The three-machine architecture (Ops → Homelab → VPS) treats the frontend as a compiled artifact. Source lives on the homelab (`/home/glenn/FlowmannerV2-frontend/`), gets rsync'd to the VPS, and is docker-compose built there. The VPS never holds canonical source. The ops machine is a thin trigger client.

**Philosophical implication:** The frontend is not a development surface. It's a deployment artifact. This is a **build-once, deploy-anywhere** philosophy applied to a Next.js SPA.

### 10. Graceful Degradation as Architecture

Local llama.cpp (Qwen3.6-27B, ~38 tok/s) runs alongside the DeepSeek API. If the API is down or rate-limited, the local model can take over. If WireGuard goes down, the VPS frontend still serves static content (just without API data). The system is designed to **degrade, not die**.

**Philosophical implication:** This is a rejection of cloud monoculture. Availability is achieved through diversity, not scaling.

---

## PART II — WEAKNESSES AND MISSING DIMENSIONS

The philosophy is coherent. The execution has gaps. Below is the systematic audit.

### A. Critical Operational Weaknesses

| # | Weakness | Evidence | Severity |
|---|----------|----------|----------|
| W1 | **Session management is broken** | QA audit: 401 errors on every page. Two-auth race condition. | CRITICAL |
| W2 | **31% page failure rate** | 6 of 19 pages fail to render (Models, Templates, Analytics, Blog, Profile, Admin). QA score: 56.8/100. | CRITICAL |
| W3 | **Zero production monitoring** | Investigation: "Zero monitoring/alerting tools" across all 3 machines. | CRITICAL |
| W4 | **Single backup cron job** | Only langfuse-backup.sh runs. No DB dumps, no volume backups, no config backups. | HIGH |
| W5 | **No CI/CD pipeline** | Deployments are manual bash scripts. No automated testing before deploy. | HIGH |
| W6 | **No automated security updates** | ✅ RESOLVED (2026-07-01): fail2ban active, sshd jail configured (maxretry=3, bantime=3600, port=2222). | ~~HIGH~~ ✅ |
| W7 | **14 Docker services pulled but never started** | ✅ RESOLVED (2026-07-01): 418GB reclaimed via P5.1 + 28GB additional cleanup (build cache + volumes). | ~~MEDIUM~~ ✅ |
| W8 | **3,000+ failed systemd units on ops machine** | ✅ RESOLVED (2026-07-01): 3 units cleared — chromium-cdp masked, drkonqi masked, krfb disabled. 0 failed units remaining. | ~~MEDIUM~~ ✅ |
| W9 | **nginx-static container unhealthy** | ✅ RESOLVED (P5.2): Container was already healthy at time of audit. | ~~MEDIUM~~ ✅ |
| W10 | **WireGuard as single point of failure** | If the tunnel goes down, the entire API surface is unreachable. No fallback routing. | MEDIUM |

### B. Architectural Weaknesses

| # | Weakness | Analysis |
|---|----------|----------|
| W11 | **No event sourcing or execution replay** | Missions execute but there is no append-only event log. You cannot replay a mission to debug it. You cannot time-travel to see what an agent thought at step 3. This makes debugging AI agents nearly impossible. |
| W12 | **No deterministic testing** | LLM outputs are non-deterministic. Without mocking/recording LLM responses for test replay, every test run produces different results. The vitest and playwright frameworks exist but cannot test agent behavior deterministically. |
| W13 | **No agent output evaluation framework** | `evaluation_models.py` exists but there is no evidence of systematic quality measurement. How do you know if agent A is better than agent B at a given mission type? There's no eval harness. |
| W14 | **No sandbox/execution isolation** | `python_sandbox.py` and `nodejs_sandbox.py` exist in the local workspace but their integration status is unclear. Without sandboxed execution, agents that run code are a security risk. |
| W15 | **No semantic caching** | `redis_cache.py` exists but there's no evidence of semantic similarity-based caching for LLM responses. Repeated or similar queries hit the LLM every time. At DeepSeek API pricing, this is directly costly. |
| W16 | **No prompt management system** | No prompt versioning, A/B testing, or prompt registry. Prompts are likely embedded in code. This means prompt changes require full deploys. |
| W17 | **No human-in-the-loop primitives** | Agents execute autonomously. There's no visible "pause and escalate to human" mechanism. No approval gates for high-stakes actions. No confidence threshold that triggers human review. |

### C. Missing Dimensions

| # | Dimension | Why It Matters |
|---|-----------|----------------|
| D1 | **Memory Architecture** | `memory_models.py` exists but there's no evidence of a sophisticated multi-tier memory system (working memory, episodic memory, semantic memory, procedural memory). RAG is retrieval, not memory. Agents cannot learn from past missions, remember user preferences across sessions, or build persistent knowledge. Without memory, every agent interaction is amnesic. |
| D2 | **Inter-Agent Communication Protocol** | `swarm.py` exists but there is no standardized message format, no agent discovery protocol, no capability advertisement. Agents cannot dynamically discover what other agents can do and negotiate task handoffs. This is the difference between a "swarm" (coordinated) and a "crowd" (uncoordinated). |
| D3 | **Execution Provenance** | When a mission completes, there is no cryptographic chain of custody showing which agent did what, with which tools, producing which outputs. For enterprise use, this is a compliance non-starter. |
| D4 | **Cost Attribution** | Usage tracking exists but there's no per-agent, per-mission, per-user cost breakdown. You cannot answer: "How much did the Code Review Agent cost this month?" This makes the marketplace economically unviable — you can't charge for what you can't measure. |
| D5 | **Federation** | Single instance only. No cross-instance agent discovery, no shared mission queues, no federated identity. A Flowmanner instance is an island. This limits network effects and the marketplace's value proposition. |
| D6 | **Multi-Modal Agent Input** | Despite having image_describer.py, ocr_text_extractor.py, speech_to_text_transcriber.py, and audio_sentiment_analyzer.py in the local workspace, there's no evidence these are integrated into the agent pipeline. Agents appear text-only. |
| D7 | **Agent-to-Human Output** | Agents produce structured outputs (JSON/text) but there's no rich rendering layer. No charts, no interactive widgets, no progressive disclosure of complex results. The chat interface is the only output surface. |
| D8 | **Kill Switch / Circuit Breaker** | If an agent enters an infinite loop or makes a catastrophic decision (e.g., deleting production data), there's no visible circuit breaker, spending cap, or emergency stop mechanism. |

---

## PART III — COMPARATIVE ANALYSIS

Flowmanner does not fit neatly into existing categories. It must be triangulated against multiple reference architectures.

### Comparison Matrix

| Dimension | Flowmanner | LangChain/LangGraph | CrewAI | AutoGPT | n8n | OpenAI GPTs |
|-----------|-----------|---------------------|--------|---------|-----|-------------|
| **Category** | Multi-Agent Mission Execution Platform | Agent framework library | Role-based agent framework | Autonomous agent | Visual workflow automation | Prompt template marketplace |
| **Agent Model** | Hierarchical swarm + delegation + marketplace | Graph-based state machines | Role-based sequential | Single-agent loop with tools | DAG-based node execution | Single prompt + tools |
| **Mission/Goal Decomposition** | ✅ Recursive decomposition with sub-tasks | ⚠️ Via LangGraph subgraphs | ❌ Linear task lists only | ❌ Single goal, linear execution | ✅ Via sub-workflows | ❌ No decomposition |
| **Agent Marketplace** | ✅ 50 agents, 10 categories, discoverable | ❌ No marketplace concept | ❌ No marketplace | ⚠️ Agent marketplace (separate) | ✅ Community templates (400+) | ✅ GPT Store |
| **Multi-Tenancy** | ✅ Native (tenants, workspaces, RBAC, subscriptions) | ❌ Library — app's responsibility | ❌ No multi-tenancy | ❌ Single user | ❌ Single user | ✅ Via ChatGPT accounts |
| **Sovereign Deployment** | ✅ Full self-hosting (homelab + VPS) | ✅ Library — deploy anywhere | ✅ Self-hosted | ✅ Self-hosted Docker | ✅ Self-hosted | ❌ Cloud only |
| **Observability** | ✅ Comprehensive (Jaeger + OTEL + Langfuse + Sentry + structlog) | ⚠️ Via LangSmith (paid, proprietary) | ❌ None built-in | ❌ Minimal logging | ⚠️ Execution history only | ❌ Black box |
| **Integration Surface** | ✅ 6+ OAuth integrations + webhooks + Linear/Discord/Slack/Notion/GitHub/GDrive | ⚠️ Via community tools | ⚠️ Limited tool set | ⚠️ Plugin system | ✅ 400+ community nodes | ⚠️ Limited (OpenAI-defined) |
| **Human-in-the-Loop** | ❌ Not visible | ✅ Via LangGraph interrupts | ⚠️ Via "human" tool | ⚠️ Via consent mechanism | ✅ Manual approval nodes | ❌ No concept |
| **Memory Architecture** | ⚠️ Basic (RAG + DB) | ⚠️ Via LangGraph checkpoints | ❌ No persistent memory | ⚠️ File-based memory | ❌ Stateless between runs | ⚠️ Basic conversation memory |
| **Execution Provenance** | ❌ Not implemented | ❌ Not built-in | ❌ Not implemented | ❌ Not implemented | ⚠️ Execution history | ❌ Not implemented |
| **Cost Attribution** | ⚠️ Basic usage tracking | ❌ Not built-in | ❌ Not implemented | ❌ Not implemented | ❌ Not built-in | ❌ Not exposed |
| **Federation** | ❌ Single instance | ❌ Not designed for it | ❌ Not designed for it | ❌ Not designed for it | ❌ Not designed for it | ❌ Not designed for it |
| **Frontend** | ✅ Custom Next.js 16 SPA with i18n | ❌ Library only (no UI) | ❌ CLI only | ✅ Separate web UI | ✅ Full visual builder | ✅ ChatGPT UI |
| **Real-time** | ✅ WebSocket native (Socket.IO) | ⚠️ Via callbacks | ❌ No | ❌ No | ✅ Event-driven | ⚠️ SSE only |
| **LLM Flexibility** | ✅ DeepSeek + local llama.cpp + any OpenAI-compatible | ✅ Any provider | ✅ Any OpenAI-compatible | ⚠️ OpenAI-focused | ✅ Any via community nodes | ❌ OpenAI only |
| **Testing** | ⚠️ Frameworks exist (vitest, playwright) but not systematically run | ⚠️ Via LangSmith testing | ❌ No testing framework | ❌ Minimal | ⚠️ Workflow testing | ❌ No user-facing testing |

### Key Differentiation: What Flowmanner Has That No One Else Does

1. **Agent Marketplace + Multi-Tenancy + Sovereign Deployment** — The combination is unique. OpenAI GPTs has marketplace + multi-tenancy but is cloud-only. n8n has marketplace + self-hosting but is workflow-based, not agent-based. CrewAI has agents + self-hosting but no marketplace or multi-tenancy.

2. **Mission Decomposition** — Recursive task breakdown is absent from every competitor except LangGraph (which requires manual graph construction). Flowmanner's mission decomposition appears to be automated (the `mission_decomposition_routes.py` endpoint name suggests algorithmic decomposition).

3. **Observability Depth** — Jaeger distributed tracing across Nginx → Next.js → WireGuard → FastAPI → Celery → LLM is unprecedented in the agent platform space. Most competitors have zero observability.

### What Flowmanner Lacks That Others Have

1. **Human-in-the-Loop** — LangGraph's `interrupt` API is the gold standard. n8n has manual approval nodes. Flowmanner has nothing visible.
2. **Visual Workflow Builder** — n8n's visual DAG editor is superior to anything Flowmanner appears to have (despite using @xyflow/react — it may only be used for flow visualization, not building).
3. **Community/Plugin Ecosystem** — n8n's 400+ community nodes and LangChain's massive integration ecosystem dwarf Flowmanner's 6 OAuth integrations.

---

## PART IV — TRUE CATEGORY

Flowmanner is not a:
- **Chatbot platform** — Chat exists but is a secondary interface, not the primary paradigm.
- **Workflow automation tool** — Triggers and webhooks exist but are integration glue, not the core abstraction.
- **Prompt engineering tool** — Templates exist but agents are the unit of value, not prompts.
- **Model router** — Multiple LLM backends exist but as infrastructure, not product.

Flowmanner's true category is:

### Multi-Agent Mission Execution Platform (MAMEP)

A **MAMEP** is defined by six properties, all of which Flowmanner exhibits:

1. **Agents are first-class, discoverable entities** — Not just code objects, but entities with identity, personality, capabilities, and a marketplace presence.
2. **Missions are the composable unit of work** — Not prompts, not chats, not workflows. Missions are goal-oriented, decomposable, and trackable.
3. **Agent orchestration is hierarchical** — Swarms, delegation, and recursive decomposition, not linear chains or simple DAGs.
4. **Multi-tenancy is native** — The platform is designed for many creators and many consumers from day one.
5. **Observability is built-in** — Tracing, logging, and evaluation are not afterthoughts.
6. **Sovereign deployment is possible** — The platform can run on owned hardware, not just in the cloud.

This category does not yet exist in industry analyst taxonomies. Flowmanner is defining it.

### Adjacent Categories (For Reference)

| Category | Example | Differentiator from MAMEP |
|----------|---------|---------------------------|
| Agent Framework | LangChain, CrewAI | Library, not platform. No marketplace, no multi-tenancy, no built-in frontend. |
| Workflow Automation | n8n, Zapier | DAG-based, not agent-based. No agent identity, no LLM-native decomposition. |
| AI Chat Platform | ChatGPT, Claude | Single-agent, prompt-based. No orchestration, no marketplace for agents. |
| MLOps Platform | MLflow, Weights & Biases | Model-focused, not agent-focused. No mission concept, no marketplace. |
| RPA Platform | UiPath, Automation Anywhere | Rule-based, not LLM-based. No natural language mission specification. |

---

## PART V — NEXT-GENERATION ARCHITECTURE (FLOWMANNER V3)

### Design Principles

1. **Memory-First Architecture** — Agents must learn across missions. Every interaction builds persistent knowledge.
2. **Execution Provenance by Default** — Every action is cryptographically traceable.
3. **Human-in-the-Loop as Architecture, Not Feature** — Approval gates are built into the execution model at every level.
4. **Federation-Ready** — The protocol anticipates multiple instances discovering each other.
5. **Economic Layer** — Per-agent, per-mission cost attribution enables a functioning marketplace.
6. **Deterministic Testing** — LLM outputs can be recorded and replayed for reliable testing.
7. **Circuit Breakers at Every Boundary** — No agent action is irreversible without explicit confirmation.

### Architecture Diagram (V3)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FLOWMANNER V3                                │
│                                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │  Marketplace │  │  Mission    │  │  Agent      │                 │
│  │  • Discovery │  │  Builder    │  │  Registry   │                 │
│  │  • Ratings   │  │  • Decomp   │  │  • Identity │                 │
│  │  • Billing   │  │  • Planning │  │  • Capability│                │
│  └──────┬───────┘  └──────┬──────┘  └──────┬──────┘                 │
│         │                 │                 │                        │
│  ┌──────┴─────────────────┴─────────────────┴──────┐                │
│  │              ORCHESTRATION ENGINE                │                │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │                │
│  │  │ Swarm    │  │ Delegation│  │ Human-in-    │  │                │
│  │  │ Protocol │  │ Graph    │  │ the-Loop     │  │                │
│  │  └──────────┘  └──────────┘  └───────────────┘  │                │
│  └──────────────────────┬──────────────────────────┘                │
│                         │                                            │
│  ┌──────────────────────┼──────────────────────────┐                │
│  │              EXECUTION LAYER                     │                │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │                │
│  │  │ Sandbox  │  │ Tool     │  │ Circuit       │  │                │
│  │  │ Runtime  │  │ Registry │  │ Breakers      │  │                │
│  │  └──────────┘  └──────────┘  └───────────────┘  │                │
│  └──────────────────────┬──────────────────────────┘                │
│                         │                                            │
│  ┌──────────────────────┼──────────────────────────┐                │
│  │              DATA LAYER                          │                │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │                │
│  │  │ Event    │  │ Memory   │  │ Vector        │  │                │
│  │  │ Store    │  │ Graph    │  │ Index         │  │                │
│  │  │ (ES)     │  │ (Neo4j)  │  │ (Qdrant)      │  │                │
│  │  └──────────┘  └──────────┘  └───────────────┘  │                │
│  └──────────────────────┬──────────────────────────┘                │
│                         │                                            │
│  ┌──────────────────────┼──────────────────────────┐                │
│  │              OBSERVABILITY                       │                │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │                │
│  │  │ Tracing  │  │ Eval     │  │ Cost          │  │                │
│  │  │ (Jaeger) │  │ Harness  │  │ Attribution   │  │                │
│  │  └──────────┘  └──────────┘  └───────────────┘  │                │
│  └─────────────────────────────────────────────────┘                │
│                                                                     │
│  ┌─────────────────────────────────────────────────┐                │
│  │              FEDERATION PROTOCOL                 │                │
│  │  • Agent Discovery  • Mission Sharing           │                │
│  │  • Cross-Instance Identity  • Reputation Sync   │                │
│  └─────────────────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────────────────┘
```

### New Components (What Must Be Built)

#### 1. Event Store (Append-Only Mission Log)

```
MISSION_CREATED → MISSION_DECOMPOSED → SUBMISSION_ASSIGNED →
AGENT_STARTED → TOOL_CALLED → LLM_REQUESTED → LLM_RESPONDED →
TOOL_RESULT → AGENT_COMPLETED → HUMAN_APPROVAL_REQUESTED →
HUMAN_APPROVED → MISSION_COMPLETED
```

**Implementation:** PostgreSQL table with `mission_id`, `sequence_num`, `event_type`, `payload (JSONB)`, `timestamp`, `agent_id`, `parent_event_id`. Enables: replay debugging, compliance audit, cost attribution, training data generation.

#### 2. Memory Graph

A multi-tier memory architecture:

- **Working Memory:** Redis-backed, mission-scoped, TTL = mission duration. What is the agent currently doing?
- **Episodic Memory:** Vector-indexed (Qdrant), cross-mission. "What similar missions have I done before?"
- **Semantic Memory:** Graph database (e.g., Neo4j or property graph in PostgreSQL). "What do I know about this user/domain/tool?"
- **Procedural Memory:** Agent capability registry. "How do I use this tool effectively?"

**Key insight:** Memory isn't just retrieval. It's **retrieval + consolidation + forgetting**. After each mission, relevant experiences are consolidated into episodic and semantic memory. Irrelevant details are forgotten (to manage vector index size).

#### 3. Human-in-the-Loop Primitives

```python
class HumanInterrupt(Exception):
    """Raised when an agent needs human input."""
    interrupt_type: Literal["approval", "clarification", "escalation"]
    context: dict  # What the agent was doing
    proposed_action: dict  # What the agent wants to do
    confidence: float  # 0.0 to 1.0
    deadline: Optional[datetime]  # If set, auto-approve/deny after deadline
```

Every tool call above a configurable risk threshold triggers a `HumanInterrupt`. The frontend has a dedicated "Inbox" for pending human interventions.

#### 4. Deterministic Testing Framework

```python
class LLMRecorder:
    """Records LLM responses and replays them for deterministic testing."""
    def record(self, prompt: str, response: str, model: str, params: dict) -> None
    def replay(self, prompt: str, model: str) -> Optional[str]
    def semantic_match(self, prompt: str, threshold: float = 0.92) -> Optional[str]
```

Combined with the Event Store, this enables: "Replay mission #1234 exactly as it happened" and "Run mission #1234 with agent B instead of agent A, using the same LLM responses where prompts match."

#### 5. Circuit Breaker System

```python
class CircuitBreaker:
    """Prevents runaway agent behavior."""
    max_llm_calls_per_mission: int = 100
    max_cost_per_mission_usd: float = 5.00
    max_duration_seconds: int = 600
    max_tool_calls_per_agent: int = 50
    destructive_actions_require_approval: bool = True  # DELETE, DROP, etc.
```

When any limit is hit, the agent is gracefully stopped, the mission is marked as `CIRCUIT_BROKEN`, and a human notification is sent.

#### 6. Cost Attribution Engine

Every event in the Event Store is tagged with cost metadata:

```json
{
  "event_type": "LLM_REQUESTED",
  "cost": {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "input_tokens": 1234,
    "output_tokens": 567,
    "cost_usd": 0.00123,
    "agent_id": "agent-abc-123",
    "mission_id": "mission-xyz-456",
    "user_id": "user-def-789",
    "workspace_id": "ws-ghi-012"
  }
}
```

This enables: per-agent billing, per-mission cost analysis, per-user usage reports, marketplace revenue sharing.

#### 7. Federation Protocol

```protobuf
// Agent Discovery
service AgentDiscovery {
  rpc Announce(AgentManifest) returns (AnnounceResponse);
  rpc Search(SearchRequest) returns (SearchResponse);
  rpc Subscribe(SubscriptionRequest) returns (stream AgentUpdate);
}

// Mission Sharing
service MissionBroker {
  rpc Submit(MissionRequest) returns (MissionResponse);
  rpc GetStatus(MissionId) returns (MissionStatus);
  rpc StreamEvents(MissionId) returns (stream MissionEvent);
}
```

A Flowmanner instance can optionally expose a federation endpoint. Other instances can discover its agents and submit missions. Reputation is synchronized across instances.

### Migration Path from V2 to V3

| Phase | Duration | Changes |
|-------|----------|---------|
| **Phase 1: Foundation** | 2 weeks | Add Event Store. Instrument all existing mission execution to emit events. No behavior change — pure instrumentation. |
| **Phase 2: Memory** | 3 weeks | Implement multi-tier memory. Add memory consolidation workers. Integrate RAG into agent context assembly. |
| **Phase 3: Reliability** | 2 weeks | Add circuit breakers. Add deterministic testing (LLMRecorder). Fix session management (unified auth). Fix all 6 broken pages. |
| **Phase 4: Human-in-the-Loop** | 2 weeks | Implement HumanInterrupt primitives. Add Inbox UI. Configure risk thresholds per tool. |
| **Phase 5: Economics** | 2 weeks | Implement cost attribution engine. Add billing dashboards. Enable marketplace revenue sharing. |
| **Phase 6: Federation** | 4 weeks | Implement federation protocol. Add cross-instance agent discovery. Add reputation sync. |

**Total: ~15 weeks to V3 MVP.**

### Deeper: The V3 Developer Experience

#### Agent Definition DSL (Replacing Imperative Python)

```yaml
# agent-definition.yaml
agent:
  id: code-reviewer
  name: "Code Review Agent"
  version: "3.0.0"
  publisher: "flowmanner-official"

  personality:
    tone: "direct"
    expertise: ["code review", "security analysis", "performance optimization"]
    constraints:
      - "Never approve code that introduces SQL injection"
      - "Always suggest tests for new functionality"

  capabilities:
    tools: [github.read_file, github.create_review, git.diff]
    models: [deepseek-chat, claude-3-opus]  # Ordered by preference
    max_tool_calls_per_mission: 20

  memory:
    episodic:
      retention_days: 90
      consolidation_strategy: "summarize_then_forget"
    semantic:
      domains: ["code_patterns", "security_vulnerabilities", "performance_anti_patterns"]

  human_in_the_loop:
    approval_required_for: [github.merge_pr, github.delete_branch]
    clarification_threshold: 0.7  # Ask human if confidence < 70%
    escalation_on: [test_failure, security_violation, timeout]

  pricing:
    per_mission_usd: 0.50
    revenue_share: 0.70  # Creator gets 70%

  evaluation:
    test_suite: "code-reviewer-evals"
    min_pass_rate: 0.85
    benchmark_missions: [mission-001, mission-002, mission-003]

mission:
  id: review-pull-request
  name: "Review Pull Request"
  description: "Comprehensive code review with security analysis"

  decomposition:
    strategy: "recursive"
    max_depth: 3
    sub_mission_types:
      - security_scan
      - style_review
      - test_coverage_check
      - dependency_audit

  agents:
    primary: code-reviewer
    reviewers: [security-expert, performance-expert]  # Swarm review
    arbiter: human  # Final decision by human

  circuit_breakers:
    max_cost_usd: 2.00
    max_duration_seconds: 300
    max_llm_calls: 50
```

---

## PART VI — FORMAL SPECIFICATION

### System Model

A Flowmanner system is a tuple:
```
FM = (A, M, U, W, O, E)
```
where:
- **A** = set of Agents (each with identity, personality, capabilities, memory)
- **M** = set of Missions (decomposable, trackable units of work)
- **U** = set of Users (with roles, subscriptions, workspaces)
- **W** = set of Workspaces (isolated tenant environments)
- **O** = Orchestration Engine (swarm protocol, delegation graph, human-in-the-loop)
- **E** = Execution Environment (sandbox, tool registry, circuit breakers)

### Agent Model

An agent a ∈ A is defined as:
```
a = (id, name, version, publisher,
     personality,           # Tone, expertise, constraints
     capabilities,          # Tools, models, max calls
     memory_config,          # Episodic, semantic, procedural
     hitl_config,           # Approval gates, escalation rules
     pricing,               # Per-mission cost, revenue share
     evaluation_suite)      # Test missions, min pass rate
```

### Mission Model

A mission m ∈ M is defined as:
```
m = (id, name, description, state,
     decomposition_tree,    # Hierarchical sub-mission structure
     agent_assignments,     # Which agents execute which sub-missions
     event_log,             # Append-only event sequence
     circuit_breaker_state, # Current breaker status
     cost_ledger)           # Accumulated costs by agent
```

Mission states: `CREATED → PLANNING → DECOMPOSED → IN_PROGRESS → AWAITING_HUMAN → COMPLETED | FAILED | CIRCUIT_BROKEN`

### Event Model

An event e ∈ E is defined as:
```
e = (id, mission_id, sequence_num, timestamp,
     event_type,            # From event type enum
     agent_id,              # Which agent generated this
     payload,               # Event-specific data
     parent_event_id,       # For causal tracing
     cost,                  # Optional cost metadata
     correlation_id)        # For distributed tracing
```

### Execution Semantics

1. **Mission Submission:** User submits mission m. State = `CREATED`. Event: `MISSION_CREATED`.

2. **Planning:** Orchestration engine analyzes mission, determines decomposition strategy. State = `PLANNING`. Event: `MISSION_PLANNED`.

3. **Decomposition:** Mission is recursively decomposed into sub-missions. State = `DECOMPOSED`. Event: `MISSION_DECOMPOSED` for each sub-mission.

4. **Agent Assignment:** For each sub-mission, the best agent is selected based on:
   - Capability match score
   - Past performance on similar sub-missions (from evaluation harness)
   - Cost efficiency
   - Current availability/load

5. **Execution:** For each sub-mission assigned to agent a:
   - Agent receives mission context + relevant memories
   - Agent selects tools and model
   - For each tool call:
     - Check circuit breakers (cost, duration, call count)
     - If tool is in `approval_required_for` list → `HumanInterrupt`
     - If confidence < `clarification_threshold` → `HumanInterrupt`
     - Execute tool in sandbox
     - Record event
   - Sub-mission completes. Event: `SUBMISSION_COMPLETED`.

6. **Aggregation:** Results from all sub-missions are aggregated. If reviewers assigned, swarm voting determines final output. If arbiter is human, final output goes to Inbox.

7. **Completion:** State = `COMPLETED`. Event: `MISSION_COMPLETED`. Memory consolidation worker triggered.

8. **Failure Handling:**
   - If circuit breaker trips → State = `CIRCUIT_BROKEN`. Human notified.
   - If agent error → Retry with different agent (max 3 retries). If all fail → State = `FAILED`.
   - If human timeout → Default action (configurable: auto-approve or auto-deny).

### Memory Consolidation Algorithm

After mission completion:

1. **Extract Episodes:** From the event log, extract sequences of (context, action, outcome).
2. **Summarize:** Each episode is summarized into a compact representation using a lightweight LLM call.
3. **Index:** Summarized episodes are embedded and stored in Qdrant with metadata (mission_id, agent_id, success/failure, tags).
4. **Consolidate:** Related episodes are merged. Patterns across episodes are extracted as semantic memories.
5. **Forget:** Episodes older than `retention_days` are summarized further and the raw events are archived (cold storage).
6. **Update Procedural Memory:** If the agent's performance improved or degraded on certain tool types, update the procedural memory weights.

### Invariants

1. **Event Immutability:** Once written, events are never modified. Append-only.
2. **Causal Ordering:** For any two events e1, e2 in the same mission, if e1 caused e2, then `e2.parent_event_id = e1.id`.
3. **Cost Monotonicity:** Total cost increases monotonically during a mission. Never decreases.
4. **Circuit Breaker Precedence:** Circuit breaker checks happen before tool execution. No tool executes without passing breaker checks.
5. **Human-in-the-Loop Supremacy:** If a human decision is pending, no further autonomous actions are taken in that mission branch.
6. **Sandbox Isolation:** All tool executions happen in isolated sandboxes. Side effects only through approved integration channels.
7. **Memory Privacy:** Agent memories are scoped to workspace. Cross-workspace memory access is prohibited.

---

## PART VII — CONTROVERSIAL POSITIONS

These are architectural opinions that challenge assumptions. They are presented as assertions to be debated, not accepted.

### 1. The Agent Marketplace Is the Product, Not the Agents

The individual agents are interchangeable. The marketplace — the ability to discover, evaluate, and compose agents — is the moat. V3 should invest disproportionately in marketplace infrastructure: ratings, reviews, benchmarks, cost comparison, A/B testing, and revenue sharing. The agents themselves will be commoditized within 12 months.

### 2. Memory Is More Important Than Intelligence

A dumb agent with perfect memory outperforms a smart agent with no memory. The V3 memory architecture should receive 40%+ of the engineering investment. Current Flowmanner has near-zero memory. This is the single biggest gap between the current product and the vision.

### 3. Human-in-the-Loop Is Not a Crutch — It's a Feature

The industry treats human intervention as a temporary necessity until agents get "good enough." This is wrong. Human judgment is irreplaceable for high-stakes decisions. V3 should make the human-in-the-loop experience *delightful* — rich context, clear options, confidence scores, and fast decision interfaces. Not an interruption. A collaboration.

### 4. Federation Is the Only Path to Network Effects

A single Flowmanner instance is valuable. A network of Flowmanner instances that share agents, missions, and reputation is exponentially more valuable. Federation should be designed in from V3, not bolted on later. This means: standard protocol, identity system, reputation model, and cross-instance billing.

### 5. Deterministic Testing Is Non-Negotiable for Enterprise Adoption

No enterprise will deploy agents that cannot be tested deterministically. The LLMRecorder pattern (record + replay + semantic matching) is the minimum viable approach. Without it, every deployment is a gamble.

### 6. Circuit Breakers Should Be Conservative by Default

The default posture should be: "stop and ask" rather than "proceed and hope." Agents should be paranoid about irreversible actions. The circuit breaker thresholds should start restrictive and loosen only with proven reliability data.

---

## APPENDIX A: Current System Metrics

| Metric | Value |
|--------|-------|
| Backend API routes | 68 |
| Backend models | 33 |
| Frontend component directories | 17 |
| Docker services (running) | 6 |
| Docker services (pulled, not running) | 14 |
| Total Docker images on disk | ~50GB |
| LLM throughput (local) | ~38 tok/s (Qwen3.6-27B Q5_MTP) |
| LLM throughput (API) | DeepSeek API |
| Database tables | 80+ |
| Pages on production | 19 |
| Pages with rendering failures | 6 (31%) |
| QA health score | 56.8/100 |
| Backup cron jobs | 1 |
| Monitoring systems | 0 |
| CI/CD pipelines | 0 |
| Test frameworks | 2 (vitest, playwright — installed but not systematically run) |
| Languages | 2 (TypeScript + Python) |
| Machines | 3 (Homelab + VPS + Ops) |
| GPU VRAM | ~32GB total (RTX 3070 8GB + RTX 3060 12GB) |

---

## APPENDIX B: Reference Architectures Cited

- **LangGraph:** LangChain's graph-based agent framework. Interrupt API for human-in-the-loop. Checkpoints for state persistence.
- **CrewAI:** Role-based multi-agent framework. Sequential and hierarchical process modes.
- **n8n:** Visual workflow automation. 400+ community nodes. Fair-code license.
- **AutoGPT:** Autonomous agent with plugin system. Goal-oriented execution loop.
- **OpenAI GPTs:** Prompt template marketplace. Cloud-only. Limited tool integration.

---

*End of analysis. This document is a living specification. It should be versioned alongside the codebase and updated as architectural decisions are made and reversed.*
