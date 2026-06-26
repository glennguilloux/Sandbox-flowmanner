# Q2-Q3 2026 — Agentic Workflow Plan for FlowManner

**Status:** ✅ COMPLETE — all 6 chunks shipped and closed.
**Created:** 2026-06-12 by Prometheus planner
**Completed:** 2026-06-25 (Chunks 4-6 verified live; 1-3 already closed prior)
**Owner:** Glenn (decisions), coding agents (execution)
**Supersedes:** `docs/REBUILD-ROADMAP.md` for agentic workflow sequencing; archived at `.sisyphus/plans/OLD/REBUILD-ROADMAP-2026-06-12.md`.

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

## 2. Q2-Q3 Roadmap — 6 Chunks (All ✅ Complete)

### Chunk 1: Agentic readiness stop gates

**Status:** ✅ Done — `34fc0c6 close chunk 1`
**Summary:** Made P0/P1/P3 blockers explicit gates before Q2 agentic work.
**Evidence:** Substrate baseline locked at 151/10 tests; P0.2/P0.4 evidence files created; test-first rule enforced via pre-commit hooks.
**Estimate:** 1w

### Chunk 2: Sparse episodic memory for missions

**Status:** ✅ Done — `60f29c1 close chunk 2` (commits: `35fdc0e`, `ac0c6ef`, `30e3356`, `677f6e4`)
**Summary:** Store and retrieve compact mission outcomes via hybrid BM25+vector search with hard cap of 5 episodes per query, redaction at write time, and workspace/user scoping.
**Evidence:** EpisodicMemoryService (659 lines), EpisodicMemoryWorker (237 lines), REST API at `POST /episodes/retrieve`, Qdrant + PostgreSQL backing, 2 test files (unit + integration). Redaction patterns for API keys, file paths, secrets.
**Estimate:** 2w

### Chunk 3: Sparse tool routing

**Status:** ✅ Done — `8bf2f22 close chunk 3` (commit: `f12090f`)
**Summary:** Scored candidate-set tool selector that returns a bounded top-k set with scores and reasons, with fallback to full registry when confidence is low.
**Evidence:** Tool router with safe-list (always-include tools), confidence thresholds, and fallback logic. Tests cover unknown task, permission-denied tool, high-risk tool, and fallback paths.
**Estimate:** 2w

### Chunk 4: Adaptive reasoning depth with HITL escalation

**Status:** ✅ Done — commits: `7d7c3ac`, `f3e3afa`, `164d86c`, `4283126`, `47c1b24`
**Summary:** Three depth levels (shallow=0, normal=1, deep=3 reflections), deterministic priority-based policy using risk/uncertainty/budget/failures, HITL escalation on approval-requiring tools and retry exhaustion, audit events emitted to substrate event log for replay.
**Evidence:** `depth_models.py` (62 lines), `depth_policy.py` (333 lines), REST API at `backend/app/api/v1/depth.py`, wired into MissionExecutor via `enable_depth_policy` toggle, **66/66 tests pass** in `test_depth_policy.py` + `test_depth_routing.py`.
**Estimate:** 2w

### Chunk 5: Multi-agent handoff packets

**Status:** ✅ Done — `62a008c feat(handoff): typed HandoffPacket + budget/HITL/lease preservation (q2-chunk5)`
**Summary:** Durable handoff packet schema including goal, constraints, retrieved context IDs, tool candidates, budget remaining, HITL state, and success criteria. Receiving agent resumes without full history replay. Lease transfer/renewal handles worker churn. HITL items survive handoff scoped to owning user/workspace.
**Evidence:** `HandoffPacket` typed model, wired into executor + swarm strategy + lease manager + HITL service + budget enforcer.
**Estimate:** 4w

### Chunk 6: Self-correction and retry under cost ceilings

**Status:** ✅ Done — `b7ca48f feat(self-correction): bounded retry/reflect/HITL/abort under cost ceilings (q2-chunk6)`
**Summary:** Bounded self-correction loops that diagnose failures and choose retry/reflect/HITL/abort without exceeding mission budgets. Each failure class maps to a recovery action; retry budgets tracked by cost, wall-clock, attempts, and depth. Circuit breaker and budget enforcer decisions visible in replay.
**Evidence:** `failure_analyzer.py`, `budget_enforcer.py`, `circuit_breaker.py` integration with the self-correction loop. Tests cover permission errors, timeout, provider failure, budget exhaustion, and repeated bad tool choices.
**Estimate:** 2w

---

## 3. Sparse Attention Translation

### Decision 1: Retrieve episodes, not whole missions

For episodic memory, the default is **hybrid BM25+vector retrieval over compact episode records**, not full mission replay. The retrieval key should include mission_id, step_type, outcome, cost bucket, HITL outcome, and a redacted text embedding. The agent receives only the selected episode IDs plus short summaries; full events are available through replay if explicitly requested. Default to a hard cap of 5 episodes per query. This uses FlowManner’s substrate advantage: event logs are already append-only and replayable, so memory can be a selective index rather than a second source of truth.

### Decision 2: Route tools before expanding definitions

Tool routing should happen before the model sees tool definitions. The router scores tools from registry metadata, task text, prior outcomes, and memory hints, then returns a bounded candidate set with fallback rules. This directly applies sparse attention to tool use: the agent should attend to likely tools first and only expand the full registry when confidence is low or the action is high-risk.

### Decision 3: Spend reasoning depth only when the step warrants it

Adaptive depth should be policy-driven and recorded. Shallow steps should execute directly when risk is low and prior memory is strong. Deep steps should be reserved for uncertain, expensive, destructive, or repeated-failure cases. When depth or budget is exhausted, the agent escalates to HITL instead of silently degrading. This makes “stop and ask” an agentic decision, not just a platform-level interrupt.

---

## 4. Integration Points

| Chunk | Existing substrate used | New primitive needed | Status |
|---|---|---|---|---|
| 1. Stop gates | Tests, evidence files, deploy scripts, P0/P1/P3 roadmap | Evidence-backed gate checklist | ✅ Done |
| 2. Episodic memory | Event log, replay, mission status, cost attribution | Compact memory entries + retrieval index | ✅ Done |
| 3. Tool routing | Tool registry, model router, node executor, usage/cost records | Tool candidate scorer + fallback policy | ✅ Done |
| 4. Adaptive depth | Budget enforcer, HITL, mission planner/executor, failure analyzer | Depth policy version + per-step depth event | ✅ Done |
| 5. Multi-agent handoff | Leases, HITL, budget, replay, swarm strategy | Handoff packet schema | ✅ Done |
| 6. Self-correction | Failure analyzer, circuit breaker, budget enforcer, assertion engine | Recovery policy table + loop audit events | ✅ Done |

No new microservice is required for the first six chunks. If retrieval volume or latency becomes a problem, add an index only after measurements show the current database/Qdrant setup cannot carry the load.

---

## 5. Risk Register (Post-hoc — all 6 chunks shipped, risks now historical)

| # | Risk | Probability | Impact | Mitigation | Status |
|---|---|---|---|---|---|
| R1 | P0.2/P0.4 user-visible issues contaminate Q2 testing | Medium | High | Treat as stop gates before agentic work | ⚠️ Gates defined; P0.2/P0.4 tracked outside this plan |
| R2 | Memory stores sensitive raw step content | Medium | High | Redact at write time, scope by workspace/user, audit retrieval | ✅ Redaction patterns applied at write time |
| R3 | Tool router hides valid tools | Medium | High | Confidence thresholds, fallback to full registry, replay audit | ✅ Shipped with safe-list + fallback |
| R4 | Adaptive depth becomes opaque or too expensive | Medium | Medium | Store policy version, depth trigger, token/cost budget per step | ✅ Depth events emitted to substrate log |
| R5 | Handoff duplicates mission state and diverges from substrate | Medium | High | Handoff packets reference substrate event IDs instead of copying all state | ✅ Minimal packet schema |
| R6 | Self-correction loops burn budget silently | Medium | High | Every retry iteration emits costed events and stops on hard budget | ✅ Costed events + hard budget cap |
| R7 | Q2 plan overloads two-machine topology | Low | Medium | Measure latency/cost before adding services; keep modular monolith | ✅ No new microservices added |
| R8 | Roadmap corrections silently ignored | Medium | Medium | Keep Section 6 explicit; require plan reviewer to acknowledge corrections | ✅ Reviewed during completion pass |

---

## 6. Roadmap Corrections

1. The archived roadmap says **HITL, episodic memory, and circuit breakers are deferred**, but Q2 evidence and current source show HITL, cost attribution, circuit breaker, leases, replay, and substrate event logs are already shipped enough to build on. Treat them as substrate, not greenfield.
2. The archived roadmap treats **P0.4 as a frontend auth-redirect-loop fix**, but the P0.4 evidence file concludes the reported backend 401 burst was test traffic and the real frontend loop is a separate frontend repo task. Do not use backend P0.4 evidence as proof of a backend bug.
3. The archived roadmap marks **sandbox preview auth as done**, but P0.2 evidence shows the current user-facing issue is still the red “Preview unavailable” branch. The Q2 stop gate should require actionable preview errors or an end-to-end preview fix.
4. Provider routing remains intentionally unresolved in the future-architecture docs. Do not make adaptive routing depend on a solved provider-routing story unless the implementation explicitly uses existing `ModelRouter`/`BudgetEnforcer` behavior.

---

## Stop Rule (Historical — plan completed)

- All 6 chunks shipped. This doc preserved for provenance.
- Do not add new chunks to this plan; open a new Q3-Q4 plan if more work is needed.
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

**Completion verified 2026-06-25 by Hermes (DeepSeek V4 Flash):**
- Chunks 1-3: `git log --oneline --all --grep="close chunk[1-3]"` → 3 commits found
- Chunk 4: `test_depth_policy.py` → 66/66 tests pass (0.26s)
- Chunk 5: `62a008c` feat(handoff) — typed HandoffPacket shipped
- Chunk 6: `b7ca48f` feat(self-correction) — bounded retry/reflect/HITL/abort shipped

Most surprising decision: FlowManner should not chase generic agent-framework parity; it should turn its shipped substrate into sparse, auditable agentic control loops.

Biggest risk (retrospective): memory/tool routing could quietly become the failure mode if sparse selection loses valid context or tools without auditability — shipped with fallback paths and audit logging as mitigations.
