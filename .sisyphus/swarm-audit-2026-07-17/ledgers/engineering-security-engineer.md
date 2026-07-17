# Threat Model Ledger — Flowmanner Security Engineer Lens
**Date**: 2026-07-17 | **Version**: 1.0 | **Author**: Security Engineer (fmw2)
**Method**: Read-only source audit of `backend/` in worktree `t_cb25b558` (branch `agent/2026-07-17-sec/swarm`).
**Lens & question I own**: VERIFY — "what breaks under an attacker?" Threat-model the whole stack. Top priority: auth chain, tenant isolation, SSRF, input validation, LLM prompt-injection surface.

> All claims cite `path:line`. No source was modified (READ-ONLY task).

---

## Top 5 Findings

### F1 — [CRITICAL] `ScopeValidationMiddleware` is a silent auth-bypass for `/api/v3/*`
**Observation**: `app/middleware/scope_validator.py` is registered as a global middleware, but it only acts on `/api/v3/` paths (line 21). It has **two independent fail-open paths** that let a request reach any v3 handler without a valid token:
- Line 25-26: if the `Authorization` header is missing or doesn't start with `Bearer `, it calls `call_next` and **passes the request straight through** — no 401.
- Line 33-36: if the JWT **fails to decode for *any* reason** (`except Exception`), it also calls `call_next` and passes through.

The middleware is the *only* thing that could pre-empt v3 routing, so a malformed/expired/garbage Bearer token (or none at all) flows to the v3 routers. Whether that becomes a real breach depends on each router also calling `get_current_user`/`get_current_session` — but the middleware's contract ("no valid token → blocked") is **not enforced**. Any v3 route that forgets its auth dependency (or is added later) is silently reachable unauthenticated. This is a classic "security control that looks like a gate but fails open."

**Evidence**: `app/middleware/scope_validator.py:21,25-26,33-36`
**Severity**: Critical (authentication-bypass enabler / fail-open control)
**Fact vs Rec**: Fact.

### F2 — [HIGH] SSRF protection is inconsistently applied across BYOK model-discovery endpoints
**Observation**: The module `app/api/v1/api_keys.py` contains a thorough, default-deny SSRF guard (`_is_safe_outbound_url`, lines 72-135) and a pinned-IP httpx backend (`_PinnedNetworkBackend`, lines 138-157) used by `fetch_provider_models` (line 219). **But** `validate_api_key` (line 350) and `discover_models` (line 441) do **not** call that guard:
- `discover_models` (line 450) calls `_get_base_url(provider)` and then `client.get(f"{base_url}/models", ...)` (line 454) with **no `_is_safe_outbound_url` check**. `_get_base_url` (line 286) returns a *user-influenced* `base_url` when provided, or the OpenAI default. If a `base_url` can reach this path (e.g. via the `BYOKValidateRequest` shape or a future call site), it would fetch an arbitrary internal URL carrying the user's `api_key` in the `Authorization` header (line 455) — cloud-metadata / internal-service credential theft. Note `discover_models` lacks the IP-pinning that defeats DNS-rebinding too.
- `validate_api_key` (line 363) only ever hits the hardcoded `_OPENAI_MODELS_URL` (line 347), so it is SSRF-safe *today*, but it is the inconsistency that matters: the secure helper exists and is bypassed by sibling endpoints.

**Evidence**: `app/api/v1/api_keys.py:72-135,138-157,219,286-289,350-366,441-456`
**Severity**: High (SSRF / credential exfiltration if `base_url` is reachable on `discover_models`)
**Fact vs Rec**: Fact (the guard exists and is not applied on `discover_models`).

### F3 — [HIGH] File upload writes user-controlled filename to disk with no sanitization
**Observation**: `app/api/v1/file.py:upload_file` (line 48) reads the uploaded file and writes it to `UPLOAD_DIR / f"{file_id}_{file.filename or 'unnamed'}"` (line 56). `file_id` is a UUID (safe), but `file.filename` is **concatenated unmodified** into the path. A filename like `../../../etc/cron.d/x` (or, on the default `UPLOAD_DIR=/opt/flowmanner/uploads`, an absolute or `..`-traversal name) is not normalized. Python's `Path` does not strip `..` segments, so a crafted filename can write outside `UPLOAD_DIR`. Even without traversal, the server later serves these bytes back via `FastAPIFileResponse` (import at line 9) keyed only by `file_id` — but the *write* step is the exposure. Also no content-type / magic-byte / size validation is visible in this handler (only `len(content_data)` is stored). Executable upload + later execution path (e.g. if uploads dir is web-served) is the blast radius.

**Evidence**: `app/api/v1/file.py:19,48-57,9`
**Severity**: High (path traversal on write / unrestricted upload)
**Fact vs Rec**: Fact.

### F4 — [HIGH] Tenant/workspace isolation relies on *every* call site remembering the membership check
**Observation**: Multi-tenant isolation is enforced per-endpoint, not at the ORM/data layer. `require_mission_access` (`app/services/mission_service.py:53-92`) correctly checks `WorkspaceMember` for the mission's `workspace_id`, **but** the check is opt-in: a mission with **no `workspace_id`** falls back to `user_id` ownership (line 65). Many v1/v2 routers resolve `workspace_id` from a header/query (`get_workspace_id`, `app/api/deps.py:366`) that the *caller* supplies — there is no server-side guarantee that the requested `workspace_id` matches the user's memberships unless the specific handler calls `_check_workspace_access` / `require_mission_access`. The CQRS `v3/workspaces.py` comment (line 10-20) acknowledges the scope-middleware enforces *nothing* for v3 and relies entirely on `_check_workspace_access`. This is a "missing default-deny at the data layer" pattern: isolation is as strong as the least-forgotten check. A new endpoint that queries `Mission`/`MemoryEntry`/`ChatThread` by id without the membership join is an IDOR waiting to happen.

**Evidence**: `app/services/mission_service.py:53-92`; `app/api/deps.py:366-377`; `app/api/v3/workspaces.py:10-20`
**Severity**: High (potential IDOR / cross-tenant read if any call site omits the join)
**Fact vs Rec**: Fact (the opt-in, header-derived scoping model is evidenced; an actual IDOR would need a per-endpoint sweep — flagged as the highest-priority verification for a follow-up).

### F5 — [MEDIUM] JWT auth accepts `HS256` with a single shared symmetric secret; no algorithm pinning / `alg=none` guard at the dependency layer
**Observation**: All JWT decode sites use `algorithms=["HS256"]` (e.g. `app/dependencies/auth_deps.py:48`, `app/middleware/service_auth.py:30`, `app/websocket/mission_ws.py:138`, `app/websocket/presence.py:73-77`). Using an allow-list of one algorithm is *good* (it rejects `alg=none` and asymmetric confusion), so this is not an immediate vuln. The concern is operational: a single `JWT_SECRET_KEY` (env, `auth_deps.py:29-33`) signed with HS256 means **token forgery is equivalent to secret leakage**, and the secret is shared across v1/v2/v3/WebSocket/ScopeValidator with no key rotation or per-audience binding. `sub` is the only identity claim widely used; there is no `aud`/`iss` check at `auth_deps.py:48` (unlike `v2/auth.py:278-282` which checks `type`). Token theft → full impersonation, no audience scoping.

**Evidence**: `app/dependencies/auth_deps.py:24,48`; `app/websocket/mission_ws.py:138-139`; `app/websocket/presence.py:73-79`
**Severity**: Medium (key-management / blast-radius, not an exploitable bug today)
**Fact vs Rec**: Fact.

---

## Biggest Single Miss / Blind Spot (my lens)
**The "security middleware" that the codebase *believes* gates v3 is fail-open and enforces nothing.** `ScopeValidationMiddleware` (`app/middleware/scope_validator.py`) is the most dangerous kind of security control: it *looks* like an auth gate in the middleware stack, logs nothing when it passes a request through, and — because no route ever calls `register_scope_requirement` (confirmed by `app/api/v3/workspaces.py:10-13`) — its scope logic is dead code. The real protection is the per-route `get_current_user`/`get_current_session` dependency, which is correct *where present* but is **not centrally guaranteed**. The blind spot: there is no defense-in-depth backstop. One forgotten `Depends(get_current_user)` on a v3 route (or a future refactor that moves a handler) turns an "admin-only" endpoint into an unauthenticated one with **zero log signal**. The platform's auth posture is only as strong as the most-forgotten dependency, and nothing in the request pipeline will catch it.

---

## 3 Ranked Brainstorm Recommendations (Flowmanner-specific)

**R1 — Replace the fail-open ScopeValidationMiddleware with a fail-closed auth pre-check (or delete it and add a mandatory auth dependency test).**
- *Idea*: Make the global middleware reject (401) any `/api/v3/*` request lacking a valid token, instead of `call_next`-ing on missing header (line 25-26) or decode error (line 33-36). Better: remove the middleware entirely and enforce auth via a FastAPI `dependencies=[Depends(get_current_session)]` on the `api_v3_router` mount, plus a CI test that asserts every v3 route requires auth.
- *Why now*: It is the single highest-leverage fix — converts a silent bypass enabler into a guaranteed gate. Cheap relative to blast radius.
- *Effort*: S (logic change + a couple of tests).
- *File:line anchor*: `app/middleware/scope_validator.py:21,25-26,33-36` (and `app/main_fastapi.py` router-mount site).

**R2 — Centralize SSRF enforcement as a required call for ALL outbound provider fetches, and add path-traversal + content validation to uploads.**
- *Idea*: (a) Route `discover_models` (`app/api/v1/api_keys.py:450-455`) and any future BYOK fetch through `_is_safe_outbound_url` + `_PinnedNetworkBackend` (the existing secure helper) so the bypass class F2 closes. (b) In `app/api/v1/file.py:56`, replace raw `file.filename` concatenation with `os.path.basename()` + UUID-only storage + magic-byte/size checks before `write_bytes`.
- *Why now*: Both are externally-reachable (upload + model-discovery) and are the classic SSRF/unrestricted-upload pair that leads to RCE on a homelab host. The secure helper already exists — this is mostly wiring.
- *Effort*: S–M.
- *File:line anchor*: `app/api/v1/api_keys.py:286-289,441-456`; `app/api/v1/file.py:19,48-57`.

**R3 — Add a data-layer tenancy backstop + an automated IDOR sweep test.**
- *Idea*: Introduce a mandatory `workspace_id` (or explicit `is_global=True`) column constraint and a query helper that *always* ANDs the caller's workspace membership, so a missing join in a handler fails closed instead of returning cross-tenant rows. Pair with a regression test that asserts each `Mission`/`MemoryEntry`/`ChatThread` GET-by-id endpoint returns 404 for a non-member. This retires the "isolation is opt-in per call site" risk in F4.
- *Why now*: As the platform ships more v3 workspace endpoints (billing, teams, invites), the count of isolation-critical call sites grows; a centralized backstop scales better than per-route review.
- *Effort*: L (schema + query-layer refactor + test suite).
- *File:line anchor*: `app/services/mission_service.py:53-92`; `app/api/deps.py:366-377`; `app/api/v3/workspaces.py:71-92`.

---

## Confidence & Cross-Check Request
- **Confidence**: High on F1, F2, F3 (directly evidenced in source). Medium on F4's *exploitability* — the isolation *model* is evidenced as opt-in/header-derived, but confirming a concrete IDOR requires a per-endpoint sweep I did not exhaustively run in this read-only pass. F5 is a hardening observation, not a live bug.
- **Single most important claim for the synthesizer to cross-check**: **F1 — `ScopeValidationMiddleware` is fail-open and enforces nothing for `/api/v3/*` (`app/middleware/scope_validator.py:25-26,33-36`)**. Verify whether any v3 route currently omits `get_current_user`/`get_current_session`; if one does, F1 is not just a latent gap — it is an active unauthenticated endpoint.
