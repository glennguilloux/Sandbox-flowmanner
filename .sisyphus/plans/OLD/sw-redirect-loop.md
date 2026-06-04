# Fix Service Worker Redirect Loop on Deploy

## TL;DR

> After every deploy, users get redirect loops because the SW's `CACHE_VERSION` is a hardcoded `"fm-v3"` that never changes between deploys. Old JS chunks in `/_next/static/` cache are never purged. Fix: bump version, switch static assets to stale-while-revalidate, and force fresh HTML for navigation requests.
>
> **Deliverables:**
> - Updated `/home/glenn/FlowmannerV2-frontend/public/sw.js` with 4 edits
> - Frontend deployed to VPS
>
> **Estimated Effort:** Short
> **Parallel Execution:** NO — sequential (single file edits, then deploy)

---

## Context

### Original Request
After every deploy, users get redirect loops on the live site. Users must clear all browser data (cache, SW, localStorage) to fix. Marketing says this looks terrible for customers.

### Root Cause Analysis

**Root Cause**: `CACHE_VERSION = "fm-v3"` is hardcoded and never changes. The activate handler only deletes caches where `!k.startsWith(CACHE_VERSION)` — but since every deploy uses the same prefix, old caches are NEVER deleted. Old JS chunks from `/_next/static/` live forever.

**Why one user refresh doesn't fix it**: The new SW activates via `skipWaiting()` and `clients.claim()`, but the old cached JS chunks are still in the `fm-v3-static` cache. The navigation request gets fresh HTML (new route config, new chunk hashes), but the HTML references JS chunks that the old SW serves from cache-first — the old JS has stale router logic → redirect loop.

**How the fix works**:
1. Bump `CACHE_VERSION` to `"fm-v4"` → old `fm-v3-*` caches get deleted on activate
2. Switch `/_next/static/` from `cacheFirst` to `staleWhileRevalidate` → instant cache hit + background refresh, so even if a chunk is stale it gets updated immediately
3. Add `cache: "no-store"` for navigation requests → always get fresh HTML from the server
4. The existing `pwa-provider.tsx` `SW_UPDATED` handler already reloads the page when the new SW activates

### Interview Summary
- **Goal**: Fix redirect loop, single file change to `sw.js`
- **Codebase**: `/home/glenn/FlowmannerV2-frontend/public/sw.js` (268 lines)
- **Deploy**: `bash /opt/flowmanner/deploy-frontend.sh` from homelab
- **Key files**: `sw.js`, `pwa-provider.tsx`, `next.config.ts`

---

## Work Objectives

### Core Objective
Eliminate post-deploy redirect loops by ensuring stale JS chunks are never served after a new SW activates.

### Concrete Deliverables
- `/home/glenn/FlowmannerV2-frontend/public/sw.js` — 4 targeted edits
- Frontend deployed to VPS (all users get new SW on next visit)

### Definition of Done
- [ ] `sw.js` CACHE_VERSION is `"fm-v4"`
- [ ] `/_next/static/` uses `staleWhileRevalidate` (not `cacheFirst`)
- [ ] Navigation requests use `networkFirstFresh` (with `cache: "no-store"`)
- [ ] `networkFirstFresh` function exists after `cacheFirst` function
- [ ] Deploy completes successfully on VPS

### Must Have
- All 4 edits to `sw.js`
- Deploy to production VPS
- No other files modified (single-file fix)

### Must NOT Have (Guardrails)
- Do NOT change `pwa-provider.tsx` — its `SW_UPDATED` → reload behavior is correct
- Do NOT change `next.config.ts` — the `sw.js` headers are already correct
- Do NOT change the push notification, background sync, or message handler code
- Do NOT add new npm dependencies
- Do NOT refactor unrelated SW code

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: NO (no SW-specific tests)
- **Automated tests**: None
- **Framework**: None
- **Agent-Executed QA**: Manual verification after deploy

### QA Policy
Every task includes agent-executed QA scenarios. Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.
- Use the Skill tool (no subagents) for simple verifications
- Browser E2E: Use Playwright MCP for interactive testing

---

## Execution Strategy

### Sequential (single file + deploy)

```
Task 1: Edit sw.js — all 4 changes (CACHE_VERSION bump, staleWhileRevalidate, networkFirstFresh, navigation fix)
  └─ Verifier: grep for the 4 patterns in the edited file

Task 2: Deploy frontend to VPS
  └─ Verifier: docker compose ps on VPS shows updated image + health check
```

---

## TODOs

- [ ] 1. Edit `/home/glenn/FlowmannerV2-frontend/public/sw.js` — all 4 changes

  **What to do:**

  **Edit 1 — Bump CACHE_VERSION (line 4):**
  ```
  BEFORE: const CACHE_VERSION = "fm-v3";
  AFTER:  const CACHE_VERSION = "fm-v4";
  ```

  **Edit 2 — Switch navigation to networkFirstFresh (lines 66-69):**
  ```
  BEFORE:
    if (request.mode === "navigate") {
      event.respondWith(networkFirst(request, PRECACHE));
      return;
    }

  AFTER:
    if (request.mode === "navigate") {
      event.respondWith(networkFirstFresh(request, PRECACHE));
      return;
    }
  ```

  **Edit 3 — Switch static assets to staleWhileRevalidate (lines 77-81):**
  ```
  BEFORE:
    // Static assets — cache-first
    if (STATIC_PATTERNS.some((p) => url.pathname.startsWith(p))) {
      event.respondWith(cacheFirst(request, RUNTIME_STATIC));
      return;
    }

  AFTER:
    // Static assets — stale-while-revalidate (instant from cache, background refresh)
    if (STATIC_PATTERNS.some((p) => url.pathname.startsWith(p))) {
      event.respondWith(staleWhileRevalidate(request, RUNTIME_STATIC));
      return;
    }
  ```

  **Edit 4 — Add networkFirstFresh function (insert after cacheFirst function, after line 134):**
  ```js
  async function networkFirstFresh(request, cacheName, timeout = 30_000) {
    const cache = await caches.open(cacheName);
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeout);
      const response = await fetch(request, {
        signal: controller.signal,
        cache: "no-store",
      });
      clearTimeout(timer);
      if (response.ok) {
        cache.put(request, response.clone());
      }
      return response;
    } catch {
      const cached = await cache.match(request);
      if (cached) return cached;
      if (request.mode === "navigate") {
        const offline = await caches.match("/offline.html");
        if (offline) return offline;
      }
      return new Response("Offline", { status: 503, statusText: "Offline" });
    }
  }
  ```

  **Must NOT do:**
  - Do NOT change any push notification, background sync, or message handler code
  - Do NOT modify the `networkFirst` or `cacheFirst` functions (they're still used by other handlers)
  - Do NOT touch any other file

  **Recommended Agent Profile:**
  - **Category**: `quick` — simple file edits
  - **Skills**: `flowmanner` (for deployment context)

  **Parallelization:**
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Sequential (Task 1 → Task 2)
  - **Blocks**: Task 2 (deploy depends on edit)
  - **Blocked By**: None

  **References:**
  - `/home/glenn/FlowmannerV2-frontend/public/sw.js` — the file to edit (lines 4, 66-69, 77-81, after 134)

  **Acceptance Criteria:**
  - [ ] `grep 'fm-v4' /home/glenn/FlowmannerV2-frontend/public/sw.js` returns a match
  - [ ] `grep 'staleWhileRevalidate(request, RUNTIME_STATIC)' /home/glenn/FlowmannerV2-frontend/public/sw.js` returns a match
  - [ ] `grep 'networkFirstFresh(request, PRECACHE)' /home/glenn/FlowmannerV2-frontend/public/sw.js` returns a match
  - [ ] `grep 'async function networkFirstFresh' /home/glenn/FlowmannerV2-frontend/public/sw.js` returns a match
  - [ ] `grep 'cache: "no-store"' /home/glenn/FlowmannerV2-frontend/public/sw.js` returns a match

  **QA Scenarios:**

  ```
  Scenario: Verify sw.js edits are correct
    Tool: Bash (grep)
    Steps:
      1. grep -n 'fm-v4' /home/glenn/FlowmannerV2-frontend/public/sw.js
      2. grep -n 'staleWhileRevalidate(request, RUNTIME_STATIC)' /home/glenn/FlowmannerV2-frontend/public/sw.js
      3. grep -n 'networkFirstFresh(request, PRECACHE)' /home/glenn/FlowmannerV2-frontend/public/sw.js
      4. grep -n 'async function networkFirstFresh' /home/glenn/FlowmannerV2-frontend/public/sw.js
      5. grep -n 'cache: "no-store"' /home/glenn/FlowmannerV2-frontend/public/sw.js
    Expected Result: All 5 greps return at least one match
    Evidence: .sisyphus/evidence/task-1-sw-edits.txt
  ```

  **Commit**: YES
  - Message: `fix(sw): eliminate post-deploy redirect loops via cache versioning + stale-while-revalidate`
  - Files: `public/sw.js`

---

- [ ] 2. Deploy frontend to VPS

  **What to do:**
  - Run the deploy script from homelab
  - ⚠️ Deploy takes ~4 minutes. Use `timeout=300` or `background=true, notify_on_complete=true`
  - If deploy times out, DO NOT retry — check if it completed: `sshpass -p '@Geegee197623' ssh -o StrictHostKeyChecking=accept-new root@74.208.115.142 "cd /opt/flowmanner && docker compose ps"`

  **Commands:**
  ```bash
  bash /opt/flowmanner/deploy-frontend.sh
  ```

  **Must NOT do:**
  - Do NOT retry a timed-out deploy without checking completion first
  - Do NOT edit any files on the VPS directly

  **Recommended Agent Profile:**
  - **Category**: `quick`
  - **Skills**: `flowmanner`

  **Parallelization:**
  - **Can Run In Parallel**: NO
  - **Blocks**: None
  - **Blocked By**: Task 1

  **Acceptance Criteria:**
  - [ ] Deploy script exits with code 0
  - [ ] VPS health check passes

  **QA Scenarios:**

  ```
  Scenario: Verify VPS deploy succeeded
    Tool: Bash (sshpass)
    Steps:
      1. sshpass -p '@Geegee197623' ssh -o StrictHostKeyChecking=accept-new root@74.208.115.142 "cd /opt/flowmanner && docker compose ps"
      2. curl -s -o /dev/null -w '%{http_code}' https://flowmanner.com/sw.js
    Expected Result: Docker containers running, sw.js returns 200, response body contains "fm-v4"
    Evidence: .sisyphus/evidence/task-2-deploy.txt
  ```

---

## Success Criteria

### Final Checklist
- [ ] `CACHE_VERSION` is `"fm-v4"` in sw.js
- [ ] `/_next/static/` uses staleWhileRevalidate
- [ ] Navigation requests use networkFirstFresh with `cache: "no-store"`
- [ ] Deploy completes successfully
- [ ] Live sw.js contains "fm-v4"
