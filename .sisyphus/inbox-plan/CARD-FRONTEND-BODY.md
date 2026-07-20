# Inbox/Notifications — Frontend Build Card (new /notifications route, Option A)

You are the **engineering-frontend-developer** persona for Flowmanner. Implement the
frontend half of the Notifications/activity-feed feature. The backend v2 router is DONE
and verified (`backend/app/api/v2/notifications.py`, routes tested 7 passed). Your job is
the frontend surface only.

Repo root is the SYMLINK `/home/glenn/f` (resolves to `/home/glenn/FlowmapperV2-frontend`).
NEVER use the spelled-out path — always `/home/glenn/f`. Read the verified backend plan at
`/opt/flowmanner/.sisyphus/inbox-plan/PLAN.md` §5 and the backend deliverable at
`/opt/flowmanner/.sisyphus/inbox-plan/BACKEND-DONE.md` first.

## Context — what already exists (REUSE, do not rebuild)
- `src/components/notifications/notification-bell.tsx` — bell + unread badge.
- `src/components/notifications/notification-panel.tsx` — the feed list panel.
- `src/lib/notification-api.ts` — calls `/api/users/me/notifications/*` (v1).
- `src/hooks/use-notifications.ts` — polling.
- `src/hooks/use-notification-sse.ts` — SSE at `/api/users/me/notifications/stream?token=`.
- `src/stores/notification-store.ts` — client state.
- `src/app/[locale]/inbox/page.tsx` — currently the HITL approval page (KEEP IT; do NOT
  repurpose the HITL inbox into the notifications feed).

## Do THIS
1. **Add a new route** `src/app/[locale]/notifications/page.tsx` (Option A from plan §5):
   render a full-page notifications feed reusing `notification-panel.tsx` + the store +
   `use-notifications.ts`. This keeps HITL approvals separate from the read-only feed.
2. **Point the API at v2.** The backend now serves:
   - `GET /api/v2/notifications` (paginated envelope: `data.items`, `data.pages`, `meta`)
   - `POST /api/v2/notifications/{id}/read`
   - `POST /api/v2/notifications/read-all`
   - `GET /api/v2/notifications/unread-count` → `{data:{unread_count:N}}`
   - (SSE `/api/v2/notifications/stream` exists in plan; wire it ONLY if low-risk, else
     leave the v1 SSE for now.)
   Adapt `src/lib/notification-api.ts` (or add a v2 variant the new page imports) so the
   new `/notifications` page consumes the v2 envelope shape. Do NOT break the existing v1
   callers (other pages may still use v1) — add, don't overwrite, unless a caller is
   exclusively the notifications feed.
   IMPORTANT envelope note: v2 `err("NOT_FOUND", …, status_code=404)` returns **HTTP 200**
   with `error.code == "NOT_FOUND"` (not a real 404). The frontend must check
   `response.error?.code` for failures, not just HTTP status. Match the existing v2 client
   pattern in the repo if one exists; otherwise guard both.
3. **Wire the bell badge** to v2 `/unread-count` (or keep v1 — both work; prefer v2 for the
   new page). Keep the existing bell component working.
4. **TypeScript must typecheck**: `cd /home/glenn/f && npx tsc --noEmit` must pass for your
   changed files (you may need to symlink `node_modules` from the main repo if the worktree
   lacks it: `ln -sfn /home/glenn/FlowmapperV2-frontend/node_modules /home/glenn/f/.worktrees/<wt>/node_modules`
   then `rm -f` it before finishing so the worktree stays clean).

## Do NOT (hard limits)
- Do NOT edit backend files (separate card, already done + verified).
- Do NOT repurpose `/inbox` (HITL) into the notifications feed — add `/notifications`.
- Do NOT run `git add -A` or `git add .` — stage EXPLICIT paths only
  (`git add src/app/[locale]/notifications/... src/lib/notification-api.ts ...`). The repo
  holds many live worktrees; `git add -A` stages them as gitlinks and contaminates `master`.
- Do NOT commit unrelated files. Commit ONLY your frontend notifications work to the card's
  exclusive branch (so a worktree reclaim cannot destroy it). Do NOT push, do NOT open a PR.
- Do NOT deploy.

## Finish
When `tsc --noEmit` passes and the page renders the feed against the v2 envelope:
- Write a deliverable summary to `/opt/flowmanner/.sisyphus/inbox-plan/FRONTEND-DONE.md`
  (what changed, file:line, tsc result, any unverified risk — e.g. live SSE not exercised).
- Call `kanban_block` (block-for-review) with a one-line summary. Do NOT mark done/closed.
