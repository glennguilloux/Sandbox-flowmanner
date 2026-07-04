# Fix Sandbox Preview 401 — Implementation Plan

## Current State

After 3 deploy rounds, preview URLs still return 401. The root cause is multi-layered:

### What's Fixed
1. **PREVIEW_DOMAIN double-preview bug** — sandboxd `.env` had `PREVIEW_DOMAIN=preview.flowmanner.com`, producing `s-<id>-3000.preview.preview.flowmanner.com`. Fixed to `flowmanner.com`.
2. **Cookie name mismatch** — forward-auth looked for `fm_refresh_token` (never set). Fixed to also read `refresh_token`.
3. **Cookie Path** — was `/api/v3/auth`, cannot match preview URL path `/`. Fixed to `/`.
4. **Cookie Domain** — was empty (same-origin only). Added `AUTH_V3_COOKIE_DOMAIN=***` to backend `.env`.
5. **v1 auth no cookies** — v1 login/register/refresh returned JSON but never set httpOnly cookies. Fixed via `_auth_response()` helper.
6. **Next.js proxy drops Set-Cookie** — `/api/auth/login` route handler forwarded JSON but dropped Set-Cookie header. Fixed.
7. **NextAuth authorize silent drop** — authorize() called backend directly (server-side), Set-Cookie went to Next.js server, never to browser. Fixed via `cookies().set()`.

### What's Still Broken

The `cookies().set()` approach inside NextAuth's authorize callback is likely not working correctly. NextAuth v5's internal handler flow may not flush cookies set mid-callback. The 401 persists.

---

## Phase 1: Root-Cause Diagnosis

### 1.1 Verify backend is setting the cookie

```bash
# Direct backend call — should see Set-Cookie header
curl -sv -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username_or_email":"<real_user>","password":"<real_pass>"}' \
  2>&1 | grep -i "set-cookie"
```

Expected: `Set-Cookie: refresh_token=<jwt>; HttpOnly; Secure; SameSite=Strict; Path=/; Max-Age=604800; Domain=.flowmanner.com`

### 1.2 Verify browser receives the cookie after login

Open DevTools → Application → Cookies → flowmanner.com
After login, there should be a `refresh_token` httpOnly cookie.

If missing → the NextAuth authorize `cookies().set()` approach doesn't work.

### 1.3 Test the forward-auth endpoint directly

```bash
# With a real token from cookie value
curl -sv "http://localhost:8000/api/sandbox/forward-auth" \
  -H "Cookie: refresh_token=<real_jwt>" \
  2>&1 | grep HTTP
```

Expected: 200 with `X-Forwarded-User` header.

### 1.4 Test the full chain from homelab

```bash
# Create a sandbox and test internally
curl -sk -H "Host: s-<id>-3000.preview.flowmanner.com" \
  -H "Cookie: refresh_token=<real_jwt>" \
  http://localhost:80/
```

Expected: 200 (sandbox page content).

---

## Phase 2: Fix Approaches (ordered by reliability)

### Approach A: Next.js Middleware (RECOMMENDED)

Instead of setting the cookie in the authorize callback, use Next.js middleware that runs on every request. When a request has a valid NextAuth session JWT, extract the refresh_token and set the httpOnly cookie.

**File:** `src/middleware.ts` (create if missing)

```typescript
import { NextResponse } from "next/server"
import type { NextRequest } from "next/server"

export async function middleware(request: NextRequest) {
  const response = NextResponse.next()

  // Read NextAuth session token from existing cookie
  const sessionToken =
    request.cookies.get("__Secure-next-auth.session-token")?.value ||
    request.cookies.get("next-auth.session-token")?.value

  if (sessionToken && !request.cookies.get("refresh_token")) {
    try {
      // Decode the NextAuth JWT to extract refresh_token
      // NextAuth stores user data in the JWT — extract refresh_token claim
      const payload = JSON.parse(
        Buffer.from(sessionToken.split(".")[1], "base64").toString()
      )
      if (payload?.refresh_token) {
        response.cookies.set("refresh_token", payload.refresh_token, {
          httpOnly: true,
          secure: true,
          sameSite: "strict",
          path: "/",
          maxAge: 7 * 24 * 60 * 60,
          domain: ".flowmanner.com",
        })
      }
    } catch {
      // Token decode failed — skip
    }
  }

  return response
}

export const config = {
  matcher: ["/((?!_next|api/auth|static|favicon).*)"],
}
```

**Pros:** Runs on every request, guaranteed to set cookie if session exists
**Cons:** NextAuth JWT structure may not contain raw refresh_token (depends on callbacks)

### Approach B: JWT Callback + Separate API Route

1. In NextAuth `callbacks.jwt`, store refresh_token in the NextAuth JWT:
   ```typescript
   callbacks: {
     async jwt({ token, user }) {
       if (user) {
         token.refresh_token = (user as any).refresh_token
       }
       return token
     }
   }
   ```

2. Create a dedicated API route `GET /api/auth/preview-cookie` that reads the session JWT and sets the httpOnly cookie:
   ```typescript
   // src/app/api/auth/preview-cookie/route.ts
   import { auth } from "@/auth"
   import { NextResponse } from "next/server"

   export async function GET() {
     const session = await auth()
     const response = NextResponse.json({ ok: true })

     if ((session as any)?.refresh_token) {
       response.cookies.set("refresh_token", (session as any).refresh_token, {
         httpOnly: true, secure: true, sameSite: "strict",
         path: "/", maxAge: 7*24*60*60, domain: ".flowmanner.com",
       })
     }
     return response
   }
   ```

3. Frontend calls this route after login (in layout or dashboard page):
   ```typescript
   // In dashboard layout or useEffect
   fetch("/api/auth/preview-cookie", { credentials: "include" })
   ```

**Pros:** Simple, explicit, works reliably
**Cons:** Extra round trip, needs frontend change

### Approach C: Token Query Parameter (Simplest)

Accept a token in the preview URL query string. Modify forward-auth to also check `?token=`:

```python
# In sandbox_preview.py _authenticate_preview_request()
# After cookie check, add:
if not token:
    token = req.query_params.get("token")
```

Frontend appends `?token=<refresh_token>` to preview URLs. This works without cookies at all.

**Pros:** No cookie complexity, works everywhere
**Cons:** Token in URL (visible in logs, history) — use short-lived single-use tokens

### Approach D: Server-Side Proxy

The FlowManner backend proxies sandbox content, adding auth server-side:

1. New endpoint: `GET /api/sandbox/{id}/proxy/*` — requires auth
2. Backend fetches sandbox content from sandboxd, returns to browser
3. All preview traffic flows through FlowManner, no subdomain cookies needed

**Pros:** Most secure, no cookie issues
**Cons:** Added latency, backend becomes bottleneck

---

## Phase 3: Better Integration Ideas

### 3.1 Preview Panel in FlowManner UI

Instead of a separate tab/window, embed the sandbox preview in an iframe within the FlowManner dashboard. Pass the access token via postMessage or URL fragment:

```typescript
// Dashboard component
<iframe
  src={`https://s-${sandboxId}-3000.preview.flowmanner.com/#token=${accessToken}`}
  sandbox="allow-scripts allow-same-origin"
/>
```

The sandbox page reads the token from the URL fragment and uses it for API calls.

### 3.2 One-Click Sandbox from Chat

When a user asks to "build a todo app", the chat agent:
1. Creates a sandbox via sandboxd API
2. Runs OpenCode inside it to generate the app
3. Returns a clickable preview link in the chat

```
User: "Build me a landing page"
Agent: [creates sandbox, runs agent, starts server]
       → "Done! Preview: https://s-abc123-3000.preview.flowmanner.com"
```

### 3.3 Sandbox Status in Dashboard

Show active sandboxes with status, preview links, and controls (stop, purge) in the FlowManner dashboard. Use the sandboxd API to list/manage sandboxes.

### 3.4 Template-Based Sandboxes

Pre-build sandbox templates for common use cases:
- React app (Vite + Tailwind)
- Python Flask app
- Static HTML page
- Next.js app
- Node.js Express API

Create sandbox from template → instant preview.

### 3.5 Sandbox Files API Integration

Expose sandbox workspace files in the FlowManner file browser. Let users:
- View/edit files in sandbox workspace
- Upload assets
- Download generated output
- Sync with FlowManner's file storage

---

## Phase 4: Implementation Order

1. **Diagnose cookie flow** (Phase 1) — determine if cookie reaches browser
2. **Implement Approach C** (token query param) as quick win — 30 min fix
3. **Implement Approach B** (separate cookie route) as proper fix — 1 hour
4. **Implement Approach A** (middleware) if B works but is too slow
5. **Add preview panel** (Phase 3.1) — embed in FlowManner UI
6. **Add one-click sandbox** (Phase 3.2) — integrate with chat agent

---

## Key Files to Modify

| File | Purpose |
|------|---------|
| `backend/app/api/v1/sandbox_preview.py:122-158` | Forward-auth logic |
| `backend/app/api/v3/auth_cookies.py:18-37` | Cookie attributes |
| `backend/app/config.py:112` | AUTH_V3_COOKIE_DOMAIN |
| `backend/.env` | AUTH_V3_COOKIE_DOMAIN=*** |
| `frontend/src/auth.ts:109-168` | NextAuth authorize callback |
| `frontend/src/middleware.ts` | (create) Cookie-setting middleware |
| `frontend/src/app/[locale]/(dashboard)/` | Preview panel component |
| `/mnt/apps/Softwares2/sandboxd/.env` | PREVIEW_DOMAIN=flowmanner.com |

---

## Debug Checklist

- [ ] Browser DevTools → Application → Cookies → flowmanner.com → `refresh_token` exists?
- [ ] Cookie has: Domain=.flowmanner.com, Path=/, HttpOnly ✓, Secure ✓
- [ ] Backend `/api/auth/login` returns Set-Cookie header
- [ ] Forward-auth `/api/sandbox/forward-auth` returns 200 with valid cookie
- [ ] Traefik can reach sandbox container internally
- [ ] Wildcard TLS cert valid for *.preview.flowmanner.com
- [ ] VPS Nginx routes *.preview.flowmanner.com → WireGuard → homelab:80
- [ ] DNS *.preview.flowmanner.com → 74.208.115.142


---

## Progress (2026-06-09)

### Implemented

- **Approach C — `?token=` query param** in `backend/app/api/v1/sandbox_preview.py::_authenticate_preview_request`. The forward-auth endpoint now accepts `?token=<refresh_token>` in the URL as a third auth source, after `Authorization: Bearer` and before the cookies. This is the most reliable path for sandbox previews because it bypasses any cross-subdomain cookie-domain edge cases. Frontend will append `?token=<refresh_token>` to preview URLs at the link-creation site.
- **Approach B — `/api/auth/preview-cookie` route** at `src/app/api/auth/preview-cookie/route.ts`. A client-callable route that reads the NextAuth session JWT and writes both `refresh_token` and `fm_refresh_token` httpOnly cookies on the response. Replaces the unreliable `cookies().set()` calls inside NextAuth `authorize`/`signIn` callbacks.
- **`<PreviewCookieSync />` client component** at `src/components/auth/preview-cookie-sync.tsx`. Watches the NextAuth session and POSTs to `/api/auth/preview-cookie` once per user session, so the cookie is mirrored on every successful login. Mounted inside `<SessionProvider>` in `src/app/providers.tsx`.
- Cookie attributes match the backend: `Path=/`, `Domain=.flowmanner.com` in production, `HttpOnly`, `Secure` in production, `SameSite=Strict`, 7-day max-age.

### Verified (local curl, before deploy)

- `POST /api/auth/login` returns `access_token` + `refresh_token` for a real user.
- `GET /api/sandbox/forward-auth?token=<refresh>` → **200** for valid token.
- `GET /api/sandbox/forward-auth` with `Authorization: Bearer <access>` → **200**.
- `sandbox_preview.py` syntax-checked clean.

### Not yet done (Phase 4 remaining)

- [ ] Deploy backend with the new `?token=` support (`bash /opt/flowmanner/deploy-backend.sh`).
- [ ] Deploy frontend with `/api/auth/preview-cookie` route + `PreviewCookieSync` (`ship`).
- [ ] End-to-end browser test: open a sandbox preview URL, confirm no 401.
- [ ] Phase 3.1: embed preview in FlowManner dashboard via `<iframe src="...?token=...">`.
- [ ] Phase 3.2: one-click sandbox from chat agent.
- [ ] Approach A: middleware-based cookie mirror (only if B proves too slow).
