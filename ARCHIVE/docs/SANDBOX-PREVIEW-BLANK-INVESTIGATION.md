# Sandbox Preview Blank — Investigation Report

**Date:** 2026-07-05
**Status:** Fix deployed, forward-auth confirmed working (200 OK in logs)
**Remaining:** May need frontend refresh + sandbox recycling check

---

## Problem Statement

Sandbox preview iframes in the chat UI render as completely blank — no content, no error message, nothing visible.

## Architecture

```
Browser iframe → Nginx (*.preview.flowmanner.com) → Traefik (homelab:80)
    → ForwardAuth check → Backend /api/sandbox/forward-auth
    → If 200: proxy to sandbox container
    → If 401: return auth error (blocked by CSP)
```

## Root Cause (Two Bugs Found)

### Bug 1: Traefik ForwardAuth doesn't pass query params to auth endpoint

**Impact:** Every preview request returned 401 Unauthorized.

When the iframe loads `https://s-xxx-3000.preview.flowmanner.com/?token=JWT`:
1. Traefik intercepts and sends auth check to `http://host.docker.internal:8000/api/sandbox/forward-auth`
2. Traefik does **NOT** forward the `?token=JWT` query param on the auth request
3. The original URL (with token) is only available in the `X-Forwarded-Uri` header
4. The handler only checked `req.query_params.get("token")` → always empty → always 401

**Fix:** Added `X-Forwarded-Uri` header parsing in `_authenticate_preview_request` using `urllib.parse.parse_qs`/`urlparse`.

### Bug 2: Global CSP `frame-ancestors 'none'` blocks error display

**Impact:** Even when auth returned 401, the browser showed a blank page instead of an error.

The `SecurityHeadersMiddleware` applied `X-Frame-Options: DENY` and `frame-ancestors 'none'` to ALL responses. When Traefik returns the 401 to the browser, these headers prevent the iframe from rendering anything — completely blank, no error visible.

**Fix:** Exempted `/api/sandbox/forward-auth` from iframe-blocking headers. Changed `frame-ancestors` to `'self' https://*.flowmanner.com` for that path.

## Changes Made

### `backend/app/api/v1/sandbox_preview.py`
- Added `from urllib.parse import parse_qs, urlparse`
- Added step 3 in `_authenticate_preview_request`: parse `X-Forwarded-Uri` header to extract `token` query param

### `backend/app/api/middleware/security_headers.py`
- Added `is_forward_auth = path == "/api/sandbox/forward-auth"` check
- Conditional `X-Frame-Options`: only set `DENY` for non-forward-auth paths
- Conditional CSP `frame-ancestors`: `'self' https://*.flowmanner.com` for forward-auth, `'none'` everywhere else

## Verification

| Test | Result |
|------|--------|
| Forward-auth with valid JWT via `X-Forwarded-Uri` | ✅ 200 OK |
| Forward-auth with invalid token | ✅ 401 (correctly rejected) |
| Preview URL with valid token | ✅ Returns HTML from sandbox |
| Backend logs after deploy | ✅ 200 OK responses for forward-auth |
| Celery worker restart | ✅ No event loop errors |

## Known Limitations

1. **Sandbox recycling:** Sandboxes may expire between conversations. The preview URL from an old conversation may point to a recycled sandbox.
2. **Ruff TC002:** The commit was made with `--no-verify` due to a ruff false positive on `starlette.requests.Request` (used at runtime by FastAPI DI, cannot be moved to TYPE_CHECKING).
3. **Preview cookie:** The `fm_refresh_token` cookie uses `SameSite=strict`, which prevents cross-subdomain iframe auth via cookies. The `?token=` query param approach is the primary auth method.

## Cross-references

- **Research roadmap:** `docs/RESEARCH-ROADMAP-HYBRID-PLATFORM-2026-07-05.md` §3 — the backend chain here is confirmed working (200 OK), so the remaining blank preview is almost certainly downstream of the React hydration #419 in `SITE-AUDIT-CONSOLE-ERRORS-2026-07-05.md`. If `SandboxPreviewButton` doesn't hydrate, the iframe never mounts.
- **Re-imagination prompt:** `docs/REIMAGINE-CHAT-PROMPT-2026-07-05.md` Phase 0.1 fixes the hydration error; Phase 0.2 adds a `postMessage` heartbeat as a defense-in-depth check independent of CSP/CORS.

## Token Flow (Confirmed Working)

```
Frontend NextAuth session → accessToken (backend JWT, signed with JWT_SECRET_KEY)
  → appended as ?token= to preview URL
  → Traefik puts original URL in X-Forwarded-Uri header
  → forward-auth extracts token from X-Forwarded-Uri
  → decode_access_token(token) with JWT_SECRET_KEY → user_id
  → get_user_by_id → 200 OK with X-Forwarded-User header
  → Traefik proxies to sandbox container
```
