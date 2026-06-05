# Flowmanner — Deep Strategic Questions for Next-Level Brainstorming

**Purpose:** This document captures the key architectural elements of Flowmanner's "Mission" system and poses deep strategic questions. Pass this to Claude Opus 4.7 to generate a concrete, actionable plan for taking Flowmanner to the next level.

**Date:** June 5, 2026
**Current State:** Functional but incomplete. Event-sourced substrate is 80% built but untested. 31% of pages fail to render. Auth 401 loop bug blocks H1 exit gate. No production monitoring.

---

## Part 1: Key Elements of "Mission" in Flowmanner

### 1.1 Mission Lifecycle & State Machine

Missions follow a strict state machine with validated transitions:

```
DRAFT → PLANNING → READY → RUNNING → COMPLETED
                    ↓         ↓
                  ABORTED   ABORTED
                    ↑         ↑
              (BUDGET_EXCEEDED, ERROR_CASCADE, USER_REQUESTED)
```

- `MissionStatus` enum enforces valid transitions via `_TRANSITIONS` dict
- `MissionTaskStatus` tracks per-task: PENDING → RUNNING → COMPLETED / FAILED
- Failed tasks can be retried
- Abort reasons: USER_REQUESTED, BUDGET_EXCEEDED, ERROR_CASCADE

### 1.2 Event-Sourced Substrate (The Foundation)

The most architecturally significant element. Every mission state change is recorded as an immutable event:

- **`SubstrateEvent`** — Append-only log table (`substrate_events`). PostgreSQL triggers prevent UPDATE/DELETE.
- **`SubstrateRunState`** — In-memory projection rebuilt from events. Not persisted; reconstructed at worker startup.
- **`ReplayEngine`** — Replays events in batches (1,000/batch) to rebuild state. Supports time-travel debugging (rebuild at any sequence number). Can verify determinism by replaying twice.
- **Event types:** 20+ types covering lifecycle (RUN_STARTED/COMPLETED), node execution, LLM calls, tool calls, human-in-the-loop interrupts, circuit breaker events, budget tracking.

### 1.3 Execution Engine (5 Layers)

```
Routing → Planning → Orchestration → Execution → Learning
```

**Execution Modes:**
| Mode | Description | Use Case |
|------|-------------|----------|
| Mission Executor | Single-agent task loop | Simple tasks |
| DAG Executor | Parallel execution with topological ordering | Independent subtasks |
| Swarm Orchestrator | Multi-agent decomposition + matching + synthesis | Complex research |
| Swarm Pipeline | 7-phase state machine (Dispatch→Research→Draft→Debate→Consensus→Synthesis→Review) | High-quality outputs |
| Graph Executor | Pre-defined node graphs from visual builder | Repeatable workflows |

**Nexus Meta-Orchestration:** Uses Query/Key/Value attention-style matching to select agents based on capabilities, similar to how transformers attend to relevant context.

### 1.4 Mission Templates & Versioning

- **`MissionTemplate`** — Reusable blueprints with `default_plan`, `default_tasks`, `default_constraints` (JSONB). Includes `expected_behaviors` for replay assertions.
- **`MissionVersion`** — Immutable snapshots for audit trails and rollbacks.
- **`NodeGroup`** — Grouped execution nodes with shared configuration.

### 1.5 Unified Run Model (Proposed)

A design blueprint to consolidate 5 overlapping concepts:

| Current | Unified |
|---------|---------|
| Mission | Blueprint (definition) + Run (execution) |
| Workflow | Blueprint + Run |
| Flow/Graph | Blueprint + Run |
| OrchestratorExecution | Run |
| SwarmPipeline | Run |

- **Blueprint** = versioned, reusable work definition (merges Mission + Template + Workflow + Graph)
- **Run** = immutable execution instance with snapshot of blueprint at execution time
- Currently: 14 disparate execution tables across 5 concepts. The `Mission` model impacts 78 files.

### 1.6 Observability Stack

- **Cost Attribution Engine** — Aggregates LLM costs by agent, mission, user, workspace, period
- **Langfuse Integration** — LiteLLM success/failure callbacks, trace linking
- **SLO Dashboards** — Mission success rate >95%, p99 SSE latency <300ms, model fallback >99%
- **Jaeger + OpenTelemetry** — Distributed tracing across services
- **Intervention Distance** (planned) — Measures autonomous actions between human interventions

### 1.7 Chat as Mission Interface

- SSE streaming with 60fps RAF-batched token updates
- Zustand global state for chat, canvas, code sandbox
- ThoughtPanel for chain-of-thought display
- Tool event feed showing real-time agent actions
- Branching conversations with thread management

### 1.8 Infrastructure

- **Homelab-first sovereign deployment** — PostgreSQL, Redis, Qdrant, RabbitMQ, Celery, Jaeger, llama.cpp all on owned hardware
- **Local LLM** — Qwen3.6-27B on dual RTX 5060 Ti (32GB VRAM), ~38 tok/s
- **Graceful degradation** — Routes between DeepSeek API and local llama.cpp
- **3-machine topology** — Homelab (backend), VPS (frontend/nginx), Ops/Dev connected via WireGuard

---

## Part 2: Deep Strategic Questions

### Category A: The Substrate — From Infrastructure to Product

The event-sourced substrate is Flowmanner's hardest-to-replicate asset. But it's 80% built and 0% tested.

**A1. Replay Assertions as a Product**
The plan calls for "Replay Assertions" — defining expected behaviors from a successful run and validating future runs against them. This is genuinely novel (no competitor does this). But:
- How do you make assertions *easy to create* without requiring users to write code? Can the system auto-suggest assertions by observing patterns across multiple successful runs?
- Should assertions be binary (pass/fail) or probabilistic (95% confidence)? How do you handle non-deterministic LLM outputs where the same prompt produces different but equally valid results?
- What's the minimum viable assertion surface that would make a user say "I can't go back to a world without this"?

**A2. Time-Travel Debugging as a Moat**
The replay engine can rebuild state at any sequence number. This enables:
- "What did the agent know at step 47?" — inspecting the exact context window at any point
- "What if the agent chose differently at step 12?" — branching alternative execution paths
- "Why did the cost spike between steps 80-85?" — correlating events with resource usage

How do you productize time-travel debugging so it's not just a developer tool but something that non-technical stakeholders (PMs, founders) use to understand agent behavior? What UI paradigm makes temporal navigation intuitive?

**A3. Event Sourcing at Scale**
The append-only event log will grow unboundedly. At what volume does this become a problem?
- How do you handle missions with 10,000+ events (complex swarm pipelines)?
- Should old events be archived to cold storage? If so, how does replay work?
- Is PostgreSQL the right long-term store for an append-only event log, or should this migrate to something like EventStoreDB or Apache Kafka with log compaction?

### Category B: Agent Intelligence & Autonomy

**B1. The Agent-to-Agent Problem**
Flowmanner has 50+ predefined agent personalities and a capability lattice for matching. But:
- How do agents *discover* each other at runtime? The Nexus QKV matching is static (pre-defined capabilities). Should it be dynamic — agents learning from past collaborations which other agents produce the best outcomes?
- When should an agent *refuse* a task? The system has circuit breakers for error cascades, but what about capability-aware refusal ("I'm a code review agent, not a data analysis agent")?
- How do you prevent "agent sprawl" — the tendency for every new feature to spawn new agent types instead of composing existing ones?

**B2. The Human-in-the-Loop Spectrum**
HITL is planned but not built. The current system is fully autonomous or fully manual. The real question:
- Where on the spectrum should each mission type sit? A code review mission might need HITL at the end (approve/reject). A research mission might need HITL at the beginning (clarify scope) and end (validate findings). A data pipeline might need HITL only on anomalies.
- Should HITL be *proactive* (agent asks for permission) or *reactive* (agent proceeds but human can interrupt)? The event log already supports `HUMAN_INTERRUPT` events.
- How do you avoid "HITL fatigue" — where the agent asks for so many approvals that the human becomes a rubber stamp?

**B3. Self-Improvement Without Catastrophic Drift**
The system has a self-improvement subsystem with error taxonomy and adaptation. But:
- How do you ensure that self-improvement doesn't cause catastrophic drift — where the agent optimizes for a metric (e.g., speed) at the expense of quality?
- Should improvements be versioned and rollback-able (like the MissionVersion snapshots)?
- What's the feedback loop? User ratings? Implicit signals (did they edit the output)? Cost efficiency? Task completion rate?

### Category C: The Product Surface

**C1. Chat as the Primary Interface — Is It Enough?**
Flowmanner's UI is chat-centric (SSE streaming, canvas, code sandbox). But:
- Is chat the right interface for *all* mission types? A data pipeline mission doesn't need a chat — it needs a dashboard. A research mission doesn't need a canvas — it needs a document editor.
- Should the UI adapt to the mission type? (Chat for conversational tasks, dashboard for monitoring tasks, editor for content tasks)
- How do you handle missions that run for hours/days? Chat is inherently short-session. The current polling-based status check (`wait_for_mission`) is CLI-grade. What does a production-grade "set it and forget it" interface look like?

**C2. The Template Marketplace**
Templates are the cold-start solution. But:
- How do you bootstrap the marketplace? Self-publish 20+ templates? Community contributions? AI-generated templates from successful runs?
- What makes a template *good*? Just "it works" isn't enough. Should templates include expected behaviors, cost estimates, quality benchmarks?
- How do you handle template versioning when the underlying LLM capabilities change? A template designed for GPT-4 might break with GPT-5's different behavior patterns.

**C3. Cost Transparency as a Feature**
The cost dashboard exists but is a monitoring afterthought. Should cost be a *first-class design constraint*?
- Should missions have mandatory cost budgets (not just circuit breakers)?
- Should the system refuse to start a mission if the estimated cost exceeds the budget?
- How do you make cost predictable for users who can't estimate LLM costs? ("This mission will cost approximately $0.15" before starting)
- Should there be a "cost optimization mode" that routes to cheaper models when quality trade-offs are acceptable?

### Category D: Architecture & Technical Debt

**D1. The Unified Run Model**
The design proposes consolidating 5 concepts (Mission, Workflow, Flow, Orchestrator, Pipeline) into Blueprint + Run. The Mission model alone impacts 78 files. This is a massive refactor.
- Should this be a "big bang" migration or an incremental one (adapters, dual-write, gradual cutover)?
- What's the rollback strategy if the migration breaks something in production?
- Is the current diversity of execution modes (5 modes) actually valuable, or should it converge to fewer, more composable primitives?

**D2. The Auth Problem**
The 401 infinite loop blocks the H1 exit gate. The "two-auth redundancy" (NextAuth + Zustand) was identified as a root cause in the architectural analysis.
- Should the auth layer be simplified to a single strategy?
- How do you handle long-running missions that outlast auth tokens? The current system doesn't address token refresh during multi-hour missions.

**D3. The Testing Gap**
The substrate is 80% built but 0% tested. The chaos test (`test_kill_worker_mid_mission`) doesn't exist.
- What's the minimum test coverage needed to ship with confidence?
- Should you invest in integration tests (test the full pipeline) or unit tests (test individual components)?
- How do you test non-deterministic LLM behavior? Mock responses? Golden datasets? Statistical assertions?

### Category E: Strategic Positioning

**E1. Who Is Flowmanner For?**
The platform has 34 models, 50 agent personalities, a marketplace, multi-tenancy, BYOK, a visual flow builder, a chat interface, a CLI, an SDK, and an event-sourced execution engine. That's a lot.
- Should Flowmanner be a "do everything" platform or focus on a specific niche?
- Who is the ideal user? A solo developer automating personal tasks? A startup running agent workflows? An enterprise with compliance requirements?
- What's the 10-second pitch that makes someone choose Flowmanner over n8n, LangChain, CrewAI, or AutoGen?

**E2. Open Source Strategy**
The Omega spec mentions "open-source replay engine" as strategically sound but a multi-month maintenance burden.
- Should the core substrate be open-sourced to build community and trust?
- What's the monetization model? Hosted SaaS? Enterprise features? Marketplace commission?
- How do you prevent a well-funded competitor from cloning the open-source core and out-competing on marketing?

**E3. The Local LLM Advantage**
Flowmanner runs Qwen3.6-27B on dual RTX 5060 Ti at ~38 tok/s. This is unique — no competitor offers sovereign AI with local inference.
- How do you make this a *product feature* rather than just infrastructure? ("Your data never leaves your hardware")
- Can local inference be the default, with cloud APIs as the fallback (the reverse of the current architecture)?
- What happens when local models can't handle a task? How do you gracefully escalate without confusing the user?

### Category F: The Hard Questions Nobody Asks

**F1. What If LLMs Get 10x Cheaper in 12 Months?**
Cost is currently a major design constraint (budget ceilings, cost dashboards, model routing). If inference costs drop to near-zero:
- Which of your cost-focused features become irrelevant?
- What becomes the new bottleneck? (Latency? Context window? Quality?)
- Should you design for the current cost landscape or the future one?

**F2. What If Agents Become Fully Autonomous?**
The "Intervention Distance" metric measures human involvement. If agents become reliable enough to never need human intervention:
- What's the value proposition of an "orchestration platform" vs. just letting agents run?
- Does HITL become a liability instead of a feature?
- What does Flowmanner become in a world where agents don't need orchestration — just infrastructure?

**F3. What's the "iPhone Moment" for Agent Platforms?**
Every technology has a moment where it goes from "useful for experts" to "everyone needs this." ChatGPT was that for LLMs. What's the equivalent for agent orchestration?
- Is it a specific use case that's so compelling it goes viral?
- Is it a UX breakthrough that makes agent orchestration as intuitive as using a spreadsheet?
- Is it an integration that puts agent workflows into tools people already use (Slack, Notion, GitHub)?

---

## Part 3: Synthesis Prompt for Claude Opus

When you pass this to Opus, use this framing:

> **System Context:** You are a senior product strategist and technical architect reviewing Flowmanner, an AI workflow orchestration platform. The platform has a working but incomplete foundation: event-sourced execution substrate (80% built, 0% tested), 5 execution modes, a chat-centric UI, cost observability, and a Python SDK. It runs on sovereign infrastructure with local LLM inference.
>
> **Your Task:** Based on the key elements and questions above, produce:
>
> 1. **A prioritized roadmap** (P0/P1/P2) with concrete deliverables for the next 90 days
> 2. **A "moat strategy"** — what 2-3 things should Flowmanner invest in that competitors can't easily replicate?
> 3. **A "kill list"** — what features or capabilities should Flowmanner explicitly NOT build, and why?
> 4. **A "10-second pitch"** — how should Flowmanner describe itself in one sentence?
> 5. **Risk analysis** — what are the top 3 existential risks and how to mitigate each?
> 6. **The "iPhone moment" hypothesis** — what specific scenario could make agent orchestration a must-have for everyone?
>
> Be opinionated. Prefer bold bets over safe incrementalism. The goal is to go from "interesting project" to "category-defining product."

---

*Generated from Flowmanner codebase analysis, June 5, 2026.*
