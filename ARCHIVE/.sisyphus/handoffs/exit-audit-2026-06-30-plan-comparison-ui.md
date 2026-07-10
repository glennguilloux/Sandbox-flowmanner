# Handoff — Plan Comparison UI (2026-06-30)

## Session Summary

Implemented the frontend plan comparison UI to display K-plan candidates from
the `mission_plan_candidates` table in the mission observatory view. Two
commits across two repos.

## WHAT CHANGED

**Backend (`f2ffdaa` on `origin/main`):**
- `backend/app/schemas/mission.py` — Added `PlanCandidateResponse` Pydantic
  model with `from_model()` classmethod mapping `tasks_json` → `tasks`
- `backend/app/api/_mission_cqrs/queries.py` — Added `list_plan_candidates()`
  CQRS query handler with ownership check, ordered by rank
- `backend/app/api/v2/missions.py` — Added `GET /{mission_id}/plan-candidates`
  endpoint returning ranked candidates as JSON array
- Also fixed 10 pre-existing TC import warnings via `ruff --unsafe-fixes`

**Frontend (`da35f25` on `origin/master`):**
- `src/lib/sdk/models/PlanCandidateResponse.ts` — **New** SDK type
- `src/hooks/use-plan-candidates.ts` — **New** `usePlanCandidates` React Query
  hook (5min stale time), exports `PlanCandidate` interface
- `src/components/observatory/plan-comparison.tsx` — **New** `PlanComparison`
  component (314 lines) with `CandidateCard`, `QualityBar` sub-components,
  winner highlighting, strategy badges, metrics grid, risk flags, expandable
  task lists
- `src/lib/sdk/services/MissionsService.ts` — Added `listPlanCandidates`
  static method + import
- `src/lib/sdk/index.ts` — Added `PlanCandidateResponse` export
- `src/components/observatory/mission-observatory.tsx` — Integrated
  `PlanComparison` after `AssertionResultsPanel` with conditional rendering

## WHAT DID NOT CHANGE BUT WAS TOUCHED

- `backend/app/schemas/mission.py` — pre-existing TC import warnings were
  auto-fixed by `ruff --unsafe-fixes` (TYPE_CHECKING block moves for `uuid`,
  `datetime`, `MissionStatus`, `MissionTaskStatus`). These were pre-existing,
  not introduced by this session.

## TESTS RUN + RESULT

```
75 passed, 1 warning in 10.87 seconds
(UserWarning: Qdrant client/server version mismatch — pre-existing)
```

```
Ruff: All checks passed!
TypeScript: 0 errors
Pre-commit hooks: both commits passed (ruff, ruff-format, mypy)
```

## Raw Status Output

### Backend (`/opt/flowmanner`)

```
$ git status
On branch main
Your branch is up to date with 'origin/main'.

Untracked files:
  docs/EXIT-AUDIT-2026-06-30-plan-comparison-ui.md
  docs/EXIT-AUDIT-2026-06-30-plan-selection.md
  docs/EXIT-AUDIT-2026-06-30-ruff-lint-cleanup.md
```

```
$ git fetch origin && git log --oneline origin/main..main
(no output — fully synced)
```

### Frontend (`/home/glenn/FlowmannerV2-frontend`)

```
$ git status
On branch master
Your branch is up to date with 'origin/master'.
nothing to commit, working tree clean
```

```
$ git fetch origin && git log --oneline origin/master..master
(no output — fully synced)
```

## Next Session Handoff

Both repos are synced with origin. The plan comparison UI feature is complete
and pushed but **not yet deployed** — both the frontend and backend need to be
deployed from homelab (`bash deploy-frontend.sh` and `bash deploy-backend.sh`).
The 200+ file ruff lint cleanup from a prior session remains uncommitted in the
backend working tree. Three untracked exit audit docs in `docs/` are ready to
be committed. Code reviewer noted one follow-up: no integration test for the
new `GET /api/v2/missions/{id}/plan-candidates` endpoint. The `plan.selected`
substrate event type exists in the backend but isn't rendered in the observatory
`EVENT_ICONS`/`EVENT_COLORS` maps — worth adding when the event bus analytics
feature lands.

## Files Untouched

- `docs/EXIT-AUDIT-2026-06-30-plan-selection.md` — untracked, from prior session
- `docs/EXIT-AUDIT-2026-06-30-ruff-lint-cleanup.md` — untracked, from prior session
- All 200+ ruff-cleanup files in backend working tree — from prior session, unstaged
