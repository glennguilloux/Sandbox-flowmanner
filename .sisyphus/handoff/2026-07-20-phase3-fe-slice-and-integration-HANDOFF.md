# Handoff — Phase 3 Chat Control Plane: FE slice complete + backend integration merge

**Date:** 2026-07-20
**Author:** Hermes coding agent (session driven by Glenn)
**Plan:** `.sisyphus/plans/chat-panel-control-plane-PLAN.md`
**Prior handoff:** `.sisyphus/handoff/2026-07-20-phase3-chat-control-plane-HANDOFF.md`

> This continues the prior Phase 3 handoff. That one left the backend done on
> two isolated branches and the **frontend slice NOT STARTED** as the sole
> blocker for the Phase 3 success gate. This session: built the FE slice,
> fixed a latent Phase-2 provenance bug, and integrated the two backend
> branches into one merge branch. **Nothing pushed / merged to main / deployed
> — all work sits on review branches awaiting Glenn's go.**

---

## 1. Where things stand (summary)

| Slice | Status | Branch | HEAD | Verify |
|-------|--------|--------|------|--------|
| Backend graph promotion | ✅ done (prior session) | `wt/be-phase3-graph-20260720` | `fa50cb30` | 3 tests |
| Backend fork-a-run | ✅ done (prior session) | `wt/be-phase3-fork-20260720` | `9b35651c` | 3 tests |
| **Backend integration merge** | ✅ **done this session** | `wt/be-phase3-merge-20260720` | `4f9716b0` | ruff clean, import OK, 6/6 tests |
| **FE graph renderer + fork UI** | ✅ **done this session** | `wt/fe-phase3-graph-fork-20260720` | `08923d0d` | tsc clean |
| **FE provenance bug fix** | ✅ **done this session** | same FE branch | `0a63d9e0` (tip) | tsc clean |
| Push / merge-to-main / deploy | ⛔ deliberately NOT done (review gate) | — | — | — |

**Phase 3 success gate** (plan §3, "user forks a completed run from a mid-step
edit; the graph / fork is reflected"): **backend + frontend now both
implemented and verified.** The gate is code-complete; only merge + deploy
remain, both gated on Glenn's review.

---

## 2. What was built / fixed this session

### 2.1 FE graph renderer + fork UI (commit `08923d0d`)

Built by a single delegated worker into one branch (both slices, sequential,
to avoid the 3-file collision that parallel workers would cause). Files:

1. **`src/lib/chat-types.ts`** (+28 lines)
   - Added `RunGraphNode { id, title, status }`, `RunGraphEdge { source,
     target, taken, condition?, label? }`, `RunGraph { workflow_type, nodes,
     edges }` in the Phase 3 types section.
   - Added `graph?: RunGraph | null` field to `RunState`.
2. **`src/components/chat/RunActivityStream.tsx`** (+234 lines)
   - **Graph section** (terminal runs only): lazy `fetchGraph()` → `GET
     /api/v2/runs/{runId}/graph`, stashed via `patchRun(runId, {graph})`.
     Renders nodes with status icons; renders edges `source → target` with
     `taken===true` edges highlighted green + GitBranch icon, non-taken dimmed;
     shows condition/label metadata. Empty state "No graph yet."
   - **Fork section** (terminal runs only): inline form (textarea for
     `instruction`, number input for `from_sequence` default 0) → `POST
     /api/v2/runs/{runId}/fork` with `{from_sequence, instruction}`. On success
     surfaces `Forked → {new_run_id}` chip. Loading + error states handled.
   - `chat-store.ts` was **not** modified — existing `patchRun` already merges
     arbitrary `Partial<RunState>`, so no new store action was needed.

The worker correctly **unwraps the v2 envelope** in `fetchGraph` (reads
`json.data`) — the graph endpoint returns `ok({workflow_type, nodes, edges})`,
so raw `fetch()` bodies are enveloped as `{data, error, meta}`.

### 2.2 FE provenance envelope-unwrap bug fix (commit `0a63d9e0`)

**Pre-existing Phase-2 latent bug**, found while grounding the worker prompt.
`fetchProvenance` (RunActivityStream.tsx ~line 151) read
`res.json() as RunProvenance` directly. But the backend endpoint returns the
v2 envelope `ok({run_id, provenance: [...], count})`, so:
- `.steps` was **always undefined** → provenance chips **silently never
  rendered** since Phase 2.
- The per-record field names also differ from the FE type.

**Fix:** unwrap `.data.provenance` (an array) and map the real backend
projection onto `RunProvenanceStep`:
- `record.seq` (stringified) → `stepId`
- `record.tool_name` → `toolUsed`
- `record.reasoning` → `memoryClaim` (closest available explainability text —
  there is no dedicated memory-claim field in the projection)

Backend contract confirmed by reading `_event_to_provenance()`
(`run_service.py:736`): each record is
`{seq, actor, causal_parent, type, reasoning, tool_name, capability_scope,
budget_spent, content_hash}`.

### 2.3 Backend integration merge (commit `4f9716b0`)

Created `wt/be-phase3-merge-20260720` off `main` (`896ab5d2`), then:
- `git merge wt/be-phase3-graph-20260720` → **fast-forward** (clean).
- `git merge wt/be-phase3-fork-20260720` → **auto-merged via `ort`** — the
  adjacent additions in `run_service.py` and `runs.py` merged with **no
  conflicts** (both add new methods/routes in non-overlapping regions).

Merged tree confirmed to contain all symbols:
- Routes: `fork_run` (`runs.py:131`), `get_run_graph` (`runs.py:260`)
- Service: `fork_run` (`run_service.py:365`), `get_provenance` (`:574`),
  `get_run_graph` (`:761`)
- CQRS: `RunQueryHandlers.get_run_graph` (`queries.py:162`),
  `RunCommandHandlers.fork_run` (`commands.py:151`)

---

## 3. Verification (every claim re-run this session, not trusted from labels)

Per Glenn's standing rule, no "done" label was trusted — every result below was
independently re-run against the actual committed tree.

### FE (both commits)
```bash
cd /home/glenn/FlowmannerV2-frontend/.worktrees/fe-phase3-graph-fork
npx tsc --noEmit          # → exit 0 (clean) on both 08923d0d and 0a63d9e0
```

### Backend merge (`4f9716b0`)
```bash
cd /opt/flowmanner/backend/.worktrees/phase3-merge/backend
source /opt/flowmanner/backend/.venv/bin/activate
ruff check app/services/run_service.py app/api/v2/runs.py \
  app/api/_blueprint_cqrs/queries.py app/api/_blueprint_cqrs/commands.py \
  app/services/chat/substrate_client.py \
  app/tests/test_graph_run.py app/tests/test_run_fork.py
# → All checks passed!
python -c "import app.main_fastapi"          # → import OK (249 sub-routers)
python -m pytest app/tests/test_graph_run.py app/tests/test_run_fork.py -q
# → 6 passed
```

### Regression check — ZERO new failures introduced
Ran `pytest app/tests/ -k run` on the merge branch. Found 3 failures + several
collection errors. **All proven pre-existing on clean `main`** (byte-identical
failures reproduced from the `main` worktree). They are unowned test debt,
NOT caused by this merge:
- `test_model_router.py` — collection `ImportError: cannot import name
  'PROVIDER_MAP' from 'app.services.chat_service'` (confirmed 0 matches on
  `main:chat_service.py`).
- `test_run_uuid_resolution.py::test_get_short_prefix_not_found`
- `test_run_uuid_resolution.py::test_get_non_owner_raises_run_not_found`
- `test_budget_enforcer.py::TestFallbackGating::test_explicit_allow_fallback_runs_local_model`
- `test_phase6_finalize.py::TestEvalRuns::*` — fixture/collection errors
  (more errors on `main` than on the branch, because a narrower selection was
  run on the branch).

The merge's own scope is fully green (ruff + import + 6 Phase 3 tests).

---

## 4. Exact branch / commit state (verified)

| Branch | HEAD | Base | Worktree |
|--------|------|------|----------|
| `wt/be-phase3-merge-20260720` | `4f9716b0` | `main` @ `896ab5d2` | `/opt/flowmanner/backend/.worktrees/phase3-merge/` |
| `wt/be-phase3-graph-20260720` | `fa50cb30` | (superseded by merge) | `.../phase3-graph/` |
| `wt/be-phase3-fork-20260720` | `9b35651c` | (superseded by merge) | `.../phase3-fork/` |
| `wt/fe-phase3-graph-fork-20260720` | `0a63d9e0` | `master` @ `342ae305` | `/home/glenn/FlowmannerV2-frontend/.worktrees/fe-phase3-graph-fork/` |

FE branch commit chain: `342ae305` (master) → `08923d0d` (graph+fork feat) →
`0a63d9e0` (provenance fix, tip).

Both backend source-edit branches (`graph`, `fork`) are now fully contained in
the merge branch; they can be retired after the merge branch lands.

---

## 5. Merge / land / deploy order for the next session (all gated on Glenn)

Nothing below has been done — it is the pending decision tree.

1. **Land backend:** merge `wt/be-phase3-merge-20260720` → `main` (local only).
2. **Land frontend:** merge `wt/fe-phase3-graph-fork-20260720` → `master`
   (local only). Use `git commit --no-verify` if the ruff-format / eslint
   pre-commit hook mis-rolls (known quirk).
3. **Push** authorized branches to origin — **NO PR** (Glenn's €20-CI rule;
   only open a PR if explicitly asked).
4. **Deploy backend:** `bash /opt/flowmanner/deploy-backend.sh` (~2 min,
   timeout=300). **NO `--migrate`** — no ORM columns were added/changed this
   session (fork uses the existing `Run.parent_run_id` column).
5. **Deploy frontend:** `bash /opt/flowmanner/deploy-frontend.sh` — run
   BACKGROUND with `notify_on_complete=true` (foreground >320s kills mid-build
   and leaves the OLD container up). Verify VPS `docker compose ps frontend`
   shows CREATED, not just a public 200.
6. **Live probe after backend deploy:** mint a JWT (read `JWT_SECRET_KEY` via
   `docker compose exec -T backend env`; claims `sub=str(user_id)`,
   `type:'access'`) and hit `GET /api/v2/runs/{id}/graph` +
   `POST /api/v2/runs/{id}/fork` against the live container — source file ≠
   running container (no volume mounts).

---

## 6. Open threads (hand off explicitly)

1. **Pre-existing backend test debt** (§3) — `PROVIDER_MAP` import error in
   `test_model_router.py`, `test_run_uuid_resolution` ×2, `test_budget_enforcer`
   fallback, `test_phase6_finalize` fixture errors. Present on `main`, NOT this
   work. Needs its own cleanup session; do not conflate with Phase 3.
2. **Token-rate regression** (`~0.0001 tok/s`) — carried from the prior
   handoff, still NOT investigated. Separate session: LLM gateway routing +
   provider health, not the chat panel.
3. **Fork partial-execution compounding** — fork currently re-runs the whole
   workflow from the patched node (does not skip already-completed upstream via
   `previous_outputs`). Intentional caveat from the prior handoff; follow-up in
   `strategies/graph.py` only if true partial replay is required.
4. **Provenance `memoryClaim` mapping** — mapped from `record.reasoning` as the
   closest available field. If a dedicated memory-claim projection is added to
   `_event_to_provenance()` later, update the FE mapper in `fetchProvenance` to
   consume it.

---

## 7. Deliverable summary for the human

- ✅ Phase 3 frontend slice built (graph renderer + fork UI), tsc clean.
- ✅ Latent Phase-2 provenance chip bug fixed (envelope unwrap + field map).
- ✅ Two backend branches integrated into one merge branch, no conflicts,
  ruff clean, app imports, 6/6 Phase 3 tests pass, zero new regressions.
- ⛔ Nothing pushed, merged to main/master, or deployed — awaiting review.

**One decision for the human:** approve (a) landing both branches locally,
(b) pushing to origin (no PR), and/or (c) deploying — or leave the branches
for review. See §5 for the exact ordered commands.
