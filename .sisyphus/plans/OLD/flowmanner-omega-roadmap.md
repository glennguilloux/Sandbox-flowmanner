# Flowmanner — Roadmap Plan
*Source corpus: /opt/flowmanner/Docs/{ARCHITECTURE, CHAT-UX-ARCHITECTURE, EXECUTION-ENGINE, FLOWMANNER Ω — ARCHITECTURAL CRI.txt, FLOWMANNER-OMEGA-SPEC, FLOWMANNER-ONTOLOGY}.md*
*Drafted: 2026-06-01*

---

## 0. How to Read This Roadmap

The six documents in /opt/flowmanner/Docs/ describe a single product from six angles. Read together they tell a coherent story:

1. **FLOWMANNER-ONTOLOGY.md** — *what the system is.* 49 models, five pillars (Missions, Agents, Chat, Graphs/Flows, Marketplace), 7 execution models, dual-machine infra.
2. **ARCHITECTURE.md** — *how the parts fit together.* Five-layer stack (Routing → Planning → Orchestration → Execution → Learning), FastAPI + Next.js 16, SSE chat, LangGraph integration, Nexus meta-orchestration.
3. **CHAT-UX-ARCHITECTURE.md** — *how the user touches it.* Composition-of-hooks + Zustand store, SSE streaming at 60fps, Canvas + CodeSandbox.
4. **EXECUTION-ENGINE.md** — *how work actually gets done.* Per-layer breakdown of solo/DAG/swarm/pipeline/graph/nexus/langgraph executors, the 9 error classes, the browser agent loop, the trigger scheduler.
5. **FLOWMANNER Ω — ARCHITECTURAL CRI.txt** — *what is wrong.* A forensic critique listing 13 weaknesses, 11 missing dimensions, 4 guarantee gaps, 18 invariants, and a 9-phase migration (Ω.0–Ω.8) for a next-generation substrate.
6. **FLOWMANNER-OMEGA-SPEC.md** — *what the next-generation system looks like.* The same critique, more rigorously, plus an executable Pydantic specification: CapabilityToken, AgentState, Budget, Workflow, Event, Kernel, CapabilityEngine, BudgetEnforcer, WorkflowTypeChecker, IOStream, LearningStore, ChaosTestSuite — with 19 invariants.

The roadmap below integrates all six. It is organized as **five horizons**, each with concrete deliverables, dependencies on the current state, and the open questions that must be answered before each horizon begins.

---

## 1. Current State (Where We Are)

### 1.1 Inventory from the docs

| Area | Count / Size | Source |
|---|---|---|
| Backend Python files | ~618 files, ~150k LOC | Ω spec preamble |
| API route modules | 67+ | ARCHITECTURE.md |
| Frontend pages | 85+ | ARCHITECTURE.md |
| Backend data models | 49 (across 12 domains) | ARCHITECTURE.md, ONTOLOGY.md |
| Execution models implemented | 7 (Solo, DAG, Swarm, SwarmPipeline, Graph, LangGraph, Nexus) | EXECUTION-ENGINE.md |
| Execution models distinct in practice | 4 of 7 (others route to the same LLM call loop) | Ω crit Part II |
| Error classes in FailureAnalyzer | 9 | EXECUTION-ENGINE.md |
| Composition patterns in CapabilityComposer | 4 (sequential, parallel, conditional, loop) | EXECUTION-ENGINE.md |
| Agent representations | 5 model files / 10 classes | Ω crit W9 |
| Org models | 2 (Workspace + Tenant) | Ω crit W7 |
| Workflow models | 2 (Flow + Graph) | Ω crit W8 |
| Auth systems | 2 (NextAuth JWT + Zustand fm_tokens) | Ω crit W6 |
| Self-healing runtime | 6 files, 518 lines, no test wire-up | Ω crit Part II |
| Chaos tests | 1 file, 0 test cases | Ω crit W12 |
| Marketplace | 5 models + 4 pages, no community | ONTOLOGY.md §1 |
| Open questions in ontology | 7 | ONTOLOGY.md §8 |

### 1.2 What works (underclaimed in the docs)

- **Chat UX** — composition-of-hooks, SSE streaming at 60fps with RAF batching, optimistic-with-rollback, dual auth, sandbox panel. ARCHITECTURE.md §4, CHAT-UX-ARCHITECTURE.md.
- **Chat streaming** — 3-retry with exponential backoff + jitter, tool event throttling (200ms), dedup via Set, [DONE] finalize with token report. CHAT-UX-ARCHITECTURE.md §2.
- **Dual-machine ops** — VPS (Nginx+Next.js) + Homelab (FastAPI+Postgres+Redis+Qdrant+RabbitMQ+Celery+Jaeger+llama.cpp) over WireGuard. AGENTS.md + ARCHITECTURE.md §2.
- **LangGraph integration** — StateGraph with process_input → convert_to_tools → check_approval → execute_tools → generate_response, with PENDING/APPROVED/REJECTED human-in-the-loop on Redis (TTL 300s). ARCHITECTURE.md §7.
- **Multimodal mission pipeline** — per Ω crit Part II "asymmetry" note.
- **FastAPI implementation** — 67 route modules, asyncpg, Alembic, OpenTelemetry+Langfuse observability. ARCHITECTURE.md §2.

### 1.3 What is broken or aspirational (overclaimed in the docs)

The Ω critique names these explicitly with code citations:

- **Mission silent success** — `mission_executor.py` historically returned `{"success": True}` on empty output (DEEP-DIVE-ANALYSIS GAP-2; appears fixed but trace remains).
- **ModelRouter silent failure** — `ModelRouter._is_model_available` calls `llm_manager.get_model(model_id)` without `user_id`/`db_session`, so all models return None and `_select_model` fails instantly. Combined with `mission_executor.py` ignoring `success=False` flag, missions complete in ~28ms with 0 tokens and `output_data={}`. (Per user's pinned memory note.)
- **Dual auth disagreement** — 401-instead-of-200 infinite loop, recurring family of bugs (audits 2026-05-17 and 2026-05-22).
- **Self-healing is a skeleton** — `runtime/` is 6 files, 518 lines, no test coverage.
- **Chaos-tested claim is a single file** — `chaos_langfuse.py` with no inspectable logic.
- **Infinite capability lattice is a constant** — `max_depth=3`.
- **Failure recovery has no budget** — 9 error classes, all recoverable; misclassified error retries forever.
- **Learning loop is write-only** — `LearningFeedbackDB` and `AdaptationRuleDB` grow monotonically; no recency weighting; no evidence planners call `inject_into_planner_context`.
- **Workspace vs Tenant** — both wired, both routed, neither canonical.
- **Flow vs Graph** — two visual builders, two persistence models, two execution engines.
- **5 agent representations** — no canonical lifecycle.
- **CodeGraph MCP** — referenced in AGENTS.homelab.md, not in requirements.txt/package.json.
- **Agent Protocol is a SQLAlchemy row** — no serialization, no version negotiation, no wire protocol.

### 1.4 The four guarantees Flowmanner lacks

The Ω spec Part VI.2 names these as the substrate an "agentic OS" in 2026 must provide:

1. **Durable** — every state transition is an event; crashes resume from the last event. *(Temporal/ESAA template.)*
2. **Type-checked** — input/output schemas enforced at composition. *(Pydantic; not dict.)*
3. **Capability-bounded** — unforgeable tokens, no ambient authority, attenuation chains. *(OCap; not RBAC.)*
4. **Bounded** — every run has a declared budget (time, cost, iterations, depth). *(First-class Budget; not aspirational.)*

---

## 2. The Five Horizons

The roadmap is sequenced into five horizons, each 2–4 quarters. Each horizon produces a shippable surface. The horizons are cumulative but each is independently valuable — a horizon can ship without the next starting.

| # | Horizon | Quarter Window | Headline Outcome |
|---|---|---|---|
| H1 | **Harden the Chat Frontier** | Q3 2026 | The product that exists today is reliable, fast, observable, and self-hostable. No more silent-success missions; no more dual-auth 401 loops. |
| H2 | **Make the Substrate Durable** | Q4 2026 → Q1 2027 | A Temporal-style event log lands behind a feature flag. The 9 error classes get budgets. The capability composer's "infinite lattice" gets a depth proof. |
| H3 | **Type-Safe Composition + OCap** | Q2 2027 → Q3 2027 | Pydantic-typed contracts everywhere; capability tokens replace RBAC for tool invocation; the chaos test suite runs in CI. |
| H4 | **Consolidate the Org & Workflow Models** | Q4 2027 | Tenant dies; Flow + Graph collapse to one Workflow model; 5 agent files collapse to 1 with a state machine. |
| H5 | **Collapse the Executors + Replay UI + Multimodal I/O** | Q1 2028 → Q2 2028 | The single durable executor is the substrate; the 7 old models are strategies. Time-travel debugging ships. Voice + structured-document I/O ship. Old product renamed **Flowmanner Classic**; new product is **Flowmanner Ω**. |

Total horizon: **5 horizons × ~3 quarters each ≈ 6–9 months per horizon with one engineer; ~3–4 months per horizon with two.** This matches Ω spec VI.8's "30–50 weeks" estimate and the "6–9 months with two engineers" framing.

---

## 3. Horizon 1 — Harden the Chat Frontier
*Goal: ship what already works, fix the silent failures, earn the right to call the system production-grade.*

### H1.1 Eliminate the ModelRouter silent failure
**Why first:** This is the load-bearing bug behind the user's pinned memory note — missions complete in 28ms with 0 tokens and `output_data={}`. Until this is fixed, every downstream metric is suspect.

- **Scope:** `app/services/llm/*` and `app/services/mission_executor.py`.
- **Acceptance criteria:**
  - `ModelRouter._is_model_available(model_id, user_id, db_session)` always receives the user context.
  - `mission_executor.py` checks `if not response.get("success"):` and surfaces the error to the user-visible mission log.
  - End-to-end test: a mission with a bogus model_id returns `success=False` and a typed error in the API response, not `success=True` with empty output.
- **Open question:** Should we keep the BYOK fast-path in `mission_executor.py` (which works) and route ALL missions through it, or fix the `ModelRouter` path? The BYOK fast-path is correct but bypasses the centralized router — fixing both preserves the abstraction.
- **Estimated effort:** 1–2 weeks.

### H1.2 Unify the dual auth path
**Why first:** Same recurrence family as H1.1. Two distinct CRITICAL bugs already (audits 2026-05-17 and 2026-05-22).

- **Scope:** `frontend/src/stores/chat-store.ts`, `frontend/src/lib/auth/*`, backend `app/routes/auth/*`.
- **Approach options:**
  - (a) Keep both, add a contract test that fails CI if they disagree.
  - (b) Pick one (likely NextAuth JWT) as source of truth; Zustand `fm_tokens` becomes a derived cache with single-write invalidation.
  - (c) Drop `fm_tokens` entirely; use NextAuth JWT + httpOnly cookie exclusively.
- **Recommendation:** (c) is cleanest but requires a frontend audit of every site that reads `fm_tokens`. (a) is the lowest-risk first step; (b) is the middle ground.
- **Open question:** Is there a `fm_tokens` reader audit available? (`grep -rn "fm_tokens" frontend/src`.)
- **Estimated effort:** 2–3 weeks.

### H1.3 Mission executor observability + abort signals
**Why first:** Without this, H2 (durable substrate) cannot be built — you cannot measure what you cannot observe.

- **Scope:** `mission_executor.py`, `swarm/orchestrator.py`, `swarm_pipeline/`.
- **Acceptance criteria:**
  - Every state transition emits a structured log line with `mission_id`, `task_id`, `actor`, `prev_state`, `next_state`, `cause`.
  - Every LLM call records `model_id`, `prompt_tokens`, `completion_tokens`, `cost_usd`, `latency_ms`, `success` in a dedicated table or stream.
  - `Mission.status` transitions are append-only in the log; the relational state is a projection.
  - A `Mission.abort(reason: AbortReason)` exists and is reachable from API + WS.
- **Estimated effort:** 2 weeks.

### H1.4 Browser agent loop hardening
**Why first:** The browser agent has a hard `max 15 iterations` but no per-iteration budget, no replay, no screenshots stored.

- **Scope:** `app/services/browser_agent.py`.
- **Acceptance criteria:**
  - Every iteration is logged with `iteration_idx`, `url`, `action`, `screenshot_path`, `tokens_used`.
  - Hard time budget per iteration (default 30s).
  - Hard total cost budget (configurable; default $0.50).
  - Screenshot artefacts are persisted to the user's storage namespace.
- **Estimated effort:** 1 week.

### H1.5 Production observability + SLOs
- **Scope:** Jaeger + Langfuse + Prometheus.
- **Acceptance criteria:**
  - SLOs defined: p99 SSE token latency < 300ms, mission success rate > 95%, model fallback success > 99%, deploy success > 99%.
  - Dashboards live in Langfuse.
  - Alerts wired to PagerDuty / ntfy.
- **Estimated effort:** 1–2 weeks.

### H1.6 Single-machine dev story
**Why:** Ω crit Part IV.2 marks single-machine dev as a comparative weakness. A `docker compose up` that brings up Postgres + Redis + Qdrant + RabbitMQ + backend on one box unblocks every contributor who isn't on the homelab LAN.

- **Scope:** `/opt/flowmanner/dev/docker-compose.dev.yml` + seeded Postgres + a hot-reload backend image.
- **Acceptance criteria:** `docker compose -f dev/docker-compose.dev.yml up` brings up a working Flowmanner on a laptop with one command.
- **Open question:** Is there appetite to maintain a second compose file, or is the homelab-only dev story acceptable?
- **Estimated effort:** 2 weeks.

### H1 deliverables
- No silent-success missions.
- No dual-auth 401 loops.
- Every mission state transition is logged + traced.
- Single-machine dev story available.
- SLOs in place.
**H1 exit criteria:** All "critical" audit findings from `audit-2026-05-22-flowmanner-com.md` and the user's pinned `DEEP-DIVE-ANALYSIS.md GAP-2` are CLOSED.

---

## 4. Horizon 2 — Make the Substrate Durable
*Goal: introduce an event-sourced substrate behind a feature flag. Old missions use the old path. New missions use the new path.*

This horizon implements the first half of the Ω migration (Ω spec VI.8: Ω.1 — Substrate).

### H2.1 Event-sourced substrate behind a feature flag
**Scope:** New module `app/services/substrate/` with:
- `Event` model (sequence, run_id, timestamp, type, payload, causal_parent, actor).
- `EventLog` (append-only API; PostgreSQL table with `SERIALIZABLE` isolation and a `BEFORE UPDATE OR DELETE` trigger that raises).
- `RunState` (projection of the event log).
- Replay engine (`apply(event) -> RunState`).
- `ExecutorV2` (runs alongside `mission_executor.py`).

**Feature flag:** `FLOWMANNER_SUBSTRATE_V2=run` (off → use old path, run → use new path for new missions only).

**Acceptance criteria:**
- A new mission with `FLOWMANNER_SUBSTRATE_V2=run` writes one event per state transition to the events table.
- Killing the worker mid-mission and restarting resumes from the last completed node.
- The events table is genuinely append-only (DB-level enforcement, not application-level).
- A 1000-node mission completes in < 5% additional time vs. the old path.
- A 1000-node mission can be replayed deterministically (within seed/temperature-controlled LLM calls).

**Estimated effort:** 4–6 weeks (Ω.1 estimate).

### H2.2 The 9 error classes get budgets
**Scope:** `app/services/failure_analyzer.py`, `app/services/runtime/recovery_strategies.py`.

- Each error class in the table (TIMEOUT, VALIDATION, RESOURCE, NETWORK, RATE_LIMIT, LOGIC, NOT_FOUND, PERMISSION, UNKNOWN) is paired with:
  - A retry budget (max attempts before typed abort).
  - A wall-clock budget (per error class).
  - A cost budget (per error class).
- `MetaLoopOrchestrator` (and eventually `ExecutorV2`) consults the budget before retrying.
- The `self_improvement.py` strategy is *only* applied within the budget.

**Estimated effort:** 2 weeks.

### H2.3 Capability composer's depth proof
**Scope:** `app/services/capability_composer.py`, `app/services/nexus/meta_loop_orchestrator.py`.

- Replace `max_depth = 3` constants with a `CapabilityLattice` that maintains a `depth` invariant.
- Static analysis: detect loops that exit on string match and reject at composition time (or require a typed termination condition).
- The four composition types (sequential, parallel, conditional, loop) each get a halting proof sketch in their docstring.

**Open question:** Is "halting proof" the right framing, or is "bounded iteration + typed termination" enough? The Ω spec Invariant I.8 says "sub_workflow may be recursive, but only if (a) the parent's budget has finite max_depth and (b) the recursive sub-workflow's input type is a strict subtype of the parent's output at the recursion point." This is the practical target.

**Estimated effort:** 2–3 weeks.

### H2.4 Trigger scheduler goes event-driven
**Why:** Today the trigger scheduler polls every 30s. With the event-sourced substrate, it can subscribe to the event stream.

- **Scope:** `app/services/trigger_scheduler.py`.
- **Approach:** Replace the asyncio tick with a Redis pubsub consumer (or PG LISTEN/NOTIFY). Cron triggers are computed from the event timestamp, not polled.
- **Acceptance criteria:** Triggers fire within 1s of the cron boundary (vs. up to 30s today).
- **Estimated effort:** 1–2 weeks.

### H2 deliverables
- The substrate is event-sourced; the 7 executors still exist; new missions can opt in.
- Every error class has a budget.
- The capability lattice has a depth invariant.
- Triggers are sub-second.
**H2 exit criteria:** A new mission can be killed mid-run and resumed on a new worker with no state loss. The chaos test `test_kill_worker_mid_mission` passes locally.

---

## 5. Horizon 3 — Type-Safe Composition + OCap
*Goal: the three missing dimensions M2 (capability-based security) and M3 (type-safe inter-agent contracts) become real. The chaos test suite runs on every PR.*

This horizon implements Ω spec VI.8 Ω.2 (Capability layer) + Ω.3 (Type-checked composition).

### H3.1 Pydantic everywhere
**Scope:** All `app/models/*.py` files where `input_schema: dict` and `output_schema: dict` appear.

- Define `Capability[In, Out]` as a Pydantic generic.
- Migrate `capability_registry.py` to typed entries.
- Add a `PydanticAdapter` that materializes dicts into typed outputs (for backward compatibility).
- Deprecate the `dict` schemas behind a warning.

**Acceptance criteria:** `grep -rn "input_schema: dict" app/` returns 0 hits in capability definitions.

**Estimated effort:** 4–6 weeks (Ω.3 estimate).

### H3.2 Capability tokens replace RBAC for tool invocation
**Scope:** `app/services/capability_engine.py` (new), `app/services/unified_tool_handler.py`, every tool handler in `app/services/tools/`.

- Define `CapabilityToken` (Pydantic, from Ω spec VII.1).
- Define `CapabilityEngine.issue / verify / revoke / attenuate`.
- Wrap every tool call: dispatcher checks for a valid token before invoking.
- The kernel is the only place that calls `CapabilityEngine.issue`.
- RBAC remains as a coarser outer layer (e.g., "only Pro users can issue tokens for `tool:run_command`").

**Acceptance criteria:**
- An agent with no capability cannot invoke a tool (test: `test_no_ambient_authority`).
- A child token's `actions` is a strict subset of the parent's (test: `test_attenuation_preserves_subset`).
- A revoked token cannot be used even if it has not yet expired.
- `grep -rn "CapabilityToken(" app/ | grep -v "capability_engine.py"` returns 0 hits (or is a comment explaining the import restriction).

**Estimated effort:** 4–6 weeks (Ω.2 estimate).

### H3.3 The chaos test suite in CI
**Scope:** New test directory `tests/chaos/` implementing the 7 tests from Ω spec VII.14.

- `test_kill_worker_mid_mission` — H2.1 makes this possible.
- `test_revoke_capability_mid_run` — H3.2 makes this possible.
- `test_exhaust_budget` — requires the budget enforcer (could land here, or as a fast-follow in H4).
- `test_type_violation_rejected` — H3.1 makes this possible.
- `test_replay_yields_same_state` — H2.1 makes this possible.
- `test_attenuation_preserves_subset` — H3.2 makes this possible.
- `test_no_ambient_authority` — H3.2 makes this possible.

**CI gate:** All 7 tests pass on every PR. The CI gate is green.

**Estimated effort:** 2–3 weeks (parallel with H3.1 + H3.2).

### H3.4 Budget as a first-class object
**Scope:** `app/services/budget_enforcer.py` (new).

- `Budget` Pydantic model from Ω spec VII.3.
- `BudgetEnforcer.call(run, request) -> LLMResponse` is the **only** path to `llm.call`. Code review enforces this.
- Every LLM call is wrapped: estimated cost vs. remaining → if exceeds, `BudgetExhausted`.
- `spike` for new missions, `enforce` for production missions (configurable).

**Acceptance criteria:** `grep -rn "llm.call" app/ | grep -v "budget_enforcer.py"` returns 0 hits in production code (tests allowed).

**Estimated effort:** 2–3 weeks.

### H3 deliverables
- Capability contracts are Pydantic.
- Tool invocation requires a capability token.
- Chaos tests run in CI and pass.
- LLM calls are budget-bounded.
**H3 exit criteria:** Invariants I.1, I.2, I.3, I.6, I.7, I.15, I.18, I.19 from the Ω spec are mechanically enforced.

---

## 6. Horizon 4 — Consolidate the Org & Workflow Models
*Goal: kill dead weight. One Tenant. One Workflow. One Agent.*

This horizon implements Ω spec VI.8 Ω.4 — Consolidation.

### H4.1 Kill Tenant; consolidate to one org model
**Scope:** `app/models/tenant*.py`, `app/routes/tenant*.py`, frontend `/tenants/*`.

- Pick Workspace (or Tenant — likely Workspace, since it has Teams and richer per-workspace roles).
- Migrate all routes and models to the chosen one.
- Add a single `TenantContext` middleware that injects the active org into every request.
- Delete the other model's files.

**Acceptance criteria:**
- `grep -rn "Tenant\|tenant" app/ frontend/src/` returns only the chosen model's references.
- No route file imports both `app.models.tenant` and `app.models.workspace`.
- Frontend `grep` confirms UI consolidation.

**Risks:**
- Partner revenue attribution references `tenant_id` — needs data migration.
- Subscription tier is currently per-tenant — needs decision: per-user? per-workspace? both?

**Estimated effort:** 6–8 weeks (Ω.4 estimate; 4 weeks is aggressive).

### H4.2 Collapse Flow + Graph into one Workflow
**Scope:** `app/models/flow*.py`, `app/models/graph*.py`, `app/services/dag_executor.py`, `app/services/graph_executor.py`, frontend `/missions/builder`, `/dashboard/graphs`.

- New `Workflow` model (Ω spec VII.4) with `WorkflowNode` + `WorkflowEdge`.
- Migrate existing `Flow` and `GraphWorkflow` rows to `Workflow` (one-shot Alembic migration).
- The visual builder choice (builder vs. graphs) becomes a *render* choice, not a *data model* choice.
- `dag_executor.py` (179L) and `graph_executor.py` (293L) collapse into one executor that uses Kahn for both.

**Open question:** Is the existing `@xyflow/react` + `elkjs` library capable of rendering both modes? Likely yes — the visual differences are render, not data.

**Estimated effort:** 4–6 weeks.

### H4.3 Collapse 5 agent files into 1 with a state machine
**Scope:** `app/models/agent*.py`, `app/models/agent_models.py`, `app/models/agent_protocol.py`, `app/models/agent_capability.py`, `app/models/agent_memory.py`.

- New `Agent` model (Ω spec VII.2) with `state: AgentState` and `manifest: AgentManifest`.
- State machine: `DEFINED → REGISTERED → CAPABILITY_GRANTED → ACTIVE → SUSPENDED → RETIRED`.
- One model file, one route module, one service.
- Old models become views (if at all) and are deprecated.
- Agent memory becomes a related table, not a separate model.

**Risks:** Agent identity currently spans `id`, `template_id`, `instance_id`. The new model needs to preserve all three semantics in one row (or in a clearly-defined extension table).

**Estimated effort:** 4 weeks.

### H4.4 One auth source of truth
**Scope:** End-state of H1.2. If H1.2 picked (a) or (b), H4.4 finishes the consolidation to (c) — one token source.

- Drop `fm_tokens` from the Zustand store.
- Migrate every `useStore.getState().fm_tokens` reader to a NextAuth `getSession()` or `useSession()` call.
- The 401-instead-of-200 bug class is structurally impossible after this.

**Estimated effort:** 2 weeks.

### H4 deliverables
- One org model.
- One workflow model.
- One agent model.
- One auth source.
**H4 exit criteria:** Removing 4 model directories and 3 route directories ships; existing test suite still passes; the saved LOC is ~1,500–2,000.

---

## 7. Horizon 5 — Collapse the Executors + Replay UI + Multimodal I/O
*Goal: the single durable executor becomes the substrate. The 7 old models are strategies. Time-travel debugging ships. Voice + structured-document I/O ship.*

This horizon implements Ω spec VI.8 Ω.5, Ω.6, Ω.7, Ω.8.

### H5.1 The single durable executor
**Scope:** New `app/services/substrate/executor.py` (Ω spec VII.7), ~1,200–1,500 lines.

- One executor implementation. No subclasses.
- The 7 old models become strategies:
  - Solo = a Workflow with one node and no edges.
  - DAG = a Workflow with typed edges, topologically evaluated.
  - Swarm = a DAG node with fan-out > 1 and a typed consensus sub-protocol.
  - Pipeline = a Workflow with all linear edges and phase gates.
  - Graph = a Workflow with conditional edges and no cycles.
  - Meta = a Workflow containing sub-workflows, bounded by budget.
  - LangGraph = a checkpointed subgraph; supported natively.
- The old `mission_executor.py` (1,387L), `dag_executor.py` (179L), `graph_executor.py` (293L), `swarm/orchestrator.py` (331L), `swarm_pipeline/orchestrator.py` + phases (~1,500L), `langgraph/agent.py` (~250L), `nexus/meta_loop_orchestrator.py` (225L) are deleted.
- The `capability_composer.py` (728L) + `capability_registry.py` (223L) are replaced by the type-checked composition layer.

**The 4 guarantees** (Ω spec VI.2) are now the executor's contract:
- Durable (H2.1)
- Type-checked (H3.1)
- Capability-bounded (H3.2)
- Bounded (H3.4)

**Risks:** This is the single largest LOC deletion in the project. The deletion is the value, not the new code.

**Estimated effort:** 8–12 weeks (Ω.5 estimate).

### H5.2 Replay UI
**Scope:** Frontend `/dashboard/missions/:id/replay`.

- A mission's event log is fetched and rendered as a vertical timeline.
- Each event is clickable; the event payload is shown.
- "What did mission X do at 3am Tuesday?" is answerable in 3 clicks.
- The user can step backward in time, see the typed output of each node, and replay forward to verify determinism.

**Acceptance criteria:** A user can open any completed mission, see the event timeline, click an event, see the payload, and replay the mission from that point with the same model and seed.

**Estimated effort:** 2–4 weeks (Ω.7).

### H5.3 Multimodal I/O
**Scope:** `IOStream`, `Modality`, `IORender` (Ω spec VII.12).

- Voice in/out (Whisper + TTS or a realtime model).
- Structured document in (PDF, CSV, JSON parsed at the modality layer).
- Code cell in the chat surface (a real runnable cell, not just the existing CodeSandboxPanel).
- The kernel is modality-agnostic; it consumes `IORender` only.

**Acceptance criteria:** A user can attach a PDF, ask a question, get a voice response. A user can open a code cell in a chat thread, run it, and see the output inline.

**Estimated effort:** 4–6 weeks (Ω.6).

### H5.4 Bounded learning loop
**Scope:** `LearningRule`, `LearningStore` (Ω spec VII.13).

- Add weight, half-life, and A/B effectiveness score to `AdaptationRuleDB` and `LearningFeedbackDB` rows.
- Periodic job retires rules older than 90 days with effectiveness < 0.3.
- `promote()` requires an A/B result; `demote()` halves weight; `retire()` soft-deletes (half-life 1 day).
- Invariant I.17: no more than 1,000 active rules.

**Estimated effort:** 2–3 weeks.

### H5.5 Rename + relaunch
**Scope:** Ω spec VII.15.

- Tag the current system as **Flowmanner Classic** (v1).
- Launch the new system as **Flowmanner Ω** (v2).
- Two products coexist for 18 months. Classic is in maintenance; Ω is the focus.
- After 18 months, Classic is EOL.

**Marketing reality:** This is a one-engineer (or two) product. The 18-month coexistence is aspirational. The honest framing is: "Classic is the app that runs today; Ω is the substrate it gradually migrates to."

**Estimated effort:** 1 week.

### H5 deliverables
- The single durable executor.
- The single agent, workflow, org model.
- The 4 guarantees.
- The replay UI.
- The multimodal I/O.
- The bounded learning loop.
**H5 exit criteria:** Invariants I.1–I.19 from the Ω spec are mechanically enforced. A new mission type defined in YAML can be added without writing a new executor.

---

## 8. The Open Questions (from the ontology)

The ontology lists 7 open questions. The roadmap addresses each. Quick map:

| # | Open question | Answered in horizon | Resolution |
|---|---|---|---|
| 1 | Flow vs Graph — converging or competing? | H4.2 | Collapsed to one Workflow model. Visual builder choice is a render choice. |
| 2 | Agent pluralism — canonical lifecycle? | H4.3 | Single `Agent` model with `DEFINED → REGISTERED → CAPABILITY_GRANTED → ACTIVE → SUSPENDED → RETIRED`. |
| 3 | Workspace vs Tenant? | H4.1 | Pick Workspace. Delete Tenant. |
| 4 | Nexus — what is it? | H5.1 | Nexus is now a *strategy* on the durable executor, not a separate engine. The `nexus/` directory is deleted. |
| 5 | Phase 4 — what were Phases 1-3? | Documentation, not code | Document the history. Not a roadmap item. |
| 6 | GraphQL v2 — future API direction? | H4 / H5 | Consolidate REST and GraphQL behind the kernel's IOStream. The kernel doesn't care which is upstream. |
| 7 | API versioning — what differentiates v1/v2/v3? | H4 / H5 | Versions are substrate versions. v1 = current. v2 = event-sourced (H2). v3 = capability-bounded (H3). v4 = Ω (H5). |

---

## 9. Cross-Cutting Concerns

These are not horizons. They are constraints on every horizon.

### 9.1 Dual-machine discipline (preserved)
- Source edits on homelab only. VPS is rsync target. No volume mounts. Docker images are the deploy unit. (AGENTS.md.)
- Frontend deploy: 4 min. Backend rebuild: 2 min. Use `timeout=300` or `background=true`. Never retry a timed-out deploy without checking completion.

### 9.2 CodeGraph MCP
- AGENTS.homelab.md says CodeGraph MCP is available. The Ω crit Part II notes it's not in requirements.txt or package.json. **The first action of H1 is to determine whether CodeGraph MCP is actually wired into the homelab agent.** If yes, the workflows in this roadmap should use it from day one. If no, we either install it or remove the claim from AGENTS.md.

### 9.3 The pinned memory: "Mission System Mock-Up Investigation"
The user's note names two root causes and proposes a fix. The fix is H1.1. The note is itself a useful execution artifact — its next-steps list maps directly to H1.1, H1.2, and H1.3. Treat the note as a co-design input, not just context.

### 9.4 BYOK posture
BYOK is one of Flowmanner's design principles (ARCHITECTURE.md §9). The Budget Enforcer (H3.4) must respect BYOK: a user-supplied key still has a cost, and the cost is still bounded. The PricingTable in the Ω spec needs an entry per provider; the implementation should fetch the table at boot and refresh on a daily cron.

### 9.5 Self-host as a first-class story
The Ω crit Part IV.3 calls out the on-prem / self-host advantage. Every horizon must keep `docker compose up` (or `docker compose -f dev/docker-compose.dev.yml up`) working. No cloud-only dependencies. No SaaS-only features.

### 9.6 Backward compatibility during migration
- H1–H4 are *additive* in the sense that old code paths remain reachable.
- H2.1 introduces a feature flag (`FLOWMANNER_SUBSTRATE_V2=run`); old missions still use the old path.
- H5.1 is the only horizon that *deletes* old executor code. Until H5.1 lands, the 7 executors coexist with the new single executor.
- The 18-month Classic / Ω coexistence (Ω spec VII.15) is the formal commitment to backward compatibility.

---

## 10. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| H1.1 fix breaks other call sites of `ModelRouter` | Medium | High | The BYOK fast-path is correct and works today; if the centralized fix breaks, the fast-path is the rollback. |
| H1.2 (a) "contract test" becomes a permanent tax instead of a real fix | Medium | Medium | Time-box H1.2 to 3 weeks. If (a) is not on a path to (c), escalate to (c) directly. |
| H2.1 (event-sourced substrate) has a performance regression | Medium | High | The feature flag is per-mission; the old path is the default until the new path is within 5% of the old path's latency and throughput. |
| H3.2 (OCap) makes every existing tool handler need a token grant | High | Medium | The default token policy grants every active agent the union of all tools the user owns. The token is the audit trail; the *enforcement* is the new part. |
| H4.1 (Tenant → Workspace) data migration fails | Medium | High | The Tenant → Workspace migration is a one-shot copy + dual-write window + cutover, not a single atomic migration. Plan a 4-week window with rollback at every step. |
| H5.1 (single executor) deletes code we end up needing | Low | High | The deletion is the last step of H5.1. Until then, the 7 old executors coexist with the new one. |
| The 5 horizons slip and become a "2028" plan | Medium | Medium | Each horizon is independently valuable. H1 is a shippable product. H1 + H2 is a shippable product. Each horizon should be celebrated as a release. |
| Two-engineer bandwidth | Medium | High | The horizons are scoped to 1 engineer for 30–50 weeks. With 2 engineers, the critical path is H1 → H2.1 → H3.2 → H5.1 (substrate + OCap + single executor). H4 (consolidation) and H5.2/H5.3 (UI) can run in parallel. |

---

## 11. What This Roadmap Is Not

- It is not a critique. The critique is in the Ω spec.
- It is not a sales pitch. The competitive positioning is in the Ω spec Part VI.9.
- It is not a guarantee of dates. The horizons are ordered, but the dates are placeholders.
- It is not a single-machine story. The dual-machine discipline (AGENTS.md) is preserved.
- It is not a complete plan for H5.1. The single durable executor deserves its own SOW. H1–H4 are well-scoped; H5.1 is a 2-engineer-quarter.

---

## 12. Next Move

The first concrete action is H1.1 — the ModelRouter silent-failure fix — because it is small, well-understood, and unblocks every downstream metric.

The first *discussion* action is the test-strategy question for H1: does the homelab have a test infrastructure today (per the Prometheus checklist), and if so, is it TDD or tests-after? The answer shapes whether H1.1 is RED-GREEN-REFACTOR or a fix-then-test.

Beyond that, this document is the candidate. The next move is yours.
