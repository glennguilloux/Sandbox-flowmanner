# Flowmanner Site Audit — Console Errors Report

**Date:** 2026-07-05
**Auditor:** Automated browser audit (Chrome DevTools)
**Account:** guillouxglenn4@gmail.com
**Scope:** All major pages + backend API logs

---

## Summary

| Page | Errors | Warnings | Network Failures | Status |
|------|--------|----------|------------------|--------|
| `/dashboard` | 0 | 0 | 0 | ✅ Clean |
| `/chat` | 1 critical | 1 | 0 | ❌ Broken |
| `/missions` | 0 | 1 | 0 | ⚠️ Minor |
| `/agents` | 0 | 0 | 0 | ✅ Clean |
| `/settings` | 0 | 0 | 0 | ✅ Clean |
| `/playground` | 0 | 0 | 0 | ✅ Clean |
| `/integrations` | 0 | 0 | 0 | ✅ Clean |
| `/integrations/browse` | 0 | 1 | 2 × 404 | ❌ Broken |

**Overall:** 6/8 pages clean. 2 pages with issues.

---

## Critical Errors

### 1. React Hydration Error #419 — `/chat`

**Severity:** 🔴 Critical
**Page:** `https://flowmanner.com/chat`
**When:** Occurs when sending a message in the chat

**Error:**
```
Uncaught Error: Minified React error #419; visit https://react.dev/errors/419
for the full message or use the non-minified dev environment for full errors
and additional helpful warnings.
```

**What it means:** React error #419 is a **server/client hydration mismatch** — the HTML rendered by the server doesn't match what React expects on the client. This causes React to throw away the server-rendered HTML and re-render from scratch, which can cause visible flickering, layout shifts, and in some cases blank content.

**Impact:** This is likely related to the blank sandbox preview. If the chat message component (which renders the `SandboxPreviewButton` and iframe) fails to hydrate correctly, the preview iframe may never render.

**Recommended fix:** Run the app in development mode (`NODE_ENV=development`) to see the full error message with the specific component that's mismatching. The minified error only gives a number — the dev build will show the exact component and DOM node.

---

### 2. 404 Not Found — `/integrations/browse`

**Severity:** 🟡 Medium
**Page:** `https://flowmanner.com/integrations/browse`
**Count:** 2 failed requests

**Failed requests:**
- `GET /api/marketplace/listings?type=integration` → **404**
- `GET /api/marketplace/listings/featured` → **404**

**What it means:** The integrations browse page tries to fetch marketplace listings from the backend, but the `/api/marketplace/listings` endpoint doesn't exist (or isn't registered).

**Impact:** The integration marketplace shows empty/broken content.

**Recommended fix:** Either implement the marketplace listings API endpoint, or update the frontend to handle the missing endpoint gracefully (fallback to a different data source or hide the browse tab).

---

## Warnings

### 3. Form Field Accessibility — Multiple Pages

**Severity:** 🟢 Low
**Pages:** `/chat`, `/missions`, `/integrations/browse`

**Warning:**
```
A form field element should have an id or name attribute
```

**Counts:**
- `/chat`: 3 form fields missing id/name
- `/missions`: 1 form field missing id/name
- `/integrations/browse`: 2 form fields missing id/name

**Impact:** Accessibility issue. Screen readers and automated testing tools rely on form field identifiers. No functional impact.

**Recommended fix:** Add `id` or `name` attributes to all `<input>`, `<select>`, and `<textarea>` elements.

---

## Backend API Errors (from Docker logs)

| Endpoint | Status | Notes |
|----------|--------|-------|
| `GET /api/sandbox/forward-auth` | 401 | **Mostly fixed** — now returns 200 with valid tokens. Some 401s from expired/missing tokens are expected. |
| `POST /api/v3/auth/sessions/refresh` | 401 | Token refresh failure — likely expired refresh token. Normal if user session expired. |
| `GET /api/marketplace/listings?type=integration` | 404 | Endpoint not implemented |
| `GET /api/marketplace/listings/featured` | 404 | Endpoint not implemented |

No 500 errors or exceptions found in backend logs.

---

## Pages Audited

### ✅ `/dashboard` — Clean
No console errors, no network failures, no warnings.

### ❌ `/chat` — React Error #419
- React hydration mismatch (critical)
- 3 form fields missing id/name (warning)

### ⚠️ `/missions` — Minor Warning
- 1 form field missing id/name (warning)

### ✅ `/agents` — Clean
No console errors, no network failures, no warnings.

### ✅ `/settings` — Clean
No console errors, no network failures, no warnings.

### ✅ `/playground` — Clean
No console errors, no network failures, no warnings.

### ✅ `/integrations` — Clean
No console errors, no network failures, no warnings.

### ❌ `/integrations/browse` — 404 Errors
- 2 × 404 for marketplace API endpoints
- 2 form fields missing id/name (warning)

---

## Recommendations (Priority Order)

1. **🔴 P0: Fix React hydration error #419 on `/chat`** — This is likely the root cause of the blank sandbox preview. Run in dev mode to identify the mismatching component.

2. **🟡 P1: Implement or stub `/api/marketplace/listings`** — The integrations browse page calls endpoints that don't exist. Either implement them or update the frontend to handle the missing API.

3. **🟢 P2: Add id/name to form fields** — Accessibility improvement across `/chat`, `/missions`, and `/integrations/browse`.

4. **🟢 P2: Handle token refresh failures gracefully** — The 401 on `/api/v3/auth/sessions/refresh` suggests the frontend isn't handling expired refresh tokens well on the integrations page.

---

## Cross-references

- **Research roadmap:** `docs/RESEARCH-ROADMAP-HYBRID-PLATFORM-2026-07-05.md` — the hydration error (#1 above) is the most likely blocker for the still-blank sandbox preview despite the backend fix in `SANDBOX-PREVIEW-BLANK-INVESTIGATION.md`. Fixing #1 unblocks the preview.
- **Re-imagination prompt:** `docs/REIMAGINE-CHAT-PROMPT-2026-07-05.md` — Phase 0 of that prompt addresses the three issues above as the stabilization gate before any new chat surface work.
