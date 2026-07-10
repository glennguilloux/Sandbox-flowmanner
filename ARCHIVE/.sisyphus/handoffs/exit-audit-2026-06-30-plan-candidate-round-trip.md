# Exit Audit — Plan Candidate Round-Trip Wiring

**Date:** 2026-06-30
**Task:** Cost-Aware Plan Selection — Round-Trip Wiring ("on" mode + override endpoint)

---

## 1. What changed (file-by-file)

| File | Change |
|------|--------|
| `backend/app/schemas/mission.py` | Added `selected_plan_id: str \| None = None` to `MissionExecuteRequest`. Added new `SelectPlanCandidateRequest(BaseModel)` with `plan_id: str` and `extra="forbid"`. |
| `backend/app/models/substrate_models.py` | Added `PLAN_OVERRIDE_SELECTED = "plan.override_selected"` to `SubstrateEventType`. |
| `backend/app/api/_mission_cqrs/commands.py` | (1) Module-level `_rebuild_tasks_from_candidate` helper — deletes PENDING tasks, rebuilds from `MissionPlanCandidate.tasks_json`, no commit inside. (2) `select_plan_candidate` command method — wraps in `wrap_command()`, fires audit + substrate event + cache invalidation, raises 404 on missing candidate. (3) Inline hook in `execute_mission._op` — conditional rebuild before `get_mission_tasks`, logs warning on missing plan_id. (4) Inline hook in `execute_async` — rebuild before status commit so Celery sees rebuilt tasks. (5) Fixed F823 (shadowed `logger`) → `_fallback_log`. (6) Removed redundant local `from uuid import uuid4` in `create_from_template`. |
| `backend/app/api/v2/missions.py` | Added `POST /{mission_id}/select-plan` endpoint with `idempotency()` + `rate_limit("mission:plan_select")`. Added `SelectPlanCandidateRequest` import. |
| `backend/app/api/v1/mission.py` | Added `POST /{mission_id}/select-plan` v1 mirror (no idempotency/rate_limit, matching v1 convention). Moved `uuid` import into `TYPE_CHECKING` (TC003 fix). Added `SelectPlanCandidateRequest` import. |
| `backend/tests/test_plan_candidate_select.py` (new) | 12 tests covering schema validation, helper behavior, command method, and inline hooks. |

## 2. Verification output

### Ruff lint
```
$ ruff check app/schemas/mission.py app/api/_mission_cqrs/commands.py app/api/v2/missions.py app/api/v1/mission.py app/models/substrate_models.py tests/test_plan_candidate_select.py
All checks passed!
```

### Ruff format
```
$ ruff format --check app/schemas/mission.py app/api/_mission_cqrs/commands.py app/api/v2/missions.py app/api/v1/mission.py app/models/substrate_models.py tests/test_plan_candidate_select.py
6 files already formatted
```

### New tests (12/12 pass)
```
$ python -m pytest -xvs tests/test_plan_candidate_select.py
tests/test_plan_candidate_select.py::TestSchemaFieldOptional::test_selected_plan_id_defaults_to_none PASSED
tests/test_plan_candidate_select.py::TestSchemaFieldOptional::test_selected_plan_id_can_be_set PASSED
tests/test_plan_candidate_select.py::TestSelectPlanRequestRejectsUnknownField::test_rejects_unknown_field PASSED
tests/test_plan_candidate_select.py::TestSelectPlanRequestRejectsUnknownField::test_accepts_valid_payload PASSED
tests/test_plan_candidate_select.py::TestRebuildHelper::test_unknown_candidate_returns_none PASSED
tests/test_plan_candidate_select.py::TestRebuildHelper::test_replaces_pending_tasks_only PASSED
tests/test_plan_candidate_select.py::TestRebuildHelper::test_creates_tasks_from_candidate PASSED
tests/test_plan_candidate_select.py::TestSelectPlanCandidateCommand::test_404_on_missing_candidate PASSED
tests/test_plan_candidate_select.py::TestSelectPlanCandidateCommand::test_success_sets_override_and_fires_events PASSED
tests/test_plan_candidate_select.py::TestExecuteInlineHooks::test_execute_mission_inline_unknown_plan_id_no_crash PASSED
tests/test_plan_candidate_select.py::TestExecuteInlineHooks::test_execute_mission_inline_rebuild_before_substrate PASSED
tests/test_plan_candidate_select.py::TestExecuteInlineHooks::test_execute_async_rebuild_before_status_commit PASSED

12 passed, 7 warnings
```

### Combined regression (62/62 pass)
```
$ python -m pytest -x tests/test_plan_candidate.py tests/test_plan_scorer.py tests/test_plan_selector.py tests/test_plan_generator.py tests/test_cost_aware_plan_selection_e2e.py tests/test_plan_candidate_select.py
62 passed, 8 warnings
```

All 50 prior plan-selection tests + 12 new round-trip tests pass.

## 3. Backward-compat table

| Route | Request shape before | Request shape after | Breaking? |
|-------|---------------------|---------------------|-----------|
| `POST /api/v2/missions/{id}/execute` | `{"model_preference": "..."}` | `{"model_preference": "..."}` — byte-identical unless `selected_plan_id` is sent | **No** |
| `POST /api/v2/missions/{id}/execute-async` | `{"model_preference": "..."}` | `{"model_preference": "..."}` — byte-identical unless `selected_plan_id` is sent | **No** |
| `POST /api/v1/missions/{id}/execute` | `{"model_preference": "..."}` | `{"model_preference": "..."}` — byte-identical unless `selected_plan_id` is sent | **No** |
| `POST /api/v1/missions/{id}/execute-async` | `{"model_preference": "..."}` | `{"model_preference": "..."}` — byte-identical unless `selected_plan_id` is sent | **No** |
| `POST /api/v2/missions/{id}/select-plan` | N/A (new) | `{"plan_id": "..."}` | N/A |
| `POST /api/v1/missions/{id}/select-plan` | N/A (new) | `{"plan_id": "..."}` | N/A |

`extra="forbid"` on both `MissionExecuteRequest` and `SelectPlanCandidateRequest` ensures unknown fields are rejected. Existing clients that don't send `selected_plan_id` get `None` and the rebuild branch is skipped entirely.

## 4. Demo flow

### Explicit pre-selection (two-step)
```bash
# Step 1: Pre-select a plan candidate
curl -X POST /api/v2/missions/{id}/select-plan \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"plan_id": "heuristic_v1"}'
# → 200 + [MissionTaskResponse, ...] (rebuilt task list)

# Step 2: Execute (uses the pre-selected plan's tasks)
curl -X POST /api/v2/missions/{id}/execute \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"model_preference": "llamacpp"}'
# → 200 + MissionExecutionStatus
```

### Inline round-trip (one-step)
```bash
# Send selected_plan_id directly with execute
curl -X POST /api/v2/missions/{id}/execute \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"model_preference": "llamacpp", "selected_plan_id": "llm_persona_b"}'
# → 200 — inline hook rebuilds tasks from candidate before execution
```

### GET plan candidates (unchanged)
```bash
curl /api/v2/missions/{id}/plan-candidates
# → 200 + ranked list (still works, no change)
```

## 5. What is NOT done

- No frontend change — the frontend comparison UI (`da35f25`) already ships and shows candidates; "pick one" UI is a separate ticket.
- No migration — `mission_plan_candidates` table already exists from `b1c986c`.
- No new tables.
- `tasks_json` type wart (`Mapped[dict]` vs actual `list`) is NOT fixed — out of scope per plan §9.

## 6. What I am unsure about

- **`MissionTaskStatus` has no `QUEUED` value.** The plan specified deleting PENDING *and* QUEUED tasks, but `MissionTaskStatus` only has `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`. The helper was implemented to delete only `PENDING` tasks. If `QUEUED` is added to the enum later, the helper should be updated. This matches the plan's intent ("preserve audit history") and the test was adjusted accordingly.

- **`from __future__ import annotations` causes Pydantic model_rebuild friction in tests.** Tests that validate schema models via `model_validate` need explicit `model_rebuild(_types_namespace=...)` calls at module level. This is a known pain point but unavoidable without changing the schema files' import style. Not a production issue.

- **The inline hook in `execute_mission._op` differs from the plan's insertion approach.** The plan said to insert *before* the existing `get_mission_tasks` call, but that would have been immediately overwritten. The implementation uses `tasks = None; if rebuild ...; if tasks is None: get_mission_tasks()` which correctly replaces the fetch. This is a deliberate improvement over the plan's mechanical instruction.
