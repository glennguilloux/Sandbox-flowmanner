# W3 Analysis — Mission + Swarm + Self-Improvement Subsystems

**Scope:** `/opt/flowmanner/backend` (note: task brief said `/opt/flowmapper` — that path does not exist; the repo is `/opt/flowmanner`, per the workspace path and AGENTS.md).
**Date:** 2026-07-07
**Audience:** Roadmap author (Phase 2+ shopfront surfacing).
**Constraint:** Analysis only — no code edits, no deploy, no commit.

---

## 0. TL;DR (the gap, stated up front)

The mission engine and self-improvement *model/planner* layers are genuinely deep and mostly wired end-to-end (plan → execute → critique → improvement records). But three things undercut the "agent orchestration depth" the front door is supposed to sell:

1. **Swarm is half-built and effectively dead on arrival.** `consensus_strategy` / `consensus_config` are stored on `SwarmProfile` but **never read** by any code path. There is **no swarm-profile CRUD endpoint** (no `create_swarm`/`list_swarms` route) — only debate/handoff/escalation *protocol* endpoints exist. The actual execution strategy (`substrate/strategies/swarm.py`) is marked `DEPRECATED = True` with the comment *"0% success with 27B model per strategy profiling 2026-07-04."* Swarm usage caps (`daily_limit`/`monthly_limit`) are persisted but **never enforced** anywhere.
2. **The improvement loop is write-only.** `ImprovementGenerator` is implemented but **never called** by any runtime path. `SelfImprovementEngine` exists and is reachable from the CQRS command handlers, but it is a deterministic `if/elif` template (not LLM-driven) and is not invoked by the executor on failure. `CritiqueService` persists critiques, but nothing merges them back into the planner. The "plan→execute→improve" claim is true at the *data-model* level, not the *autonomous-loop* level.
3. **The learning-feedback loop is the one bright spot** — execution records *are* written to `LearningService` (`record_execution` in `substrate/executor.py`) and *are* read back into the planner prompt (`inject_into_planner_context`). That part is wired.

The landing page undersells the engine because the engine's most marketable surfaces (missions you can watch plan/execute, a swarm you can watch debate) are either (a) reachable only via raw API routes a shopfront doesn't expose, or (b) not actually functional at the swarm layer.

---

## 1. Plan → Execute → Improve lifecycle, end to end (real function names)

### 1a. Plan (`pending → planning → planned`)
- Entry: `MissionCommandHandlers.plan_mission()` — `backend/app/api/_mission_cqrs/commands.py:374`. Thin DI shell over `MissionPlanner`.
- Engine: `MissionPlanner.plan_mission()` — `backend/app/services/mission_planner.py:98`. Owns the lifecycle transition:
  - Sets `Mission.status = PLANNING` (`mission_planner.py:132`), commits.
  - If tasks already exist → jumps straight to `PLANNED` (plan-update only).
  - Otherwise builds a planner prompt via `_build_plan_prompt()` (`:483`), which appends (in order): optional `LEARNING CONTEXT` (transient, program-injected, `DATA ONLY` delimited), optional `PERSONAL MEMORY CONTEXT` (T21, privacy-filtered), and the LLM task-json instructions.
  - Two plan modes:
    - Single-shot (`BUDGET_AWARE_PLAN_SELECTION` off/unset): `_generate_plan()` (`:832`) → `ModelRouter.route_request()` (with `httpx` fallback) → regex-extracts a JSON task array.
    - K-plan selection (on/auto): `_plan_with_selection()` (`:311`) → `plan_generator.generate_plan_candidates()` + `plan_selector.select_plan()` → persists `MissionPlanCandidate` rows, emits `PLAN_SELECTED` substrate event, falls back to single-shot on any error.
  - Creates `MissionTask` rows (status `PENDING`), sets `Mission.status = PLANNED` (`:271`), persists `mission.plan`.
  - Injects historical learning via `LearningService.inject_into_planner_context()` (`:188`) — guarded by try/except so it never derails planning.
- Validation: `MissionStatus._TRANSITIONS` (`mission_models.py:58`) + SQLAlchemy event listeners (`_on_mission_status_set`, `:288`) enforce legal transitions.

### 1b. Execute (`planned → queued → executing/running → completed/approved/failed`)
- Synchronous: `MissionCommandHandlers.execute_mission()` — `commands.py:393`. Builds a `Workflow` via `mission_to_workflow()` adapter, runs `get_unified_executor().execute(self.session, workflow)` (the H5.1 `UnifiedExecutor`, the sole GA execution path). Honors `selected_plan_id` (rebuilds tasks from `MissionPlanCandidate`). Fires analytics + audit.
- Async: `MissionCommandHandlers.execute_async()` — `commands.py:487`. Multi-commit: status→`QUEUED`, log separately, dispatch to Celery `dispatch_mission_execution()` (fallback to `asyncio.create_task` + UnifiedExecutor).
- Recording: `substrate/executor.py:913` calls `LearningService.record_execution(...)` after a run — this is the **real learning write** that feeds 1a.
- Self-correction: `self_correction_loop.SelfCorrectionLoop.correct()` (`backend/app/services/self_correction_loop.py:183`) is the documented failure-recovery path (classifies via `FailureAnalyzer`, decides via `RecoveryPolicy`, bounded by `SelfCorrectionBudget` of $2.00 / 10 attempts / 600s). Emits `SELF_CORRECTION_*` substrate events.

### 1c. Improve (the weakest link)
- **Critique:** `CritiqueService.create_from_critic()` (`backend/app/services/critique_service.py:138`) persists a `Critique` row (workspace-isolated, score-clamped). Exposed via `api/v2/critiques.py` as an inspection surface — it is a *persistence* layer only.
- **Generate improvements:** `ImprovementGenerator.generate()` (`backend/app/services/improvement_generator.py:221`) is a **pure, deterministic, sync transformer** (`CriticOutput → ImprovementBatch`) with tool-suggestion extraction and recommendation thresholds. **It is never called by any runtime path** (verified: zero `.generate()` call sites outside its own docstring).
- **Manual improvement records:** `SelfImprovementEngine.generate_strategy()` / `apply_strategy()` (`backend/app/services/self_improvement.py:21,42`) — reachable from `MissionCommandHandlers.create_improvement()` / `apply_improvement()` (`commands.py:1019,1035`). Generic `if/elif` failure templates, NOT LLM-driven, NOT auto-invoked on failure.
- **Mission Programs (scheduled/standing missions):** `MissionProgramService.fire_program()` (`mission_program_service.py:309`) creates a `Mission` + `ProgramRun`, injects the consolidated `learning_brief` into the planner constraints; `consolidate_learning()` (`:440`) merges outcomes back. This closes a *standing-mission* loop (cron/webhook/manual), independent of the per-mission critique loop. Models: `MissionProgram` / `ProgramRun` (`mission_program_models.py`).

**Verdict on lifecycle:** Plan and Execute are production-wired through the substrate. Improve exists as callable services + data models, but the *autonomous closure* (critique → generate → apply → re-plan) is not connected. The learning-feedback half (1a↔1b via `LearningService`) is the only part that truly loops.

---

## 2. Swarm consensus strategies + usage caps — what is actually implemented

### 2a. Consensus strategies
- `SwarmProfile.consensus_strategy` / `consensus_config` columns exist (`models/swarm.py:31-32`), accepted by `SwarmCreate` schema (`schemas/swarm.py:12-13`) and persisted in `swarm_service.create_swarm()` (`swarm_service.py:34-35`).
- **No strategy enumeration, validation, or dispatch exists.** Searched the whole backend: `consensus_strategy` appears only in the model, schema, `swarm_service.py` (write), and the migration. It is **never read** by `DebateProtocol`, `HandoffProtocol`, `EscalationChain`, or any strategy. The accepted values are an open `str` — anything is accepted, nothing is enforced.
- The only "consensus" logic that runs is inside `DebateProtocol` (`services/swarm/debate_protocol.py`): an LLM-judge scores two agent positions and sets `consensus_reached`. That is hardcoded debate behavior, **not** driven by `consensus_strategy`.
- `swarm_tasks.py:check_consensus_timeouts()` (Celery beat) references strategies `"simple_majority"` / `"unanimous"` only as a *default string* when auto-resolving timed-out `SwarmConsensusRound` rows — it reads `consensus.strategy_used` off the round, not off the profile.
- **Conclusion:** "Configurable consensus strategies + usage caps" (per the brief §6) is **not implemented**. The field is a documented intent that never got a strategy registry.

### 2b. Usage caps mechanism
- `SwarmProfile.daily_limit` / `monthly_limit` (USD, `models/swarm.py:33-34`) are accepted by schema + persisted in `create_swarm()`.
- **They are never read at execution or scheduling time.** The only other `daily_limit`/`monthly_limit` enforcement in the backend lives in an unrelated module: `nexus/cost_optimizer.py` (a *workspace/nexus* budget enforcer, not swarm). Swarm caps have **no enforcement code** — a swarm can run unbounded regardless of the configured limits.
- Contrast: mission-level budgets ARE enforced (per-mission `MissionCircuitBreaker` + `BudgetEnforcer` in the substrate). Swarm caps are the unenforced sibling.

### 2c. Swarm execution status (the big one)
- `substrate/strategies/swarm.py:SwarmStrategy` is marked `DEPRECATED = True` with the comment *"0% success with 27B model per strategy profiling 2026-07-04."* The old `swarm/orchestrator.py` has **no `.py` source** in the tree (only stale `.pyc` files) — it was replaced by this deprecated strategy.
- `SwarmAgent` / `SwarmTask` / `SwarmConsensusRound` models exist and `swarm_service.py` has full CRUD (`create_swarm`, `add_agent_to_swarm`, `populate_swarm_from_division/slugs`, `create_swarm_task`, `get_swarm_stats`). **But none of that CRUD is mounted behind an HTTP router** (see §3).

---

## 3. What is ACTUALLY wired vs stub/seed (precise flags)

### WIRED (works)
- Mission lifecycle: plan (single-shot + K-plan selection), execute (sync + async/Celery), abort/pause/resume/retry, status stream — all via `_mission_cqrs`. ✓
- Substrate `UnifiedExecutor` + 7 strategies (solo/dag/graph/swarm/pipeline/meta/langgraph) — GA. ✓
- `LearningService` record→inject loop (Qdrant + Postgres fallback). ✓
- `MissionProgram` scheduled missions (`fire_program` / `consolidate_learning`), cron via `trigger_bridge`. ✓
- `CritiqueService` persistence + v2 `/critiques` inspection API. ✓
- `SelfCorrectionLoop` bounded retry (used by executor on task failure, per AGENTS.md). ✓
- Swarm **protocols** (debate/handoff/escalation) — `swarm_protocol.py` mounts 12 endpoints; the underlying `DebateProtocol`/`HandoffProtocol`/`EscalationChain` are real and functional. ✓ (But see caveat below.)

### STUB / UNFINISHED / DEAD (flagged)
1. **Swarm profile CRUD is invisible.** `swarm_service.py` implements `create_swarm`/`get_swarm`/`list_swarms`/`dissolve_swarm`/`add_agent_to_swarm`/etc., but **no API router wires them**. The only registered swarm route is `swarm_protocol` (debate/handoff/escalation). There is **no `POST /swarms`, no `GET /swarms`**. A frontend "SwarmDashboard" (referenced in `swarm_protocol.py` docstring) has no backend surface to create or list swarms. → **Swarm creation/listing is effectively unreachable.**
2. **`consensus_strategy` / `consensus_config` are write-only.** Stored, never read, no enum, no validation, no dispatch. → **Documented feature does not exist.**
3. **`daily_limit` / `monthly_limit` are write-only.** No enforcement path. → **Usage caps are cosmetic.**
4. **`SwarmStrategy` is DEPRECATED at 0% success.** The swarm execution path behind the substrate is known-broken on the default 27B model. → **Swarm "execution" cannot be demonstrated.**
5. **`ImprovementGenerator` is never invoked.** Pure logic, fully built, zero call sites. → **The critique→improvement synthesis step is dead code.**
6. **`SelfImprovementEngine` is template-only and not auto-triggered.** `if/elif` failure strings, reachable only via explicit `POST .../improvements` CQRS call. → **Not an autonomous loop.**
7. **`swarm_protocol.py` model references are loose.** It imports `DebateProtocol`/`HandoffProtocol`/`EscalationChain` and maps `HandoffRecord`/`EscalationRecord`/`DebateRound` shapes (defined in `models/agent.py`), but it does **not** import `SwarmProfile` or `SwarmConsensusRound` — consistent with the finding that profile-level config (consensus/caps) is never consulted.
8. **Personal-memory injection (T21) depends on late-bound `get_personal_memory_service`.** Wired in `plan_mission` only when the callable is registered; otherwise silently omitted. Confirmed safe-fail, but means the "personalized planning" claim depends on an external registration not verified here.

### SEED (not a gap, noted)
- Marketplace listings are seed data (per brief §9) — not in scope here but relevant to the shopfront argument.
- `MissionProgram` learning brief starts empty; populates over runs.

---

## 4. Why the landing page under-sells this (the Phase 2+ argument)

The brief is right that the backend is deep. But the gap between **what the engine does** and **what the front door shows** is structural, not cosmetic, and it is concentrated in exactly the two surfaces this analysis covers:

1. **Missions are invisible until you dig.** A user lands and sees a chat-first front door. The genuinely impressive capability — *watch an LLM break your goal into a dependency-ordered task graph, execute it through a durable substrate with self-correction, and accumulate learning across runs* — is hidden behind raw `/api/v2/missions/{id}/plan|execute|stream` routes that no shopfront screen surfaces. There is no "mission gallery," no live plan/execute visualization, no "this is what the engine just did for you" moment. The engine *plans and executes*; the front door *chats*.

2. **Swarm is the poster child of the gap.** The brief sells "agent orchestration depth" and the code has `SwarmProfile`, `SwarmAgent`, `SwarmTask`, `SwarmConsensusRound`, debate/handoff/escalation protocols — but:
   - you **cannot create or list a swarm** from any HTTP route (CRUD unmounted),
   - the **consensus config you'd set does nothing**,
   - the **usage caps you'd trust are not enforced**, and
   - the **execution strategy is deprecated at 0% success**.
   So any shopfront "Swarm" tile would be a facade over a non-functional subsystem. That is the precise thing that makes the front door *undersell* (it hides real depth in missions) while simultaneously *over-promising* (it implies swarm depth that isn't wired).

3. **The improvement story is data-only.** The backend can *record* critiques and *store* improvement suggestions, but nothing autonomously turns a failed mission into a better next plan. A shopfront "watch your AI get smarter" narrative would be aspirational, not live.

**The Phase 2+ move (from this analysis):** Don't build new engine. *Expose and finish the seams that exist.*
- **Surface missions through the shopfront:** a Mission Gallery + live plan/execute/stream view, pulling straight from the already-wired `v2/missions` CQRS routes. This alone converts the deepest, most-working subsystem into a first-impression.
- **Either finish or fence the swarm:** (a) mount `swarm_service` CRUD + a real `consensus_strategy` registry + enforce `daily/monthly_limit`, and un-deprecate `SwarmStrategy` (or replace it); OR (b) remove swarm from the marketed surface until it is real. Shipping the facade is the worst option.
- **Close the improvement loop visibly:** call `ImprovementGenerator` from the critique-write path and surface "suggested improvements" in the mission view. The logic is already written — it just needs one wiring call.

Priority order: **missions-first (safe, already works) → critique→improvement wiring (logic done, 1 call site) → swarm finish-or-hide (largest gap, highest risk of over-promising).**

---

## 5. File reference index
- `backend/app/services/mission_planner.py` — `plan_mission`, `_plan_with_selection`, `_generate_plan`, `_build_plan_prompt`, `_render_personal_memory_section`
- `backend/app/api/_mission_cqrs/commands.py` — `plan_mission` (374), `execute_mission` (393), `execute_async` (487), `create_improvement`/`apply_improvement` (1019/1035)
- `backend/app/models/mission_models.py` — `MissionStatus`/`MissionTaskStatus` transition tables + listeners
- `backend/app/models/mission_program_models.py` — `MissionProgram`/`ProgramRun`
- `backend/app/services/swarm_service.py` — swarm CRUD (unmounted in any router)
- `backend/app/models/swarm.py` — `SwarmProfile` (consensus_strategy/config, daily/monthly_limit), `SwarmAgent`, `SwarmTask`, `SwarmConsensusRound`
- `backend/app/api/v1/swarm_protocol.py` — 12 debate/handoff/escalation endpoints only; no profile CRUD
- `backend/app/services/swarm/debate_protocol.py`, `handoff_protocol.py`, `escalation_chain.py` — functional protocols
- `backend/app/services/substrate/strategies/swarm.py` — `SwarmStrategy(DEPRECATED=True, "0% success with 27B model")`
- `backend/app/services/self_improvement.py` — `SelfImprovementEngine` (template-only)
- `backend/app/services/improvement_generator.py` — `ImprovementGenerator` (never called)
- `backend/app/services/critique_service.py` — `CritiqueService.create_from_critic` (persistence only)
- `backend/app/services/learning_service.py` — `record_execution` (called by executor) + `inject_into_planner_context` (called by planner) — the real loop
- `backend/app/services/self_correction_loop.py` — `SelfCorrectionLoop.correct` (bounded retry)
- `backend/app/services/mission_program_service.py` — `fire_program`, `consolidate_learning`
