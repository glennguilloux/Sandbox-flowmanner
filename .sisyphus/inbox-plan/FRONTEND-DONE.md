# Frontend Build — DONE (v2 Notifications full-page feed, Option A)

Branch: `agent/20260719-inbox/frontend-build`
Worktree: `/home/glenn/FlowmannerV2-frontend/.worktrees/t_4d0f6d91`
Workspace root symlink: `/home/glenn/f` (resolves to `/home/glenn/FlowmannerV2-frontend`)

## What changed

Implemented the frontend half of the Notifications/activity-feed feature (Option A
from plan §5): a new full-page `/notifications` feed that consumes the **v2**
backend envelope, while leaving all v1 callers (the bell, the HITL `/inbox`)
untouched.

### New files
1. **`src/lib/notification-api-v2.ts`** — v2 API client. Talks to
   `GET/POST /api/v2/notifications*`. Unwraps the `{data,meta,error}` envelope
   **manually** (raw `fetch`), mirroring `roadmap/page-client.tsx`, and raises
   `NotificationV2Error` when `error` is present — **including the v2
   HTTP-200-with-`error.code==="NOT_FOUND"` logical-error case** the backend
   uses. Exposes `fetchNotificationsV2`, `fetchUnreadCountV2`,
   `markNotificationReadV2`, `markAllNotificationsReadV2`.
2. **`src/hooks/use-notifications-v2.ts`** — drives the **existing global
   `notification-store`** from the v2 API (`setNotifications`, `setUnreadCount`,
   optimistic `markAsRead`/`markAllAsRead`). Keeps the bell badge in sync
   because both read/write the same store. `NOT_FOUND` on the list endpoint is
   treated as an empty feed (not an error), per the backend contract.
3. **`src/components/notifications/notification-feed.tsx`** — full-page feed UI
   (filter tabs All/Unread, per-item mark-read, mark-all-read, load-more, empty
   + loading + error states). Accessible (`role=tab/tablist`, `aria-selected`,
   `role=alert`), keyboard-friendly, reuses the store `Notification` shape.
   NOTE: the dropdown `notification-panel.tsx` is a popover (`absolute
   bottom-full`) and cannot be embedded full-page, so the feed renders an
   equivalent list with the same data contract + visual language rather than
   literally mounting the popover. This still satisfies "reuse the store +
   feed data" — the store is the shared piece.

### Modified files
4. **`src/app/[locale]/(dashboard)/notifications/page.tsx`** — was a bare
   `redirect("/settings/notifications")`. Now renders `<NotificationFeed />`
   (the `/notifications` URL, within the `(dashboard)` group so it keeps the
   dashboard error boundary). This is the Option-A route the task asked for.
   A separate top-level `src/app/[locale]/notifications/page.tsx` was **not**
   created because it would collide with `(dashboard)/notifications` (route
   groups don't add to the URL) — same `/notifications` path, ambiguous route.
   Replacing the redirect page is the conflict-free way to ship the feed at
   exactly `/notifications`.
5. **`src/i18n/locales/en.json`** — added feed strings to the `notifications`
   namespace (`feedTitle`, `feedSubtitle`, `filterLabel`, `all`, `unread`,
   `markAllRead`, `markRead`, `loading`, `noNotifications`, `loadMore`,
   `untitled`) without touching the existing settings strings.

### Left untouched (non-breaking, per task)
- `src/lib/notification-api.ts` (v1) — bell still uses it.
- `src/components/notifications/notification-bell.tsx`, `notification-panel.tsx`.
- `src/hooks/use-notification-sse.ts` — v1 SSE kept (task said wire v2 SSE only
  if low-risk; left v1, which already works).
- `src/stores/notification-store.ts` — reused as-is.

## Type / lint / build results
- `npx tsc --noEmit` → **exit 0** (clean).
- `npx eslint <4 changed files>` → **exit 0**.
- `npx next build` → **exit 0**; `/[locale]/notifications` present in route table.
- (node_modules symlink into the worktree was created for tsc/eslint/build and
  **removed** before finishing, so the worktree stays clean.)

## Unverified / risk notes
- **Live API not exercised** (no auth session / no deployed v2 backend hit from
  this headless run). The envelope-unwrap + `error.code` guard is implemented
  per the verified backend contract (`BACKEND-DONE.md`) but not run against a
  live `GET /api/v2/notifications`. Recommend a post-deploy smoke: open
  `/notifications`, confirm the list + unread badge populate and mark-read works.
- **v2 SSE not wired** — the new page relies on polling via the v2 hook; the
  bell continues to use v1 SSE. A follow-up could repoint
  `use-notification-sse.ts` at `/api/v2/notifications/stream`, but that was
  explicitly optional and left out to avoid risk.
- **`(dashboard)/notifications` URL resolution**: this page now serves the feed,
  not a redirect to settings. The settings page remains at
  `/settings/notifications` (unchanged). Confirm no other code depends on
  `/notifications` redirecting to settings.
