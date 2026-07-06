# Task: Phase 6 — Evals + Prompt Versioning

**Status:** DRAFT (revised by Hermes — supersedes DeepSeek draft)
**Priority:** P6 — reliability + quality loop
**Estimated effort:** 2 sessions
**Created:** 2026-07-05
**Depends on:** Phase 2 (agent step streaming) ✅ complete
**Blocks:** None — final phase
**Context docs:** `docs/HYBRID-PLATFORM-WORKSPACE.md`, `docs/REIMAGINE-CHAT-PROMPT-2026-07-05.md` §Phase 6, `.specs/REFERENCE-PROTOTYPE.md`

---

## ⚠️ Corrections from the DeepSeek draft

1. **The `evaluation/` module already exists** in `app/services/evaluation/` (per `services/AGENTS.md` §19 — "Evaluation / LLM-as-judge"). Phase 6 must reuse the existing LLM-as-judge implementation rather than inventing a parallel judge loop. Read `evaluation/` before writing `run_eval_suite` — it likely has the judge prompt, the comparison logic, and the score format already. The Celery task is the new piece: it calls the existing evaluator in a batch.

2. **The `reliability` checks also already exist** (per `services/AGENTS.md` §—"HITL / governance / reliability" — `reliability_assertions`). The research doc says "reliability.py already produces checks" — confirm the exact filename via `ls backend/app/services/reliability*` and `ls backend/app/api/v1/reliability.py`. The dashboard's "reliability tab" should extend the existing reliability surface, not be a fresh implementation.

3. **`openclaw-llm-bench` is referenced as a pattern.** This is a benchmark harness (per the available skills list in this session — `mlops/evaluation/evaluating-llms-harness`). Phase 6 does NOT install or import openclaw itself; it borrows the suite structure (named test cases, scored runs, trend tracking). Don't add a dependency on a benchmark harness for production code — Phase 6 ships its own minimal suite runner.

4. **The chat settings system prompt is per-thread (`thread.metadata_.get("system_prompt")`)**, not per-workspace by default. The draft's `_build_chat_messages` lookup chain (`prompt_versions` first, then thread metadata) is sound, but check the actual thread metadata field name in `chat_service.py:_build_chat_messages` before coding — the draft's `thread.metadata_.get("system_prompt", "You are a helpful assistant.")` may use a different attribute name than the real Thread model. Read `_build_chat_messages` first.

5. **Agent definitions** live in `app/agent_definitions/` (17 domain-agent directories per the research doc). The draft's `prompt_version_id` reference in agent config is sound but unverified — read one agent definition file (e.g. `agent_definitions/engineering/`) to confirm the config schema before adding the field.

6. **Celery app is in `app/tasks/celery_app.py`** (per `backend/AGENTS.md` — "Task Queue: Celery 5.3 + RabbitMQ"). The new `run_eval_suite` task goes in `app/tasks/eval_run.py` following the existing task registration pattern.

---

## 🔴 Reference prototype patterns (from `.sisyphus/src/`)

### A. `prompt_versions` table — the migration reference

From `db/schema.ts:246-257`:
```
id, name (TEXT NOT NULL), content (TEXT NOT NULL), version (INTEGER DEFAULT 1),
is_active (BOOLEAN DEFAULT TRUE), created_at (TIMESTAMPTZ DEFAULT NOW())
INDEX: (name)
```

Note: the prototype's `prompt_versions` table does **not** have a `workspace_id` column — it's global. The drafts' version added `workspace_id` for per-workspace scoping. The production implementation should add `workspace_id` (the drafts were right to add it), but the prototype's simpler global-scoping is the starting reference.

### B. `agent_teams` table — the agent team config reference

From `db/schema.ts:231-242`:
```
id, name, description, members (JSONB: [{ name, role, systemPrompt }]),
protocol (TEXT: sequential|debate|swarm|escalation), max_turns (INTEGER DEFAULT 10),
escalation_policy (JSONB), created_at
```

This is relevant for Phase 6's "wire prompts to agent definitions" — each agent team member has a `systemPrompt` field that should be replaced by a `prompt_version_id` reference.

### C. `TopBar.tsx` — the model picker / agent team picker pattern

`components/TopBar.tsx:56-97` — the prototype's model picker dropdown:
- Button with icon + label
- Dropdown panel with options, each showing label + provider
- Active option highlighted with blue
- Click sets the thread's model via `updateThread`

The prompt version dropdown in `ChatSettings.tsx` should follow this exact pattern — replace "model" with "prompt version" and "provider" with "version number + active indicator".

### D. `done` SSE event carries cost data

From the mock stream (`chat/stream/route.ts:282-289`):
```json
{
  "type": "done",
  "data": {
    "messageId": "uuid",
    "tokenCount": 342,
    "cost": 420,
    "timestamp": 1234567890
  }
}
```

The `cost` field (in micro-cents per `db/schema.ts:106`: `cost: integer("cost") // stored in micro-cents`) is the per-message cost that Phase 5's cost tracking produces. Phase 6's eval dashboard should aggregate these values. The `AgentTracePanel.tsx:211-225` Cost section already sums `message.tokenCount` — extend it with the cost rollup.

---

## Problem

There's no way to version or compare system prompts for chat threads or agent definitions. When a prompt change breaks agent behavior, there's no rollback path. There's also no automated evaluation of agent reliability — no benchmark suite, no scoring, no trend tracking.

**Goal:** Close the loop on agent reliability with prompt versioning (CRUD + rollback) and automated eval runs (benchmark suites + dashboard scoring), reusing the existing `evaluation/` LLM-as-judge module.

---

## Acceptance Criteria

- [ ] `prompt_versions` table created via Alembic migration
- [ ] CRUD API for prompt versions: create, list, get, activate, soft-delete
- [ ] `ChatSettings.tsx` system prompt field becomes a version dropdown
- [ ] "Save as new version" flow in chat settings
- [ ] Agent definitions can reference prompt versions (verify agent-definition schema first)
- [ ] `eval_run` Celery task runs benchmark suites (reuses `evaluation/` LLM-as-judge)
- [ ] `eval_run` table records score per case
- [ ] Dashboard `reliability` tab visualizes eval trends with recharts (extends existing reliability surface)
- [ ] `pnpm lint && pnpm build` passes
- [ ] Backend tests pass: `test_prompt_versions.py`, `test_eval_run.py`

---

## Sub-tasks

### 6.1 — Read existing modules before coding

**Read first (all backend):**
- `backend/app/services/evaluation/` — existing LLM-as-judge (reuse, don't reinvent)
- `backend/app/services/` — locate the exact `reliability*` file (`ls backend/app/services/reliability*`)
- `backend/app/services/chat_service.py:_build_chat_messages` — verify the actual `thread.metadata_.get("system_prompt")` attribute name
- `backend/app/agent_definitions/<one_dir>/` — confirm the config schema before adding `prompt_version_id`
- `backend/app/tasks/celery_app.py` and one existing task file — match the Celery registration pattern

### 6.2 — Create prompt_versions table (backend)

**Create model:** `backend/app/models/prompt_version_models.py`

```python
class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id = Column(Integer, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=False)
    name = Column(String, nullable=False)  # e.g. "Default Assistant", "Code Helper"
    content = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("users.id"))
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", "version", name="uq_prompt_version"),
    )
```

**Create migration:** `backend/alembic/versions/xxx_prompt_versions.py`

Pre-flight: `SELECT COUNT(*) FROM workspaces` — the migration is a pure `CREATE TABLE`, no sentinel needed.

### 6.3 — Prompt version CRUD API (backend)

**Create:** `backend/app/api/v2/prompts.py`

```python
@router.get("/prompts")
async def list_prompts(workspace_id: str, ...):
    """List all prompt versions for a workspace."""

@router.post("/prompts")
async def create_prompt(body: CreatePromptRequest, ...):
    """Create a new prompt version. Auto-increments version number per (workspace_id, name)."""

@router.get("/prompts/{prompt_id}")
async def get_prompt(prompt_id: int, ...):
    """Get a specific prompt version."""

@router.put("/prompts/{prompt_id}/activate")
async def activate_prompt(prompt_id: int, ...):
    """Set this prompt version as the active one for its name group.
    The activate path uses a sentinel UPDATE (sets is_active=true for the target, false for others)
    not a DELETE."""

@router.delete("/prompts/{prompt_id}")
async def delete_prompt(prompt_id: int, ...):
    """Soft-delete a prompt version (set is_active=False)."""
```

**Register** in `backend/app/api/v2/__init__.py`.

### 6.4 — Wire prompts to chat settings (backend)

**File:** `backend/app/services/chat_service.py` — `_build_chat_messages`

Update `_build_chat_messages()` to load the active prompt version instead of the thread's inline system prompt. But first **read `_build_chat_messages`** to confirm the actual metadata attribute name — don't trust the draft's `thread.metadata_.get("system_prompt")`:

```python
async def _build_chat_messages(db, thread_id, max_history=20):
    thread = await get_chat_thread(db, thread_id)

    # Try prompt_versions first, fall back to thread metadata
    if thread.workspace_id:
        prompt = await get_active_prompt(db, thread.workspace_id, "Default Assistant")
        if prompt:
            system_prompt = prompt.content
        else:
            # Use the actual attribute name found by reading _build_chat_messages:
            system_prompt = thread.metadata_.get("system_prompt", "You are a helpful assistant.")
    else:
        system_prompt = thread.metadata_.get("system_prompt", "You are a helpful assistant.")

    # ... rest of message building
```

### 6.5 — Version dropdown in ChatSettings (frontend)

**File:** `frontend/src/components/chat/ChatSettings.tsx`

Replace the system prompt `<textarea>` with a version-aware editor:

```tsx
const ChatSettings = () => {
  const { data: prompts } = useQuery(['prompts', workspaceId], () => fetchPrompts(workspaceId));

  return (
    <div>
      <Select value={selectedPromptId} onValueChange={setSelectedPromptId}>
        {prompts?.map(p => (
          <SelectItem key={p.id} value={p.id}>
            {p.name} v{p.version} {p.is_active && "✓"}
          </SelectItem>
        ))}
      </Select>

      <Textarea value={promptContent} onChange={setPromptContent} />

      <div className="flex gap-2">
        <Button onClick={saveAsNewVersion}>Save as New Version</Button>
        <Button onClick={activateVersion} variant="outline">Activate</Button>
      </div>
    </div>
  );
};
```

### 6.6 — Wire prompts to agent definitions (backend)

**File:** `backend/app/agent_definitions/` (each agent directory — read one first)

Add optional `prompt_version_id` to agent config. When set, the agent's system prompt is loaded from `prompt_versions` instead of the inline `system_prompt` field. This enables:
- Version-controlled agent prompts
- A/B testing different prompts
- Rollback to known-good prompts

**⚠ Verify the agent config schema first** — read one `agent_definitions/<dir>/config.*` file before adding the field.

### 6.7 — Create eval_run Celery task (backend)

**Create:** `backend/app/tasks/eval_run.py`

```python
from app.tasks.celery_app import celery_app  # match the actual import path
from app.services.evaluation import ...  # reuse the existing LLM-as-judge — don't reinvent

@celery_app.task(bind=True, max_retries=2)
def run_eval_suite(self, eval_suite_id: int, target_type: str, target_id: str):
    """Run an evaluation suite against a chat thread or agent.

    eval_suite_id: ID of the eval suite (test cases + scoring criteria)
    target_type: "chat_thread" | "agent_id"
    target_id: thread ID or agent ID to evaluate

    Reuses the existing evaluation/ LLM-as-judge — do NOT write a parallel scorer.
    """
    # 1. Load eval suite from DB
    # 2. For each test case:
    #    a. Send the test prompt to the target
    #    b. Collect the response
    #    c. Score with the existing evaluation/LLM-as-judge (reuse, not reinvent)
    #    d. Record score in eval_run table
    # 3. Compute aggregate scores (reliability, accuracy, latency)
    # 4. Store eval_run results
```

### 6.8 — Create eval_run table (backend)

**Create model:** `backend/app/models/eval_models.py`

```python
class EvalSuite(Base):
    __tablename__ = "eval_suites"

    id = Column(Integer, primary_key=True)
    workspace_id = Column(String, ForeignKey("workspaces.id"))
    name = Column(String, nullable=False)
    description = Column(Text)
    test_cases = Column(JSON)  # [{prompt, expected_behavior, scoring_criteria}]
    created_at = Column(DateTime, default=datetime.utcnow)

class EvalRun(Base):
    __tablename__ = "eval_runs"

    id = Column(Integer, primary_key=True)
    eval_suite_id = Column(Integer, ForeignKey("eval_suites.id"))
    target_type = Column(String)  # "chat_thread" | "agent_id"
    target_id = Column(String)
    scores = Column(JSON)  # {case_id: {score, reasoning, latency_ms}}
    aggregate_scores = Column(JSON)  # {reliability, accuracy, avg_latency}
    status = Column(String)  # "pending" | "running" | "complete" | "failed"
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
```

**Create migration:** `backend/alembic/versions/xxx_eval_tables.py`

### 6.9 — Dashboard reliability tab (frontend)

**Create:** `frontend/src/components/dashboard/ReliabilityTab.tsx`

Dashboard tab showing eval run results:
- Line chart: reliability score over time (recharts, already installed)
- Table: recent eval runs with scores, latency, status
- Filter by: eval suite, target (thread/agent), date range
- Drill-down: click a run to see per-case scores

**⚠ Read the existing reliability surface first** (`backend/app/api/v1/reliability.py` per the v1 AGENTS.md router inventory; also `services/reliability_assertions`). The new tab should extend the existing reliability surface, not duplicate it. If the existing dashboard already has a reliability view, add the eval-run chart alongside it.

### 6.10 — Eval suite management UI (frontend)

**Create:** `frontend/src/components/settings/EvalSuiteManager.tsx`

Settings page for managing eval suites:
- Create/edit eval suites
- Add test cases (prompt + expected behavior + scoring criteria)
- Run eval suite against a thread or agent
- View results

### 6.11 — Tests

**Backend:**
- `test_prompt_versions.py`: CRUD, version auto-increment, activate/rollback
- `test_eval_run.py`: task execution, score recording, aggregate computation. Use the existing `evaluation/` module's input/output format in the test fixtures — don't fabricate a judge response.

**Frontend:**
- Manual: create prompt version, activate it, send chat message, verify it uses the new prompt
- Manual: create eval suite with 3 test cases, run it, view results in dashboard

### 6.12 — Verification gate

```bash
# Backend
cd /opt/flowmanner
docker compose exec backend pytest app/tests/test_prompt_versions.py -v
docker compose exec backend pytest app/tests/test_eval_run.py -v

# Frontend
cd /home/glenn/FlowmannerV2-frontend
pnpm lint && pnpm build

# Manual:
# 1. Create a prompt version in chat settings
# 2. Activate it, send a message, verify the new system prompt is used
# 3. Create an eval suite with 3 test cases
# 4. Run it against a chat thread
# 5. View results in dashboard reliability tab
```

---

## File Map

| File | Action |
|------|--------|
| `backend/app/models/prompt_version_models.py` | **NEW** — PromptVersion model |
| `backend/app/models/eval_models.py` | **NEW** — EvalSuite + EvalRun models |
| `backend/alembic/versions/xxx_prompt_versions.py` | **NEW** — migration (pure CREATE TABLE) |
| `backend/alembic/versions/xxx_eval_tables.py` | **NEW** — migration (pure CREATE TABLE) |
| `backend/app/api/v2/prompts.py` | **NEW** — prompt CRUD endpoints |
| `backend/app/api/v2/__init__.py` | Register prompts router |
| `backend/app/services/chat_service.py` | Load active prompt version in `_build_chat_messages` (verify attribute name first) |
| `backend/app/tasks/eval_run.py` | **NEW** — Celery task (reuses existing `evaluation/` LLM-as-judge) |
| `frontend/src/components/chat/ChatSettings.tsx` | Version dropdown + save flow |
| `frontend/src/components/dashboard/ReliabilityTab.tsx` | **NEW** — eval results chart (extends existing reliability surface) |
| `frontend/src/components/settings/EvalSuiteManager.tsx` | **NEW** — eval suite CRUD |
| `backend/tests/test_prompt_versions.py` | **NEW** — prompt version tests |
| `backend/tests/test_eval_run.py` | **NEW** — eval run tests |

---

## Design Notes

- **Prompt versioning is per-workspace, not global.** Each workspace has its own prompt library. Shared prompts can be promoted to a "global" scope later.
- **Eval suites reuse the existing `evaluation/` LLM-as-judge** — do NOT write a parallel judge. The judge model is configurable per suite (default: `deepseek/deepseek-v4-flash` for cost efficiency per the user's setup).
- **Eval runs are async** (Celery task). The dashboard polls for completion or uses SSE for real-time updates.
- **Reliability score** = percentage of test cases that pass the scoring criteria. `passed / total * 100`.
- **Dashboard extends existing reliability surface** — read `v1/reliability.py` and `services/reliability_assertions` first. Do not duplicate.
- **`openclaw-llm-bench`** is referenced as a pattern (`mlops/evaluation/evaluating-llms-harness` skill), not an installed dependency. Phase 6 ships its own minimal suite runner — do not add a benchmark harness dependency to the backend.

---

## Risks

| Risk | Mitigation |
|------|------------|
| Prompt version rollback breaks active conversations | Only new messages use the new prompt. Existing conversations keep their inline system prompt until explicitly updated. |
| Eval runs are expensive (LLM calls per case) | Use the cheapest model for judging (deepseek v4 flash per user setup). Limit eval suite size. Cache results. |
| Eval scoring is subjective (LLM-as-judge) | Use structured scoring criteria (1-5 scale with rubric). Run each case 3x and take median. |
| Dashboard chart performance with many eval runs | Paginate runs, aggregate at query level, use recharts `isAnimationActive={false}` for large datasets. |
| `evaluation/` module not in the expected shape | 6.1 read-first step verifies; if the module shape differs, adapt the task to the actual judge interface. |
| Agent definition schema doesn't support `prompt_version_id` | 6.6 verifies; if the schema differs, gate this sub-task behind a separate ADR rather than forcing it into Phase 6. |
