# Draft: Flowmanner Audit Round 5 Fix Plan

## Requirements (from audit report)
- Fix login broken — CredentialsSignin for known credentials
- Fix /roadmap shows raw "API Error: 401 Not authenticated" instead of redirecting to login
- Fix "UnknownAction: Cannot parse action at /api/auth/login" NextAuth error
- Fix "Get started for free" CTA button — anchor link that doesn't navigate to signup
- Fix no user-visible error messages on signup form (22 AuthError console errors)
- Address 8 API routes returning 404 (low priority — likely not yet implemented)

## Technical Decisions

### Issue 1: Login Broken (CredentialsSignin)
**Root Cause Analysis**:
- `src/auth.ts` — NextAuth Credentials provider calls `authorize()` which POSTs to `${BACKEND_URL}/api/auth/login`
- The backend `/api/auth/login` endpoint (in `backend/app/api/v1/auth.py`) has **account lockout** logic: `record_failed_login()` is called BEFORE checking credentials (line 172)
- This means every login attempt increments the failure counter, even successful ones
- Wait — actually looking more carefully: `record_failed_login` is called, and if locked, it raises 429. But if NOT locked, it continues to check credentials.
- The real issue: The backend login endpoint returns `HTTPException(status=401, detail="Invalid credentials")` on failure
- In `src/auth.ts`, `authorize()` returns `null` when `!res.ok`, which triggers NextAuth's `CredentialsSignin` error
- **Most likely cause**: The user's password was changed, OR the account got locked from too many failed attempts during audits

**Fix approach**: 
1. Check if account is locked in backend (Redis-based lockout)
2. Verify credentials work via direct backend API call
3. If credentials are valid but still failing, investigate the auth chain

### Issue 2: /roadmap 401 Error
**Root Cause**: 
- `roadmap/page-client.tsx` calls `apiClient.get("/api/roadmap")` 
- `api-client.ts` checks if path requires auth: `path.startsWith("/api/") && !PUBLIC_PATHS.some(p => path.startsWith(p))`
- `/api/roadmap` is NOT in PUBLIC_PATHS, so it requires auth token
- When no token exists, it throws `ApiError(401, "Not authenticated — no token available")`
- The roadmap page is a PUBLIC page (shouldn't require auth for GET)
- The backend `list_roadmap_items()` endpoint does NOT require auth (no `Depends(get_current_user)`)
- **Fix**: Add `/api/roadmap` and `/api/roadmap/` to PUBLIC_PATHS in api-client.ts

### Issue 3: UnknownAction: /api/auth/login
**Root Cause**:
- `src/app/api/auth/[...nextauth]/route.ts` has a custom POST handler that checks for `/api/auth/register` and delegates everything else to `handlers.POST(request)`
- The `UnknownAction` error happens when NextAuth v5 receives a POST to `/api/auth/login` — but NextAuth v5 doesn't use `/api/auth/login` as an action endpoint
- In NextAuth v5 (Auth.js), credentials login is done via `signIn("credentials")` which POSTs to `/api/auth/callback/credentials`, NOT `/api/auth/login`
- The frontend `lib/auth.ts` has `authApi.login()` which POSTs to `/api/auth/login` — this is a CUSTOM endpoint that proxies to the backend
- But the NextAuth route handler at `[...nextauth]/route.ts` doesn't handle `/api/auth/login` properly
- **Fix**: Add explicit handling for `/api/auth/login` in the route.ts to proxy to backend, OR ensure the frontend uses the correct NextAuth v5 callback URL

### Issue 4: "Get started for free" CTA
**Root Cause**:
- `page-client.tsx` line ~155: `<Link href="/register">` — this IS a Next.js Link, not an anchor
- Wait, the audit says it's an anchor link. Let me re-read...
- The CTA section uses `<Link href="/register">` which should work
- BUT the audit says "Get started for free" — this maps to `tp("cta")` which is a translation key
- The Link goes to `/register` not `/en/signup` — might be the wrong path
- Actually looking at the audit: "Get started for free" CTA button doesn't navigate to signup — it's an anchor link that just scrolls
- This might be a different CTA than the one in page-client.tsx. Could be in the floating-nav or another component.

### Issue 5: Signup form error messages
- Signup page at `(auth)/signup/page.tsx` — needs to be checked for error display
- The 22 AuthError console errors suggest server action failures not being surfaced to UI

### Issue 6: 8 API routes returning 404 (LOW)
- `/api/templates`, `/api/models`, `/api/rag/documents`, `/api/analytics/executions`, `/api/marketplace/items`, `/api/team/members`, `/api/settings`, `/api/notification`
- These are frontend pages that call API endpoints that don't exist on the backend yet
- Low priority — pages exist but backend endpoints not implemented

## Research Findings

### Auth Flow Architecture
1. **NextAuth v5** (`src/auth.ts`) handles server-side auth for protected routes via middleware
2. **Zustand auth-store** (`src/stores/auth-store.ts`) handles client-side auth state with localStorage tokens
3. **Backend FastAPI** (`backend/app/api/v1/auth.py`) provides REST API for login/register/me
4. **Nginx** proxies `/api/auth/*` to frontend, `/api/*` to backend (10.99.0.3:8000)

### Key Conflict
- The frontend has TWO auth systems running simultaneously:
  - NextAuth v5 (server-side, cookie-based, for middleware protection)
  - Custom token-based auth (client-side, localStorage, via `authApi` and `apiClient`)
- The `api-client.ts` uses localStorage tokens, NOT NextAuth session cookies
- This means NextAuth protects routes via middleware, but API calls use a separate token system

### Roadmap Page
- Public page (not in `protectedPaths` in middleware.ts)
- Uses `apiClient.get("/api/roadmap")` which requires localStorage token
- Backend endpoint is public (no auth required)
- Fix: Add to PUBLIC_PATHS

### Nginx Proxy
- `/api/auth/*` → frontend:3000 (NextAuth)
- `/api/*` → backend:8000 (FastAPI)
- This means `/api/auth/login` goes to frontend, but the frontend route handler proxies register and delegates rest to NextAuth

## Open Questions
1. What are the actual login credentials? (guillouxglenn4@gmail.com / Admin123 may have changed)
2. Should the roadmap page be fully public or auth-gated?
3. Should we consolidate the dual auth system or keep both?

## Scope Boundaries
- INCLUDE: Fix all 6 audit issues
- EXCLUDE: Major auth system refactoring (keep both systems working)
- EXCLUDE: Implementing missing backend API endpoints (issue 6 is low priority, just add stubs or handle gracefully)
