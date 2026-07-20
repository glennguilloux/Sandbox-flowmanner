# Inbox / Notifications Feed — Recon & Build Plan

**Branch:** `agent/20260719-inbox/recon-plan` (worktree `/opt/flowmanner/.worktrees/t_a84988e5`)
**HEAD at recon:** `0f798031` (same as `feat/sandbox-model-picker-phase-a`)
**Mode:** READ-ONLY recon + plan. No migrations, no feature code, no commits.

---

## 0. TL;DR — What the recon actually found

The task framing ("the Inbox has NO backend behind it — every candidate API path 404s")
is **partially incorrect**. A full notifications backend **already exists** in v1, is
migrated to the DB, and the frontend already talks to it. The real gaps are narrower:

| Claim in task | Reality (verified) |
|---|---|
| "no notifications model/route/handler" | `app/models/notification_models.py` + `app/services/notification_service.py` exist; router mounted at `/api/users/me/notifications/*` (`app/api/v1/__init__.py:204,262-263`); table migrated (`alembic/versions/20260601_notifications_table.py`). |
| `/api/v2/notifications` returns 404 | **TRUE.** v2 has zero notification routers (`search app/api/v2` → 0 hits for `notification`). |
| `/inbox` route has no backend | The `/inbox` page is the **HITL inbox** (`inbox_items` table, `/api/inbox/*`), NOT a notifications feed. Owner wants to repurpose it as a notifications/activity feed. |
| mission/run completion emit notifications | **FALSE today.** Only `background_review_tasks.py:445` and `mission_compensation_service.py:170` call `send_notification`. Mission/run completion is **not** wired to emit. |

**Conclusion:** This is an *extension + wiring* task, not a greenfield build. The plan
below preserves the existing v1 system and adds: (a) the missing v2 notifications surface,
(b) emission at mission/run completion, and (c) a decision on how `/inbox` is repurposed.

---

## 1. Confirmed gap evidence (file:line)

### 1.1 Existing notifications backend (v1) — DOES EXIST
- Model: `app/models/notification_models.py:71` — `class Notification(Base, TimestampMixin)`,
  table `notifications` (`:77`). Fields: `id, user_id(FK users.id, idx), title, message,
  notification_type(String50), severity(String20), is_read(Bool), read_at, entity_type,
  entity_id, meta(Text)`. Plus `NotificationSettings` (`:11`) and `PushSubscription` (`:40`).
- Router: `app/services/notification_service.py:73` — `APIRouter(prefix="/notifications")`.
  Registered with REMAPPED prefix `/users/me` at `app/api/v1/__init__.py:262-263`, so
  effective routes are `/api/users/me/notifications/...`.
- Registered: `app/api/v1/__init__.py:204` (`("notification", notification_router)`).
- SSE stream: `app/services/notification_service.py:416` `GET /stream` (token-auth), backed
  by `app/services/sse_service.py` channel `user:{user_id}:notifications`
  (`sse_service.py:42,60,123,145`). `publish_user_notification` (`:38`) called by
  `send_notification` (`:593`).
- DB migration: `alembic/versions/20260601_notifications_table.py` (`revision =
  "notifications_table_001"`, creates `notifications` at `:20`; dropped at `:44`).
  `notification_settings`/`push_subscriptions` added in `20260520_fix_notifications_columns.py`
  and `20260602_push_subscriptions_table.py`. Model is imported into metadata at
  `app/models/__init__.py:242`.

### 1.2 v2 notifications surface — DOES NOT EXIST (the real 404)
- `app/api/v2/__init__.py:14` mounts `api_v2_router` at `/api/v2`. Its include list
  (lines 23-133) enumerates ~30 sub-routers: auth, missions, agents, chat, workspaces,
  runs, blueprints, marketplace, prompts, eval_runs, etc. **No `notifications` router.**
- Grep `app/api/v2` for `notification|Notification|send_notification` → **0 matches**.
  Hence `/api/v2/notifications`, `/api/v2/notifications/unread-count`, etc. all 404.
  This matches the live observation for every `/api/v2/*` candidate path.

### 1.3 Existing event-emission points that SHOULD feed the feed (but mostly don't)
- `app/tasks/background_review_tasks.py:445` — `send_notification(...)` on review completion.
- `app/services/mission_compensation_service.py:170` — `send_notification(...)` on
  mission compensation decisions.
- **Mission completion/failure** — canonical transition at
  `app/services/trigger_service.py:269`:
  `mission.status = MissionStatus.COMPLETED if getattr(result,"success",False) else MissionStatus.FAILED`
  Also `app/tasks/mission_execution.py:178` (`MissionStatus.FAILED` on async exec error) and
  `mission_execution.py:97` (`MissionStatus.RUNNING`). **None of these call `send_notification`.**
- **Single chokepoint for ALL mission status transitions:** `MissionStatus._on_mission_status_set`
  (validator on the status column — referenced at `app/tasks/expire_paused_missions.py:79`
  "The ORM validator (MissionStatus._on_mission_status_set) enforces the ..."). This is the
  most robust emission site (catches COMPLETED/FAILED/RUNNING/APPROVED/PAUSED uniformly).
- **Run completion:** `Run` model in `app/models/blueprint_models.py`; Run status transitions
  occur in the substrate executor. v2 `app/api/v2/runs.py:22` exposes runs but does NOT emit
  notifications.
- **Existing activity/audit rows that could back an activity feed:** `WorkspaceActivityLog`
  (`app/models/workspace_activity_log.py:13`, table `workspace_activity_log`, indexed at `:28`)
  and `MissionLog` (written at `mission_execution.py:100,147,181`). These are workspace-scoped,
  not user-scoped — a user notification feed needs the per-user `notifications` table, not these.

---

## 2. Data model (proposed) — EXTEND, don't rebuild

The `Notification` model already satisfies the feed requirements. **No new table needed.**
Recommended additive changes only:

```python
# app/models/notification_models.py — ADD fields to existing Notification (line 71)
class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"
    id: Mapped[int]                      # exists
    user_id: Mapped[int]                 # exists (FK users.id, ondelete CASCADE)
    title: Mapped[str]                   # exists
    message: Mapped[str]                 # exists
    notification_type: Mapped[str]       # exists — USE as the type enum (see 2.1)
    severity: Mapped[str]                # exists
    is_read: Mapped[bool]                # exists
    read_at: Mapped[datetime | None]     # exists
    entity_type: Mapped[str | None]      # exists — 'mission' | 'run' | 'system'
    entity_id: Mapped[str | None]        # exists — mission_id / run_id
    meta: Mapped[str | None]             # exists — JSON string payload

    # ── PROPOSED ADDITIVE COLUMNS (new migration) ──
    actor_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 'system'|'agent'|'user'
    # NOTE: meta is currently TEXT (not JSONB). Optional follow-up: migrate to JSONB
    #       for queryability. Out of scope for v1-compatible feed; flagged as enhancement.
```

### 2.1 Type enum (use `notification_type` values, current code already does)
Existing `send_notification` keys off `mission_completed` / `mission_failed`
(`notification_service.py:578-581`). Standardize the feed vocabulary:
- `mission_update`  — status transition (RUNNING/COMPLETED/FAILED/APPROVED/PAUSED)
- `mission_completed` / `mission_failed` (alias kept for settings compat)
- `run_complete`   — Run finished
- `system_alert`   — maintenance / audit / platform notices
- `mention`        — reserved (settings `event_mention` already exists)

**Indexes already present / to add:**
- `ix_notifications_user_id` (FK, `notification_models.py:80`) — exists.
- **Proposed:** `CREATE INDEX ix_notifications_user_unread ON notifications(user_id) WHERE is_read = false;`
  (partial index for the hot unread-count + unread-only list paths).
- **Proposed:** `CREATE INDEX ix_notifications_user_created ON notifications(user_id, created_at DESC);`
  (supports the default feed sort without a filesort).

No changes to any existing table beyond the additive `notifications` columns above.

---

## 3. v2 API surface (proposed) — follow `app/api/v2/base` envelope

Create `app/api/v2/notifications.py` and register at `app/api/v2/__init__.py` (insert
`api_v2_router.include_router(notifications_router)` near line 23). Reuse the existing
`Notification` model + `_add_notification`/`send_notification` from
`app/services/notification_service.py` (import, do not duplicate).

Envelope contract (from `app/api/v2/base.py`): `ok()`, `paginated()`, `err()`.
Auth: `Depends(get_current_user)` (see `app/api/v2/missions.py` usage). Owner check:
local `_require_owner` mirroring `app/api/v2/missions.py` (compare `notification.user_id == current_user.id`).

| Method | Path | Purpose | Envelope |
|---|---|---|---|
| GET | `/api/v2/notifications` | List, paginated; query `?read=true|false&type=mission_update&page=&per_page=` | `paginated(items=NotificationItem, total, page, per_page, pages)` |
| POST | `/api/v2/notifications/{id}/read` | Mark one read (owner-checked) | `ok(NotificationItem)` or `err("NOT_FOUND", 404)` |
| POST | `/api/v2/notifications/read-all` | Mark all read | `ok({updated: N})` |
| GET | `/api/v2/notifications/unread-count` | Badge count | `ok({unread_count: int})` |
| GET | `/api/v2/notifications/stream` | SSE (token-auth, optional parity with v1) | `text/event-stream` |

Schema mapping (keep v1 shape for frontend compat):
```python
# v2 NotificationItem — mirror v1 (notification_service.py:79) but envelope it
class NotificationItem(BaseModel):
    id: int
    user_id: int
    title: str
    message: str = ""
    type: str            # = notification_type (frontend expects 'type')
    notification_type: str
    severity: str
    is_read: bool
    read_at: str | None
    entity_type: str | None
    entity_id: str | None
    meta: str | None
    created_at: str
    model_config = {"from_attributes": True}
```

**Route handlers (sketch, v2 envelope):**
```python
from app.api.v2.base import ok, paginated, err
from app.api.deps import get_current_user
from app.database import get_db
from app.models.notification_models import Notification
from sqlalchemy import select, func

router = APIRouter(prefix="/notifications", tags=["v2-notifications"])

@router.get("")
async def list_notifications(read: bool | None = None, type: str | None = None,
                             page: int = 1, per_page: int = 20,
                             user=Depends(get_current_user), db=Depends(get_db)):
    q = select(Notification).where(Notification.user_id == user.id)
    if read is not None:
        q = q.where(Notification.is_read == read)
    if type:
        q = q.where(Notification.notification_type == type)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar() or 0
    rows = (await db.execute(
        q.order_by(Notification.created_at.desc())
         .offset((page-1)*per_page).limit(per_page))).scalars().all()
    return paginated([NotificationItem.model_validate(r) for r in rows], total, page, per_page)

@router.get("/unread-count")
async def unread_count(user=Depends(get_current_user), db=Depends(get_db)):
    c = (await db.execute(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.is_read == False))).scalar() or 0
    return ok({"unread_count": c})

@router.post("/{nid}/read")
async def mark_read(nid: int, user=Depends(get_current_user), db=Depends(get_db)):
    item = (await db.execute(select(Notification).where(
        Notification.id == nid, Notification.user_id == user.id))).scalar_one_or_none()
    if not item:
        return err("NOT_FOUND", "Notification not found", status_code=404)
    item.is_read = True; item.read_at = datetime.now(UTC)
    await db.flush(); await db.refresh(item)
    return ok(NotificationItem.model_validate(item))

@router.post("/read-all")
async def mark_all_read(user=Depends(get_current_user), db=Depends(get_db)):
    res = await db.execute(select(Notification).where(
        Notification.user_id == user.id, Notification.is_read == False))
    n = 0
    for it in res.scalars().all():
        it.is_read = True; it.read_at = datetime.now(UTC); n += 1
    await db.flush()
    return ok({"updated": n})
```

> Note: v1 uses `POST /{id}/read` and `POST /read-all`; the frontend contract test
> (`app/tests/test_frontend_backend_contract.py:380-401`) expects `PATCH /api/users/me/notifications/{id}/read`.
> Decide ONE canonical method (recommend keeping POST to match v1 + current frontend
> `notification-api.ts:22-27`) and update the contract test assertion, not the method.

---

## 4. Where notifications are emitted (exact call sites)

### 4.1 Mission completion / failure  (THE MISSING WIRING)
**Recommended single chokepoint** — `MissionStatus._on_mission_status_set` validator:
emits `mission_update` (type `mission_completed`/`mission_failed`/`mission_update`) on every
transition. This catches all paths: `trigger_service.py:269`, `mission_execution.py:97/178`,
`expire_paused_missions.py:83`, `hitl_resume.py:86`. Implementation must be **lazy**: import
`send_notification` inside the validator, guard on `user_id` presence, and never raise (swallow
+ log, like `stream_message_to_llm`'s memory-recall guard documented in the test-baseline skill).
Must avoid recursion (validator fires on flush; only emit on actual status *change*).

**Alternative (explicit, lower-risk):** add emission at the two explicit completion sites:
- `app/services/trigger_service.py:269` (success/fail) — primary.
- `app/tasks/mission_execution.py:178` (async exec error → FAILED) — secondary.

Both should call the existing `send_notification(user_id, "mission_completed"|"mission_failed",
{"mission_id":..., "mission_name":..., "dashboard_url":...}, db)`.

### 4.2 Run completion
- `Run` status transitions land in the substrate executor / `blueprint_models.Run`. Add emission
  in the Run-finalize path (grep `RunStatus.COMPLETED` in `app/services/substrate/`). Emit type
  `run_complete` with `entity_type="run", entity_id=run.id`.

### 4.3 System alerts
- Health/audit/deploy events currently logged only. Add `send_notification(user_id, "system_alert", ...)`
  at: maintenance hooks, failed-background-task alerts (e.g. `mission_execution.py:194`
  `mission_execute_async_failure_log_failed`), and any place that today only `logger.warning`s
  a user-relevant failure.

---

## 5. Frontend shape (brief — DO NOT EDIT)

Symlink root: `/home/glenn/f/src` (never the spelled `FlowmannerV2-frontend` path).

**Already exists (reuse, do not rebuild):**
- Notifications panel + bell: `components/notifications/notification-bell.tsx`,
  `notification-panel.tsx`, `stores/notification-store.ts`, `hooks/use-notifications.ts`,
  `hooks/use-notification-sse.ts` (SSE at `/api/users/me/notifications/stream?token=`,
  `use-notification-sse.ts:28`), `lib/notification-api.ts` (calls `/api/users/me/notifications/*`),
  `lib/sdk/services/NotificationsService.ts`.
- Inbox page (currently HITL): `app/[locale]/inbox/page.tsx`, `components/inbox/inbox-page.tsx`,
  `inbox-item-card.tsx`, `inbox-bell.tsx`, `stores/inbox-store.ts`, `lib/inbox-api.ts`
  (calls `/api/inbox/*`), `hooks/use-inbox-sse.ts`.

**Repurposing `/inbox` into a notifications/activity feed — two options:**
- **(A) Keep `/inbox` = HITL, add a new `/notifications` route** that renders the existing
  `notification-panel` full-page. Lowest risk; HITL approvals stay separate. Recommended.
- **(B) Merge HITL + notifications into one `/inbox` feed.** Higher UX cohesion but couples two
  unrelated bounded contexts (approvals need action; notifications are read-only). Not recommended
  for v1.

**Subscription model (already implemented):** SSE via `use-notification-sse.ts` is the live path.
For v2, point `notification-api.ts` at `/api/v2/notifications/stream` (or keep v1 for now and add
v2 later). Polling fallback already present in `use-notifications.ts`.

**Badge:** `notification-bell.tsx` already reads `unread_count` from the store; wire it to the
v2 `/unread-count` once the v2 route ships (or leave on v1 — both work).

---

## 6. Dependency-ordered implementation checklist

1. **Decision:** choose emission strategy (4.1 chokepoint vs explicit). Recommend explicit at
   `trigger_service.py:269` + `mission_execution.py:178` for v1 (lower blast radius).
2. **Migration:** additive `notifications` columns (`actor_type`) + two indexes
   (`ix_notifications_user_unread`, `ix_notifications_user_created`). New file
   `alembic/versions/<ts>_notifications_feed_ext.py`. (Out of scope for this READ-ONLY plan —
   implement in a follow-up coding task.)
3. **v2 router:** create `app/api/v2/notifications.py` (§3). Register at
   `app/api/v2/__init__.py` (~line 23).
4. **Wire emission:** add `send_notification` calls at §4.1–4.3 call sites; pass `db` from the
   surrounding session (use `AsyncSessionLocal()` where no session is in scope, mirroring
   `mission_execution.py:174`).
5. **Frontend (separate task):** add `/notifications` route OR repurpose `/inbox` (option A);
   optionally repoint `notification-api.ts` to v2.
6. **Contract test fix:** reconcile `test_frontend_backend_contract.py:380-401`
   (POST vs PATCH method; `/users/me/notifications` path already matches v1).
7. **Tests:** add `tests/test_v2_notifications.py` (list/unread-count/mark-read/read-all,
   owner-isolation, type filter, pagination envelope shape). Add emission integration test
   (mission completion creates a `Notification` row for the owner).

---

## 7. Acceptance criteria

**Tests (backend, host-run, see `flowmanner-test-baseline` skill):**
- `pytest tests/test_v2_notifications.py -q` — all green; asserts v2 envelope
  (`data.items/pages`, `meta.request_id`, `error: null`).
- Owner-isolation: user A cannot read/mark user B's notification (404/403).
- Emission test: completing a mission (success path at `trigger_service.py:269`) creates exactly
  one `Notification` row for the mission owner with `notification_type in {mission_completed}` and
  `entity_id == mission_id`.
- `make lint` + `make test` baseline unchanged for unrelated suites.

**Live smoke (after deploy, human-gated per AGENTS.md — NOT in this read-only task):**
- `GET /api/v2/notifications` returns paginated envelope (not 404).
- `GET /api/v2/notifications/unread-count` returns `{data:{unread_count:N}}`.
- Completing a test mission produces a new row visible in `GET /api/v2/notifications`.
- SSE `/api/v2/notifications/stream?token=...` (or v1 equivalent) pushes the event live.
- Frontend `/inbox` (or new `/notifications`) renders the feed and the bell badge increments.

---

## 8. Risks / notes
- **Don't rebuild v1.** The v1 notifications system is live and frontend-backed. v2 is additive.
- **Emission in status validator (4.1 chokepoint) risks recursion/flush loops** — if chosen,
  guard strictly and emit only on value change; prefer explicit call sites for v1.
- **`meta` is TEXT, not JSONB** — querying inside payload requires parse. Acceptable for a
  read-only feed; JSONB migration is a separate enhancement.
- **Contract test mismatch** (`POST` vs `PATCH`) is pre-existing; resolve by aligning the test,
  not the API, to avoid breaking the shipped frontend (`notification-api.ts` uses POST).
- **Branch hygiene:** this worktree sits at `0f798031` on `agent/20260719-inbox/recon-plan`.
  Implement on a fresh feature branch; keep this recon branch read-only.
