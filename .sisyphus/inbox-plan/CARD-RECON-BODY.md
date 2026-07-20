# Inbox Feature — Recon + Build Plan (READ-ONLY, plan only)

You are acting as the **engineering-backend-architect** persona for Flowmanner.
Your job is RESEARCH + PLAN only. Do NOT write feature code, do NOT run alembic
migrations, do NOT commit. You may explore the repo, read files, and grep.

## Context
The live site `https://flowmanner.com/inbox` is a frontend route that requires
auth but has NO backend behind it — every candidate API path
(`/api/v2/inbox`, `/api/v2/notifications`, `/api/v2/user/notifications`,
`/api/v2/me`, `/api/v2/session`, `/api/auth/session`) returns `404` / `null`.
The owner decided the Inbox should be a **Notifications / activity feed**:
mission updates, run completions, system alerts.

## Your tasks
1. **Prove the gap is real in the repo (not just live 404s).**
   - `grep -rn` the backend for `inbox|notification|activity` across
     `app/api/v2`, `app/models`, `app/schemas`, `app/services`. Confirm there is
     no notifications model/route/handler.
   - Note any EXISTING event-emission points that would naturally feed an
     activity feed: mission status transitions, Run completion, blueprint
     triggers, websocket/SSE broadcasts, audit_log rows.

2. **Design the data model.** Propose a `Notification` (or `ActivityEvent`)
   SQLAlchemy model: fields, FK to user, read/unread state, type enum
   (mission_update | run_complete | system_alert | ...), payload JSON,
   timestamps. Keep it additive — no changes to existing tables beyond an FK.

3. **Design the v2 API surface** following the v2 contract
   (`app/api/v2/base` `ok()`/`paginated()`/`err()` envelope,
   `Depends(get_current_user)`, local `_require_owner` where relevant):
   - `GET /api/v2/notifications` — paginated, filter by read/unread+type.
   - `POST /api/v2/notifications/{id}/read` — mark read.
   - `POST /api/v2/notifications/read-all` — mark all read.
   - `GET /api/v2/notifications/unread-count` — badge count.
   - Where should notifications be emitted? Identify the exact call sites
     (file:line) where mission/run completion should create a row.

4. **Frontend shape (brief).** Point at the existing Next.js app under
   `/home/glenn/f/src` (symlink — never the spelled path) for the Inbox page
   route and shared layout. Describe what page/component to add and how it would
   poll or subscribe (existing SSE/WS patterns). Do NOT edit frontend files.

5. **Write the PLAN** to a STABLE path OUTSIDE any worktree:
   `/opt/flowmanner/.sisyphus/inbox-plan/PLAN.md`
   It must contain: confirmed gap evidence (file:line greps), proposed model,
   proposed v2 routes with envelope shape, exact emission call sites,
   frontend page plan, a dependency-ordered implementation checklist, and the
   acceptance criteria (tests + live smoke). Keep it concrete and file:line
   anchored — no vague hand-waving.

## Hard constraints
- READ-ONLY. No commits, no migrations, no feature code.
- The deliverable is the PLAN.md file at the stable path above.
- When done, call `kanban_block` (block-for-review) with a one-line summary.
- Do not trust memory; verify against current source on this branch.
