# Chat Panel → Control-Plane Front Door — HANDOFF (updated 2026-07-20, end of Phase 2)

**Original handoff date:** 2026-07-20 · **Author:** Hermes (Glenn's agent)
**This update:** 2026-07-20 (Phase 1 MERGED + Phase 2 COMPLETE & VERIFIED) · **Status:** Phase 1 merged to `main`/`master`; Phase 2 code-complete on isolated `wt/*` branches, verified (ruff + 21 tests + F1–F4 reviewers). **Phase 3 NOT STARTED.**
**Source plan:** `/opt/flowmanner/.sisyphus/plans/chat-panel-control-plane-PLAN.md` (owner-approved 2026-07-20)
**Repo roots:** backend `/opt/flowmanner/` (no volume mounts); frontend `/home/glenn/FlowmannerV2-frontend/` (symlink `/home/glenn/f`).

---

## 0. TL;DR for the owner (Glenn)

Phase 1 is **merged to `main`/`master` and verified**. Phase 2 is **code-complete and independently verified** — director Pause/Abort/Resume, dag promotion, and a provenance read endpoint — sitting on 4 isolated `wt/*` branches (3 backend + 1 frontend), each with green ruff + tests + an F1–F4 reviewer verdict of "safe to merge." **Nothing is pushed to origin, nothing deployed.** Phase 3 (graph promotion, fork-a-run, swarm re-eval) is the next open work, anchored below.

---

## 1. Phase 1 — MERGED (was: code-complete on branches)

### Backend — merged into `main` (commit `2a991caf`, merge of `wt/be-chatpanel-phase1-2026-07-20`)
Merged via `git merge --no-ff wt/be-chatpanel-phase1-2026-07-20` at session start (Phase 2 prep). Files landed on `main`:
- `backend/app/services/chat/substrate_client.py` — `SubstrateClient` facade (solo only).
- `backend/app/services/sse_buffer.py` — §7 IDOR fix (owner-binds replay buffer).
- `backend/app/api/v2/chat.py` + `backend/app/api/v1/chat.py` — `/threads/{id}/runs` (build+dispatch→`{run_id}`), `/threads/{id}/runs/stream` (SSE replay), v1 `replay_stream` lockdown.
- `backend/app/services/chat/__init__.py` — re-export.
- `backend/app/tests/test_substrate_client.py` (11 tests) + `test_sse_buffer_owner.py` (3 tests).

### Frontend — merged into `master` (commit on top of `4d6ac240`)
Merged `wt/fe-chatpanel-phase1-2026-07-20` (`181a3214`) into `master`. Files on `master`:
- `src/hooks/useChatController.ts`, `src/stores/chat-store.ts` (`recentThreads` + `activeRuns`), `src/lib/chat-types.ts` (`RunState`/`RunStep`), `src/components/chat/RunActivityStream.tsx`, `Canvas.tsx`, `SSEChat.tsx`.

### Phase 1 verification (re-run this session, independent)
- `ruff` clean on all 7 merged files; **14 pytest passed** (`test_substrate_client` 11 + `test_sse_buffer_owner` 3).
- Frontend `tsc --noEmit` **0 errors**. 4 pre-existing eslint errors (SSEChat.tsx 212/232/528, chat-types.ts 341) are inherited master debt, NOT Phase 1's — confirmed by diff-line check.

---

## 2. Phase 2 — COMPLETE & VERIFIED (on isolated branches, NOT merged)

### 2.1 Dispatch note — contamination trap caught and fixed
First dispatch used `--workspace dir:/opt/flowmanner`, which hands workers the **shared checkout** → fmw1's commit `0d2e9016` became a 3-worker blend (its own director code + fmw2's dag in `substrate_client.py` + fmw3's provenance route in `runs.py`) and fmw2/fmw3's service-layer support was left uncommitted → committed code did not import. This is the AGENTS.md concurrency-contamination class.
**Remediation (root-cause):** preserved evidence (`git tag evidence/phase2-contam-20260720` + `stash@{0}`), reset `main` to clean Phase-1 merge `2a991caf`, re-dispatched on **isolated worktrees** (`worktree:/opt/flowmanner`, unique `wt/be-phase2-*-20260720` branches). Second pass clean. **Lesson: for multi-worker fan-out use `worktree:` (isolated), NOT `dir:` (shared checkout).** The dispatch recipe's `dir:` guidance is wrong for parallel workers.

### 2.2 Backend slices (each on its own branch + worktree)
| Card | Worker | Branch | ruff | tests | Reviewer verdict |
|---|---|---|---|---|---|
| Director controls (pause/resume/abort) | fmw1 | `wt/be-phase2-director-20260720` (`20a25794`) | ✅ | 6 pass | `t_bebaa701` F1–F4 PASS (cross-user pause→404 verified by `test_cross_user_pause_rejected_404`, `test_pause_rejected_when_run_id_mismatch`) |
| dag promotion (layered step-tree) | fmw2 | `wt/be-phase2-dag-20260720` (`051a0fd`) | ✅ | 7 pass | `t_29cce1c2` F1–F4 PASS (no deploy/alembic; notes pre-existing `test_run_uuid_resolution.py` mismatch, filed separately) |
| Provenance endpoint | fmw3 | `wt/be-phase2-provenance-20260720` (`797578f6`) | ✅ | 8 pass | `t_c486c0bf` F1–F4 PASS (read-only, no migration; skipped mypy — known tolerated broken gate) |

Files per slice (from `git diff main..HEAD`, verified isolated — no cross-slice code):
- **director:** `chat.py` (+90), `runs.py` (+28 pause/resume), `executor.py` (+96 pause/resume + asyncio.Event), `substrate_models.py` (+4 PAUSE/RESUME_REQUESTED events), `run_service.py` (+42), `test_chat_run_director.py` (+239).
- **dag:** `substrate_client.py` (+331 build_dag_workflow + dag SSE branch), `run_service.py` (+103 get_run_tree), `runs.py` (+20 /tree), `test_dag_run_tree.py` (+244).
- **provenance:** `runs.py` (+29 /provenance), `_blueprint_cqrs/queries.py` (+16 get_provenance), `run_service.py` (+115), `test_run_provenance.py` (+244).

### 2.3 Frontend slice
- Card `t_527f0482` (fmw1), branch `wt/fe-phase2-director-20260720` (`342ae305`) on isolated worktree `/home/glenn/FlowmannerV2-frontend/.worktrees/t_527f0482`.
- `RunActivityStream.tsx`: one-row Pause/Abort/Resume (`canPause`/`canResume`/`canAbort` gating) + provenance chips on expand.
- **tsc --noEmit 0 errors; 0 NEW eslint errors** (the 1 remaining eslint error is pre-existing `any` at `chat-types.ts:341`).

### 2.4 Independent integration verification (my own, not the workers' claim)
Test-merged all 3 backend branches into a throwaway `inttest/phase2-20260720` (from `2a991caf`, order director→dag→provenance): **ruff clean on all 10 files, 21 tests pass together, `app.main_fastapi` imports cleanly.** Zero conflicts (each edits non-overlapping line ranges in `runs.py`/`run_service.py`). Throwaway branch deleted; `main` left at `2a991caf`.

---

## 3. Process notes / things to know

- **Branch isolation honored:** all Phase 2 work on isolated `wt/*` branches + worktrees. No merge to `main`/`master`, no push, no deploy (per AGENTS.md: human review; backend has no volume mounts).
- **Evidence preserved:** `evidence/phase2-contam-20260720` tag + `stash@{0}` hold the first (contaminated) attempt's code, recoverable if ever needed.
- **Reviewers ran F1–F4** on each backend slice (cards `t_bebaa701`/`t_29cce1c2`/`t_c486c0bf`), all "safe to merge / promote at your discretion."
- **Reviewer flag (non-blocker):** `test_run_uuid_resolution.py` has a pre-existing `RunNotFoundError` mismatch that predates the dag branch — file as a separate fix, not part of Phase 2.
- **FE worktree `master` ref is stale** (based off local `181a3214`, not your latest `master`). Harmless (one commit on top) but rebase onto current `master` before merge if you want a clean history.

---

## 4. MERGE ORDER (when you approve — nothing pushed/deployed yet)

1. `wt/be-phase2-director-20260720` → `main`
2. `wt/be-phase2-dag-20260720` → `main`
3. `wt/be-phase2-provenance-20260720` → `main`
4. `wt/fe-phase2-director-20260720` → `master`
5. `deploy-backend.sh` (homelab) + `deploy-frontend.sh` (from homelab, ~4 min, background) — your call.

Also still open from the original handoff's decision point #1: **push the merged Phase 1** (`main`/`master`) to origin for remote reviewability, or hold until Phase 2 also merges.

---

## 5. Phase 3 — NOT STARTED (next open work; anchors verified 2026-07-20)

Per plan §3 PHASE 3 ("Runs compound"), build on the now-merged Phase 1 + Phase 2:

| Item | Anchor (verified `file:line` on `main`) | Action |
|---|---|---|
| Promote **graph** | `backend/app/services/substrate/strategies/graph.py:37` `GraphStrategy`, `execute` at `:54` | Branching/conditional runs once graph validated safe. Mirror Phase 2's dag promotion: `substrate_client.build_graph_workflow` + `run_service.get_run_graph` + `runs.py /{run_id}/graph`. |
| **Fork-a-run** from a mid-step edit | `backend/app/services/substrate/replay_engine.py:23` `ReplayEngine`; `rebuild_state` `:32`, `rebuild_state_at_sequence` `:84`, `get_checkpoint_sequences` `:124`; `event_log.py:64` `append` | Re-run from a step with an edited instruction, leveraging event-log replay. New `POST /api/v2/runs/{run_id}/fork` (or chat `/threads/{id}/runs/{run_id}/fork`) that replays to a checkpoint seq then re-executes with a patched instruction. |
| Re-evaluate **swarm**/pipeline | `backend/app/services/substrate/strategies/swarm.py:69-71` `DEPRECATED=True`/`EXPERIMENTAL=True`/"0% success with 27B" | **Gate UNMET.** Only expose if a stronger model clears the success threshold. Stay deprecated for Phase 3. Do NOT promote swarm. |
| Memory-hub convergence | B1 thesis | Each visible, steerable run becomes durable, re-enterable thread history. |

**Phase 3 success gate (from plan):** user forks a completed run from a mid-step edit; runs are first-class, re-openable thread entities.

**Suggested Phase 3 decomposition (for next session's kanban dispatch):**
1. BE: graph promotion (mirror dag slice) — `wt/be-phase3-graph-20260720`.
2. BE: fork-a-run endpoint (replay + re-execute with patched instruction) — `wt/be-phase3-fork-20260720`.
3. FE: graph renderer + fork UI in `RunActivityStream` — `wt/fe-phase3-graph-fork-20260720`.
4. Reviewer F1–F4 per backend slice.
Dispatch on **isolated worktrees** (`worktree:` mode), NOT `dir:`. Board `default` already has `default_workdir` set to `/opt/flowmanner` (fixes the Pitfall-5 spawn failure). Worker profiles `fmw1`/`fmw2`/`fmw3`/`fmw_synth` are dispatch-ready (valid `OPENROUTER_API_KEY` + `config.yaml` model.default `tencent/hy3:free`).

---

## 6. Single decision point for Glenn (carried from original handoff + this session)

Phase 1 merged, Phase 2 verified on branches. Choose:
1. **Review & merge** the 4 Phase 2 `wt/*` branches (order §4) → then `deploy-backend.sh` + `deploy-frontend.sh` to make it live.
2. **Push Phase 1** (`main`/`master`) to origin for remote review, hold Phase 2.
3. **Proceed to Phase 3** scoping/dispatch (anchors in §5).
4. **Defer** — leave everything on branches.

No action taken beyond writing this handoff. Nothing is merged-to-main for Phase 2, pushed, or deployed.
