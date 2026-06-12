# Q2-Q3 2026 — Agentic Workflow Plan for FlowManner

**Status:** REVISED — executable Q2-Q3 planning pass.
**Created:** 2026-06-12 by hermes-agent
**Revised:** 2026-06-12 after source-prompt/evidence review
**Owner:** Glenn (decisions), coding agents (execution)
**Supersedes:** `docs/REBUILD-ROADMAP.md` for agentic workflow sequencing only; archived roadmap remains evidence at `.sisyphus/plans/OLD/REBUILD-ROADMAP-2026-06-12.md`.

---

## 1. Strategic Position

FlowManner should not try to beat LangGraph, CrewAI, AutoGen, Claude Agent SDK, or OpenAI Agents SDK at being the most generic agent framework. Its defensible wedge is narrower and more valuable: **cost-aware, interruptible, resumable agentic workflows that can run on sovereign infrastructure and still expose enough traceability for humans to trust them.**

The shipped substrate already gives FlowManner pieces competitors usually bolt on late: worker leases, HITL pause/resume, per-step cost attribution, replayable event logs, sandbox execution, circuit breakers, and provider fallback. The Q2-Q3 product move is to turn that substrate into **agentic control loops**: agents that retrieve the right memory, choose the right tools, reason at the right depth, recover from failures, and hand off work without losing state or budget discipline.

### Best initial use case

**Long-running operational workflows with human checkpoints and real cost sensitivity**, for example:

- research-to-decision missions,
- code/test/fix loops,
- workflow automation with approval gates,
- data pipeline triage,
- customer-support investigation agents.

These use cases need long-horizon state, selective context, human escalation, and cost ceilings. They are a better fit than pure chat agents or one-shot tool calls.

### Capabilities that make FlowManner the obvious choice

1. **Sparse episodic memory over mission history** — retrieve only the prior steps/outcomes that matter, capped by relevance and cost.
2. **HITL-native escalation** — pause, clarify, approve, reject, resume, and audit without losing mission state.
3. **Per-step and per-mission cost attribution** — budget decisions can be made by the agent, not just by the platform wrapper.
4. **Leased, resumable execution** — long-running work can survive worker churn and resume from durable state.
5. **Tool routing instead of tool enumeration** — agents can select likely tools from a scored candidate set instead of flooding context with every tool definition.

### What not to build

- **Agent marketplace** — no publisher economy, ratings, revenue share, or external agent hosting in Q2-Q3.
- **General-purpose multi-modal agents** — out of scope unless a concrete FlowManner workflow requires it.
- **Federation / Neo4j / graph database rewrite** — revisit only after FlowManner proves the current substrate can support agentic work.
- **Self-improving agents that rewrite their own prompts/models** — too risky without stronger evaluation and audit.
- **A third model-routing layer** — adaptive routing should use existing `BudgetEnforcer` + `llm_router.ModelRouter` semantics unless a concrete gap is proven.

---

## 2. Q2-Q3 Roadmap — 6 Chunks

### Chunk 1: Agentic readiness stop gates

**Summary:** Make P0/P1/P3 blockers explicit gates before any Q2 agentic feature ships.
**Why now:** Q2 agentic work will be blamed for broken auth, preview, or substrate behavior unless the platform is first stabilized and measured.
**Code surface:** `backend/tests/`, `frontend/src/auth.ts`, `frontend/src/lib/api-client.ts`, `frontend/src/components/chat/SandboxPreviewButton.tsx`, `backend/app/api/v1/sandbox_preview.py`, `.sisyphus/evidence/P0.2-preview-trace.md`, `.sisyphus/evidence/P0.4-auth-redirect-loop-investigation.md`.
**Dependencies:** None. This is a gate, not a feature.
**Success criteria:**
- P0.2 preview failure is actionable in UI or fixed end-to-end.
- Frontend auth loop is either fixed in the frontend repo or explicitly re-scoped.
- Existing substrate tests remain green; new agentic chunks add tests before implementation.
- No VPS source edits and no `docker cp`; only official deploy scripts are used.
**Risk:** Stop gates can become procrastination. Mitigation: each gate has a named owner-role, evidence file, and max budget.
**Estimate:** 1w

### Chunk 2: Sparse episodic memory for missions

**Summary:** Store and retrieve compact mission outcomes, step traces, costs, HITL decisions, and final verdicts for future runs.
**Why now:** Long-horizon agents fail when they replay entire histories. FlowManner already has mission/event-log substrate, so it can build selective memory without a new service.
**Code surface:** `backend/app/models/memory_models.py`, `backend/app/services/memory_service.py`, `backend/app/services/episodic_memory_worker.py`, `backend/app/memory/consolidation_worker.py`, `backend/app/services/substrate/event_log.py`, `backend/app/services/substrate/replay_engine.py`, Alembic migrations under `backend/alembic/versions/*memory*`.
**Dependencies:** Chunk 1 stop gates; existing substrate event log and mission status semantics.
**Success criteria:**
- Completed missions produce compact memory entries with mission_id, step_type, outcome, cost bucket, HITL outcome, and retrieval text.
- Retrieval returns top-k relevant episodes per query with a hard cap and redaction policy.
- Tests prove sensitive raw step content is not blindly stored.
- Replay can show which memory entries influenced a run.
**Risk:** Memory becomes a privacy leak. Mitigation: redaction at write time, workspace/user scoping, and retrieval audit fields.
**Estimate:** 2w

### Chunk 3: Sparse tool routing

**Summary:** Replace “send every tool definition” behavior with a scored candidate-set selector for tool calls.
**Why now:** Tool enumeration wastes context and increases bad calls. A router can use task text, prior tool outcomes, and registry metadata to pick a small candidate set before the model sees tool definitions.
**Code surface:** `backend/app/services/model_router.py`, `backend/app/services/llm_router.py`, `backend/app/services/substrate/node_executor.py`, `backend/app/tools/`, `backend/app/api/v1/llm_advanced.py`, `backend/app/api/v1/io.py`, `backend/app/api/v1/substrate.py`.
**Dependencies:** Chunk 2 memory helps but is not required; tool registry metadata must be stable first.
**Success criteria:**
- Router returns a bounded top-k tool candidate set with scores and reasons.
- Fallback path preserves current behavior when routing confidence is low.
- Tests cover unknown task, permission-denied tool, high-risk tool, and fallback-to-full-registry cases.
- Cost/token savings are measured against baseline tool enumeration.
**Risk:** Router hides valid tools. Mitigation: confidence thresholds, audit logging, and fallback when low confidence.
**Estimate:** 2w

### Chunk 4: Adaptive reasoning depth with HITL escalation

**Summary:** Let missions choose shallow act, normal plan/act, or deep deliberation based on risk, uncertainty, budget, and prior failures.
**Why now:** Not every step deserves a long chain-of-thought or expensive model call. FlowManner can use HITL as the escalation target when depth is exhausted or uncertainty is high.
**Code surface:** `backend/app/services/mission_planner.py`, `backend/app/services/mission_executor.py`, `backend/app/services/budget_enforcer.py`, `backend/app/services/nexus/failure_analyzer.py`, `backend/app/services/hitl_service.py`, `backend/app/services/substrate/hitl_pause.py`.
**Dependencies:** Chunk 1 budget/error semantics; Chunk 2 memory preferred but not required.
**Success criteria:**
- Each step records reasoning depth, trigger reason, token/cost budget, and escalation decision.
- High-risk actions require HITL or explicit policy override.
- Tests prove depth choices change when budget, uncertainty, or risk changes.
- Mission replay can reconstruct why the agent chose shallow vs deep reasoning.
**Risk:** Depth policy becomes a black box. Mitigation: store trigger reason and policy version with each step.
**Estimate:** 2w

### Chunk 5: Multi-agent handoff packets

**Summary:** Add durable handoff packets so one agent can delegate to another without losing context, budget, permissions, or human-interrupt state.
**Why now:** Multi-agent coordination is only useful if handoff is explicit and auditable. FlowManner already has leases, HITL, cost attribution, and replay; the missing piece is a compact contract between agents.
**Code surface:** `backend/app/services/substrate/executor.py`, `backend/app/services/substrate/strategies/swarm.py`, `backend/app/services/substrate/lease_manager.py`, `backend/app/services/hitl_service.py`, `backend/app/services/budget_enforcer.py`, `backend/app/models/mission_models.py`, `backend/app/models/blueprint_models.py`.
**Dependencies:** Chunks 2 and 4 strongly preferred; Chunk 1 stop gates required.
**Success criteria:**
- Handoff packet includes goal, constraints, retrieved context IDs, tool candidates, budget remaining, HITL state, and success criteria.
- Receiving agent can resume from the packet without full history replay.
- Lease transfer/renewal is tested for worker churn.
- HITL items remain scoped to the owning user/workspace and survive handoff.
**Risk:** Handoff becomes a second schema for the whole mission. Mitigation: keep packet minimal and reference substrate events rather than copying all state.
**Estimate:** 4w

### Chunk 6: Self-correction and retry under cost ceilings

**Summary:** Add bounded self-correction loops that diagnose failures, choose retry/reflection/HITL/abort, and never exceed mission budgets.
**Why now:** Long-running agents will fail. The differentiator is not “retry forever”; it is disciplined recovery with cost, depth, and human escalation limits.
**Code surface:** `backend/app/services/nexus/failure_analyzer.py`, `backend/app/services/budget_enforcer.py`, `backend/app/services/substrate/circuit_breaker.py`, `backend/app/services/substrate/replay_engine.py`, `backend/app/services/substrate/assertion_engine.py`, `backend/app/services/mission_executor.py`, `backend/app/api/_mission_cqrs/commands.py`.
**Dependencies:** Chunk 1 error/budget semantics; Chunk 4 reasoning depth; Chunk 2 memory preferred.
**Success criteria:**
- Each failure class maps to a recovery action: retry, reflect, ask HITL, fallback provider, or abort.
- Retry budgets are tracked by cost, wall-clock, attempts, and depth.
- Circuit breaker and budget enforcer decisions are visible in replay.
- Tests cover permission errors, timeout, provider failure, budget exhaustion, and repeated bad tool choice.
**Risk:** Self-correction loops burn budget silently. Mitigation: every loop iteration emits a costed event and stops on budget exhaustion.
**Estimate:** 2w

---

## 3. Sparse Attention Translation

### Decision 1: Retrieve episodes, not whole missions

For episodic memory, the default is **top-k sparse retrieval over compact episode records**, not full mission replay. The retrieval key should include mission_id, step_type, outcome, cost bucket, HITL outcome, and a redacted text embedding. The agent receives only the selected episode IDs plus short summaries; full events are available through replay if explicitly requested. This uses FlowManner’s substrate advantage: event logs are already append-only and replayable, so memory can be a selective index rather than a second source of truth.

### Decision 2: Route tools before expanding definitions

Tool routing should happen before the model sees tool definitions. The router scores tools from registry metadata, task text, prior outcomes, and memory hints, then returns a bounded candidate set with fallback rules. This directly applies sparse attention to tool use: the agent should attend to likely tools first and only expand the full registry when confidence is low or the action is high-risk.

### Decision 3: Spend reasoning depth only when the step warrants it

Adaptive depth should be policy-driven and recorded. Shallow steps should execute directly when risk is low and prior memory is strong. Deep steps should be reserved for uncertain, expensive, destructive, or repeated-failure cases. When depth or budget is exhausted, the agent escalates to HITL instead of silently degrading. This makes “stop and ask” an agentic decision, not just a platform-level interrupt.

---

## 4. Integration Points

| Chunk | Existing substrate used | New primitive needed | Timing |
|---|---|---|---|
| 1. Stop gates | Tests, evidence files, deploy scripts, P0/P1/P3 roadmap | Evidence-backed gate checklist | Immediate |
| 2. Episodic memory | Event log, replay, mission status, cost attribution | Compact memory entries + retrieval index | Q2 |
| 3. Tool routing | Tool registry, model router, node executor, usage/cost records | Tool candidate scorer + fallback policy | Q2 |
| 4. Adaptive depth | Budget enforcer, HITL, mission planner/executor, failure analyzer | Depth policy version + per-step depth event | Q2-Q3 |
| 5. Multi-agent handoff | Leases, HITL, budget, replay, swarm strategy | Handoff packet schema | Q3 |
| 6. Self-correction | Failure analyzer, circuit breaker, budget enforcer, assertion engine | Recovery policy table + loop audit events | Q3 |

No new microservice is required for the first six chunks. If retrieval volume or latency becomes a problem, add an index only after measurements show the current database/Qdrant setup cannot carry the load.

---

## 5. Risk Register

| # | Risk | Probability | Impact | Mitigation | Owner-role |
|---|---|---:|---:|---|---|
| R1 | P0.2/P0.4 user-visible issues remain unresolved and contaminate Q2 testing | Medium | High | Treat as stop gates with evidence files before agentic work | Product owner + QA |
| R2 | Episodic memory stores sensitive raw step content | Medium | High | Redact at write time, scope by workspace/user, audit retrieval | Backend lead |
| R3 | Tool router hides valid tools and lowers task success | Medium | High | Confidence thresholds, fallback to full registry, replay audit | Backend lead |
| R4 | Adaptive depth becomes opaque or too expensive | Medium | Medium | Store policy version, depth trigger, token/cost budget per step | Agent runtime owner |
| R5 | Multi-agent handoff duplicates mission state and diverges from substrate | Medium | High | Handoff packets reference substrate event IDs instead of copying all state | Architecture owner |
| R6 | Self-correction loops burn budget before failure is visible | Medium | High | Every retry iteration emits costed events and stops on hard budget | Agent runtime owner |
| R7 | Q2 plan overloads the current two-machine topology | Low | Medium | Measure latency/cost before adding services; keep modular monolith | Infra owner |
| R8 | Roadmap corrections are silently ignored | Medium | Medium | Keep Section 6 explicit; require plan reviewer to acknowledge corrections | Plan reviewer |

---

## 6. Roadmap Corrections

1. The archived roadmap says **HITL, episodic memory, and circuit breakers are deferred**, but Q2 evidence and current source show HITL, cost attribution, circuit breaker, leases, replay, and substrate event logs are already shipped enough to build on. Treat them as substrate, not greenfield.
2. The archived roadmap treats **P0.4 as a frontend auth-redirect-loop fix**, but the P0.4 evidence file concludes the reported backend 401 burst was test traffic and the real frontend loop is a separate frontend repo task. Do not use backend P0.4 evidence as proof of a backend bug.
3. The archived roadmap marks **sandbox preview auth as done**, but P0.2 evidence shows the current user-facing issue is still the red “Preview unavailable” branch. The Q2 stop gate should require actionable preview errors or an end-to-end preview fix.
4. Provider routing remains intentionally unresolved in the future-architecture docs. Do not make adaptive routing depend on a solved provider-routing story unless the implementation explicitly uses existing `ModelRouter`/`BudgetEnforcer` behavior.

---

## Stop Rule

- Keep this plan to 5-8 pages of executable direction.
- Do not start agentic feature chunks until Chunk 1 stop gates have evidence.
- Do not propose P0.2/P0.4 fixes inside this plan; they are tracked separately.
- If a chunk cannot name concrete files/modules and tests, split or drop it.
- No VPS source edits, no `docker cp`, and no raw Docker deploy commands; use official deploy scripts only.

---

## Provenance

This revised plan was created from:

- `.hermes/plans/q2-opus-agentic-workflow-prompt.md`
- `.sisyphus/plans/OLD/REBUILD-ROADMAP-2026-06-12.md`
- `.sisyphus/evidence/P0.2-preview-trace.md`
- `.sisyphus/evidence/P0.4-auth-redirect-loop-investigation.md`
- `.sisyphus/evidence/task-10-drift-report.md`
- Current backend source paths discovered during revision

Most surprising decision: FlowManner should not chase generic agent-framework parity; it should turn its shipped substrate into sparse, auditable agentic control loops.

Biggest risk: memory/tool routing can quietly become the failure mode if sparse selection loses valid context or tools without auditability.
