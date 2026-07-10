# Task: Cost-Aware Plan Selection — Round-Trip Wiring ("on" mode + override endpoint)

**Date:** 2026-06-30
**Estimated effort:** 1–1.5 days
**Priority:** High — closes the loop on the `b1c986c` plan-selection feature so `on` mode is more than a config flag, and the override is auditable.

---

## 0. ⚠️ REPO PATH WARNING

Backend lives at `/opt/flowmanner/backend/`. Verify with `pwd` — must print `/opt/flowmanner`.
**DO NOT** touch the frontend (`/home/glenn/FlowmannerV2-frontend/`). The frontend comparison UI (`da35f25`) is already wired; this task is backend-only.

## 1. Context — what's already shipped (do NOT rebuild)

Verified 2026-06-30 on `main`, four commits on `origin/main`:

| SHA | What it shipped |
|---|---|
| `b1c986c` | `app/services/plan_selection/` (4 modules, 737 lines), `MissionPlanCandidate` model + alembic migration, `BUDGET_AWARE_PLAN_SELECTION=off/on/auto` modes. Persists `tasks_json` (list-of-dicts, despite typed as `Mapped[dict]`) per candidate. 75 tests pass. **At plan time, `auto` mode auto-creates `MissionTask` rows from the winning candidate.** |
| `d973e3a` | `test_cost_aware_plan_selection_e2e.py` now asserts `plan_selected` event. |
| `f2ffdaa` | `GET /api/v2/missions/{id}/plan-candidates` (lists candidates, ordered by rank) + `PlanCandidateResponse` schema. |
| `da35f25` | Frontend `PlanComparison` component reads the candidate list and lets the user *see* the K candidates. **It does NOT yet let the user *pick* one and feed that choice into execution.** |

**What is missing (this task):**

- `select_plan_candidate` command handler (rebuilds `MissionTask` rows from a chosen `MissionPlanCandidate.tasks_json`)
- `selected_plan_id` field on `MissionExecuteRequest` (so callers can pass the pick at execute time without a separate round-trip)
- Inline hook inside `execute_mission._op` and `execute_async` to apply the rebuild before substrate execution
- A `POST /api/v2/missions/{id}/select-plan` endpoint for explicit pre-execution selection
- A `plan_override_selected` substrate event so audits / failure-analysis can tell "auto-pick" apart from "user picked differently"
- Tests covering the full round trip

## 2. Why this is small and safe

The substrate doesn't change. The schema doesn't change. Only three categories of edit:

1. **Add a field** to a Pydantic model (`extra="forbid"` so existing clients are unaffected).
2. **Add a module-level helper** + **one command method** that performs a transactional row swap (delete PENDING tasks → read `tasks_json` → insert new tasks). Pure ORM ops, no transactions invented.
3. **Wire a single call** into two existing `_op` blocks. Two lines of glue per executor.

No new columns, no migrations, no frontend work.

## 3. Files to touch

| File | Lines (current) | Change |
|------|-----------------|--------|
| `backend/app/schemas/mission.py` | 237 | Add `selected_plan_id: str \| None = None` to `MissionExecuteRequest` (line 132). Add new `SelectPlanCandidateRequest` schema with one field `plan_id: str` and `extra="forbid"`. |
| `backend/app/api/_mission_cqrs/commands.py` | 1065 | (a) module-level helper `_rebuild_tasks_from_candidate(session, mission_id, plan_id) -> list[MissionTask] \| None` after the imports (line ~73). (b) new command method `select_plan_candidate` near the existing `create_task`/`update_task` cluster (line ~313). (c) inline call to the helper inside `execute_mission._op` (line ~347) and `execute_async` (line ~460). |
| `backend/app/api/v2/missions.py` | 545 | Add `POST /api/v2/missions/{id}/select-plan` endpoint near `plan-candidates` GET (line ~227). Mirror the existing `idempotency()` + `rate_limit(...)` deps used by execute (lines 264-279). |
| `backend/app/api/v1/mission.py` | 234 | Add `POST /api/v1/missions/{id}/select-plan` endpoint for symmetry with `execute_mission` (line 208) and `execute_async` (line 228). |
| `backend/tests/test_plan_candidate_select.py` (new) | 0 → ~250 | Round-trip tests (see §6). |

Five files total. No new files in `app/services/`.

## 4. Detailed requirements

### 4.1 Schema — `backend/app/schemas/mission.py`

Add the new field to `MissionExecuteRequest`:

```python
selected_plan_id: str | None = None
```

Add new schema (place between `MissionExecuteRequest` and `MissionExecutionStatus`):

```python
class SelectPlanCandidateRequest(BaseModel):
    """Body for POST /api/v2/missions/{id}/select-plan.

    Lets a user pre-select a non-default candidate before execution.
    The chosen plan_id must match a row in mission_plan_candidates
    for the mission; otherwise 404.
    """

    model_config = ConfigDict(extra="forbid")

    plan_id: str
```

Do NOT change `PlanCandidateResponse`. Do NOT add fields to `MissionTaskResponse`.

### 4.2 Module-level helper — `_rebuild_tasks_from_candidate`

In `backend/app/api/_mission_cqrs/commands.py`, place after the `if TYPE_CHECKING:` block (around line 73) and before `class MissionCommandHandlers`.

```python
async def _rebuild_tasks_from_candidate(
    session: AsyncSession,
    mission_id: uuid.UUID,
    plan_id: str,
) -> list[MissionTask] | None:
    """Delete existing PENDING tasks for a mission and rebuild them from
    a MissionPlanCandidate.tasks_json row.  Returns the new task list, or
    None if no candidate row matched.

    Caller owns the transaction.  No commit() inside this function.
    """
    from app.models.mission_advanced_models import MissionPlanCandidate

    cand_row = (
        await session.execute(
            select(MissionPlanCandidate).where(
                MissionPlanCandidate.mission_id == str(mission_id),
                MissionPlanCandidate.plan_id == plan_id,
            )
        )
    ).scalars().first()
    if cand_row is None:
        return None

    task_defs = cand_row.tasks_json
    if not isinstance(task_defs, list):
        return None

    # Delete PENDING / QUEUED tasks only — preserve completed history.
    existing = await get_mission_tasks(session, mission_id)
    for t in existing:
        if t.status in (MissionTaskStatus.PENDING, MissionTaskStatus.QUEUED):
            await session.delete(t)
    await session.flush()

    new_tasks: list[MissionTask] = []
    for idx, task_def in enumerate(task_defs):
        if not isinstance(task_def, dict):
            continue
        new_task = MissionTask(
            id=str(uuid4()),
            mission_id=str(mission_id),
            title=task_def.get("title", f"Task {idx + 1}"),
            description=task_def.get("description", ""),
            task_type=task_def.get("task_type", "llm"),
            order_index=idx,
            dependencies=task_def.get("dependencies", []),
            input_data=task_def.get("input_data"),
            assigned_agent_id=task_def.get("assigned_agent_id"),
            assigned_model=task_def.get("assigned_model"),
            status=MissionTaskStatus.PENDING,
            max_retries=task_def.get("max_retries", 3),
        )
        session.add(new_task)
        new_tasks.append(new_task)
    await session.flush()
    return new_tasks
```

Two imports to add to the module top:

- `from uuid import uuid4` (it's already lazy-imported in `create_from_template`; module-level makes the helper cleaner)
- `SelectPlanCandidateRequest` from `app.schemas.mission` (alongside the existing `MissionExecuteRequest` import)
- `MissionTaskResponse` is NOT needed at the top — leave the schema imports alone unless you actually use it.

**DO NOT add `MissionTaskResponse` to the import block.** It was a mistake I made in a prior partial attempt — the helper returns `list[MissionTask]` (ORM), not `list[MissionTaskResponse]`. The caller (the command) does any DTO mapping.

### 4.3 New command — `select_plan_candidate`

In `MissionCommandHandlers`, add this method. Place it right after `update_task` (around line 313, near the existing Task cluster) so the diff stays in one zone.

```python
async def select_plan_candidate(
    self,
    user: User,
    mission_id: uuid.UUID,
    payload: SelectPlanCandidateRequest,
) -> list[MissionTaskResponse]:
    """Pre-select a non-default plan candidate. Rebuilds MissionTask
    rows from MissionPlanCandidate.tasks_json so the next execute call
    uses the chosen plan.  No-op execution-wise — the actual run is the
    caller's job.

    Returns 404 if no candidate matches. Wrapped in wrap_command() so
    the task rebuild is atomic with the plan_metadata bookkeeping.
    """
    await require_mission_access(self.session, mission_id, user.id)

    async def _op():
        # Verify candidate exists FIRST so callers get a clean 404,
        # not a half-rebuilt mission.
        cand_check = await _rebuild_tasks_from_candidate(
            self.session, mission_id, payload.plan_id
        )
        if cand_check is None:
            raise MissionNotFoundError(
                f"No plan candidate '{payload.plan_id}' for mission {mission_id}"
            )
        new_tasks = cand_check

        # Stash the override in mission.plan["plan_selection"] so
        # downstream tooling can tell auto-pick apart from explicit
        # user override.
        from app.models.mission_advanced_models import MissionPlanCandidate
        plan_meta = {}
        mission_row = (
            await self.session.execute(
                select(Mission).where(Mission.id == str(mission_id))
            )
        ).scalars().first()
        if mission_row is not None and isinstance(mission_row.plan, dict):
            plan_meta = dict(mission_row.plan)
        plan_meta.setdefault("plan_selection", {})
        plan_meta["plan_selection"]["override_id"] = payload.plan_id
        if mission_row is not None:
            mission_row.plan = plan_meta

        # Emit plan_override_selected substrate event (best-effort).
        try:
            from app.models.substrate_models import SubstrateEventType
            from app.services.substrate.event_log import get_event_log
            await get_event_log().append(
                self.session,
                str(mission_id),
                [{
                    "type": SubstrateEventType.PLAN_OVERRIDE_SELECTED,
                    "payload": {
                        "override_id": payload.plan_id,
                        "actor_id": str(user.id),
                        "task_count": len(new_tasks),
                    },
                    "actor": "user",
                    "mission_id": str(mission_id),
                }],
            )
        except Exception as ev_err:
            logger.debug("plan_override_selected_event_failed: %s", ev_err)

        # Audit log (best-effort, like the rest of the command handlers).
        if self.audit is not None:
            self.audit.mission_updated(
                mission_id=mission_id,
                actor_id=user.id,
                old_status="select_plan_candidate",
                new_status="select_plan_candidate",
                request_id=self._request_id,
                override_plan_id=payload.plan_id,
                task_count=len(new_tasks),
            )

        _schedule_fire_and_forget(
            invalidate_mission_cache(user.id, str(mission_id))
        )
        return new_tasks

    tasks = await self.wrap_command(_op)
    return [MissionTaskResponse.model_validate(t) for t in tasks]
```

### 4.4 Inline hook — `execute_mission._op` and `execute_async._op`

**execute_mission (around line 347):** Right after `tasks = await get_mission_tasks(...)`, insert a conditional rebuild. But cleaner is to swap the **first** `get_mission_tasks` call for a helper that does the rebuild first if needed. Use a tiny inline block instead of refactoring — keep the diff small:

Insertion point: line 347, immediately **before** `tasks = await get_mission_tasks(self.session, mission_id)`:

```python
            # Round-trip: honor MissionExecuteRequest.selected_plan_id
            # by rebuilding the task list from the chosen candidate
            # before the substrate UnifiedExecutor runs.  An unknown
            # plan_id is logged + skipped (we never fail execution
            # because of a missing override).
            if payload is not None and getattr(payload, "selected_plan_id", None):
                rebuilt = await _rebuild_tasks_from_candidate(
                    self.session, mission_id, payload.selected_plan_id
                )
                if rebuilt is None:
                    logger.warning(
                        "execute_mission_selected_plan_id_not_found",
                        mission_id=str(mission_id),
                        selected_plan_id=payload.selected_plan_id,
                    )
                else:
                    tasks = rebuilt
```

**execute_async (around line 532):** Same pattern. Insertion: same offset relative to the `tasks = await get_mission_tasks(...)` call inside `execute_async`. Note `execute_async` is multi-commit, so the rebuild should happen **inside the FIRST sync block, before the status commit at line ~569**, so the Celery worker that runs later sees the rebuilt tasks. Specifically: right after `require_mission_access(self.session, mission_id, user.id)` and before `limit_check = await check_mission_execute_allowed(...)`.

The inline for `execute_async` is:

```python
        # Round-trip hook — accept selected_plan_id so the Celery worker
        # dispatches against the rebuilt task list.  Unknown IDs log and
        # fall through.
        if payload is not None and getattr(payload, "selected_plan_id", None):
            rebuilt = await _rebuild_tasks_from_candidate(
                self.session, mission_id, payload.selected_plan_id
            )
            if rebuilt is None:
                logger.warning(
                    "execute_async_selected_plan_id_not_found",
                    mission_id=str(mission_id),
                    selected_plan_id=payload.selected_plan_id,
                )
```

If the rebuild succeeds, it commits as part of `await self.session.commit()` at line ~569 (the QUEUED commit). The Celery task will then `get_mission_tasks` and see the new list. If the rebuild fails (candidate missing), the original task list stays intact.

### 4.5 Add `PLAN_OVERRIDE_SELECTED` to `SubstrateEventType`

In `backend/app/models/substrate_models.py`, alongside `PLAN_SELECTED = "plan.selected"` (line ~140), add:

```python
PLAN_OVERRIDE_SELECTED = "plan.override_selected"
```

The existing `event_log.append()` will accept strings — no enum widening needed in the event log itself.

### 4.6 Endpoint — `POST /api/v2/missions/{id}/select-plan`

In `backend/app/api/v2/missions.py`, place immediately after the existing `list_plan_candidates` GET (line ~227). Mirror the execute endpoint's dependency set.

```python
@router.post("/{mission_id}/select-plan")
async def select_plan_candidate(
    mission_id: uuid.UUID,
    payload: SelectPlanCandidateRequest,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
    _idem: Any = Depends(idempotency()),
    _rate: Any = Depends(rate_limit("mission:plan_select")),
):
    """Pre-select a non-default plan candidate. Rebuilds the mission's
    task list from the chosen candidate's tasks_json.  The actual
    execution happens via the existing execute / execute-async
    endpoints — this just stages the choice.

    POST body: ``{"plan_id": "heuristic_v1"}``
    Returns: ``[MissionTaskResponse]`` — the rebuilt task list.
    """
    if isinstance(_idem, JSONResponse):
        return _idem
    if isinstance(_rate, JSONResponse):
        return _rate
    tasks = await c.select_plan_candidate(user, mission_id, payload)
    return ok([t.model_dump() for t in tasks])
```

Imports — add to the top of `app/api/v2/missions.py`:

```python
from app.schemas.mission import SelectPlanCandidateRequest
```

(Assuming it's not already there. If not, slot it into the existing `from app.schemas.mission import (...)` block alphabetically.)

### 4.7 Endpoint — `POST /api/v1/missions/{id}/select-plan`

In `backend/app/api/v1/mission.py`, immediately after `execute_mission_async` (line ~234):

```python
@router.post("/{mission_id}/select-plan")
async def select_plan_candidate(
    mission_id: uuid.UUID,
    payload: SelectPlanCandidateRequest,
    user: User = Depends(get_current_user),
    c: MissionCommandHandlers = Depends(get_mission_commands),
):
    """Pre-select a non-default plan candidate. v1 mirror of v2 route."""
    tasks = await c.select_plan_candidate(user, mission_id, payload)
    return [t.model_dump() for t in tasks]
```

(Verify whether v1 uses `Depends(idempotency())` and `Depends(rate_limit(...))` on its mutation routes. If yes, mirror them. If no, do NOT add — keeping v1 in lockstep with its current convention.)

Imports — add `SelectPlanCandidateRequest` to the existing v1 import.

## 5. Constraints (HARD)

1. **Working tree must be clean before you start.** Run `git status` and confirm only the `docs/EXIT-AUDIT-2026-06-30-ruff-lint-cleanup.md` untracked file remains. If anything else is dirty, STOP and report.
2. **No new tables, no migrations.** The `mission_plan_candidates` table already exists (`b1c986c` migration).
3. **No frontend touch.** Frontend comparison UI (`da35f25`) is shipped. Do NOT enhance it for "pre-select" — that's a separate UI ticket.
4. **`off` mode behavior unchanged.** Your patches to `execute_mission._op` / `execute_async` are conditional on `payload.selected_plan_id` being set; if the client sends the existing `MissionExecuteRequest{ model_preference: "..." }` shape, behavior is byte-for-byte identical to today.
5. **`extra="forbid"` already on `MissionExecuteRequest`.** Adding `selected_plan_id` is opt-in. Existing clients that don't send it get `None` from `model_validate` and the rebuild branch is skipped.
6. **Transaction discipline.** `_rebuild_tasks_from_candidate` does NOT commit. The caller (the command's `wrap_command()`) owns the commit. For `execute_async`, the rebuild happens before the explicit `await self.session.commit()` at line ~569 — that single commit groups rebuild + status transition atomically.
7. **Unknown plan_id is logged, never raised.** Both inline hooks in `execute_mission._op` / `execute_async` log a `warning` and fall through. The dedicated `select_plan_candidate` command IS allowed to raise (404 → `MissionNotFoundError`) because the endpoint is reserved for explicit pre-selection.
8. **No `import app.models.mission_advanced_models` at module top.** Lazy import inside the helper — it avoids a circular risk that already exists with several other CQRS files. Match the existing pattern.
9. **No `import app.services.substrate.event_log` at module top.** Lazy import inside the command — same reasoning.
10. **Pre-commit hooks MUST pass.** Per memory: run `pre-commit run --files <list>` on each touched file before committing. Do NOT use `--no-verify`.
11. **No `db.commit()` from `app.api._mission_cqrs.commands` outside `wrap_command()`.** Match the existing pattern verified in `app/api/_mission_cqrs/AGENTS.md` §2 and §3 of that file.
12. **Delete-PENDING-only.** The helper must only delete tasks with status `PENDING` or `QUEUED`. Never delete `COMPLETED` / `RUNNING` / `FAILED` — preserve audit history even if a user changes their mind mid-execution.

## 6. Tests — required deliverables

New file: `backend/tests/test_plan_candidate_select.py`. Tests must:

1. Use `tests/`-style mocks (per the pattern in `test_h1_3_observability_abort.py` and `test_cost_aware_plan_selection_e2e.py`). No real DB.
2. Run in <30s combined.
3. NOT call any external LLM (mock the route or skip the codepath).

### Test cases

| # | Name | What it verifies |
|---|------|------------------|
| 1 | `test_schema_field_optional` | `MissionExecuteRequest.model_validate({})` → `selected_plan_id is None`. `model_validate({"selected_plan_id": "heuristic_v1"})` → field set. |
| 2 | `test_select_plan_request_rejects_unknown_field` | `SelectPlanCandidateRequest.model_validate({"plan_id": "x", "bogus": 1})` → raises ValidationError (`extra="forbid"`). |
| 3 | `test_rebuild_helper_unknown_candidate_returns_none` | `_rebuild_tasks_from_candidate(mock_session, mid, "missing")` → `None`. No `session.add` / `session.delete` called. |
| 4 | `test_rebuild_helper_replaces_pending_tasks_only` | Mock `get_mission_tasks` to return one PENDING + one COMPLETED + one RUNNING task. Verify only the PENDING is `session.delete`d. Verify the COMPLETED and RUNNING are untouched. |
| 5 | `test_rebuild_helper_creates_tasks_from_candidate` | Provide a candidate `tasks_json` of 3 dicts. Verify exactly 3 `MissionTask` `session.add()` calls with the right `order_index` and `title` fields. |
| 6 | `test_select_plan_candidate_command_404_on_missing` | Call `select_plan_candidate` with `plan_id="missing"`. Expect `MissionNotFoundError` raised by the command. No audit fired. (The endpoint maps this to HTTP 404 via the existing error handler.) |
| 7 | `test_select_plan_candidate_command_success` | Set up mock candidate + mock get_mission_tasks (returns 2 PENDING old tasks) + mock wrap_command context. Verify: rebuild invoked, plan_metadata override_id set, audit fired with `override_plan_id` meta, substrate event appended, cache invalidated. Verify returned list is `list[MissionTaskResponse]` shape. |
| 8 | `test_execute_mission_inline_unknown_plan_id_no_crash` | Patch `MissionExecuteRequest` with `selected_plan_id="missing"`. Verify the warning is logged and execution proceeds with the original task list (the helper returns `None`). |
| 9 | `test_execute_mission_inline_rebuild_before_substrate` | Patch `MissionExecuteRequest` with `selected_plan_id="heuristic_v1"` and verify `_rebuild_tasks_from_candidate` is awaited before `get_unified_executor().execute()`. Use mock ordering checks (call_args_list). |
| 10 | `test_execute_async_rebuild_before_status_commit` | Verify rebuild happens before `await self.session.commit()` (line ~569) so the Celery worker sees the new tasks. |

### Tests updates to existing files

- `backend/tests/test_cost_aware_plan_selection_e2e.py`: add 1 case that calls `commands.select_plan_candidate` end-to-end with a mocked candidate, asserts tasks rebuilt and `mission.plan["plan_selection"]["override_id"]` set.
- `backend/app/tests/test_mission_planner.py`: NO changes. Selection is a planner-time concern; this task is execute-time round-tripping.

## 7. Backend verification (must run, must pass, paste output in handoff)

```bash
cd /opt/flowmanner/backend

# 1. Lint (all files you touched + all new files)
ruff check app/schemas/mission.py app/api/_mission_cqrs/commands.py app/api/v2/missions.py app/api/v1/mission.py app/models/substrate_models.py tests/test_plan_candidate_select.py

# 2. Format
ruff format --check app/schemas/mission.py app/api/_mission_cqrs/commands.py app/api/v2/missions.py app/api/v1/mission.py app/models/substrate_models.py tests/test_plan_candidate_select.py

# 3. Pre-commit (required — matches project memory rule)
pre-commit run --files \
  backend/app/schemas/mission.py \
  backend/app/api/_mission_cqrs/commands.py \
  backend/app/api/v2/missions.py \
  backend/app/api/v1/mission.py \
  backend/app/models/substrate_models.py \
  backend/tests/test_plan_candidate_select.py

# 4. Tests
pytest -xvs tests/test_plan_candidate_select.py tests/test_cost_aware_plan_selection_e2e.py
```

All must exit 0. Save the full output to `/tmp/deepseek-plan-candidate-round-trip-verify.txt`.

Run one combined-merge sanity test — make sure the existing 75 plan-selection tests still pass:

```bash
pytest -x tests/test_plan_candidate.py tests/test_plan_scorer.py tests/test_plan_selector.py tests/test_plan_generator.py tests/test_cost_aware_plan_selection_e2e.py tests/test_plan_candidate_select.py app/tests/test_mission_planner.py
```

Expect: 75 prior tests still pass + new round-trip tests pass.

## 8. Hand-off format

Write to `.sisyphus/handoffs/exit-audit-2026-06-30-plan-candidate-round-trip.md`:

1. **What changed** — file-by-file diff summary.
2. **Verification output** — paste `/tmp/deepseek-plan-candidate-round-trip-verify.txt`.
3. **Backward-compat table** — one row per public route that you touched, showing the request shape before vs. after (it MUST be byte-for-byte identical unless `selected_plan_id` is sent).
4. **Demo flow** —
   - Set `BUDGET_AWARE_PLAN_SELECTION=on` in `.env`.
   - `POST /api/v2/missions/{id}/select-plan` body `{"plan_id": "heuristic_v1"}` → 200 + task list.
   - `POST /api/v2/missions/{id}/execute` body `{"model_preference": "..."}` → existing execute path.
   - `GET /api/v2/missions/{id}/plan-candidates` → still ranks 1..N.
   - Or skip the explicit select, send `{"model_preference": "...", "selected_plan_id": "llm_persona_b"}` directly to `execute` → round-trip fires inline.
5. **What is NOT done** — explicitly say "no frontend change, no migration, no new tables."
6. **What I am unsure about** — if anything, document with the test output verbatim.

## 9. Stop-the-line rules

- **If `wrap_command()` pattern doesn't fit cleanly** for any reason (e.g., the rebuild needs to commit between two async operations), STOP and document the exact blocker. Do not invent a parallel `async with` transaction path. Note in `app/api/_mission_cqrs/AGENTS.md` §3 that the rebuild is "explicit multi-commit" if needed.
- **If `execute_async`'s rebuild-before-commit requires a `db.flush()` that's not already in the existing flow**, STOP. The current `execute_async` has a single explicit `await self.session.commit()` after the rebuild point — preserve that boundary.
- **If `MissionPlanCandidate.tasks_json` is stored as `dict` but the planner inserts a `list`**, the migration is already shipped and the column is `JSONB`. Postgres stores the actual JSON shape regardless of ORM typing. Just keep storing/consuming `list` and silently accept the Mypy false-positive (already present and not your problem to fix this round). Do NOT touch the model type.
- **If pre-commit fails on something you don't recognize** (e.g., a mypy error in an unrelated file), STOP and paste the full pre-commit log in the handoff. Do NOT `git commit --no-verify`.
- **If the `extra="forbid"` model_config on `MissionExecuteRequest` already rejects `selected_plan_id`** because of a stale pickled copy or something, STOP — that's not the case as of HEAD, but if it is, document and don't fight it.

## 10. What "done" means

- All 4 verification commands in §7 exit 0.
- Handoff written to `.sisyphus/handoffs/exit-audit-2026-06-30-plan-candidate-round-trip.md`.
- Working tree has ONLY your commit's changes plus the pre-existing untracked `docs/EXIT-AUDIT-2026-06-30-ruff-lint-cleanup.md` audit.
- **You do NOT commit.** Per `AGENTS.md` session ritual: Glenn reviews and Hermes commits. Stop at the handoff.
- **You do NOT touch the docs/EXIT-AUDIT-2026-06-30-ruff-lint-cleanup.md file** in any way. That is a separate prior-session artifact and is not in scope.
