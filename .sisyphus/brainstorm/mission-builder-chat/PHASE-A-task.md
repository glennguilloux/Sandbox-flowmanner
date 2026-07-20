# Phase A — Backend gate: establish the Run→Mission link

You are injected as a SOFTWARE ARCHITECT persona. Implement the backend half of the
deep-dive plan at
`/opt/flowmanner/.sisyphus/brainstorm/mission-builder-chat/DEEP-DIVE-PLAN.md`
(section 2, Phase A: tasks A1–A4). This is a REAL implementation card (not
read-only): make a blueprint `Run` carry a `mission_id` so the Chat
`MissionStatusTile` has something to poll.

## The verified problem (do not re-litigate; fix it)
- `Run` model `backend/app/models/blueprint_models.py:107-163` → `runs` table has
  NO `mission_id` column (confirmed live via `\d runs` on Postgres).
- `RunResponse` schema `backend/app/schemas/blueprint.py:143-170` has NO
  `mission_id` field.
- `RunService.create_from_blueprint` `backend/app/services/run_service.py:50-102`
  creates a `Run` and returns it — it NEVER touches `missions` or `mission_runs`.
- `mission_runs` table DOES have a `mission_id` FK → `missions.id` (separate
  aggregate from blueprint `runs`). A blueprint run and a mission run are currently
  unrelated rows.
- The Chat tile `MissionStatusTile.tsx` polls `GET /api/v2/missions/{id}/status`
  which returns `ok(...)` (`backend/app/api/v2/missions.py:358-363`).

## Tasks (implement, in order)

**A1 — Add `mission_id` to the `Run` model + Alembic migration.**
- In `backend/app/models/blueprint_models.py` `class Run` (after `parent_run_id`,
  ~line 157), add:
  ```python
  mission_id: Mapped[str | None] = mapped_column(
      UUID(as_uuid=True),
      ForeignKey("missions.id", ondelete="SET NULL"),
      nullable=True, index=True,
  )
  ```
- Generate the migration from the HOST venv (NOT inside a worktree — worktrees
  have no `.env` and the probe lies):
  `/opt/flowmanner/backend/.venv/bin/alembic -c alembic.ini revision --autogenerate -m "add mission_id to runs"`
- Verify the migration offline BEFORE applying:
  `/opt/flowmanner/backend/.venv/bin/alembic -c alembic.ini upgrade <PARENT>:<CHILD> --sql`
  → assert `ALTER TABLE runs ADD COLUMN mission_id` is present and
  `grep -icE DROP` == 0. Re-run `py_compile` on the new migration file.
- MIGRATION DATA RULE (backend AGENTS.md): nullable column, NO backfill, NO DELETE.
  If any row had NULL it would already be nullable — no sentinel needed.

**A2 — Populate `mission_id` when a blueprint run is created.**
In `backend/app/services/run_service.py` `create_from_blueprint` (the `Run(...)`
constructor at lines 90-99), AFTER building the `run` but BEFORE `self.db.add(run)`:
- Create (or reuse) a `Mission` from the blueprint definition, set
  `run.mission_id = mission.id`, then `self.db.add(run)` / `await self.db.flush()`.
- Reuse the existing mission-creation path — do NOT invent one. The substrate
  adapter `mission_to_workflow` lives in `backend/app/services/substrate/adapters.py`
  (per `backend/app/api/AGENTS.md` §8). Prefer
  `MissionCommandHandlers.create_mission` (from `app.api._mission_cqrs.commands`)
  so ownership/auth/audit are correct. If that path is heavy, the lighter
  alternative is: only set `mission_id` when an explicit `mission_id` is passed
  into `create_from_blueprint` (caller-supplied) and otherwise leave it NULL —
  but the PLAN's recommended path (A2a) is to create the mission inline so the
  link always exists. Pick A2a (inline create) unless it drags in a large
  dependency; document your choice in the commit/PR.
- Add `mission_id: str | None = None` to the `create_from_blueprint` signature
  and pass it through if caller-supplied.

**A3 — Expose `mission_id` in the response.**
- `backend/app/schemas/blueprint.py` `RunResponse` (line 143): add
  `mission_id: str | None = None` (the existing `field_validator` at line 167
  already coerces `id`/`blueprint_id`/`workspace_id`/`parent_run_id` UUID→str;
  add `mission_id` to that validator's field list so it serializes as a string).
- Confirm the run-create / run-execute return path wraps in `RunResponse`
  (the abort/retry routes already do at `run_service.py:83` and `:97` via
  `RunResponse.model_validate(run).model_dump()` — ensure the create/execute
  path does the same so `mission_id` is in the JSON).

**A4 — Note the frontend envelope fix (do NOT implement frontend here).**
The tile bug is in `MissionStatusTile.tsx:66` (`setData(res as MissionStatusData)`
should be `setData(res.data as MissionStatusData)` because the status route
returns `ok(...)`). This card is BACKEND-ONLY. Add a one-line code comment
near the `RunResponse.mission_id` field noting the frontend must unwrap `res.data`,
and leave the `.tsx` untouched. (Phase B/C owns the frontend.)

## Acceptance (you must PROVE these, not assert)
1. New Alembic migration applies clean; `runs` table now has `mission_id`
   (verify: `docker compose exec -T postgres psql -U flowmanner -d flowmanner
   -c "\d runs"` shows the column).
2. Live: `POST /api/v2/blueprints/{id}/run` response `data` contains a
   non-null `mission_id` matching a row in `missions` AND `mission_runs`.
3. `GET /api/v2/missions/{that_id}/status` returns `ok({data:{mission_id,status,...}})`.
4. `backend/.venv/bin/ruff check backend/app/services/run_service.py backend/app/models/blueprint_models.py backend/app/schemas/blueprint.py` clean.
5. `PYTHONPATH=backend python -m pytest backend/app/tests/test_runs.py backend/app/tests/test_missions.py -q` passes (run INSIDE the worktree to avoid E902; if those test files don't exist, add a focused test: (a) `Run` carries `mission_id` after `create_from_blueprint`, (b) `RunResponse` serializes it).

## Done protocol
- Commit on your exclusive branch (`agent/2026-07-19-phaseA/run-mission-link`).
- Run the ruff + pytest checks above yourself and report the actual counts.
- Block-for-review when done (`hermes kanban block <id>`), do NOT push/merge.
- Report: migration file name, the exact `runs` column addition, the
  `create_from_blueprint` change (inline-create vs caller-supplied), and the
  test results. Cite file:line for every change.
