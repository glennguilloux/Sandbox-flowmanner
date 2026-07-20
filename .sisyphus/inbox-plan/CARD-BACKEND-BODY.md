# Inbox/Notifications — Backend Build Card (v2 router + emission + tests)

You are the **engineering-backend-architect** persona for Flowmanner. Implement the
backend half of the Notifications/activity-feed feature, following the verified plan at
`/opt/flowmanner/.sisyphus/inbox-plan/PLAN.md` (read it first — its file:line claims were
independently verified against live source).

## Scope (DO THIS)
1. **Create `backend/app/api/v2/notifications.py`** — v2 envelope router:
   - `GET /api/v2/notifications` — paginated; query `?read=true|false&type=<type>&page=&per_page=`.
   - `POST /api/v2/notifications/{id}/read` — mark one read, owner-checked.
   - `POST /api/v2/notifications/read-all` — mark all read.
   - `GET /api/v2/notifications/unread-count` — badge count.
   Use `ok()` / `paginated()` / `err()` from `app.api.v2.base`. Auth via
   `Depends(get_current_user)` from `app.api.deps`. Owner check: `notification.user_id == current_user.id`
   (mirror `app/api/v2/missions.py` `_require_owner` pattern). Reuse the EXISTING `Notification`
   model (`app/models/notification_models.py`) and `send_notification` from
   `app/services/notification_service.py` — do NOT duplicate logic.
   Respect `app/api/v2/base.py` envelope contract and `validation_middleware` (no raw enums/sets
   in responses; `from_attributes` models serialize cleanly).

2. **Register the router** in `backend/app/api/v2/__init__.py` near the other
   `api_v2_router.include_router(...)` calls (after the `search_router` include, ~line 23-30).
   Import the router at top of the file like the others.

3. **Wire emission at mission completion (EXPLICIT, not the status-validator chokepoint):**
   - `backend/app/services/trigger_service.py:269` — on success/fail transition, call
     `send_notification(user_id, "mission_completed"|"mission_failed", {...}, db)` for the
     mission owner. Pass the surrounding `db` session; if none is in scope, open
     `AsyncSessionLocal()` and close it (mirror `mission_execution.py:174`).
   - `backend/app/tasks/mission_execution.py:178` — on async exec error → FAILED, same call.
   - Make emission LAZY + NON-RAISING (import inside function, try/except, log on failure, never
     block the mission transition).
   - Do NOT touch `MissionStatus._on_mission_status_set` validator (recursion/flush-loop risk).

4. **Tests** — `backend/app/tests/test_v2_notifications.py`:
   - list returns paginated envelope (`data.items`, `data.pages`, `meta.request_id`, `error: null`).
   - `unread-count` returns `{data:{unread_count:N}}`.
   - mark-read / read-all return correct envelope; missing id → `err("NOT_FOUND", 404)`.
   - **owner isolation**: user A cannot read/mark user B's notification (404).
   - **emission integration**: completing a mission (success path at `trigger_service.py:269`)
     creates exactly one `Notification` row for the owner with `notification_type in
     {mission_completed}` and `entity_id == mission_id`.
   Run with the host venv: `cd /opt/flowmanner/backend && PYTHONPATH=. .venv/bin/python -m pytest
   app/tests/test_v2_notifications.py -q`. Also run `make lint` from repo root and fix any new
   ruff errors in YOUR changed files only.

## Do NOT (hard limits)
- Do NOT modify v1 notification code or its response shapes (v1 is backward-compatible forever).
- Do NOT rebuild/migrate the `notifications` table or add new columns (plan §2 additive columns
  are a SEPARATE future task — skip migration here). Use the existing model as-is.
- Do NOT edit frontend files (separate card).
- Do NOT commit, push, or deploy. Leave changes staged/committed on the card's branch only
  (it's your exclusive branch). Actually: commit your work to the branch so a worktree reclaim
  cannot destroy it, but do NOT push and do NOT open a PR.
- Do NOT touch `auth.py` / login.

## Envelope reference (from app/api/v2/base.py)
- `return ok(payload)` → `{"data": payload, "meta": {...}, "error": null}`
- `return paginated(items=list, total=N, page=P, per_page=PP)`
- `return err("CODE", "message", status_code=404)`

## Finish
When tests pass + lint clean on your changed files:
- Write a short deliverable summary to `/opt/flowmanner/.sisyphus/inbox-plan/BACKEND-DONE.md`
  (what changed, file:line, test count, any unverified risk).
- Call `kanban_block` (block-for-review) with a one-line summary. Do NOT mark done/closed.
