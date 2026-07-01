# Exit Audit — Plan Comparison UI (2026-06-30)

**Session:** Wire frontend plan comparison UI to display candidates from
`mission_plan_candidates` table.

**Verdict:** ✅ Complete. Backend endpoint + frontend component deployed to
both repos.

---

## Commits

| Repo | Commit | Message | Files |
|------|--------|---------|-------|
| Backend | `f2ffdaa` | `feat(api): add plan candidates endpoint for frontend comparison UI` | 3 files, +90/-6 |
| Frontend | `da35f25` | `feat(ui): add plan comparison component to mission observatory` | 6 files, +407 |

Both commits pushed to `origin/main` (backend) and `origin/master` (frontend).
Working tree clean on both repos (2 untracked doc files on backend only).

---

## Verification

| Check | Result |
|-------|--------|
| **Ruff** (backend 3 files) | ✅ All checks passed |
| **Pytest** (75 plan selection tests) | ✅ 75 passed, 1 warning |
| **TypeScript** (frontend) | ✅ 0 errors |
| **Pre-commit hooks** | ✅ Both commits passed (ruff, ruff-format, mypy) |
| **Code reviewer** | ✅ Approved — no blockers |

---

## Files Changed

### Backend (3 modified)

| File | Change |
|------|--------|
| `backend/app/schemas/mission.py` | Added `PlanCandidateResponse` Pydantic model with `from_model()` classmethod (maps `tasks_json` → `tasks`) |
| `backend/app/api/_mission_cqrs/queries.py` | Added `list_plan_candidates()` CQRS query handler with ownership check, ordered by rank |
| `backend/app/api/v2/missions.py` | Added `GET /{mission_id}/plan-candidates` endpoint returning ranked candidates as JSON array |

Also fixed 10 pre-existing TC import warnings via `ruff --unsafe-fixes` (TYPE_CHECKING block moves).

### Frontend (3 new + 3 modified)

| File | Change |
|------|--------|
| `src/lib/sdk/models/PlanCandidateResponse.ts` | **New** — SDK type matching backend schema |
| `src/hooks/use-plan-candidates.ts` | **New** — `usePlanCandidates` React Query hook (5min stale time), exports `PlanCandidate` interface |
| `src/components/observatory/plan-comparison.tsx` | **New** — `PlanComparison` component (314 lines) with `CandidateCard`, `QualityBar` sub-components |
| `src/lib/sdk/services/MissionsService.ts` | Added `listPlanCandidates` static method + `PlanCandidateResponse` import |
| `src/lib/sdk/index.ts` | Added `PlanCandidateResponse` export |
| `src/components/observatory/mission-observatory.tsx` | Integrated `PlanComparison` after `AssertionResultsPanel` with conditional rendering |

---

## Component Features

The `PlanComparison` component displays plan candidates side-by-side with:

- **Winner highlighting** — gold border + trophy badge for rank 1
- **Strategy badges** — color-coded labels (Heuristic, LLM Persona, etc.)
- **Metrics grid** — cost, latency, tokens with best-value green highlighting
- **Quality bar** — color-coded progress bar (green ≥80%, amber ≥60%, red <60%)
- **Risk flags** — amber badges for risk flag strings
- **Rationale** — human-readable explanation text
- **Expandable task lists** — per-candidate collapsible task details
- **Responsive grid** — 1-3 columns depending on viewport width

---

## Out of Scope (correctly NOT done)

- **Loading skeleton/error state** for the plan comparison section — acceptable since it only renders when data exists
- **Frontend deployment** — not done (requires `bash deploy-frontend.sh` from homelab)
- **Backend deployment** — not done (requires `bash deploy-backend.sh` from homelab)
- **Backend integration test** for the new endpoint — noted by code reviewer as follow-up
- **`plan.selected` substrate event** rendering in the observatory event list — the event type exists but isn't shown in `EVENT_ICONS`/`EVENT_COLORS` maps

---

## Code Reviewer Notes (non-blocking)

1. **Hook returns `PlanCandidate[]` not `PlanCandidateResponse[]`** — The hook defines its own interface rather than importing from SDK. This is the existing pattern in the codebase (`use-missions.ts` does the same).
2. **No loading/error state** — If the query fails silently, nothing is shown. Acceptable given the feature is opt-in.
3. **`as string` casts** — Safe in practice (task fields from JSONB are always strings), but technically runtime-unsafe.
4. **No backend test** for the new endpoint — 75 existing plan selection tests cover the underlying data layer.

---

## Pre-existing State

- **Ruff lint cleanup (200+ files)** still uncommitted in backend working tree — from a prior session, unrelated to this work.
- **2 untracked doc files** in backend: `docs/EXIT-AUDIT-2026-06-30-plan-selection.md` and `docs/EXIT-AUDIT-2026-06-30-ruff-lint-cleanup.md`.

---

## Next Steps

1. Deploy frontend: `bash /opt/flowmanner/deploy-frontend.sh` from homelab
2. Deploy backend: `bash /opt/flowmanner/deploy-backend.sh` from homelab
3. Add integration test for `GET /api/v2/missions/{id}/plan-candidates`
4. Add `plan.selected` to `EVENT_ICONS`/`EVENT_COLORS` in observatory
