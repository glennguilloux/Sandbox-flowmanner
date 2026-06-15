# Mission Upgrade Brainstorm — Natural Next Move

**Status:** BRAINSTORM — for Claude Opus review and implementation planning.
**Created:** 2026-06-13
**Author:** Hermes (brainstorm), Glenn (decisions), Claude Opus (implementation)
**Preceded by:** `.sisyphus/plans/q2-q3-agentic-workflow.md` (all 6 chunks now have implementations)

---

## 0. What Mission Is Today

A mission is a **one-shot, stateless agentic workflow**:

```
User creates mission (title, description, constraints)
    → MissionPlanner generates tasks via LLM (pending → planning → planned)
    → UnifiedExecutor runs tasks in dependency order (executing → running)
    → Results, cost, logs written
    → Terminal state (completed / failed / aborted)
```

Key characteristics of the current model:

1. **Stateless between runs.** Each mission starts from scratch. The planner does not know what worked or failed in past missions of the same type.
2. **Triggers fire copies.** `MissionTrigger` (cron + webhook) can re-execute a mission, but each fire generates the same plan from the same prompt — no accumulated learning.
3. **The agent inside is smart, the mission is not.** All 6 Q2-Q3 agentic capabilities are implemented (episodic memory, tool routing, adaptive depth, self-correction, multi-agent handoff, recovery policy). These make the agent's execution smarter within a single run. None of them make the mission smarter across runs.
4. **No feedback loop.** I searched for any path where mission results influence future planning — there is none. The `MissionImprovement` table captures suggestions but nothing feeds them back into the planner.
5. **Templates exist but are static.** `MissionTemplate` + `create_from_template` let users clone a mission definition, but the template never evolves based on outcomes.

**The gap:** FlowManner has built a sophisticated agentic execution engine, but the unit of work (the mission) is still a disposable batch job. The substrate is durable, replayable, cost-aware, and interruptible — but the mission itself has no memory of its own past and no ability to improve.

---

## 1. Three Candidate Upgrades

### Candidate A: Mission Programs — Self-Improving Standing Missions

**Pitch:** Turn missions from disposable batch jobs into persistent operational agents that run repeatedly, accumulate outcome intelligence, and improve their own plans over time.

**What changes:**
- A new `MissionProgram` entity wraps a mission definition + trigger configuration + accumulated learning state.
- Each time the program fires (cron, webhook, or manual), the planner receives **context from past runs**: what plans succeeded, what failed, average cost, common pitfalls, HITL outcomes.
- The plan adapts. A program that has run 47 times generates a smarter plan than its first run.
- The program maintains a **rolling brief** — a compact, evolving summary of what it has learned, stored as structured memory (not raw episode replay).

**Why this is the most natural move:**
- Every component already exists and is implemented. This is a **composition upgrade**, not a new subsystem:
  - `MissionTrigger` → fires the program
  - `EpisodicMemoryService` → stores past run outcomes
  - `MissionPlanner` → generates plans (just needs the learning context injected)
  - `MissionTemplate` → becomes the program's definition
  - `UnifiedExecutor` → runs the generated plan (no change needed)
- The only missing piece is the **feedback loop**: past outcomes → planner context → adapted plan. That's a new model + a planner prompt enhancement + a consolidation step. 1-2 weeks of work.
- It directly delivers the roadmap's stated wedge: "cost-aware, interruptible, resumable agentic workflows" evolve into **self-improving operational agents**.

**Product story:** "Your AI workforce that gets measurably better every day. Define a responsibility once. The agent learns from every run, every failure, every human redirect — and the next run is smarter."

**Concrete example:**
- Day 1: "Monitor competitor pricing changes and alert me on significant moves." Mission plans a web-scrape → compare → alert pipeline. First run is naive: scrapes everything, triggers 15 false-positive alerts.
- Day 7: The program has run 40 times. The planner knows: "price changes under 3% don't matter to this user (HITL rejection history). Amazon scraper fails on weekends (failure pattern). Best tool: SearXNG price comparison, not direct scrape." The plan is now tighter, cheaper, and more accurate.

**Build surface (files that would change):**
- NEW: `backend/app/models/mission_program_models.py` — `MissionProgram`, `ProgramLearning`, `ProgramRunHistory`
- NEW: `backend/app/services/mission_program_service.py` — program lifecycle, learning consolidation
- MODIFY: `backend/app/services/mission_planner.py` — inject learning context into the planning prompt
- MODIFY: `backend/app/services/substrate/trigger_bridge.py` — fire programs, not just missions
- MODIFY: `backend/app/api/v2/missions.py` (or new `v2/programs.py`) — program CRUD + run history + learning state
- NEW: `backend/alembic/versions/*_mission_programs.py` — migration
- MODIFY: `frontend/src/hooks/use-missions.ts` — program hooks
- NEW: `frontend/src/components/missions/MissionProgramView.tsx` — program dashboard

**Estimated effort:** 1.5–2 weeks (1 backend agent + frontend after API is stable).

**Risks:**
- Learning consolidation could become expensive if it runs on every fire. Mitigation: batch consolidation (Celery task every N runs or daily).
- Privacy: accumulated learning must respect workspace/user scoping. Mitigation: reuse existing episodic memory redaction + workspace isolation.

---

### Candidate B: Conversational Mission Studio

**Pitch:** Replace form-based mission creation with a chat-based collaborative design experience. The user describes what they want in natural language; the agent proposes a plan, the user refines it through conversation, and the mission launches from the agreed plan.

**What changes:**
- A new "mission design" chat mode where the LLM acts as a mission architect.
- The agent can propose task breakdowns, suggest constraints, recommend tools, flag risks — all through conversation.
- The user can redirect ("actually, skip the web scraping step, I already have the data"), and the plan updates live.
- Once both agree, one click launches the mission with the finalized plan.
- This also enables mid-flight redirection: the user can chat with a running mission to inject context, change priorities, or request replanning.

**Why it's natural:**
- FlowManner already has a chat layer (`chat_service.py`, chat threads, streaming). Missions and chat are separate today — this bridges them.
- The `MissionPlanner` already uses an LLM to generate plans. The conversational studio just makes that planning interactive instead of one-shot.
- HITL already exists for pause/resume — conversational redirection is a natural extension.

**Product story:** "Design your AI workflow like talking to a senior engineer. No forms, no YAML. Just describe the outcome, refine together, and launch."

**Why it's ranked below A:**
- It's primarily a **frontend/UX upgrade**, not a substrate capability. The backend changes are modest (a chat-to-mission bridge). The value is in the UI, which is the harder surface to get right.
- It doesn't make missions smarter over time — it makes them easier to set up once. Candidate A compounds; B does not.

**Build surface:**
- NEW: `backend/app/api/v2/mission_studio.py` — chat-based planning endpoint
- MODIFY: `backend/app/services/mission_planner.py` — iterative plan refinement
- NEW: `frontend/src/components/missions/MissionStudio.tsx` — conversational UI
- MODIFY: `frontend/src/hooks/use-missions.ts` — studio hooks

**Estimated effort:** 2–3 weeks (frontend-heavy).

---

### Candidate C: Mission Graph — Composable Pipelines

**Pitch:** Let missions invoke other missions as sub-workflows. Build complex AI pipelines by composing simple mission building blocks. Visual DAG of missions feeding into missions.

**What changes:**
- A mission task's `task_type` can be `sub_mission` — it invokes another mission (or template) as a child.
- The child's output flows into the parent mission's context via the existing `{{node_id.output.field}}` interpolation.
- A visual builder lets users wire missions together into dependency graphs.
- Mission templates become reusable components in a library.

**Why it's natural:**
- The substrate already supports this at the execution level: `NodeExecutor._MAX_SUB_WORKFLOW_DEPTH = 5`, sub-workflows share parent budget, and `mission_to_workflow` adapters exist.
- `HandoffPacket` (Chunk 5) already defines how context/budget/tools transfer between agents — sub-missions are a specialization of this.
- The DAG and Graph strategies already handle dependency-ordered execution.

**Why it's ranked below A:**
- The execution substrate already supports sub-workflows. The work here is mostly **data model + API + UI** for composition, which is substantial.
- It's a **power-user feature** — most users won't compose mission graphs. Candidate A benefits every user who runs a mission more than once.
- Risk of over-engineering: composition introduces state management complexity (what if a sub-mission fails? cascading abort? budget allocation across children?).

**Build surface:**
- MODIFY: `backend/app/models/mission_models.py` — add `sub_mission` task type, parent/child relationships
- MODIFY: `backend/app/services/substrate/node_executor.py` — sub-mission execution path
- MODIFY: `backend/app/services/substrate/adapters.py` — compose parent + child workflows
- NEW: `frontend/src/components/missions/MissionGraphBuilder.tsx` — visual builder
- MODIFY: `backend/app/api/v2/missions.py` — composition endpoints

**Estimated effort:** 3–4 weeks.

---

## 2. Recommendation

**Build Candidate A: Mission Programs first.**

Rationale:

1. **Highest leverage per unit of work.** Every component exists. The build is a new model + a feedback loop + a planner enhancement. ~2 weeks.
2. **Compounds value.** Every mission that runs more than once gets smarter. The longer a program runs, the more valuable it becomes. This is a moat.
3. **Directly extends the shipped substrate.** Triggers, episodic memory, planner, executor — all already implemented. Mission Programs is the connective tissue that turns these individual capabilities into a coherent product story.
4. **No new infrastructure.** No new services, no new databases, no new frontend paradigm. It's a backend-first feature with a straightforward API + dashboard.
5. **Natural sequencing.** After A ships, B (Conversational Studio) and C (Composable Pipelines) both become more compelling: you'd want to conversationally design a Mission Program, and you'd want to compose programs into pipelines.

**A then B then C** is the natural roadmap.

---

## 3. Candidate A — Detailed Build Plan

### Phase 1: Mission Program Data Model (3 days)

**New model: `MissionProgram`**

```python
class MissionProgram(Base, TimestampMixin):
    __tablename__ = "mission_programs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("workspaces.id"), nullable=True, index=True)

    # Identity
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    mission_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # The mission definition (like a template, but alive)
    base_constraints: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    base_context_files: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    base_context_urls: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Trigger configuration
    trigger_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {"type": "cron", "expression": "0 9 * * *", "timezone": "UTC"}
    # {"type": "webhook", "secret": "...", "path": "..."}
    # {"type": "manual"}  # user clicks "Run"

    # Accumulated learning (the rolling brief)
    learning_brief: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {
    #   "total_runs": 47,
    #   "success_rate": 0.89,
    #   "avg_cost_usd": 0.034,
    #   "avg_tokens": 12500,
    #   "common_failures": [{"pattern": "...", "count": 3, "mitigation": "..."}],
    #   "effective_tools": ["searxng_search", "rag_retrieve"],
  	#   "ineffective_tools": ["direct_scrape"],
    #   "hitl_history": [{"outcome": "approved", "count": 12}, {"outcome": "rejected", "count": 3}],
    #   "plan_adjustments": "Skip scraping on weekends. Alert threshold 3%+.",
    #   "last_consolidated_at": "2026-06-13T..."
    # }

    # Status
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    # "active" | "paused" | "archived"

    # Budget guardrails
    per_run_budget_usd: Mapped[float | None] = mapped_column(Double, nullable=True)
    monthly_budget_usd: Mapped[float | None] = mapped_column(Double, nullable=True)
```

**New model: `ProgramRun`** (lightweight — links a program to each mission it spawned)

```python
class ProgramRun(Base, TimestampMixin):
    __tablename__ = "program_runs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    program_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("mission_programs.id"), nullable=False, index=True)
    mission_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("missions.id"), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "cron" | "webhook" | "manual"
    trigger_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)  # "running" | "completed" | "failed" | "aborted"
    cost_usd: Mapped[float | None] = mapped_column(Double, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Double, nullable=True)
    outcome_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
```

**Migration:** `backend/alembic/versions/2026_06_14_mission_programs.py`

### Phase 2: Program Execution Path (4 days)

**New service: `backend/app/services/mission_program_service.py`**

```python
class MissionProgramService:
    async def fire_program(self, program_id: UUID, trigger_type: str, payload: dict | None = None) -> Mission:
        """
        1. Load the program and its learning_brief.
        2. Create a new Mission from the program's base definition.
        3. Inject the learning_brief into the mission's constraints as
           `_planning_context` so the planner can use it.
        4. Create a ProgramRun linking program → mission.
        5. Dispatch the mission to UnifiedExecutor (existing path).
        6. Return the mission.
        """

    async def consolidate_learning(self, program_id: UUID) -> dict:
        """
        1. Load the last N completed ProgramRuns (default 10).
        2. Pull their episodic memory episodes, costs, HITL outcomes,
           failure patterns, and tool usage.
        3. Summarize into a compact learning_brief update.
        4. Write back to program.learning_brief.
        5. Return the new brief.

        Called by a Celery beat task (daily or every N runs) or
        manually via API.
        """
```

**Modify: `backend/app/services/mission_planner.py`**

The planner's LLM prompt currently receives:
- Mission title + description
- Constraints
- Available tools/models

After the upgrade, it ALSO receives (when `_planning_context` is present in constraints):
- Past run count, success rate, avg cost
- Common failure patterns + known mitigations
- Tools that worked well / poorly in past runs
- HITL outcomes (what humans approved vs rejected)
- Natural-language plan adjustments from the learning brief

Example prompt injection:
```
## Learning Context (from 47 prior runs of this program)
- Success rate: 89% | Avg cost: $0.034 | Avg tokens: 12,500
- Known failures: "direct_scrape" fails on weekends (3 occurrences) → use SearXNG instead
- Effective tools: searxng_search, rag_retrieve
- HITL history: 12 approved, 3 rejected (rejections were for price changes < 3%)
- Plan adjustments: Skip scraping on weekends. Alert threshold is 3%+.

Generate a plan that accounts for this learning.
```

**Modify: `backend/app/services/substrate/trigger_bridge.py`**

Currently fires a Mission directly. After the upgrade, if the trigger belongs to a MissionProgram, it calls `program_service.fire_program()` instead of creating a bare mission.

### Phase 3: Learning Consolidation Worker (2 days)

**New Celery task: `backend/app/tasks/program_consolidation.py`**

```python
@celery_app.task(name="consolidate_program_learning")
def consolidate_program_learning(program_id: str):
    """Daily or every-N-runs consolidation of program learning."""
    # Calls program_service.consolidate_learning(program_id)
```

**Add to Celery beat schedule:** run daily at 03:00 UTC for all active programs.

The consolidation uses the existing `EpisodicMemoryService` to pull compact episode summaries, then an LLM call to synthesize them into the structured `learning_brief`. The LLM call goes through `BudgetEnforcer.call()` per substrate contract.

### Phase 4: API + Frontend (3 days)

**New API: `backend/app/api/v2/programs.py`**

| Method | Path | Description |
|--------|------|-------------|
| POST | `/programs` | Create a mission program |
| GET | `/programs` | List programs (paginated) |
| GET | `/programs/{id}` | Get program detail + learning brief |
| PATCH | `/programs/{id}` | Update program (name, constraints, trigger config) |
| DELETE | `/programs/{id}` | Archive program |
| POST | `/programs/{id}/fire` | Manually trigger a run |
| GET | `/programs/{id}/runs` | List run history |
| POST | `/programs/{id}/consolidate` | Manually trigger learning consolidation |
| GET | `/programs/{id}/learning` | Get the current learning brief |

**Frontend: `frontend/src/hooks/use-programs.ts` + `MissionProgramView.tsx`**

- Program list with status badges (active/paused/archived), run count, success rate
- Program detail page: learning brief panel, run history table, fire button
- Create program form: same fields as mission creation + trigger configuration

### Phase 5: Tests (ongoing, parallel to each phase)

| Test file | Coverage |
|-----------|----------|
| `test_mission_program_models.py` | Model creation, relationships, status transitions |
| `test_mission_program_service.py` | fire_program, consolidate_learning, budget enforcement |
| `test_program_planner_context.py` | Planner receives and uses learning context |
| `test_program_trigger_bridge.py` | Trigger fires program, not bare mission |
| `test_program_api.py` | All endpoints, ownership checks, pagination |
| `test_program_consolidation.py` | Celery task, episodic memory integration |

---

## 4. What Not to Build

- **Auto-tuning of model selection.** The learning brief informs the planner, but the program should not automatically switch models without human visibility. Keep model selection in the planner's reasoning, not in a hidden optimizer.
- **Cross-program learning.** Programs learn from their own runs only. Sharing learning across programs is a later feature (and a privacy surface to design carefully).
- **Program marketplace.** Explicitly out of scope per the Q2-Q3 roadmap. Programs are private to a workspace.
- **Real-time plan editing during consolidation.** The learning brief is updated on a schedule, not on every run. Real-time would be too expensive and would destabilize the planner prompt.

---

## 5. Success Criteria

1. A user can create a Mission Program with a trigger (cron, webhook, or manual).
2. Each fire creates a Mission with the program's learning context injected into the planning prompt.
3. After N completed runs, the consolidation worker updates the program's learning brief.
4. The Nth run's plan differs from the 1st run's plan in ways that reflect accumulated learning (verified by test).
5. The program dashboard shows: run count, success rate, avg cost, learning brief, and run history.
6. Budget guardrails (per-run + monthly) are enforced.
7. All tests pass. No regressions in existing mission/substrate tests.
8. No VPS source edits. No `docker cp`. Official deploy scripts only.

---

## 6. Open Questions for Glenn

1. **Should MissionProgram subsume MissionTrigger?** The program has its own trigger_config. Or should triggers remain a separate entity that can attach to either a mission or a program?
2. **Consolidation cadence:** daily, every N runs, or both? (Recommendation: both — daily + every 10 runs, whichever comes first.)
3. **Should the learning brief be human-editable?** (Recommendation: yes, read-write. The user should be able to add their own notes that the planner respects.)
4. **Budget model:** should program budget be separate from workspace budget, or a sub-allocation? (Recommendation: separate guardrail, enforced independently.)

---

## Provenance

This brainstorm was created from:
- `backend/app/models/mission_models.py` — Mission, MissionTask, MissionStatus lifecycle
- `backend/app/models/trigger_models.py` — MissionTrigger (cron + webhook, but stateless firing)
- `backend/app/models/mission_advanced_models.py` — MissionTemplate (static, no learning)
- `backend/app/services/mission_planner.py` — LLM-driven plan generation (no learning context injected)
- `backend/app/services/mission_executor.py` — execution orchestrator
- `backend/app/services/substrate/` — UnifiedExecutor, 7 strategies, event log, replay, triggers
- `backend/app/services/episodic_memory_service.py` — episode storage + retrieval (exists, not fed to planner)
- `backend/app/services/tool_router.py` — sparse tool routing (exists)
- `backend/app/services/depth_policy.py` — adaptive reasoning depth (exists)
- `backend/app/services/self_correction_loop.py` — bounded self-correction (exists)
- `backend/app/services/swarm/handoff_protocol.py` — typed handoff packets (exists)
- `.sisyphus/plans/q2-q3-agentic-workflow.md` — the 6-chunk roadmap (all implemented)
- Frontend `use-missions.ts` — current mission API hooks (basic CRUD + execute)

**Most important finding:** All 6 Q2-Q3 agentic chunks have implementations. The agent inside a mission is smart. But the mission itself has no memory across runs and no ability to improve. That gap is the natural upgrade.
