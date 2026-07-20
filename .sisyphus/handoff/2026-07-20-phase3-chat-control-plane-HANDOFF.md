# Handoff — Phase 3 Chat Panel Control Plane (graph promotion + fork-a-run)

**Date:** 2026-07-20
**Author:** Hermes coding agent (kanban-style worker slot)
**Plan:** `.sisyphus/plans/chat-panel-control-plane-PLAN.md`
**Prior handoff:** `.sisyphus/handoff/2026-07-20-phase1-chat-substrate-HANDOFF.md`

> This document replaces the handoff the kanban workers *should* have written. It records exactly what is done, what is verified, what is blocked, and what the next session must pick up. Do NOT re-derive context — it is all here.

---

## 1. Where things stand (summary)

| Slice | Status | Branch / location | Tests |
|-------|--------|------------------|-------|
| Phase 2 merge (backend `main` + frontend `master`) | ✅ merged | `main` = `896ab5d2` | 21 (36 in plan) |
| Phase 3 — graph promotion (backend) | ✅ done, committed | `wt/be-phase3-graph-20260720` @ `fa50cb30` | 3 passed |
| Phase 3 — fork-a-run (backend) | ✅ done, committed | `wt/be-phase3-fork-20260720` @ `9b35651c` | 3 passed |
| Phase 3 — frontend (graph renderer + fork UI) | ⛔ **NOT STARTED** | — | 0 |
| Verify full suite (ruff + pytest + tsc) | ⏳ partial — per-slice only | — | — |
| Push / deploy | ⛔ deliberately not done (user review gate) | — | — |

**Success gate from plan §5 ("user forks a completed run from a mid-step edit, and the graph / fork is reflected"):** backend side is complete and unit-tested; **frontend side is the only remaining blocker for the gate.**

---

## 2. Repo / worktree layout (exact, verified)

Backend inner repo lives at `/opt/flowmanner/backend/`. Worktrees are nested
under `/opt/flowmanner/backend/.worktrees/<name>/backend/` (the worktree was
added from inside the inner repo, so the code path is one level deeper than the
wt name).

| Worktree | Branch | HEAD | Purpose |
|----------|--------|------|---------|
| `.worktrees/phase3-graph/backend/` | `wt/be-phase3-graph-20260720` | `fa50cb30` | graph promotion backend |
| `.worktrees/phase3-fork/backend/` | `wt/be-phase3-fork-20260720` | `9b35651c` | fork-a-run backend |
| `.worktrees/phase2-verify-20260720` (`inttest/phase2-verify-20260720`) | throwaway | — | Phase 2 merge verification; safe to delete |

Frontend repo (double-N, never "Flowmapper"): `/home/glenn/FlowmapperV2-frontend`
→ correct path is `/home/glenn/FlowmannerV2-frontend`. Symlink `/home/glenn/f`
is reliable. Master HEAD at start of Phase 3: `342ae305`.

**Concurrency rule (AGENTS.md):** each agent works on its OWN branch + worktree.
Graph and fork live on separate branches by design — do NOT merge them into a
shared checkout.

---

## 3. Phase 3 backend — graph promotion (DONE, verified)

Mirrors the Phase 2 dag-promotion pattern (CQRS: router → RunQueryHandlers →
RunService → substrate_client).

### Changes (`wt/be-phase3-graph-20260720`)
1. **`app/services/chat/substrate_client.py`** — added `build_graph_workflow()`
   (mirrors `build_dag_workflow`) and `execute_graph_run()` (mirrors
   `execute_dag_run`). Exported in `__all__`.
2. **`app/services/run_service.py`** — added `get_run_graph(run_id, user_id)`.
   Mirrors `get_run_tree`; returns `{workflow_type, nodes, edges}` where an
   edge is `taken` only if **both** endpoints reached a terminal status
   (corrected semantics — naive target-only / source-only checks are wrong;
   covered by test).
3. **`app/api/_blueprint_cqrs/queries.py`** — added
   `RunQueryHandlers.get_run_graph`.
4. **`app/api/v2/runs.py`** — added `GET /{run_id}/graph`.
5. **`app/tests/test_graph_run.py`** — 3 tests (happy path + taken-edge logic +
   ownership rejection), all pass.

### How to verify (re-run anytime)
```bash
cd /opt/flowmanner/backend/.worktrees/phase3-graph/backend
source .venv/bin/activate
ruff check app/services/chat/substrate_client.py app/services/run_service.py \
  app/api/_blueprint_cqrs/queries.py app/api/v2/runs.py app/tests/test_graph_run.py
python -m pytest app/tests/test_graph_run.py -q
```
Result at handoff: **ruff clean, 3 passed, `import app.main_fastapi` OK.**

---

## 4. Phase 3 backend — fork-a-run (DONE, verified)

"Re-run a completed run from a mid-step edit, with the edited instruction patched
into the node active at the fork checkpoint." Leverages the existing
`ReplayEngine.rebuild_state_at_sequence` primitive.

### Changes (`wt/be-phase3-fork-20260720`)
1. **`app/services/run_service.py`** — added
   `fork_run(run_id, user_id, *, from_sequence, instruction)`:
   - Ownership check via existing `self.get`.
   - Replays event log to `from_sequence` to locate the **active fork node**
     (node with `status == "running"` at that point; falls back to the event's
     `node_id`/`task_id`; further falls back to topology node 0).
   - Rebuilds the workflow from the original snapshot and patches the fork
     node's `config["prompt"]` + `description` with the edited `instruction`.
   - Creates a **new** `Run` row with `parent_run_id` = original (lineage;
     `Run` model already has the column), dispatches through
     `UnifiedExecutor.execute` with `context={"previous_outputs": dict(task_states)}`.
   - Returns `{new_run_id, parent_run_id, workflow_type, forked_from_sequence,
     forked_node, status, total_tokens, total_cost_usd}`.
   - Import added: `from app.services.substrate.event_log import get_event_log`
     (was missing — `fork_run` uses it; this was a real bug caught before commit).
2. **`app/api/_blueprint_cqrs/commands.py`** — added `RunCommandHandlers.fork_run`
   (mirrors `retry_run`, wraps `wrap_command`).
3. **`app/api/v2/runs.py`** — added `POST /{run_id}/fork` (Body:
   `from_sequence: int`, `instruction: str`); imports `Body`.
4. **`app/tests/test_run_fork.py`** — 3 hermetic tests (no Postgres): patches
   `RunService.get`, `get_replay_engine`, `get_event_log`, `get_unified_executor`,
   asserts (a) node prompt patched, (b) new child run created with `parent_run_id`,
   (c) executor dispatched, (d) cross-user access raises `RunNotFoundError`,
   (e) empty-event-log fallback to topology node 0. All pass.

### Known design caveat (intentional, flag for review)
A fork currently **re-executes the whole workflow** from the patched node with
upstream nodes re-run (the substrate treats the fork as a fresh run). The plan's
"from a step" compounding (skip already-completed upstream) is *not* wired into a
partial replay — `previous_outputs` is passed as context but the GraphStrategy
does not auto-skip completed nodes from it yet. This is fine for the demo success
gate (fork + compare via `/diff`), but if true partial-execution compounding is
required, that's a follow-up in `strategies/graph.py`.

### How to verify
```bash
cd /opt/flowmapper/backend/.worktrees/phase3-fork/backend   # NOTE: correct path is phase3-fork/backend
cd /opt/flowmanner/backend/.worktrees/phase3-fork/backend
source .venv/bin/activate
ruff check app/services/run_service.py app/api/_blueprint_cqrs/commands.py \
  app/api/v2/runs.py app/tests/test_run_fork.py
python -m pytest app/tests/test_run_fork.py -q
```
Result at handoff: **ruff clean, 3 passed, `import app.main_fastapi` OK.**

---

## 5. Phase 3 frontend — graph renderer + fork UI (NOT STARTED)

**This is the only incomplete slice.** Plan §5 asks for:
- A **graph view** in `RunActivityStream` for completed runs: fetch
  `GET /api/v2/runs/{runId}/graph`, render `nodes` + `edges`, highlight the
  `taken` path (branches + taken edges).
- A **fork UI**: a button that collects an edited `instruction` + a checkpoint
  `from_sequence`, then `POST /api/v2/runs/{runId}/fork`, and surfaces the
  returned `new_run_id` (which the user can compare via `/diff`).

### Files the next agent will touch (verified present, read before editing)
- `/home/glenn/FlowmannerV2-frontend/src/components/chat/RunActivityStream.tsx`
  (Phase-2 director controls + provenance chips already there; add Graph tab +
  Fork button; mirror the `fetchProvenance` lazy-load pattern and the
  `runControlDispatch` store-registration pattern).
- `/home/glenn/FlowmannerV2-frontend/src/lib/chat-types.ts` — add a `RunGraph`
  type: `{ workflow_type: string; nodes: {id, title, status}[]; edges: {source,
  target, taken}[] }`.
- `/home/glenn/FlowmannerV2-frontend/src/stores/chat-store.ts` — add
  `runGraphDispatch` / `runForkDispatch` (or inline `fetch` from the component,
  mirroring the provenance fetch) + `patchRun(runId, {graph})`. Store already
  has `runControlDispatch`, `activeRuns: Record<string, RunState>`, `patchRun`,
  `addRun`.

### Frontend gotcha (from memory, still live)
`src/lib/api-client.ts` auto-unwraps the v2 envelope, so `apiClient.get` returns
`{items, ...}` not an array. Resolvers must use `data.items ?? []`, NOT
`data.data ?? []` (latent bug at `ThreadSidebar.tsx:80`). When adding the graph
fetch, consume the unwrapped `data` shape, not `data.data`.

### FE verification command
```bash
cd /home/glenn/FlowmannerV2-frontend
npx tsc --noEmit          # or: pnpm tsc --noEmit
```
The project carries ~303 pre-existing src-lint errors that are **unowned debt**;
Glenn has approved `--skip-precheck` / ignoring them for shipping. tsc passing
is the real gate. Do NOT treat `--skip` as failure.

---

## 6. Merge / integration order for the next session

1. Finish the frontend slice (§5).
2. Run full per-slice verify (graph worktree + fork worktree ruff/pytest) — already green.
3. Run `npx tsc --noEmit` in the FE repo.
4. **Integrate the two backend worktrees into a single Phase-3 branch** to land
   on `main` (graph + fork touch adjacent but non-overlapping regions:
   `substrate_client.py`, `run_service.py`, `queries.py`, `commands.py`,
   `runs.py`). Suggested: create `wt/be-phase3-merge` off `main`, merge
   `wt/be-phase3-graph-20260720` then `wt/be-phase3-fork-20260720`, resolve any
   conflict in `run_service.py` (both add methods near `retry`), re-run ruff +
   both test files.
5. **DO NOT push or deploy** without explicit user go. Leave branches for review.
   Use `git commit --no-verify` only if the worktree `ruff format` pre-commit
   hook mis-rolls (known quirk — it reformats then aborts; re-stage + commit
   works).

---

## 7. Open threads (hand off explicitly — do NOT leave implied)

1. **Frontend slice incomplete** — graph renderer + fork UI not built (§5).
2. **Token-rate regression** — user reports inference is again
   `~0.0001 tok/s` (same symptom as a prior incident). NOT investigated this
   session; likely a billing/provider/throughput regression. Needs its own
   session: check the LLM gateway routing + provider health, not the chat panel.
3. **Fork partial-execution compounding** — currently re-runs whole workflow,
   not a true "from a step" partial replay (§4 caveat). Follow-up if required.
4. **Test count gap** — Phase 2 plan called for 36 tests, 21 landed. Phase 3
   added 6 (3 graph + 3 fork). No blocker, just note the gap vs plan.

---

## 8. Deliverable summary for the human

- ✅ Phase 3 backend fully implemented on two isolated branches, unit-tested
  (6 new tests, all green), ruff clean, app imports clean.
- ⛔ Frontend not started (blocked only on that slice).
- ⛔ Nothing pushed, nothing deployed — awaiting review.
- ⚠️ Separate token-rate regression (`0.0001 tok/s`) flagged by user, not in
  scope of this panel work; needs its own investigation.

One decision for the human: review the two branches (`wt/be-phase3-graph-20260720`,
`wt/be-phase3-fork-20260720`) and either (a) approve the frontend build + merge,
or (b) retire/adjust scope. No autonomous push/deploy.
