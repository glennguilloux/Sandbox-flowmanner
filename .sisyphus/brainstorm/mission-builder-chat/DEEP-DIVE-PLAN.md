# Deep-Dive Plan — Mission Builder ⇄ Chat Handoff (Builder FEEDS Chat)

**Date:** 2026-07-19
**Author:** Hermes (synthesized from a 3-lens persona brainstorm + live verification)
**Status:** PLAN / not started
**Branch target:** `wt/mission-builder-chat-handoff` (exclusive worktree per repo rule)
**Scope:** Make the Flowmanner Mission Builder and the Chat page relate — a one-click
Builder→Chat handoff, with a working (not broken) mission-status bridge.

---

## 0. Why this plan exists (the "unhappy with the whole thing" root cause)

Verified live 2026-07-19 against the running backend + frontend tree:

1. **The two surfaces are disconnected by design.** The Mission Builder
   (`/home/glenn/f/src/components/mission-builder/FlowEditor.tsx`, 2198 lines) emits a
   **Blueprint** + a **`Run`** (`POST /api/v2/blueprints/{id}/run`,
   `runs.ts:128` `startRun`). Chat (`/home/glenn/f/src/app/[locale]/(dashboard)/chat/`)
   consumes missions only via a `MissionStatus` canvas tile. There is **no path** for a
   built graph to become a chat-runnable agent, and no path for chat to seed a graph.
2. **The one existing bridge is doubly broken.** `MissionStatusTile.tsx`:
   - Reads `missionId` from the tile payload (`MissionStatusTile.tsx:49`). The only way
     to add the tile is the manual "Add tile" dropdown (`Canvas.tsx:226`) which creates
     it with an **empty payload** → renders *"No missionId in tile payload."*
     (`MissionStatusTile.tsx:55-58`). Dead-end for a normal user.
   - Even with an id, it reads the status endpoint **without unwrapping the v2 envelope**:
     `setData(res as MissionStatusData)` (`MissionStatusTile.tsx:66`), but
     `GET /api/v2/missions/{id}/status` returns `ok(...)` →
     `{data:{...}, meta, error}` (`missions.py:358-363`). So `res.mission_id`
     (`MissionStatusTile.tsx:102`) is always `undefined`. **The tile has never worked.**
3. **The Run→Mission link does not exist at any layer.** This is the decisive finding
   from the live check:
   - `Run` model (`backend/app/models/blueprint_models.py:107-163`) → `runs` table
     (`\d runs` on live Postgres) has **NO `mission_id` column** — only `blueprint_id`.
   - `RunResponse` schema (`backend/app/schemas/blueprint.py:143-170`) has **NO
     `mission_id` field**.
   - `RunService.create_from_blueprint` (`run_service.py:50-102`) creates a `Run`
     row and returns it — it **never touches `missions` or `mission_runs`**.
   - There ARE two separate run aggregates: `runs` (blueprint) and `mission_runs`
     (`\d mission_runs` shows a `mission_id` FK → `missions.id`). A blueprint run
     and a mission run are currently **unrelated rows**.

**Conclusion:** The brainstorm's assumed "frontend-only first step" is WRONG. The
Builder→Chat handoff **requires a small backend change first** (establish the
Run→Mission link), or the chat tile will have nothing to poll and the handoff collapses
back into the broken "No missionId" state. This plan orders the work correctly.

---

## 1. Direction (agreed by all 3 brainstorm lenses)

**Builder FEEDS Chat** (not chat-drives-builder, not a third hub):
- Builder = where you **compose** a repeatable workflow.
- Chat = where you **operate and converse** with it.
- A single shared **Run→Mission link** connects them, with no manual ID plumbing.

Deferred (explicitly out of scope): chat-authors-the-graph (NL → node draft). All
three personas rated this a larger, riskier bet with no evidence yet.

---

## 2. Build order (dependency-correct)

### Phase A — Backend: establish the Run→Mission link  ⚠️ GATE / do first
*Why first:* every frontend step depends on a `mission_id` being obtainable from a run.

**A1. Add `mission_id` to the `Run` model + migration.**
- `backend/app/models/blueprint_models.py` — add to `class Run` (after `parent_run_id`,
  ~line 157):
  ```python
  mission_id: Mapped[str | None] = mapped_column(
      UUID(as_uuid=True),
      ForeignKey("missions.id", ondelete="SET NULL"),
      nullable=True, index=True,
  )
  ```
- Generate an Alembic migration (`docker compose exec backend alembic revision
  --autogenerate -m "add mission_id to runs"`), then verify offline:
  `alembic upgrade <parent>:<child> --sql` → assert `ALTER TABLE runs ADD
  COLUMN mission_id` present and `grep -icE DROP` == 0.
- **Migration data-mutation rule** (backend AGENTS.md): never DELETE; use sentinel if
  backfilling NULLs. (Here: nullable column, no backfill needed.)

**A2. Populate `mission_id` when a blueprint run is also a mission run.**
Two honest options — pick ONE (do not do both):
- **A2a (recommended, minimal):** In `RunService.create_from_blueprint`
  (`run_service.py:90`), after building the `Run`, also create a `MissionRun`
  row linking `mission_id` → a *new or existing* mission derived from the blueprint,
  and set `run.mission_id`. This makes `runs` and `mission_runs` share a key.
  - New-mission path: create a `Mission` from the blueprint `definition`
    (reuse `MissionCommandHandlers.create_mission` / the existing
    `mission_to_workflow` adapter in `app/services/substrate/adapters.py`).
  - Set `run.mission_id = mission.id` before `db.add(run)` / `flush()`.
- **A2b (lighter, lazy):** Leave `Run` unlinked at creation; add a separate
  `POST /api/v2/blueprints/{id}/run-as-mission` endpoint that creates BOTH the
  `Run` and the `MissionRun` + `Mission` in one `wrap_command()`. Cleaner
  separation but more surface area. **Prefer A2a** unless the mission-creation
  dependency is heavy.

**A3. Expose `mission_id` in the response.**
- `backend/app/schemas/blueprint.py` `RunResponse` (line 143): add
  `mission_id: str | None = None` (with the existing `field_validator` coercing
  UUID→str at line 167).
- Confirm `run_service.py` returns the run via `RunResponse.model_validate`
  (the abort/retry routes already do, lines 83/97; the create/execute path must
  too). The frontend `startRun` (`runs.ts:128`) will then receive `mission_id`
  in the `Run` object.

**A4. Envelope correctness (fixes the tile's second bug at the source).**
- `MissionStatusTile.tsx:66` currently does `setData(res as MissionStatusData)`.
  The endpoint returns `ok(...)` → the real data is at `res.data`. Change to
  `setData(res.data as MissionStatusData)`. (Covered in Phase C, but note the
  contract here: v2 endpoints ALWAYS wrap in `ok()` — see
  `backend/app/api/v2/AGENTS.md` envelope section.)

**A-acceptance (prove, don't assert):**
- New Alembic migration applies clean; `runs` now has `mission_id`.
- Live: `POST /api/v2/blueprints/{id}/run` response `data` contains a non-null
  `mission_id` that matches a row in `missions` + `mission_runs`.
- `GET /api/v2/missions/{that_id}/status` returns `ok({data:{mission_id,status,...}})`.

---

### Phase B — Frontend: bidirectional `MissionStatusTile` (the v1 seam)
*Smallest change that makes the seam real. No new backend endpoint.*

**B1. `MissionStatusTile.tsx` — fix + make it a two-way bridge.**
- Fix envelope: `setData(res.data as MissionStatusData)` (A4).
- Wrap the card in a link/button → `/missions/builder?missionId=<id>` (backward
  seam to the graph). Source: the tile already holds `missionId`
  (`MissionStatusTile.tsx:49`).
- Add a "Discuss" button → navigates to `/chat?missionId=<id>` (forward seam).

**B2. `chat/page-client.tsx` — auto-open the tile from URL.**
- If `?missionId=` is present on mount, call
  `store.addCanvasTile("mission_status", "Mission Status", { missionId })` (existing
  action `chat-store.ts:390`). The tile now arrives **pre-populated** instead of
  showing "No missionId" (`MissionStatusTile.tsx:55`).

**B3. `Canvas.tsx` "Add tile" — pre-fill payload from URL.**
- In the `AddTileButton` path (`Canvas.tsx:226`), when adding `mission_status`,
  seed `payload.mission_id` from `?missionId=` if present. (Defensive; B2 covers
  the main entry.)

**B-acceptance:**
- `MissionStatusTile` renders live status (polls every 5s, `MissionStatusTile.tsx:78`)
  from a real `mission_id`, not the error string.
- Clicking the tile opens the builder for that mission; "Discuss" opens chat with the
  tile auto-added.

---

### Phase C — Frontend: one-click Run→Chat handoff (the payoff)
*Depends on Phase A (needs `mission_id` in the `Run`).*

**C1. `FlowEditor.tsx` — after `handleRun` succeeds.**
- `handleRun` (~`FlowEditor.tsx:1333-1356`) calls `startRun(savedId, {})`
  (`runs.ts:128`) and then `startPolling`. After the run returns, capture
  `run.mission_id` (now populated by Phase A) and call a new helper
  `openChatForMission(run.mission_id, blueprintTitle)`.
- New module `src/lib/chat-launch.ts`:
  `createThreadForMission(missionId, title)` → `POST /api/v2/chat/threads`
  (existing route `chat.py:178-185`, envelope `ok(...)`) → then
  `store.addCanvasTile("mission_status", title, { missionId })`.
- Navigate to `/chat?thread=<newId>&missionId=<missionId>`.

**C2. `chat-store.ts` — add `openThreadWithMissionTile`.**
- Thin wrapper over existing `addCanvasTile` (`chat-store.ts:390`) +
  `createThread` so the Builder can fire one call. (Optional — C1 can call the
  store directly; add only if it reduces duplication.)

**C-acceptance:**
- In the Builder, click **Run** → lands in a Chat thread pre-wired to that run's
  mission, with a live `MissionStatusTile` already polling. One click, Builder→Chat,
  zero manual ID copy.

---

## 3. Risks / contract gaps (carried from verification)

| # | Risk | Mitigation |
|---|---|---|
| R1 | `Run` has no `mission_id` (confirmed) | Phase A is the whole point — do NOT skip to B/C. |
| R2 | Tile reads envelope wrong (`res` not `res.data`) | A4 + B1 fix; the status route returns `ok(...)` per `missions.py:363`. |
| R3 | `addCanvasTile` de-dupes by `kind` (`chat-store.ts:396`) | One thread shows only the latest mission tile — acceptable for v1; documented. |
| R4 | Auth parity | Both `/api/v2/chat/threads` (`chat.py:182`) and `/api/v2/missions/{id}/status` (`missions.py:360`) use `get_current_user` — same JWT. No gap. |
| R5 | Migration must not DELETE | Sentinel rule from backend AGENTS.md; column is nullable, no backfill. |
| R6 | `RunService` returns via `RunResponse`? | Verify create/execute path wraps in `RunResponse.model_validate` (abort/retry already do, lines 83/97). |

---

## 4. Verification plan (per repo AGENTS.md — path-aware)

Source files touched: backend `.py` (Phase A) + frontend `.tsx`/`.ts` (Phases B/C).
Therefore **`make test; make lint; make build` DO apply** (source changed).

- **Backend:** `backend/.venv/bin/ruff check .` + `PYTHONPATH=backend python -m
  pytest app/tests/test_runs.py app/tests/test_missions.py -q` (run INSIDE the
  worktree, not repo root, to avoid E902). New tests: (a) `Run` carries
  `mission_id` after `create_from_blueprint` (A2), (b) `RunResponse` serializes
  it (A3).
- **Frontend:** `cd /home/glenn/f && npx tsc --noEmit` + the existing
  `*.test.tsx` for `MissionStatusTile`, `Canvas`, `chat-store`. Run in the
  frontend worktree; if `node_modules` missing, symlink the main repo's:
  `ln -sfn /home/glenn/FlowmannerV2-frontend/node_modules <wt>/node_modules`.
- **Live smoke (post-deploy, per `lfe-deploy-smoke-verify`):** hit the running
  backend: `POST /api/v2/blueprints/{id}/run` → assert `data.mission_id`
  non-null → `GET /api/v2/missions/{id}/status` returns `ok({data:{...}})`.

---

## 5. What "done" looks like

A user who finishes a mission in the Builder lands, with **one click (Run)**, in a Chat
thread that shows that exact run's mission live (status, progress, tokens, failures)
and lets them act on it. They can later re-invoke that mission from Chat without
touching the canvas. The Builder is where you *compose*; Chat is where you *operate
and converse*; a single shared Run→Mission link connects them with no manual ID
plumbing. The previously-broken `MissionStatusTile` is now a working two-way bridge.

---

## 6. Reference anchors (all verified live 2026-07-19)

- Builder editor: `/home/glenn/f/src/components/mission-builder/FlowEditor.tsx`
- Builder run: `FlowEditor.handleRun` (~`:1333`), `src/lib/api/runs.ts:128` `startRun`
- Chat page: `/home/glenn/f/src/app/[locale]/(dashboard)/chat/page-client.tsx`
- Chat store: `/home/glenn/f/src/stores/chat-store.ts:390` `addCanvasTile`
- Broken tile: `/home/glenn/f/src/components/chat/tiles/MissionStatusTile.tsx:49,55,66,102`
- Tile add UI: `/home/glenn/f/src/components/chat/Canvas.tsx:226`
- Backend Run model: `backend/app/models/blueprint_models.py:107`
- Backend Run service: `backend/app/services/run_service.py:50` `create_from_blueprint`
- Backend Run schema: `backend/app/schemas/blueprint.py:143` `RunResponse`
- Backend mission status route: `backend/app/api/v2/missions.py:358` `ok(...)`
- Live proof: `runs` table has no `mission_id`; `mission_runs` has `mission_id` FK;
  `runs` table is empty (no run has ever linked to a mission).

## 7. Source brainstorm docs (this plan synthesizes them)

- `/opt/flowmanner/.sisyphus/brainstorm/mission-builder-chat/B1-PRODUCT.md`
- `/opt/flowmanner/.sisyphus/brainstorm/mission-builder-chat/B2-ARCH.md`
- `/opt/flowmanner/.sisyphus/brainstorm/mission-builder-chat/B3-UX.md`
