# BE API Error Audit — Findings

**Branch under audit:** `agent/2026-07-11-intent-execution-architecture` (resolved at HEAD `f6fc3637`, identical to the `wt/be-audit-api-20260713` checkout).
**Scope:** `backend/app/api/` (v1/v2/v3 routers, deps.py, `api/middleware/`), `backend/app/websocket/`, `backend/app/schemas/`, `backend/app/middleware/`.
**Method:** Read the actual files (not grep-only) for every flagged item. Several suspected bugs were confirmed as **false positives** and excluded: `await require_mission_access(...)` / `await require_graph_access(...)` in `mission_ws.py` are correct (both services are `async`); the `WorkspaceMessage` import in `mission_ws.py:330` is valid; `StrictValidationMiddleware._is_json_serializable` *does* recurse into list items (`validation_middleware.py:62-66`); the `_broadcast_presence(...)` call (`mission_ws.py:81`) passes `status` positionally and `skip_sid` as kwarg correctly; `_redis_allowed` *does* apply `effective_burst` (`rate_limit.py:73-82`).

Path prefix below is `backend/app/...` (repo root is the worktree; `app/` lives under `backend/`).

---

🔴 **WebSocket connect admits anonymous users (user_id=0) into mission/graph/workspace rooms** — `backend/app/websocket/mission_ws.py:124-159` (connect handler)

```python
user_id = int(payload.get("sub", 0))      # line 139 (handshake) / 149 (environ)
...
if user_id:
    await sio.save_session(sid, {"user_id": user_id})
else:
    logger.debug("WebSocket connect: no valid JWT (sid=%s)", sid)
    # Don't reject — allow anonymous for mission/graph subscriptions
```

`int(payload.get("sub", 0))` yields `0` for a missing/invalid `sub`. Because `0` is truthy-checked as `if user_id:` → `0` is falsy, so a missing `sub` correctly stays anonymous, **but** any JWT whose `sub` claim is the integer/string `"0"` (or a malformed token that decodes to `{"sub": 0}`) is admitted with `user_id = 0`. A client presenting such a token is then treated as a real, authenticated principal: `subscribe_mission` (line 172-189) and `subscribe_graph` (212-236) read `user_id` from the session and call `require_mission_access(db, mission_uuid, 0)` / `require_graph_access(db, workflow_id, 0)`, and `workspace:subscribe` (263-301) gates only on DB membership for `user_id=0`. An attacker who can mint/obtain a token with `sub=0` (or who exploits the fact that `0` is a valid-looking id) reaches the access-check path as a non-None user and, if any resource happens to be owned by user 0, is admitted to its private room. The comment explicitly says anonymous is *allowed*, yet the code admits `0` as a valid user id rather than distinguishing "no auth" from "authenticated as user 0".

```python
# Fix: treat 0 / missing sub as anonymous, never as a real principal.
sub = payload.get("sub")
user_id = int(sub) if isinstance(sub, (str, int)) and str(sub) not in ("", "0") else None
if user_id:
    await sio.save_session(sid, {"user_id": user_id})
# else: truly anonymous — do not set user_id
```

---

🔴 **`APIVersioningMiddleware` is defined but never mounted** — `backend/app/api/middleware/versioning.py` + `backend/app/main_fastapi.py:109-198`

```python
# main_fastapi.py mounts these middlewares, in order:
app.add_middleware(AuthCookieMiddleware)
app.add_middleware(ScopeValidationMiddleware)
app.add_middleware(CORSMiddleware, ...)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AuditMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(GlobalRateLimitMiddleware)
app.add_middleware(GraphQLDeprecationMiddleware)
app.add_middleware(RateLimitHeadersMiddleware)      # v2
app.add_middleware(IdempotencyFinalizationMiddleware)
# ...v2/v3 routers included...
# APIVersioningMiddleware is NEVER added.
```

`APIVersioningMiddleware` exists (`versioning.py:71`) and `app/api/AGENTS.md` line 26 + line 90 declare it "the single source of truth for `X-API-Version` headers" and that it negotiates version via `Accept-Version` / `?version=` and rejects invalid versions with `400`. None of that runs, because no `add_middleware(APIVersioningMiddleware)` call exists anywhere in `app/` (verified by search — only the class def and doc references). Consequence in normal operation:
- `X-API-Version` is **never** set on any response (the header the v1/v2/v3 contracts promise is absent).
- `Accept-Version: v9` / `?version=v9` is silently ignored (no 400).
- Deprecation/`Sunset`/`Link` headers are never applied (that part is partly covered by the separate `GraphQLDeprecationMiddleware`, but only for the deprecated-registry paths, not for the versioning middleware's logic).

This is a silent, always-on failure of a documented capability.

```python
# Fix: mount it (before the routers are included, anywhere after CORS):
app.add_middleware(APIVersioningMiddleware)
```

---

🔴 **v2/v3 exception handlers are shadowed by the v3 registrations — v2 errors lose their envelope** — `backend/app/main_fastapi.py:262` + `backend/app/api/v2/middleware.py:112-142` + `backend/app/api/v3/middleware.py:42-81`

`FastAPI` stores exception handlers in a dict keyed by exception class; re-registering the same class **overwrites** the previous handler. Registration order in `main_fastapi.py`:

1. `general_error_handler` for `Exception` (line 262)
2. `register_v2_exception_handlers(app)` → `v2_http_exception_handler` (HTTPException) + `v2_general_exception_handler` (Exception) (line 408)
3. `register_v3_exception_handlers(app)` → `v3_http_exception_handler` (HTTPException) + `v3_general_exception_handler` (Exception) (line 422) — **LAST wins**

So the *effective* app-wide handlers for both `HTTPException` and `Exception` are the **v3** ones. They each check `if not request.url.path.startswith("/api/v3"): return PlainJSON(status, {"detail": exc.detail})`. For any `/api/v2/...` error (including `raise HTTPException(400/403/404/...)` and unhandled 500s), the v3 handler runs and returns a **bare `{"detail": ...}` dict** — *not* the v2 envelope (`{"data": null, "meta": {...}, "error": {"code", "message", ...}}`) that `backend/app/api/v2/AGENTS.md` mandates for every v2 response and that `v2_http_exception_handler` was written to produce. The v2 envelope is therefore silently dropped on every v2 error path. (v1 was always bare `{"detail": ...}`, so its behavior is unchanged; v3 errors are correct because the v3 handler *is* the active one.)

```python
# Fix options:
# (a) Make each version handler fall through to the next by checking ALL prefixes, or
# (b) register a single unified handler that branches on path prefix and emits the
#     correct envelope (v2 vs v3 vs bare), instead of three mutually-overwriting ones.
# Minimal correct version: in v3's handlers, only short-circuit for /api/v3; for
# /api/v2 let the v2 handler own it — but since v3 overwrites v2, you must
# merge: e.g. a top-level handler that dispatches by prefix.
```

---

🟡 **`MetricsMiddleware` collects nothing — Prometheus counters are never incremented** — `backend/app/api/middleware/metrics.py:14-19`

```python
class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        return response
```

`REQUEST_COUNT` and `REQUEST_LATENCY` are defined at module load (lines 6-11) but `dispatch` never references them. No label is ever set, no observation recorded. Any dashboard/scrape built on these metrics shows **zero requests and no latency** — silently incorrect observability data (matches the audit brief's "silently produce incorrect data"). The middleware is effectively a no-op named "Metrics".

```python
# Fix: actually observe.
RESPONSE_LATENCY.observe(process_time)            # Histogram
REQUEST_COUNT.labels(request.method, request.url.path, response.status_code).inc()
```

---

🟡 **`get_current_session` treats the refresh cookie as an access token (latent — currently unused in routing but documented as the v3 auth dependency)** — `backend/app/api/deps.py:312-342`

```python
refresh_token = request.cookies.get("fm_refresh_token")   # v3 cookie is "refresh_token", set in auth_cookies.py:29
if refresh_token:
    token_payload = v3_decode_access_token(refresh_token)
```

`AuthCookieMiddleware` (main_fastapi.py:113) extracts cookie `"refresh_token"` into `request.state.refresh_token_cookie`; `auth_cookies.py` sets the cookie with key `"refresh_token"` (line 29). But `get_current_session` reads `request.cookies.get("fm_refresh_token")` (deps.py:312) — the **wrong cookie name**. The correct name (`refresh_token`) is only read in `sandbox_preview.py` (legacy v1 path). More importantly, even if the name were right, the cookie holds a **refresh** token, while `v3_decode_access_token` (auth_v3_service.py:158-164) *requires* `payload.get("type") == "access"` and returns `None` otherwise — so a refresh token would decode to `None` and the function would fall through to "Session not found." Net: `get_current_session` cannot authenticate a cookie-based v3 session at all. This is latent because **no v3 route currently depends on `get_current_session`** (only `require_scope` references it internally, and `get_v3_session`/`get_refresh_from_request` are what `auth.py` actually uses). But `deps.py` and `backend/app/api/v3/AGENTS.md` present `get_current_session` as *the* v3 auth dependency, so it is a trap waiting to be wired in.

```python
# Fix: read the correct cookie and use the refresh-token decoder, not the access-token decoder.
from app.api.v3.auth_cookies import get_refresh_from_request
refresh_token = get_refresh_from_request(request)   # handles "refresh_token" cookie + body
if refresh_token:
    token_payload = v3_decode_refresh_token(refresh_token)  # type == "refresh"
```

---

🟡 **`ScopeValidationMiddleware` is a no-op security gate** — `backend/app/middleware/scope_validator.py:11-65`

```python
SCOPE_REQUIREMENTS: dict[str, dict[str, list[str]]] = {}   # never populated
...
if key in SCOPE_REQUIREMENTS:        # always False — nothing registers a scope
    ...
return await call_next(request)
```

No code anywhere calls `register_scope_requirement(...)` (verified by search), so `SCOPE_REQUIREMENTS` is always empty and every `/api/v3/*` request passes straight through. The middleware claims to enforce OAuth2-style scopes but enforces nothing. It also short-circuits `admin`/`owner` roles (line 40) before any scope check. Because v3 workspace routes use **membership** checks (`_check_workspace_access`) instead of scopes (documented in `v3/AGENTS.md`), this is currently harmless — but it is dead, misleading security code that would silently authorize everything if someone *believed* it was active.

```python
# Fix: either remove it, or wire register_scope_requirement() calls for the
# v3 endpoints that should require scopes, and have the handler actually deny.
```

---

## VERDICT

**🔴 Blockers: 3** — (1) anonymous/attacker `user_id=0` admission into authenticated WebSocket rooms in `mission_ws.py`; (2) `APIVersioningMiddleware` defined but never mounted, so the promised `X-API-Version` header, version negotiation, and invalid-version 400s never happen; (3) v2/v3 exception-handler registrations overwrite each other, so the v3 handler wins app-wide and every `/api/v2/*` error returns a bare `{"detail": ...}` instead of the mandated v2 envelope.

**🟡 Suggestions: 3** — (4) `MetricsMiddleware` never increments its Prometheus counters (silently zero metrics); (5) `get_current_session` reads the wrong cookie name and decodes a refresh token as an access token, so it cannot authenticate a v3 cookie session (latent — currently unused in routing, but documented as the v3 auth dependency); (6) `ScopeValidationMiddleware` is an empty security gate (no route registers a scope, so it always allows).

**Single highest-risk error:** the **WebSocket anonymous-admission bug in `mission_ws.py:124-159`** — it is the only blocker that is simultaneously a security boundary failure and reachable on every unauthenticated socket connection, and the `sub=0` confusion lets a crafted/low-privilege token be treated as a real principal during `subscribe_mission` / `subscribe_graph` / `workspace:subscribe`.

> Read-only audit. No source files were modified.
