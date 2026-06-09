# backend/app/api/v3 — Local Contract

## Purpose

Document every router in the v3 API, the endpoints it exposes, and the exact response envelope shape each one returns. v3 is the **workspace-scoped** API tier: every endpoint is gated by both an `Auth V3` feature flag and a `WorkspaceMember` check, and refresh tokens are carried in httpOnly cookies (with `Authorization: Bearer` as a fallback). See [`../AGENTS.md`](../AGENTS.md) for the v1/v2/v3 versioning policy that this subtree implements.

## Ownership

- **Owners:** platform/api team
- **Mount point:** `api_v3_router` (FastAPI `APIRouter(prefix="/api/v3")`) — see [`__init__.py`](./__init__.py)
- **Mounted into:** `app.main_fastapi:app` (via `main_fastapi.py`)
- **Sub-routers (9):** auth, workspaces, invitations, teams, activity, billing, oidc, webhooks (the `api_v3_router` init also reserves an `auth_cookies` helper module, but it is **not a router** — it is a utility imported by `auth.py`)

## Local Contracts

These contracts apply to **every** file in this subtree.

### Response envelope (universal)

Every v3 endpoint returns one of three shapes, built from helpers in [`base.py`](./base.py):

- **Success** — `{"data": <payload>, "meta": {"request_id": "...", "timestamp": "..."}, "error": null}`
- **Paginated** — `{"data": {"items": [...], "total": N, "page": N, "per_page": N, "pages": N}, "meta": {...}, "error": null}`
- **Error** — `{"data": null, "error": {"code": "...", "message": "...", "details": {...}, "trace_id": "..."}, "meta": {...}}`

The only difference from v2 is the **`trace_id`** field in `error` — emitted for log correlation. Every v3 error response carries a `trace_id` (UUID4) that the client can quote when reporting bugs.

Use the `ok()`, `paginated()`, and `err()` helpers — **never** return a raw dict or model from a v3 endpoint. The v3 `err()` helper takes an optional `trace_id` so internal callers can pin it to a known value (e.g. from `request.state.trace_id`).

### Auth: cookie + Bearer dual-mode

v3 supports two ways to send a refresh token:

1. **httpOnly cookie** — primary path for browsers. The cookie is set by the auth handlers via [`auth_cookies.set_refresh_cookie()`](./auth_cookies.py) and cleared via `clear_refresh_cookie()`. Attributes: `HttpOnly`, `Secure` (prod only), `SameSite=Strict`, `Path=/api/v3/auth` (so the cookie is only sent to the v3 auth endpoints), `Max-Age=JWT_REFRESH_TOKEN_EXPIRES` (default 7 days), `Domain=AUTH_V3_COOKIE_DOMAIN` (`.flowmanner.com` in prod, `None` in dev).
2. **`Authorization: Bearer <refresh_token>` body fallback** — primary path for non-browser clients. Handled in [`auth.py:refresh_session_handler`](./auth.py).

Resolution order inside the handler is **cookie first** (`AuthCookieMiddleware` stashes it in `request.state.refresh_token_cookie`), then body (`payload.refresh_token`).

For access tokens, only `Authorization: Bearer <access_token>` is supported (15-min lifetime, contains `session_id` claim so `list_sessions` can mark the current session).

### Feature flags

Every v3 endpoint is gated on a feature flag stored in the `feature_flags` table. The flag is **per-endpoint-group** (not per-endpoint):

| Flag | Gates | Behavior on off |
|---|---|---|
| `AUTH_V3_ENABLED` | All of `auth.py` | 404 on every endpoint (handler `_require_v3_enabled`) |
| `AUTH_V3_OIDC` | `auth_oidc.py` | 404 on `/auth/oidc/*` |
| `AUTH_V3_WEBHOOKS` | `auth_webhooks.py` | 404 on `/auth/webhooks*` |
| `WORKSPACES_V3_ENDPOINTS` | `workspaces.py` | 404 on `/workspaces*` |
| `WORKSPACES_V3_INVITES` | `workspace_invitations.py` | 404 on `/workspaces/{id}/invitations*` |
| `WORKSPACES_V3_TEAMS_TOPLEVEL` | `teams.py` | 404 on `/teams*` |
| `WORKSPACES_V3_AUDIT` | `workspace_activity.py` | 404 on `/workspaces/{id}/audit-log` |
| `WORKSPACES_V3_BILLING` | `workspace_billing.py` | 404 on `/workspaces/{id}/billing` |

The flag check happens **before** the ownership check so disabled endpoints do not leak existence. Flags are read with `SELECT enabled_globally FROM feature_flags WHERE key = '...'` — a raw `text()` query, not ORM. A `None` / `False` result → `404 NOT_FOUND` (not `403` — never leak existence).

### Workspace-scoping

Almost every v3 endpoint requires a `WorkspaceMember` row for `(workspace_id, user.id)`. The check pattern (see `_check_workspace_access` in [`workspaces.py`](./workspaces.py)):

1. `SELECT * FROM workspace_members WHERE workspace_id = :ws AND user_id = :user`
2. If missing → `404 NOT_FOUND` (never `403` — never leak existence).
3. If `required_roles` is set and `membership.role not in required_roles` → `403 FORBIDDEN` (this one is `403` because the user **knows** the workspace exists — they're a member).

`required_roles` is `None` for any-member access (read endpoints), `["admin", "owner"]` for management endpoints, and `["owner"]` for destructive endpoints (delete workspace, etc.).

### Cross-cutting dependencies

| Concern | Dependency | Where it lives |
|---|---|---|
| Auth (access token) | `Depends(get_current_user)` from `app.api.deps` | external |
| DB session | `Depends(get_db)` from `app.database` | external |
| Refresh cookie resolution | `get_refresh_from_request(request)` | [`auth_cookies.py`](./auth_cookies.py) |
| Feature flag check | inline `text()` query in each router | per-router `_require_*` helper |
| Workspace access | inline `WorkspaceMember` check in each router | per-router `_check_workspace_access` helper |

There is **no** v3 version of `idempotency`, `rate_limit`, `tier_rate_limit`, `cursor_pagination`, or `validation_middleware` — those are v2-only. v3 relies on global IP-based rate limiting in [`auth.py`](./auth.py) (`check_rate_limit` for `v3_register`, `v3_login`, `v3_2fa`) and a per-endpoint 404 on disabled flags. If you need a richer rate-limit story, port the v2 helpers (do not import them cross-package).

### Error envelope construction

- HTTP exception → [`middleware.py`](./middleware.py) maps status to code via `_STATUS_CODE_MAP` (same as v2, plus `423=ACCOUNT_LOCKED`):
  ```
  400 → BAD_REQUEST
  401 → UNAUTHORIZED
  403 → FORBIDDEN
  404 → NOT_FOUND
  409 → CONFLICT
  422 → VALIDATION_ERROR
  423 → ACCOUNT_LOCKED
  429 → RATE_LIMITED
  500 → INTERNAL_ERROR
  502 → BAD_GATEWAY
  ```
- Domain exceptions: none yet. When added, mirror v2's pattern (e.g. `WorkspaceNotFoundError` → 404 with code `WORKSPACE_NOT_FOUND`).
- Unhandled exception → `500 INTERNAL_ERROR` with `trace_id` from `request.state.trace_id` (set by `AuthCookieMiddleware` if registered, else generated inline).

### Cookie semantics on logout

`DELETE /auth/sessions/{session_id}` only clears the cookie when **the revoked session is the current one** (matched by `session_id` claim in the access token). Revoking a different session leaves the cookie intact.

`PATCH /auth/users/me` with a `password` change revokes **all** of the user's sessions (cookie included — the password change is treated as a security event).

### H4.1 billing migration

[`workspace_billing.py`](./workspace_billing.py) reads subscription data from `Workspace.subscription_tier_id` + `Workspace.billing_customer_id` (migrated from the legacy `Tenant` model). The `subscription` block in the response is `null` if `subscription_tier_id` is not set; otherwise it resolves the tier via `SubscriptionTier` and exposes the per-tier limits (`missions_per_day`, `missions_per_month`, `has_api_access`, `has_custom_models`).

## Router Inventory

All routers are mounted under `prefix="/api/v3"` in [`__init__.py`](./__init__.py). Tags in OpenAPI use the `v3-*` prefix so they're easy to filter.

### 1. auth — [`auth.py`](./auth.py) (tag: `v3-auth`)

Endpoints:

| Method | Path | Auth | Response shape |
|---|---|---|---|
| POST | `/auth/users` | none | `201 {data: SessionResponse, meta, error: null}` — sets `refresh_token` cookie |
| POST | `/auth/sessions` | none | `201 {data: SessionResponse, ...}` **or** `200 {data: TempTokenResponse, ...}` when 2FA required, **or** `401/403/423` |
| POST | `/auth/sessions/verify` | none | `200 {data: SessionResponse, ...}` — sets `refresh_token` cookie |
| POST | `/auth/sessions/refresh` | cookie **or** `body.refresh_token` | `200 {data: SessionResponse, ...}` — sets new `refresh_token` cookie |
| GET | `/auth/sessions` | required | `200 {data: [SessionListResponse], ...}` — each entry has `is_current: bool` |
| DELETE | `/auth/sessions/{session_id}` | required | `204` — clears cookie only if revoking the current session |
| GET | `/auth/users/me` | required | `200 {data: UserResponse, ...}` |
| PATCH | `/auth/users/me` | required | `200 {data: UserResponse, ...}` — password change revokes all sessions |
| POST | `/auth/api-keys` | required | `201 {data: ApiKeyResponse, ...}` — full key returned **once** |
| GET | `/auth/api-keys` | required | `200 {data: [ApiKeyListResponse], ...}` — only `key_prefix` is shown, never the full key |
| DELETE | `/auth/api-keys/{key_id}` | required | `204` |

Notes:
- `SessionResponse` = `{ access_token, session_id, expires_at, user: UserSummary }`
- `SessionListResponse` = `{ id, device_name, device_os, browser, ip_address, location, is_current, last_used_at, created_at, expires_at }`
- `ApiKeyResponse` (POST only) = `{ id, name, key, key_prefix, scopes, expires_at, created_at }` — `key` is the full plaintext, shown exactly once
- `ApiKeyListResponse` (GET) = `{ id, name, key_prefix, scopes, is_active, last_used_at, expires_at, created_at }` — **no `key` field**
- `UserSummary` = `{ id, email, username, full_name, role, avatar_url, totp_enabled }`
- `UserResponse` = full user object including `is_admin`, `is_active`, `created_at`, `last_login_at`, `onboarding_*`
- All handlers call `await _require_v3_enabled(db)` first → 404 if `AUTH_V3_ENABLED=0`.

### 2. auth OIDC — [`auth_oidc.py`](./auth_oidc.py) (tag: `v3-auth-oidc`)

⚠️ **Stub / WIP** — these handlers return placeholder data and should not be considered production-ready.

| Method | Path | Auth | Response shape |
|---|---|---|---|
| POST | `/auth/oidc/{provider}/login` | required | `200 {data: {authorization_url, state}, ...}` — currently hardcoded `https://example.com/...` |
| GET | `/auth/oidc/{provider}/callback?code=&state=` | none | `302` redirect to `/` (no body) |

Notes: 404 unless `AUTH_V3_OIDC=1`. The `provider` path param is taken as-is; no allowlist yet.

### 3. auth webhooks — [`auth_webhooks.py`](./auth_webhooks.py) (tag: `v3-auth-webhooks`)

⚠️ **Partial implementation** — `workspace_id`, `url`, and `events` are passed as **query params** to POST (not as a body payload), which is wrong REST. Refactor to a Pydantic body before shipping.

| Method | Path | Auth | Response shape |
|---|---|---|---|
| POST | `/auth/webhooks?workspace_id=&url=&events=` | required | `201 {data: {id, workspace_id, url}, ...}` — `secret` is generated but **not** returned |
| GET | `/auth/webhooks?workspace_id=` | required | `200 {data: [{id, url, events, is_active}, ...], ...}` |
| DELETE | `/auth/webhooks/{webhook_id}` | required | `204` |

Notes: 404 unless `AUTH_V3_WEBHOOKS=1`. No signature verification, no retry logic, no HMAC headers — does not actually deliver webhooks yet.

### 4. workspaces — [`workspaces.py`](./workspaces.py) (tag: `v3-workspaces`)

| Method | Path | Min role | Response shape |
|---|---|---|---|
| GET | `/workspaces` | any member | `200 {data: [WorkspaceListItem], ...}` — includes the caller's `role` per workspace |
| POST | `/workspaces` | – | `201 {data: WorkspaceResponse, ...}` — auto-creates an `owner` `WorkspaceMember` |
| GET | `/workspaces/{workspace_id}` | any member | `200 {data: WorkspaceResponse, ...}` |
| PATCH | `/workspaces/{workspace_id}` | admin/owner | `200 {data: WorkspaceResponse, ...}` |
| DELETE | `/workspaces/{workspace_id}` | owner | `204` |
| GET | `/workspaces/{workspace_id}/members?include=user` | any member | `200 {data: [{user_id, role, joined_at, ...?email, full_name, avatar_url}], ...}` — `include=user` adds user fields |

Notes:
- `WorkspaceListItem` = `{ id, name, slug, plan, member_count, logo_url, role, created_at }`
- `WorkspaceResponse` = `{ id, name, slug, owner_id, plan, member_count, member_limit, logo_url, settings, storage_used_bytes, created_at, updated_at }`
- 404 unless `WORKSPACES_V3_ENDPOINTS=1`. Slug uniqueness enforced (`409 CONFLICT` on duplicate).
- PATCH/DELETE on missing workspace → `404`. On wrong role → `403`.

### 5. workspace invitations — [`workspace_invitations.py`](./workspace_invitations.py) (tag: `v3-workspace-invitations`)

| Method | Path | Min role | Response shape |
|---|---|---|---|
| POST | `/workspaces/{workspace_id}/invitations` | any member | `201 {data: InvitationCreatedResponse, ...}` — includes the `token` (returned **once** at creation) |
| GET | `/workspaces/{workspace_id}/invitations` | any member | `200 {data: [InvitationResponse], ...}` — **no token** is leaked in the list response |
| DELETE | `/workspaces/{workspace_id}/invitations/{invite_id}` | any member | `204` — sets `status="revoked"` |
| POST | `/workspaces/{workspace_id}/invitations/{invite_id}/accept` | required | `200 {data: {workspace_id, role, message}, ...}` — adds the caller as a `WorkspaceMember` |

Notes:
- `InvitationCreatedResponse` (POST) = `{ id, workspace_id, email, role, status, message, created_at, expires_at, token }` — token shown once
- `InvitationResponse` (GET) = same shape **minus** `token`
- Token expiry: 7 days. Reuse of a pending invitation for the same email → `400 BAD_REQUEST`. Accepting an expired or already-processed invitation → `400`.
- 404 unless `WORKSPACES_V3_INVITES=1`. Note: POST does **not** currently require admin/owner — any member can invite.

### 6. teams — [`teams.py`](./teams.py) (tag: `v3-teams`)

⚠️ **Top-level** — these routes are mounted at `/teams` (not `/workspaces/{id}/teams` like v2). This is the "v3-native" routing; v2 still has the nested variant.

| Method | Path | Min role | Response shape |
|---|---|---|---|
| GET | `/teams?workspace_id=` | any member | `200 {data: [TeamResponse], ...}` |
| POST | `/teams` | admin/owner | `201 {data: TeamResponse, ...}` — body requires `workspace_id` |
| DELETE | `/teams/{team_id}` | admin/owner (on the team's workspace) | `204` |

Notes:
- `TeamResponse` = `{ id, workspace_id, name, description, created_at }`
- 404 unless `WORKSPACES_V3_TEAMS_TOPLEVEL=1`. POST's role check is per-`workspace_id` from the body.

### 7. workspace activity (audit log) — [`workspace_activity.py`](./workspace_activity.py) (tag: `v3-workspace-audit`)

| Method | Path | Min role | Response shape |
|---|---|---|---|
| GET | `/workspaces/{workspace_id}/audit-log?limit=&offset=` | any member | `200 {data: [AuditLogEntry], ...}` |

Notes:
- `AuditLogEntry` = `{ id, actor_id, action, target_type, target_id, activity_metadata: dict, created_at }`
- `limit` defaults to 50, max 200. `offset` defaults to 0, must be ≥ 0.
- 404 unless `WORKSPACES_V3_AUDIT=1`. Read-only; no POST/DELETE.
- Read is `order by created_at DESC` (newest first). Cursor pagination is **not** implemented — pass `limit`/`offset` and accept the `OFFSET`-scan cost on large workspaces.

### 8. workspace billing — [`workspace_billing.py`](./workspace_billing.py) (tag: `v3-workspace-billing`)

| Method | Path | Min role | Response shape |
|---|---|---|---|
| GET | `/workspaces/{workspace_id}/billing` | any member | `200 {data: {workspace_id, plan, plan_display_name, member_limit, storage_limit_bytes, storage_used_bytes, subscription: {tier_id, tier_name, tier_display, missions_per_day, missions_per_month, has_api_access, has_custom_models} | null, billing_customer_id}, ...}` |

Notes:
- `subscription` is `null` when `Workspace.subscription_tier_id` is not set (free workspaces with no upgrade).
- `storage_limit_bytes` is currently hardcoded to `1073741824` (1 GiB); read from a plan setting once the subscription module is wired in.
- 404 unless `WORKSPACES_V3_BILLING=1`. Read-only; no POST/PATCH for billing data yet (use the v2 `subscription` routes for write paths).

## Work Guidance

### Adding a new v3 endpoint

1. Pick the right router file. If the endpoint is workspace-scoped, add to `workspaces.py`; if it touches a different resource (auth, billing, audit), add to the relevant file.
2. Add a feature-flag helper at the top of the file (e.g. `_require_mything_enabled(db)`) and call it **first** — before any auth or ownership check — so disabled endpoints return 404 without leaking existence.
3. Use the helpers from `base.py` — `ok(payload)`, `paginated(items, total, page, per_page)`, `err(code, message, status_code, trace_id)`. **Do not** return a raw dict or Pydantic model directly.
4. For workspace-scoped reads, use the `_check_workspace_access(db, workspace_id, user.id)` helper from `workspaces.py`. For destructive ops, pass `required_roles=["owner"]`. Always raise `404 NOT_FOUND` (not `403`) for missing membership.
5. For cookie-bearing responses (auth mutations), build a `JSONResponse(...)`, then call `set_refresh_cookie(resp, token)` before returning.
6. For schemas that include datetime fields, call `.model_dump(mode="json")` (not `.model_dump()`) so the response is JSON-serializable without the `validation_middleware` having to coerce.
7. Run `uv run python -c "from app.main_fastapi import app; print(len(app.routes))"` to confirm the route registered, then `curl http://localhost:8000/api/v3/openapi.json | jq '.paths | keys'` (once `openapi.py` is added — it's still on the v2 router only).

### Adding a new feature flag

1. Insert a row in the `feature_flags` table: `INSERT INTO feature_flags (key, enabled_globally) VALUES ('MY_FLAG', false)`.
2. Add a `_require_mything_enabled(db)` helper at the top of the affected router that runs `SELECT enabled_globally FROM feature_flags WHERE key = 'MY_FLAG'`.
3. Add a new entry to the **Feature flags** table in this AGENTS.md.
4. Never expose the flag value in the response — disabled endpoints should look exactly like missing endpoints (`404 NOT_FOUND`).

### Working with the cookie

- Always use `set_refresh_cookie(resp, token)` to set the cookie — never call `response.set_cookie(...)` directly. The helper applies the correct `Secure` / `SameSite=Strict` / `Path=/api/v3/auth` / `Domain` settings.
- For 204 responses that revoke the **current** session, call `clear_refresh_cookie(resp)` — but only if `session_id == current_session_id` (decode the access token to check).
- `get_refresh_from_request(request)` resolves the cookie from `request.state.refresh_token_cookie` first (set by `AuthCookieMiddleware`), then falls back to `request.cookies.get("refresh_token")` for test environments.

### Migrating a v2 endpoint to v3

1. Add the endpoint to the appropriate v3 router with the v3 envelope and feature-flag gate.
2. Keep the v2 path / method / response shape unchanged — v2 must stay forward-compatible.
3. If the v2 shape is unkeepable, freeze v2 and add a v3 endpoint as a redesign (e.g. cookie + session list).
4. Update this AGENTS.md and the v2 AGENTS.md to point at each other.

## Verification

Smoke tests:

```bash
# Auth round-trip (cookie capture)
curl -si -c /tmp/cookies.txt -X POST http://localhost:8000/api/v3/auth/sessions \
  -H "Content-Type: application/json" \
  -d '{"login":"you@example.com","password":"..."}'

# Cookie should be set on /tmp/cookies.txt with HttpOnly + SameSite=Strict

# Subsequent call uses the cookie
curl -sb /tmp/cookies.txt http://localhost:8000/api/v3/auth/sessions

# Refresh via cookie
curl -sb /tmp/cookies.txt -X POST http://localhost:8000/api/v3/auth/sessions/refresh

# Refresh via body (non-browser client)
curl -s -X POST http://localhost:8000/api/v3/auth/sessions/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<token>"}'

# Feature flag off → 404
curl -si http://localhost:8000/api/v3/workspaces -H "Authorization: Bearer $TOK"
# If WORKSPACES_V3_ENDPOINTS=0 → 404 with trace_id in error envelope

# trace_id in error response
curl -s http://localhost:8000/api/v3/workspaces/nonexistent -H "Authorization: Bearer $TOK" | jq '.error.trace_id'
```

Targeted pytest invocations (run from `backend/`):

```bash
# v3 envelope + routing
uv run pytest tests/api/v3/ -v

# Auth flow (cookie + session list + revoke)
uv run pytest tests/api/v3/test_auth.py -v
uv run pytest tests/api/v3/test_sessions.py -v

# Feature flag gating
uv run pytest tests/api/v3/test_feature_flags.py -v

# Workspace CRUD
uv run pytest tests/api/v3/test_workspaces.py -v
uv run pytest tests/api/v3/test_invitations.py -v
uv run pytest tests/api/v3/test_teams.py -v
uv run pytest tests/api/v3/test_billing.py -v
uv run pytest tests/api/v3/test_audit.py -v

# API key CRUD
uv run pytest tests/api/v3/test_api_keys.py -v
```

Lint & types:

```bash
uv run ruff check app/api/v3/
uv run mypy app/api/v3/
```

## Child DOX Index

| Path | Purpose | Status |
|---|---|---|
| `./__init__.py` | Mounts 8 sub-routers + 1 utility module under `/api/v3` | ✅ stable |
| `./base.py` | `ok` / `paginated` / `err` envelope helpers + `ResponseMeta` / `ErrorDetail` (with `trace_id`) / `PaginatedData` | ✅ stable |
| `./middleware.py` | Maps HTTPException + unhandled errors to v3 error envelopes (only for `/api/v3/*`) | ✅ stable |
| `./auth_cookies.py` | `set_refresh_cookie` / `clear_refresh_cookie` / `get_refresh_from_request` — httpOnly cookie + body-fallback refresh | ✅ stable |
| `./auth.py` | Sessions, users, API keys — 11 endpoints | ✅ stable |
| `./auth_oidc.py` | OIDC provider login + callback — **stub** | ⚠️ WIP — needs real provider integration |
| `./auth_webhooks.py` | Webhook subscriptions — **partial** (POST takes query params instead of body) | ⚠️ needs Pydantic body refactor |
| `./teams.py` | Top-level teams — feature-flagged | ✅ stable |
| `./workspace_activity.py` | Audit log read — feature-flagged, read-only | ✅ stable |
| `./workspace_billing.py` | Billing snapshot — feature-flagged, read-only (H4.1 migration) | ✅ stable |
| `./workspace_invitations.py` | Invitation CRUD + accept — feature-flagged | ✅ stable |
| `./workspaces.py` | Workspace CRUD + members — feature-flagged | ✅ stable |
| `./openapi.py` | v3-only OpenAPI spec (filter + tier docs) | ⏳ needed — mirror `v2/openapi.py` |

## Open DOX Gaps

- **`v3/openapi.py`** — currently only `v2/openapi.py` exists. Add a v3 variant that filters the full app schema to only `/api/v3/*` paths, includes the `trace_id` field in the error schema, and documents the feature-flag table.
- **`v3/idempotency.py` / `v3/rate_limit.py` / `v3/validation_middleware.py`** — not implemented. Port from `v2/` if needed. For now, v3 relies on global IP rate limits in `auth.py` and no idempotency on writes.
- **Cursor pagination** — `workspace_activity.py` audit log uses OFFSET pagination. Add a cursor variant if audit logs grow past ~10k rows per workspace.
- **OIDC + webhooks** — both routers are stubs. When completed, update their per-method tables to reflect the real provider integrations and HMAC signature flows.
