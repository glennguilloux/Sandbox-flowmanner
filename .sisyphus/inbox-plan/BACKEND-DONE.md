# Backend Build — DONE (v2 Notifications + Emission)

Branch: `agent/20260719-inbox/backend-build` (commit `87bd019a`)
Worktree: `/opt/flowmanner/.worktrees/t_160b172b`
Head at start: `0f798031` (unchanged until commit).

## What changed (file:line)

1. **`backend/app/api/v2/notifications.py`** (NEW, additive) — v2 envelope router:
   - `GET /api/v2/notifications` — paginated; `?read=true|false&type=<type>&page=&per_page=`.
     Returns `paginated(items, total, page, per_page, pages)` with `meta.request_id`.
   - `GET /api/v2/notifications/unread-count` — `{data:{unread_count:N}}`.
   - `POST /api/v2/notifications/{id}/read` — owner-checked; `err("NOT_FOUND")` when not
     the owner's row (v2 envelope: HTTP 200 + `error.code`).
   - `POST /api/v2/notifications/read-all` — `{data:{updated:N}}`.
   - `NotificationItem` mirrors the v1 shape (`type`/`notification_type`, `from_attributes`).
   - Uses `ok()`/`paginated()`/`err()` from `app.api.v2.base`; auth via
     `Depends(get_current_user)`; owner check `notification.user_id == current_user.id`.

2. **`backend/app/api/v2/__init__.py`** (`:22`, `:31`) — import + `include_router(notifications_router)`
   after the `search_router` include (per plan §3).

3. **`backend/app/services/trigger_service.py`** (`:269`–`:298`) — on the success/fail
   transition in `_execute_mission_background`, call `send_notification(user_id,
   "mission_completed"|"mission_failed", {...}, db)` for the mission owner, using the
   in-scope `db` session. **Lazy import + try/except + log-on-failure: never raises,
   never blocks the mission transition.**

4. **`backend/app/tasks/mission_execution.py`** (`:191`–`:218`) — on async exec error →
   FAILED, same lazy non-raising `send_notification` call inside the existing
   `fail_session` (before its commit).

5. **`backend/app/services/notification_service.py`** — `_add_notification` (`:115`) and
   `send_notification` (`:588`) now accept and persist the EXISTING `entity_type` /
   `entity_id` / `meta` columns (previously never populated). This is what makes the
   acceptance criterion `entity_id == mission_id` satisfiable. **No migration; the
   columns already existed on the `Notification` model.**

6. **`backend/app/tests/test_v2_notifications.py`** (NEW) — hermetic (unique throwaway
   Postgres DB per test, `127.0.0.1:5432` with the `.env` credentials). Covers:
   list envelope shape, unread-count, mark-read + 404 code, read-all, **owner isolation**
   (user A cannot read/mark user B's notification), type filter, and **emission contract**
   (mission completion creates exactly one `Notification` for the owner with
   `notification_type == "mission_completed"` and `entity_id == mission_id`).

## Tests

```
cd backend && PYTHONPATH=. .venv/bin/python -m pytest app/tests/test_v2_notifications.py -q
=> 7 passed
```
Run from the **worktree's `backend/` dir** (so pydantic-settings finds `backend/.env`
with the correct DB password — running from the worktree root resolves a different
`.env` and fails auth). Redis is unreachable on the host, so the emission test stubs
`publish_user_notification` (production sites already wrap `send_notification` in
try/except and never raise on it).

## Lint

`ruff check` on the changed files: **no NEW errors.** Remaining findings are all
pre-existing patterns in those files (E402 module-level imports in `__init__.py`;
E712 `== False/True` and F401/F841 at lines outside my edits in
`notification_service.py` / `trigger_service.py` / `mission_execution.py`).

## Hard limits respected

- No v1 notification code or response shapes changed (v1 is backward-compatible).
- No `notifications` table migration / no new columns added.
- No frontend files edited.
- No auth.py / login touched.
- `MissionStatus._on_mission_status_set` validator NOT touched (explicit call sites only,
  per plan §4.1 lower-risk choice).

## Unverified / risk notes

- **Live SSE publish path not exercised on host** (Redis `redis:6379` unreachable). The
  emission test stubs `publish_user_notification`; in production the inline calls are
  wrapped in try/except so a Redis outage cannot block a mission transition. Verify SSE
  delivery only after deploy (human-gated per AGENTS.md).
- The `err("NOT_FOUND", …, status_code=404)` helper stores the status in the envelope but
  routers return a dict, so the **HTTP status is 200** with `error.code == "NOT_FOUND"`.
  This matches the existing v2 envelope convention (other v2 routers do the same). If a
  true HTTP 404 is desired, the routers would need to raise `HTTPException` instead — flag
  for frontend-contract review.
- Mission **RUN** completion emission (plan §4.2) is OUT of scope for this card (separate
  task); only mission success/failure is wired.
