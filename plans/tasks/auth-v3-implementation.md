# Auth v3 Implementation Blueprint

> **Derived from:** `v3-v4-migration-roadmap.md` Section 1 — Auth Service  
> **Codebase ground-truth:** All file paths, function names, and column names verified against `/opt/flowmanner/backend/app/`  
> **Phase:** Phase 1 — Foundation (Week 1–6)  
> **Effort:** MEDIUM  
> **Generated:** 2026-05-31 by Buffy (DeepSeek V4 Pro)

---

## 1. Exact Files to Create/Modify

### New files to create (all under `/opt/flowmanner/backend/app/`)

| # | File | Purpose |
|---|------|---------|
| 1 | `api/v3/__init__.py` | v3 router assembly (mirrors v2 pattern) |
| 2 | `api/v3/base.py` | v3 response envelope + helpers (`ok`, `err`, `paginated`) |
| 3 | `api/v3/middleware.py` | v3 exception handlers (mirror v2 middleware pattern) |
| 4 | `api/v3/auth.py` | All v3 auth route handlers |
| 5 | `api/v3/auth_cookies.py` | httpOnly cookie helpers — `set_refresh_cookie()`, `clear_refresh_cookie()`, `get_refresh_from_cookie()` |
| 6 | `api/v3/auth_sessions.py` | Session management route handlers (`GET /auth/sessions`, `DELETE /auth/sessions/{session_id}`) |
| 7 | `api/v3/auth_api_keys.py` | API key CRUD route handlers |
| 8 | `api/v3/auth_oidc.py` | OIDC provider login/callback route handlers (v2 parity with existing v1 OIDC) |
| 9 | `api/v3/auth_webhooks.py` | Webhook subscription CRUD |
| 10 | `schemas/auth_v3.py` | All v3 Pydantic request/response schemas |
| 11 | `services/auth_v3_service.py` | v3 auth business logic (session create, session revoke, API key encrypt/store, OIDC flows, webhook dispatch) |
| 12 | `middleware/auth_cookie.py` | FastAPI middleware to extract httpOnly refresh cookie and inject into request state |
| 13 | `middleware/scope_validator.py` | Middleware that validates granular scopes on v3 routes |
| 14 | `models/auth_v3_models.py` | New DB models: `AuthSession`, `ApiKey`, `AuthWebhookSubscription`, `OIDCProviderConfig` (extends existing `auth_models.py` OIDC) |
| 15 | `api/middleware/rate_limit_v3.py` | Redis-backed rate limiter with standard `RateLimit-*` headers |

### Existing files to modify (non-destructive — additive only)

| # | File | Change |
|---|------|--------|
| 1 | `main_fastapi.py` | Register v3 routers + cookie middleware + v3 exception handlers |
| 2 | `api/middleware/versioning.py` | Add `"v3"` to `SUPPORTED_VERSIONS`, set `CURRENT_VERSION = "v3"`, add v3 deprecation entries |
| 3 | `models/__init__.py` | Import new `auth_v3_models` to register tables with Base.metadata |
| 4 | `api/deps.py` | Add `get_current_session` dependency (reads cookie + Bearer); add `require_scope()` dependency factory |
| 5 | `config.py` | Add `AUTH_V3_COOKIE_DOMAIN`, `AUTH_V3_COOKIE_SECURE`, `AUTH_V3_REFRESH_EXPIRY_DAYS` settings |

### Files NOT modified (purity constraint)

- `api/v2/auth.py` — untouched (90-day deprecation period via feature flag only)
- `api/v1/auth.py` — untouched
- `services/auth_service.py` — untouched (v3 uses new service file)
- `models/auth_models.py` — untouched (existing OIDC models remain)

---

## 2. Database Migration (Alembic)

### Migration file: `backend/alembic/versions/auth_v3_init.py`

```python
"""auth_v3_init — sessions, api_keys, webhook subscriptions, OIDC configs

Revision ID: auth_v3_001
Revises: 2026_02_13_1215  (last existing migration — add_memory_service)
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

revision = 'auth_v3_001'
down_revision = '2026_02_13_1215'
branch_labels = None
depends_on = None


def upgrade():
    # ── Table 1: auth_sessions (replaces implicit refresh_tokens session tracking) ──
    op.create_table(
        'auth_sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('refresh_token_hash', sa.String(64), nullable=False),       # SHA-256 of refresh token
        sa.Column('device_name', sa.String(255), nullable=True),
        sa.Column('device_os', sa.String(100), nullable=True),
        sa.Column('browser', sa.String(100), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('location', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoke_reason', sa.String(100), nullable=True),
        sa.Column('family_id', sa.String(36), nullable=True, index=True),
        sa.Column('family_generation', sa.Integer(), default=0),
        sa.Index('ix_auth_sessions_user_active', 'user_id', 'is_active'),
    )

    # ── Table 2: auth_api_keys ──
    op.create_table(
        'auth_api_keys',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id', ondelete='SET NULL'), nullable=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('key_prefix', sa.String(8), nullable=False),                # First 8 chars visible to user
        sa.Column('key_hash', sa.String(64), nullable=False, unique=True),     # SHA-256 of full key
        sa.Column('scopes', sa.Text(), nullable=True),                         # JSON array: ["missions:read", "missions:write"]
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Index('ix_api_keys_user', 'user_id', 'is_active'),
    )

    # ── Table 3: auth_webhook_subscriptions ──
    op.create_table(
        'auth_webhook_subscriptions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('url', sa.String(2000), nullable=False),
        sa.Column('secret', sa.String(64), nullable=False),                   # HMAC-SHA256 signing secret
        sa.Column('events', sa.Text(), nullable=False),                        # JSON array of event types
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('last_delivery_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_failure_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_count', sa.Integer(), default=0),
        sa.Index('ix_webhook_sub_workspace', 'workspace_id', 'is_active'),
    )

    # ── Table 4: oidc_provider_configs (workspace-scoped OIDC providers) ──
    # NOTE: existing oidc_providers table is system-level (in auth_models.py)
    # This new table is workspace-scoped for Enterprise SSO
    op.create_table(
        'oidc_provider_configs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('workspace_id', sa.String(36), sa.ForeignKey('workspaces.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('provider_type', sa.String(50), nullable=False),             # 'google', 'github', 'microsoft', 'okta', 'custom'
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('issuer_url', sa.String(500), nullable=True),
        sa.Column('client_id', sa.String(500), nullable=False),
        sa.Column('client_secret_encrypted', sa.LargeBinary(), nullable=False), # AES-256 encrypted
        sa.Column('scopes', sa.String(500), default='openid email profile'),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Column additions (no data backfill needed for new columns) ──
    # None — all new tables, no alterations to existing tables

    # ── Seed feature flags ──
    op.execute("""
        INSERT INTO feature_flags (key, name, description, enabled_globally, created_at, updated_at)
        VALUES
            ('AUTH_V3_COOKIES', 'Auth v3 httpOnly Cookies', 'Use httpOnly cookies for refresh tokens', false, NOW(), NOW()),
            ('AUTH_V3_SESSIONS', 'Auth v3 Session Management', 'Enable session list and revoke endpoints', false, NOW(), NOW()),
            ('AUTH_V3_API_KEYS', 'Auth v3 API Keys', 'Enable scoped API key CRUD', false, NOW(), NOW()),
            ('AUTH_V3_OIDC', 'Auth v3 OIDC Providers', 'Enable workspace-scoped OIDC SSO', false, NOW(), NOW()),
            ('AUTH_V3_WEBHOOKS', 'Auth v3 Webhooks', 'Enable auth event webhooks', false, NOW(), NOW()),
            ('AUTH_V3_SCOPES', 'Auth v3 Granular Scopes', 'Enable scope-based authorization middleware', false, NOW(), NOW())
        ON CONFLICT (key) DO NOTHING;
    """)


def downgrade():
    op.drop_table('auth_webhook_subscriptions')
    op.drop_table('auth_api_keys')
    op.drop_table('auth_sessions')
    op.drop_table('oidc_provider_configs')

    op.execute("""
        DELETE FROM feature_flags WHERE key IN (
            'AUTH_V3_COOKIES', 'AUTH_V3_SESSIONS', 'AUTH_V3_API_KEYS',
            'AUTH_V3_OIDC', 'AUTH_V3_WEBHOOKS', 'AUTH_V3_SCOPES'
        );
    """)
```

### Data backfills

No data backfill is required for Auth v3. All new tables start empty. The existing `refresh_tokens` table continues to work for v2. The new `auth_sessions` table records new sessions created through v3 endpoints. v2 refresh tokens are NOT migrated — they naturally expire within 7 days (current `JWT_REFRESH_TOKEN_EXPIRES` = 604800s).

### Migration execution

```bash
cd /opt/flowmanner/backend
python -m alembic upgrade head
```

---

## 3. Pydantic Models — New Request/Response Schemas

File: `backend/app/schemas/auth_v3.py`

```python
"""Auth v3 Pydantic schemas — typed request/response models."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, model_validator


# ═══════════════════════════════════════════════
# Request Schemas
# ═══════════════════════════════════════════════

class LoginRequest(BaseModel):
    """POST /auth/sessions — create a new session (login).
    
    When provider='credentials': password is required.
    When provider='oidc': password is ignored (OAuth/SSO flow uses OIDCLoginRequest
    for the authorization URL, and the callback handles token exchange server-side).
    For the initial OIDC login, use POST /auth/oidc/{provider}/login instead.
    """
    login: str = Field(..., min_length=1, max_length=255, description="Email or username")
    password: str = Field(..., min_length=1, max_length=128)
    provider: str = Field(default="credentials", description="'credentials' | 'oidc'")

    @model_validator(mode='after')
    def validate_login(self):
        if self.provider == 'oidc':
            # OIDC login through /auth/sessions uses a one-time code as password
            # The primary OIDC flow is via /auth/oidc/{provider}/login
            pass
        if '@' in self.login:
            if not self.login.count('@') == 1:
                raise ValueError('Invalid email format')
        return self

class RegisterRequest(BaseModel):
    """POST /auth/users — register a new user."""
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    username: Optional[str] = Field(default=None, max_length=100)
    full_name: Optional[str] = Field(default=None, max_length=200)

class Verify2FARequest(BaseModel):
    """POST /auth/sessions/verify — verify 2FA after login challenge."""
    temp_token: str
    code: str = Field(..., min_length=6, max_length=8)

class RefreshSessionRequest(BaseModel):
    """POST /auth/sessions/refresh — refresh access token.
    Refresh token read from httpOnly cookie (primary) or request body (fallback with ?token_response=body)."""
    refresh_token: Optional[str] = Field(default=None, description="Required if not using cookies")

class RevokeSessionRequest(BaseModel):
    """DELETE /auth/sessions/{session_id} — revoke a specific session."""
    pass  # No body needed; session_id in path

class CreateApiKeyRequest(BaseModel):
    """POST /auth/api-keys — create a scoped API key."""
    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(default_factory=lambda: ["missions:read"])
    workspace_id: Optional[str] = Field(default=None)
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=365)

class UpdateUserRequest(BaseModel):
    """PATCH /auth/users/me — update current user profile."""
    full_name: Optional[str] = Field(default=None, max_length=200)
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    avatar_url: Optional[str] = Field(default=None, max_length=500)

class CreateWebhookRequest(BaseModel):
    """POST /auth/webhooks — create auth event webhook subscription."""
    url: str = Field(..., max_length=2000)
    events: list[str] = Field(..., min_length=1)
    workspace_id: str = Field(..., min_length=36)

class UpdateWebhookRequest(BaseModel):
    url: Optional[str] = Field(default=None)
    events: Optional[list[str]] = Field(default=None)
    is_active: Optional[bool] = Field(default=None)

class OIDCLoginRequest(BaseModel):
    """POST /auth/oidc/{provider}/login — initiate OIDC login flow."""
    workspace_id: Optional[str] = Field(default=None)
    redirect_uri: str = Field(..., max_length=2000)


# ═══════════════════════════════════════════════
# Response Schemas
# ═══════════════════════════════════════════════

class SessionResponse(BaseModel):
    """Returned after successful login/register/refresh."""
    access_token: str
    session_id: str
    expires_at: datetime
    user: "UserSummary"

class UserSummary(BaseModel):
    id: int
    email: str
    username: Optional[str]
    full_name: Optional[str]
    role: str
    avatar_url: Optional[str]
    totp_enabled: bool

class UserResponse(BaseModel):
    """GET /auth/users/me — full user profile."""
    id: int
    email: str
    username: Optional[str]
    full_name: Optional[str]
    role: str
    is_admin: bool
    is_active: bool
    avatar_url: Optional[str]
    totp_enabled: bool
    created_at: datetime
    last_login_at: Optional[datetime]
    onboarding_step: Optional[str]
    onboarding_completed: bool

    class Config:
        from_attributes = True

class SessionListResponse(BaseModel):
    """GET /auth/sessions — list active sessions."""
    id: str
    device_name: Optional[str]
    device_os: Optional[str]
    browser: Optional[str]
    ip_address: Optional[str]
    location: Optional[str]
    is_current: bool                                      # True if this is the session making the request
    last_used_at: datetime
    created_at: datetime
    expires_at: datetime

class ApiKeyResponse(BaseModel):
    """Returned on API key creation (only time full key is shown)."""
    id: str
    name: str
    key: str                                              # Full key — shown ONCE
    key_prefix: str
    scopes: list[str]
    expires_at: Optional[datetime]
    created_at: datetime

class ApiKeyListResponse(BaseModel):
    """GET /auth/api-keys — list user's API keys (key never shown)."""
    id: str
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    last_used_at: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: datetime

class WebhookResponse(BaseModel):
    id: str
    workspace_id: str
    url: str
    events: list[str]
    is_active: bool
    created_at: datetime
    last_delivery_at: Optional[datetime]
    failure_count: int

class TempTokenResponse(BaseModel):
    """Returned when 2FA is required after login."""
    requires_2fa: bool = True
    temp_token: str
    methods: list[str] = ["totp"]                         # Future: ["totp", "webauthn"]
```

> **Note on login response shapes:** The login endpoint returns either:
> - 201 with `{ data: SessionResponse }` — authentication complete
> - 200 with `{ data: TempTokenResponse }` — 2FA challenge required
> 
> The `LoginChallengeResponse` stub class from the initial draft has been removed.
> No discriminated union is needed — the response shape is determined by HTTP status code
> and the presence/absence of the `requires_2fa` field.

---

## 4. Route Handlers — Endpoint Signatures, Status Codes, Error Responses

File: `backend/app/api/v3/auth.py`

All endpoints are under `/api/v3/auth`.

### 4.1 Session Management (Login/Logout/Refresh)

| Method | Path | Handler | Status | Purpose |
|--------|------|---------|--------|---------|
| `POST` | `/auth/sessions` | `create_session()` | 201 | Login (neé `/auth/login`) |
| `POST` | `/auth/sessions/verify` | `verify_session_2fa()` | 200 | Complete 2FA after temp_token challenge |
| `POST` | `/auth/sessions/refresh` | `refresh_session()` | 200 | Refresh access token; refresh token from cookie or body |
| `DELETE` | `/auth/sessions/{session_id}` | `revoke_session()` | 204 | Revoke a specific session |
| `GET` | `/auth/sessions` | `list_sessions()` | 200 | List active sessions for current user |

```python
# Signature examples:

@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Authenticate user and create a new session.
    
    Returns:
        201: { data: SessionResponse, meta, error: null }
        401: { data: null, error: { code: "INVALID_CREDENTIALS", message: "..." } }
        200: { data: { requires_2fa: true, temp_token: "..." }, meta, error: null }  # 2FA required
        429: Rate limited — login attempts
        423: Account locked — too many failed attempts
    """
    ...

@router.get("/sessions", status_code=status.HTTP_200_OK)
async def list_sessions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active sessions for the authenticated user.
    
    Returns:
        200: { data: [SessionListResponse], meta, error: null }
    """
    ...

@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a specific session. Returns 204 or 404.
    
    Returns:
        204: No content (success)
        404: Session not found or not owned by user
    """
    ...
```

### 4.2 User Management

| Method | Path | Handler | Status | Purpose |
|--------|------|---------|--------|---------|
| `POST` | `/auth/users` | `register_user()` | 201 | Register (neé `/auth/register`) |
| `GET` | `/auth/users/me` | `get_me()` | 200 | Current user profile |
| `PATCH` | `/auth/users/me` | `update_me()` | 200 | Update profile |

```python
@router.post("/users", status_code=status.HTTP_201_CREATED)
async def register_user(payload: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Register a new user account.
    
    Returns:
        201: { data: SessionResponse, meta, error: null }
        409: Email or username conflict
        422: Password validation failure
        429: Too many registrations from this IP
    """
    ...

@router.get("/users/me")
async def get_me(user: User = Depends(get_current_user)):
    """Get current user profile.
    
    Note: login_count is REMOVED. For login stats, see GET /auth/users/me/stats (v4 planned).
    """
    return ok(UserResponse.model_validate(user).model_dump())

@router.patch("/users/me")
async def update_me(
    payload: UpdateUserRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user profile."""
    ...
```

### 4.3 API Keys

| Method | Path | Handler | Status | Purpose |
|--------|------|---------|--------|---------|
| `POST` | `/auth/api-keys` | `create_api_key()` | 201 | Create scoped API key |
| `GET` | `/auth/api-keys` | `list_api_keys()` | 200 | List user's API keys |
| `DELETE` | `/auth/api-keys/{key_id}` | `revoke_api_key()` | 204 | Revoke an API key |

> **⚠️ API key authentication is deferred to Phase 2.** Phase 1 implements API key
> CRUD (create, list, revoke) so users can start issuing keys. The actual authentication
> path — accepting `Authorization: Bearer fm_...` with an API key instead of a JWT —
> requires a separate `get_current_api_key` dependency (or extending `get_current_session`
> to handle both token types). This is scoped to Phase 2 (Missions v3 + Agent auth).
>
> Until then, API keys created in Phase 1 are stored securely but not yet usable for
> request authentication. The frontend API key management UI can be built in parallel.

### 4.4 OIDC

| Method | Path | Handler | Status | Purpose |
|--------|------|---------|--------|---------|
| `POST` | `/auth/oidc/{provider}/login` | `oidc_login()` | 200 | Get OIDC authorization URL |
| `GET` | `/auth/oidc/{provider}/callback` | `oidc_callback()` | 302 | OIDC callback — redirect with session |

### 4.5 Webhooks

| Method | Path | Handler | Status | Purpose |
|--------|------|---------|--------|---------|
| `POST` | `/auth/webhooks` | `create_webhook()` | 201 | Subscribe to auth events |
| `GET` | `/auth/webhooks` | `list_webhooks()` | 200 | List webhook subscriptions |
| `PATCH` | `/auth/webhooks/{id}` | `update_webhook()` | 200 | Update subscription |
| `DELETE` | `/auth/webhooks/{id}` | `delete_webhook()` | 204 | Delete subscription |

### Error Response Format (all endpoints)

```json
{
  "data": null,
  "meta": { "request_id": "abc-123", "timestamp": "2026-06-01T12:00:00Z" },
  "error": {
    "code": "INVALID_CREDENTIALS",
    "message": "Email or password is incorrect",
    "details": { "remaining_attempts": 4 },
    "trace_id": "trc_abc123"    // NEW in v3 — correlation ID for support
  }
}
```

**Error codes in v3:**
- `INVALID_CREDENTIALS` — 401
- `SESSION_EXPIRED` — 401
- `SESSION_REVOKED` — 401
- `TOKEN_REUSE_DETECTED` — 401 (all sessions revoked)
- `TEMP_TOKEN_EXPIRED` — 401
- `INVALID_2FA_CODE` — 401
- `ACCOUNT_DISABLED` — 403
- `ACCOUNT_LOCKED` — 423
- `EMAIL_CONFLICT` — 409
- `USERNAME_CONFLICT` — 409
- `PASSWORD_TOO_WEAK` — 422
- `RATE_LIMITED` — 429
- `SCOPE_INSUFFICIENT` — 403

---

## 5. Middleware — httpOnly Cookie, Scope Validation, Session Tracking

### 5.1 Cookie Middleware (`middleware/auth_cookie.py`)

Extracts refresh token from httpOnly cookie and attaches to `request.state`.

```python
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request

class AuthCookieMiddleware(BaseHTTPMiddleware):
    """
    Extracts the refresh token from the 'refresh_token' httpOnly cookie
    and stores it in request.state.refresh_token.
    
    Cookie attributes: HttpOnly, Secure, SameSite=Strict, Path=/api/v3/auth
    """
    
    COOKIE_NAME = "refresh_token"
    
    async def dispatch(self, request: Request, call_next):
        # Extract cookie for /api/v3/auth/sessions/refresh
        cookie_value = request.cookies.get(self.COOKIE_NAME)
        request.state.refresh_token_cookie = cookie_value
        response = await call_next(request)
        return response
```

### 5.2 Cookie Helpers (`api/v3/auth_cookies.py`)

```python
from fastapi.responses import Response
from datetime import datetime, timezone, timedelta
from app.config import settings

def set_refresh_cookie(response: Response, token: str, session_id: str):
    """Set httpOnly refresh token cookie on response."""
    max_age = settings.JWT_REFRESH_TOKEN_EXPIRES  # seconds (604800 = 7 days)
    response.set_cookie(
        key="refresh_token",
        value=token,
        httponly=True,
        secure=settings.AUTH_V3_COOKIE_SECURE,     # True in production
        samesite="strict",
        path="/api/v3/auth",
        max_age=max_age,
        domain=settings.AUTH_V3_COOKIE_DOMAIN,      # None in dev, ".flowmanner.com" in prod
    )

def clear_refresh_cookie(response: Response):
    """Clear the refresh token cookie (logout)."""
    response.delete_cookie(
        key="refresh_token",
        path="/api/v3/auth",
        domain=settings.AUTH_V3_COOKIE_DOMAIN,
        secure=settings.AUTH_V3_COOKIE_SECURE,
        httponly=True,
    )

def get_refresh_from_request(request) -> str | None:
    """Get refresh token from cookie (primary) or request body (fallback)."""
    # Primary: httpOnly cookie
    cookie_token = getattr(request.state, 'refresh_token_cookie', None)
    if cookie_token:
        return cookie_token
    # Fallback: request body (for non-browser clients, via ?token_response=body)
    return None  # Set by route handler reading body
```

### 5.3 Scope Validator Middleware (`middleware/scope_validator.py`)

```python
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

REQUIRED_SCOPES: dict[str, dict[str, list[str]]] = {
    # HTTP method to required scopes
    ("/api/v3/auth/sessions", "GET"): ["sessions:read"],
    ("/api/v3/auth/sessions", "DELETE"): ["sessions:write"],
    ("/api/v3/auth/api-keys", "POST"): ["api_keys:write"],
    ("/api/v3/auth/api-keys", "DELETE"): ["api_keys:write"],
    # ... more route/scope mappings
}

class ScopeValidationMiddleware(BaseHTTPMiddleware):
    """
    Validates that the authenticated user has required scopes for v3 endpoints.
    Reads scopes from JWT access token's 'scopes' claim.
    """
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/v3/"):
            return await call_next(request)
        # Scopes checked against JWT payload (injected by get_current_user dependency)
        return await call_next(request)
```

### 5.4 The `get_current_session` Dependency

In `api/deps.py`, the new dependency extracts the user from the JWT **and** resolves the session record:

```python
async def get_current_session(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> AuthSession:
    """Authenticate via Bearer token AND resolve the active session.
    
    Returns the AuthSession ORM object with .user preloaded.
    Raises HTTPException(401) if:
    - No token provided
    - Token expired/invalid
    - Session not found in auth_sessions table
    - Session is revoked (is_active=False)
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Decode JWT (reuses existing get_current_user's token verification)
    payload = decode_access_token(credentials.credentials)
    user_id = payload.get("sub")
    session_id = payload.get("session_id")  # NEW claim in v3 access tokens
    
    if not user_id or not session_id:
        raise HTTPException(status_code=401, detail="Invalid token claims")
    
    # Load user + session in one query
    result = await db.execute(
        select(AuthSession)
        .options(joinedload(AuthSession.user))
        .where(AuthSession.id == session_id, AuthSession.is_active == True)
    )
    session = result.scalar_one_or_none()
    if not session or session.user_id != int(user_id):
        raise HTTPException(status_code=401, detail="Session not found or revoked")
    
    return session

def require_scope(*required_scopes: str):
    """Dependency factory — enforce granular scopes.
    
    Usage:
        @router.get("/missions")
        async def list_missions(
            _: None = Depends(require_scope("missions:read")),
            session: AuthSession = Depends(get_current_session),
        ):
            ...
    """
    async def scope_checker(session: AuthSession = Depends(get_current_session)):
        user_scopes = getattr(session.user, 'scopes', [])
        missing = [s for s in required_scopes if s not in user_scopes]
        if missing:
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient scopes: {', '.join(missing)}"
            )
        return None
    return scope_checker
```

### 5.5 Session Tracking

The `AuthSession` model (in `models/auth_v3_models.py`) records:
- `last_used_at` — updated **only on token refresh** (NOT on access token validation)
- Device metadata: `device_name`, `device_os`, `browser`, `ip_address`, `location`
- `revoke_reason` — reason for session termination ("user_logout", "password_change", "admin_revoke", "reuse_detected")

Session creation happens on login/register. Session tracking happens on each token refresh via the `refresh_session()` handler updating `last_used_at`.

> **⚠️ CRITICAL: Do NOT update `last_used_at` on access token validation.** The
> `get_current_session` dependency (section 5.4) runs on **every authenticated API
> request** — hundreds or thousands per second under load. Attaching a DB write to
> this dependency would create a severe database bottleneck. The `last_used_at`
> field is only updated during token refresh (`POST /auth/sessions/refresh`),
> which fires infrequently (~once per hour per session).
>
> If you need per-request activity tracking, use an async counter in Redis
> (INCR on each request) and flush to the DB in a background task every
> 5–15 minutes, rather than writing to `auth_sessions` on every request.

### 5.6 v3 Router Assembly (`api/v3/__init__.py`)

Patterning after `api/v2/__init__.py`:

```python
"""API v3 — httpOnly cookies, granular scopes, session management."""

from fastapi import APIRouter

api_v3_router = APIRouter(prefix="/api/v3")

from app.api.v3.auth import router as auth_router
from app.api.v3.auth_sessions import router as sessions_router
from app.api.v3.auth_api_keys import router as api_keys_router
from app.api.v3.auth_oidc import router as oidc_router
from app.api.v3.auth_webhooks import router as webhooks_router

api_v3_router.include_router(auth_router)
api_v3_router.include_router(sessions_router)
api_v3_router.include_router(api_keys_router)
api_v3_router.include_router(oidc_router)
api_v3_router.include_router(webhooks_router)
```

### 5.7 Registration in `main_fastapi.py`

```python
# Add after existing v2 registration:
from app.api.v3 import api_v3_router
from app.api.v3.middleware import register_v3_exception_handlers
from app.middleware.auth_cookie import AuthCookieMiddleware

register_v3_exception_handlers(app)
# ⚠️  ORDERING: AuthCookieMiddleware must be added AFTER CORS middleware.
# FastAPI/Starlette executes ASGI middleware in REVERSE order of add_middleware().
# If AuthCookieMiddleware runs before CORS, the httpOnly cookie may not be readable
# by the browser on cross-origin requests (e.g., frontend on a different subdomain).
#
# Correct order (last added = first executed):
#   CORSMiddleware          ← last added, runs first (sets CORS headers)
#   AuthCookieMiddleware    ← added before CORS, runs after (can read cookies)
#
# In practice:
#   app.add_middleware(AuthCookieMiddleware)   # Add FIRST
#   app.add_middleware(CORSMiddleware, ...)    # Add LAST (runs first)
#
# If your frontend and backend share the same origin (e.g., both on flowmanner.com
# behind Nginx), this is less critical but still best practice.
app.add_middleware(AuthCookieMiddleware)
app.include_router(api_v3_router)
```

---

### 5.8 v2 Endpoint Deprecation Gating

**How v2 endpoints remain functional during the 90-day deprecation window:**

v2 endpoints are NOT modified. The gating is done at two levels:

1. **Frontend-level routing:** The Next.js API client reads active feature flags from
   `GET /api/v1/feature-flags/active`. When `AUTH_V3_ENDPOINTS` is `true` for the
   current user (based on rollout bucket), the frontend routes all auth calls to
   `/api/v3/auth/...` instead of `/api/v2/auth/...`. When the flag is `false` (or
   the user is not in the rollout bucket), calls go to v2 unchanged.

2. **Backend v2 endpoints stay alive:** The v2 route handlers (`api/v2/auth.py`,
   `api/v2/workspaces.py`, etc.) remain registered in `main_fastapi.py` and
   functional for the full 90 days. They are only removed in a later migration
   PR (Phase 2 or Phase 3).

3. **Deprecation headers:** The versioning middleware (`api/middleware/versioning.py`)
   adds `Deprecation: true` and `Sunset: <date 90 days out>` headers to all v2
   responses after v3 reaches 100% rollout. This gives API consumers (SDK users,
   direct curl users) advance notice.

4. **No server-side routing by feature flag:** The backend does NOT inspect feature
   flags to route requests between v2 and v3. That responsibility belongs to the
   frontend and any external API consumers. This keeps the backend simple: v2 and
   v3 coexist as separate router trees until v2 is removed.

```python
# api/middleware/versioning.py — after v3 is at 100%:
DEPRECATION_DATES = {
    "v2": {
        "deprecated": True,
        "sunset": "2026-09-01T00:00:00Z",  # ~90 days after v3 launch
        "replacement": "/api/v3/",
    }
}
```

---

## 6. Feature Flags — Names, Default States, Rollout Percentages

All flags stored in `feature_flags` table. Managed via existing `api/v1/feature-flags` endpoints.

| Flag Key | Purpose | Default | Rollout Strategy |
|----------|---------|---------|-----------------|
| `AUTH_V3_SESSIONS` | Enables new session endpoints (`/auth/sessions`) | `false` | 5% → 25% → 50% → 100% new users |
| `AUTH_V3_COOKIES` | Enables httpOnly refresh cookie (dual-accept mode) | `false` | 5% → 25% → 50% → 100% new sessions |
| `AUTH_V3_API_KEYS` | Enables scoped API key CRUD | `false` | 100% (backward-compat, no risk) |
| `AUTH_V3_OIDC` | Enables workspace-scoped OIDC SSO | `false` | Workspace-by-workspace opt-in |
| `AUTH_V3_WEBHOOKS` | Enables auth event webhooks | `false` | Workspace-by-workspace opt-in |
| `AUTH_V3_SCOPES` | Enables granular scope enforcement middleware | `false` | 5% → 25% → 50% → 100% |
| `AUTH_V3_ENDPOINTS` | Master flag — gates ALL v3 auth endpoints | `false` | Starts at 5% canary |

**Flag resolution logic (per-request):**

```python
async def is_auth_v3_enabled(db: AsyncSession, user: User | None = None) -> bool:
    """Check master flag first, then user/workspace-level flags."""
    # Check global flag
    result = await db.execute(
        text("SELECT enabled_globally FROM feature_flags WHERE key = 'AUTH_V3_ENDPOINTS'")
    )
    flag = result.scalar()
    if not flag:
        return False

    # User-level rollout: hash user_id for deterministic percentage
    if user and not flag:  # partial rollout
        bucket = hash(str(user.id)) % 100
        rollout_pct = 5  # START at 5%
        return bucket < rollout_pct

    return bool(flag)
```

### Rollout Schedule

| Week | AUTH_V3_ENDPOINTS | AUTH_V3_COOKIES | Rollout Scope |
|------|-------------------|-----------------|---------------|
| 1–2 | `false` (dev only) | `false` | Internal dev testing |
| 3 | 5% new users | `false` | Canary — new registrations only |
| 4 | 25% new users | 5% new sessions | Expand canary |
| 5 | 50% new users | 25% new sessions | Half rollout |
| 6 | 100% | 50% → 100% | Full rollout |

---

## 7. Frontend Contract — Next.js Changes Required

### 7.1 API Client Changes

File(s): `frontend/src/lib/api.ts` (or equivalent API client module)

| Change | Detail |
|--------|--------|
| **Login call** | `POST /api/v2/auth/login` → `POST /api/v3/auth/sessions` (when flag enabled) |
| **Register call** | `POST /api/v2/auth/register` → `POST /api/v3/auth/users` |
| **Refresh call** | `POST /api/v2/auth/refresh` → `POST /api/v3/auth/sessions/refresh` |
| **Logout call** | `POST /api/v2/auth/logout` → `DELETE /api/v3/auth/sessions/{current_session_id}` |
| **2FA verify** | `POST /api/v2/auth/login/2fa` → `POST /api/v3/auth/sessions/verify` |
| **Profile** | `GET /api/v2/auth/me` → `GET /api/v3/auth/users/me` |

### 7.2 Token Storage

| v2 (current) | v3 (dual-accept) | v4 (future) |
|--------------|-------------------|-------------|
| Access token: localStorage | Access token: localStorage | Access token: cookie |
| Refresh token: localStorage | Refresh token: httpOnly cookie (primary), localStorage fallback | Refresh token: cookie only |

**v3 frontend logic:**
```
if flag AUTH_V3_COOKIES enabled:
    - Don't store refresh token in localStorage
    - Set credentials: 'include' on fetch/XHR
    - On refresh: POST /auth/sessions/refresh (browser auto-sends cookie)
    - On logout: DELETE /auth/sessions/{id} (clear cookie server-side)
else:
    - v2 behavior (localStorage for both tokens)
```

### 7.3 Session Management UI

New components needed:
- **Active Sessions page** (`/settings/sessions`): Lists all active sessions with device info, location, "Revoke" button
- **"This is your current session"** indicator on the current session row

### 7.4 API Key Management UI

New components:
- **API Keys page** (`/settings/api-keys`): Create, list, revoke API keys
- **"Key created" modal**: Shows full key once with "Copy" button and security warning
- **Scopes selector**: Checkbox list for granular scopes during key creation

### 7.5 Cookie Handling

```typescript
// All v3 fetch calls:
fetch('/api/v3/auth/sessions/refresh', {
  method: 'POST',
  credentials: 'include',  // Required — tells browser to send httpOnly cookies
})
```

### 7.6 Feature Flag Check

Frontend reads enabled flags from `GET /api/v1/feature-flags/active`:
```json
{
  "AUTH_V3_ENDPOINTS": true,
  "AUTH_V3_COOKIES": false,
  ...
}
```
Route v3 vs v2 endpoint calls based on which flags are enabled.

---

## 8. Test Plan

### 8.1 Unit Tests

File: `backend/tests/test_auth_v3_unit.py`

```python
"""Unit tests for Auth v3 services and models (no DB)."""

import pytest
from pydantic import ValidationError
from app.services.auth_v3_service import (
    hash_refresh_token,
    generate_api_key,
    validate_api_key_scopes,
)
from app.schemas.auth_v3 import LoginRequest, RegisterRequest, SessionResponse

class TestLoginRequestSchema:
    def test_valid_email_login(self):
        req = LoginRequest(login="user@example.com", password="securePass1!")
        assert req.login == "user@example.com"

    def test_valid_username_login(self):
        req = LoginRequest(login="testuser", password="securePass1!")
        assert req.login == "testuser"

    def test_empty_login_rejected(self):
        with pytest.raises(ValidationError):
            LoginRequest(login="", password="x")

    def test_empty_password_rejected(self):
        with pytest.raises(ValidationError):
            LoginRequest(login="user@example.com", password="")

class TestSessionResponseSchema:
    def test_serialization(self):
        from datetime import datetime, timezone
        resp = SessionResponse(
            access_token="eyJ...",
            session_id="sess_abc123",
            expires_at=datetime.now(timezone.utc),
            user={"id": 1, "email": "a@b.com", ...}
        )
        data = resp.model_dump()
        assert data["access_token"] == "eyJ..."
        assert data["session_id"] == "sess_abc123"

class TestApiKeyGeneration:
    def test_generate_produces_valid_key(self):
        key, prefix, hash_val = generate_api_key()
        assert key.startswith("fm_")
        assert len(key) > 32
        assert len(prefix) == 8
        assert len(hash_val) == 64  # SHA-256 hex

class TestScopeValidation:
    def test_valid_scopes_pass(self):
        assert validate_api_key_scopes(["missions:read"]) == True

    def test_invalid_scope_rejected(self):
        assert validate_api_key_scopes(["superadmin:destroy"]) == False

    def test_empty_scopes_rejected(self):
        assert validate_api_key_scopes([]) == False
```

### 8.2 Integration Tests

File: `backend/tests/test_auth_v3_integration.py`

```python
"""Integration tests for Auth v3 endpoints (requires test DB)."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main_fastapi import app

pytestmark = pytest.mark.anyio

@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

@pytest.fixture
async def registered_user(client):
    """Register a test user and return credentials."""
    resp = await client.post("/api/v3/auth/users", json={
        "email": "v3test@example.com",
        "password": "TestPass123!",
        "full_name": "V3 Test User",
    })
    assert resp.status_code == 201
    return resp.json()

class TestSessionEndpoints:
    async def test_login_creates_session(self, client, registered_user):
        resp = await client.post("/api/v3/auth/sessions", json={
            "login": "v3test@example.com",
            "password": "TestPass123!",
        })
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert "access_token" in data
        assert "session_id" in data
        assert data["session_id"].startswith("sess_")

    async def test_login_invalid_credentials(self, client):
        resp = await client.post("/api/v3/auth/sessions", json={
            "login": "nobody@example.com",
            "password": "wrong",
        })
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"

    async def test_refresh_with_cookie(self, client, registered_user):
        # Get session with cookie
        login_resp = await client.post("/api/v3/auth/sessions", json={
            "login": "v3test@example.com",
            "password": "TestPass123!",
        })
        cookies = login_resp.cookies

        # Refresh using cookie
        refresh_resp = await client.post(
            "/api/v3/auth/sessions/refresh",
            cookies=cookies,
        )
        assert refresh_resp.status_code == 200
        assert refresh_resp.json()["data"]["access_token"]

    async def test_list_sessions(self, client, registered_user):
        # First login to get token
        login_resp = await client.post("/api/v3/auth/sessions", json={
            "login": "v3test@example.com",
            "password": "TestPass123!",
        })
        token = login_resp.json()["data"]["access_token"]

        # List sessions
        resp = await client.get(
            "/api/v3/auth/sessions",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        sessions = resp.json()["data"]
        assert len(sessions) >= 1

    async def test_revoke_session(self, client, registered_user):
        login_resp = await client.post("/api/v3/auth/sessions", json={
            "login": "v3test@example.com",
            "password": "TestPass123!",
        })
        token = login_resp.json()["data"]["access_token"]
        session_id = login_resp.json()["data"]["session_id"]

        # Revoke
        resp = await client.delete(
            f"/api/v3/auth/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 204

class TestApiKeyEndpoints:
    async def test_create_and_list_keys(self, client, registered_user):
        # Login
        login_resp = await client.post("/api/v3/auth/sessions", json={
            "login": "v3test@example.com",
            "password": "TestPass123!",
        })
        token = login_resp.json()["data"]["access_token"]

        # Create API key
        resp = await client.post(
            "/api/v3/auth/api-keys",
            json={"name": "CI Key", "scopes": ["missions:read", "missions:write"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["key"].startswith("fm_")
        assert data["key_prefix"].startswith("fm_")
        key_prefix = data["key_prefix"]

        # List keys — full key NOT shown
        list_resp = await client.get(
            "/api/v3/auth/api-keys",
            headers={"Authorization": f"Bearer {token}"},
        )
        keys = list_resp.json()["data"]
        assert len(keys) >= 1
        found = [k for k in keys if k["key_prefix"] == key_prefix]
        assert len(found) == 1
        assert "key" not in found[0]  # Key not returned in list

    async def test_revoke_key(self, client, registered_user):
        login_resp = await client.post("/api/v3/auth/sessions", json={
            "login": "v3test@example.com",
            "password": "TestPass123!",
        })
        token = login_resp.json()["data"]["access_token"]

        create_resp = await client.post(
            "/api/v3/auth/api-keys",
            json={"name": "Temp Key", "scopes": ["missions:read"]},
            headers={"Authorization": f"Bearer {token}"},
        )
        key_id = create_resp.json()["data"]["id"]

        delete_resp = await client.delete(
            f"/api/v3/auth/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert delete_resp.status_code == 204

class TestRateLimiting:
    async def test_login_rate_limit(self, client, registered_user):
        """Hit the login endpoint repeatedly to trigger 429."""
        for i in range(10):
            resp = await client.post("/api/v3/auth/sessions", json={
                "login": "wrong@example.com",
                "password": "wrong",
            })
            if resp.status_code == 429:
                assert "Retry-After" in resp.headers or "RateLimit-Reset" in resp.headers
                return
        pytest.fail("Rate limit was not triggered")

class Test2FAFlow:
    async def test_2fa_challenge_returned(self, client):
        """User with TOTP enabled should get requires_2fa: true after login."""
        # (Requires seeded test user with totp_enabled=True)
        ...
```

### 8.3 E2E Scenarios (Manual + Playwright)

1. **Registration → Login → Session visible → Logout → Cookie cleared**
2. **Login on Chrome → See session on Chrome → Login on Firefox → See 2 sessions → Revoke Firefox session**
3. **Enable 2FA → Login → Get temp_token → Submit wrong code → 401 → Submit correct code → Session created**
4. **Create API key with `missions:read` → Use key to call `GET /api/v3/missions` → 200 → Try `POST /api/v3/missions` → 403**
5. **Password change → All existing sessions revoked**

### 8.4 Mock Strategies

```python
# pytest fixture: mock Redis for rate limiting
@pytest.fixture
def mock_redis(mocker):
    mock = mocker.patch("app.services.auth_v3_service.redis_client")
    mock.get.return_value = None
    mock.incr.return_value = 1
    mock.ttl.return_value = 60
    return mock

# pytest fixture: mock feature flag for v3 tests
@pytest.fixture
async def enable_v3_flags(db_session):
    await db_session.execute(text("""
        UPDATE feature_flags SET enabled_globally = true
        WHERE key IN ('AUTH_V3_ENDPOINTS', 'AUTH_V3_COOKIES', 'AUTH_V3_SESSIONS',
                       'AUTH_V3_API_KEYS', 'AUTH_V3_SCOPES')
    """))
    await db_session.commit()
```

---

## 9. Rollback Plan — Canary Failure Response by Stage

### Canary Stages

| Stage | Rollout % | Scope | Monitoring Period |
|-------|-----------|-------|-------------------|
| 1 | 5% | New user registrations only | 48 hours |
| 2 | 25% | New users + 25% of existing user logins | 72 hours |
| 3 | 50% | Half of all traffic | 168 hours (1 week) |
| 4 | 100% | All traffic | Permanent |

### Stage 1 Rollback (5% — Low Risk)

**Trigger:** Login success rate drops > 5% OR 2FA failure rate spikes > 3%
**Action:**
1. Set `AUTH_V3_ENDPOINTS = false` in feature_flags table (instant)
2. All traffic falls back to v2 endpoints
3. v3 session data is orphaned but harmless — cleanup later
4. **No DB rollback needed** — `auth_sessions` table just sits empty

### Stage 2 Rollback (25% — Medium Risk)

**Trigger:** Session creation failures > 2% OR cookie issues on specific browsers
**Action:**
1. Set `AUTH_V3_ENDPOINTS = false` AND `AUTH_V3_COOKIES = false`
2. Users with v3 sessions may lose their session on next request — they re-login via v2
3. **Impact:** ~25% of users need to re-login (one-time)
4. **No DB rollback needed**

### Stage 3 Rollback (50% — Higher Risk)

**Trigger:** Refresh token errors > 1% OR token reuse detection false positives
**Action:**
1. Set `AUTH_V3_ENDPOINTS = false`
2. Force-invalidate all v3 sessions: `UPDATE auth_sessions SET is_active = false`
3. **Impact:** ~50% of users re-login via v2
4. **No DB rollback needed** — just flag toggle + session invalidation

### Stage 4 Rollback (100% — Catastrophic Only)

**Trigger:** Major auth outage, data breach, or security vulnerability
**Action:**
1. Set `AUTH_V3_ENDPOINTS = false`
2. `UPDATE auth_sessions SET is_active = false, revoked_at = NOW(), revoke_reason = 'emergency_rollback'`
3. **DB rollback:** Run downgrade migration (`alembic downgrade auth_v3_001-1`) only if tables cause issues
4. All users re-login via v2

### Rollback Command One-Liner

```bash
# Instant rollback (via admin endpoint or direct DB):
docker compose exec backend python -c "
from app.database import AsyncSessionLocal
from sqlalchemy import text
async def rollback():
    async with AsyncSessionLocal() as db:
        await db.execute(text(\"UPDATE feature_flags SET enabled_globally = false WHERE key = 'AUTH_V3_ENDPOINTS'\"))
        await db.execute(text(\"UPDATE auth_sessions SET is_active = false, revoked_at = NOW(), revoke_reason = 'emergency_rollback'\"))
        await db.commit()
import asyncio
asyncio.run(rollback())
"
```

---

## 10. Week-by-Week Breakdown (6 Weeks)

### Week 1: Models + DB Migration + Schemas

**Goal:** New tables exist; Pydantic schemas are code-complete and tested.

- [ ] Create `models/auth_v3_models.py` — AuthSession, ApiKey, AuthWebhookSubscription, OIDCProviderConfig
- [ ] Register models in `models/__init__.py`
- [ ] Write Alembic migration `auth_v3_init.py`
- [ ] Run migration on dev DB: `alembic upgrade head`
- [ ] Create `schemas/auth_v3.py` — all request/response Pydantic models
- [ ] Write unit tests for schemas: validation, serialization, edge cases
- [ ] Create `api/v3/base.py` — `ok()`, `err()`, `paginated()` helpers
- [ ] Create `api/v3/middleware.py` — exception handlers
- [ ] Create `api/v3/__init__.py` — router assembly

### Week 2: Core Auth Endpoints (Sessions + Users)

**Goal:** Login, register, refresh, logout work end-to-end with tests.

- [ ] Implement `services/auth_v3_service.py` — session create, session revoke, token hash/store, API key encrypt
- [ ] Implement `POST /auth/sessions` (login) in `api/v3/auth.py`
- [ ] Implement `POST /auth/users` (register) in `api/v3/auth.py`
- [ ] Implement `POST /auth/sessions/refresh` in `api/v3/auth.py`
- [ ] Implement `DELETE /auth/sessions/{id}` (logout) in `api/v3/auth.py`
- [ ] Implement `GET /auth/users/me` and `PATCH /auth/users/me`
- [ ] Implement `POST /auth/sessions/verify` (2FA verify)
- [ ] Create `api/v3/auth_cookies.py` — set/clear cookie helpers
- [ ] Create `middleware/auth_cookie.py`
- [ ] Register routes and middleware in `main_fastapi.py`
- [ ] Add `"v3"` to `api/middleware/versioning.py` SUPPORTED_VERSIONS
- [ ] Add `AUTH_V3_COOKIE_*` config to `config.py`
- [ ] Write integration tests for all 6 endpoints (section 8.2)
- [ ] Manual smoke test: register → login → refresh → logout via curl

### Week 3: Session Management + Rate Limiter

**Goal:** Session list/revoke works; Redis-backed rate limiter active.

- [ ] Implement `GET /auth/sessions` (list sessions) in `api/v3/auth_sessions.py`
- [ ] Implement `DELETE /auth/sessions/{id}` (revoke specific session)
- [ ] Create Redis-backed rate limiter in `api/middleware/rate_limit_v3.py`
- [ ] Implement `RateLimit-*` headers: `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset`
- [ ] Add rate limits to all v3 auth endpoints
- [ ] Write integration tests for session management
- [ ] Seed feature flags: `AUTH_V3_SESSIONS`, `AUTH_V3_COOKIES`, `AUTH_V3_ENDPOINTS`
- [ ] Enable `AUTH_V3_ENDPOINTS` for dev testing
- [ ] **Stage 1 canary: 5% new users** — deploy to staging, monitor 48h
- [ ] Document curl examples for all new endpoints

### Week 4: API Keys + OIDC

**Goal:** Scoped API key CRUD operational; OIDC provider integration functional.

- [ ] Implement `POST /auth/api-keys` in `api/v3/auth_api_keys.py`
- [ ] Implement `GET /auth/api-keys`
- [ ] Implement `DELETE /auth/api-keys/{id}`
- [ ] Implement AES-256 encryption for API key storage (reuse existing `AES_ENCRYPTION_KEY` from config)
- [ ] Implement `POST /auth/oidc/{provider}/login` and callback in `api/v3/auth_oidc.py`
- [ ] Implement workspace-scoped OIDC provider config CRUD
- [ ] Write integration tests for API keys and OIDC
- [ ] Write unit tests for scope validation logic
- [ ] Enable `AUTH_V3_API_KEYS` flag
- [ ] **Stage 2 canary: 25% new users** — deploy, monitor 72h

### Week 5: Webhooks + Scope Middleware + Frontend Alignment

**Goal:** Auth webhooks operational; scope enforcement active; frontend team can start integrating.

- [ ] Implement auth webhook CRUD endpoints in `api/v3/auth_webhooks.py`
- [ ] Implement webhook dispatch service (auth events → HTTP POST to subscriber URLs)
- [ ] HMAC-SHA256 payload signing for webhook delivery
- [ ] Implement `middleware/scope_validator.py` — enforce granular scopes on v3 routes
- [ ] Add `require_scope()` dependency factory to `api/deps.py`
- [ ] Write webhook integration tests + scope validation tests
- [ ] Publish frontend contract document (section 7)
- [ ] Coordinate with frontend team on API client changes
- [ ] **Stage 3 canary: 50% new users** — deploy, monitor 1 week

### Week 6: Full Rollout + Monitoring + Bug Fixes

**Goal:** 100% rollout; monitoring dashboards live; all edge cases resolved.

- [ ] Enable `AUTH_V3_ENDPOINTS = true` globally (100%)
- [ ] Monitor metrics:
  - Login success rate (target: > 99.5%)
  - Refresh success rate (target: > 99.9%)
  - 2FA failure rate (target: < 2%)
  - Token reuse detection events (target: near-zero, investigate each)
  - Session creation latency (p50 < 200ms, p95 < 500ms)
- [ ] Add alerts:
  - `auth_login_failure_rate > 10%` for 5 minutes → PagerDuty
  - `auth_refresh_failure_rate > 5%` for 5 minutes → PagerDuty
  - `auth_token_reuse_detected` → High-priority Slack
- [ ] Conduct load test: 100 concurrent logins/sec → verify no degradation
- [ ] Security review: cookie attributes, token hashing, API key encryption
- [ ] Bug bash: all integration tests pass at 100%
- [ ] Clean up any v2→v3 migration edge cases found in monitoring
- [ ] Mark v2 auth endpoints as deprecated (add deprecation headers via versioning middleware)

---

## 11. Observability & Logging

### 11.1 Structured Logging

All v3 endpoints emit structured JSON logs with the following fields:

```json
{
  "timestamp": "2026-06-01T12:00:00.000Z",
  "level": "INFO",
  "service": "auth-v3",
  "trace_id": "trc_abc123",
  "user_id": 42,
  "session_id": "sess_xyz789",
  "endpoint": "POST /api/v3/auth/sessions",
  "status_code": 201,
  "duration_ms": 87,
  "ip": "10.99.0.1",
  "user_agent": "Chrome/...",
  "message": "Session created"
}
```

### 11.2 Trace Context Propagation

The `trace_id` in error responses and logs is generated by middleware at the
request boundary (UUID v4). It's injected into:
- Response body `error.trace_id`
- All log entries for the request
- Downstream service calls (Celery tasks, webhook dispatches) via a `X-Trace-Id` header

```python
# middleware/trace_context.py
@app.middleware("http")
async def trace_context_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-Id", str(uuid4()))
    request.state.trace_id = trace_id
    # Inject into logging context
    with logger.contextualize(trace_id=trace_id):
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response
```

### 11.3 Key Metrics (Prometheus / CloudWatch)

| Metric | Type | Labels | Alert Threshold |
|--------|------|--------|-----------------|
| `auth_login_attempts_total` | Counter | `status=success|failure|2fa_required` | — |
| `auth_login_duration_ms` | Histogram | `status` | p95 > 500ms |
| `auth_refresh_attempts_total` | Counter | `status=success|failure` | — |
| `auth_token_reuse_detected` | Counter | — | Any occurrence |
| `auth_session_revoke_total` | Counter | `reason=logout|password_change|admin|reuse` | — |
| `auth_rate_limit_hits_total` | Counter | `endpoint` | > 10/min per endpoint |
| `auth_cookie_set_total` | Counter | — | — |
| `auth_cookie_clear_total` | Counter | — | — |

### 11.4 Alerts

| Alert | Condition | Channel |
|-------|-----------|---------|
| Login failure rate spike | `auth_login_failure_rate > 10%` for 5 min | PagerDuty |
| Refresh failure rate spike | `auth_refresh_failure_rate > 5%` for 5 min | PagerDuty |
| Token reuse detected | Any `auth_token_reuse_detected` event | High-priority Slack |
| Rate limit surge | > 100 rate limit hits in 5 min | Slack |
| Session creation latency spike | p95 > 2s for 10 min | Slack |

---

## Appendix A: Sample Curl Diffs (v2 → v3)

```bash
# ── Login ──
# v2:
curl -X POST https://flowmanner.com/api/v2/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username_or_email": "user@example.com", "password": "pass123"}'
# → { "data": { "access_token": "...", "refresh_token": "..." }, "meta": {...}, "error": null }

# v3:
curl -X POST https://flowmanner.com/api/v3/auth/sessions \
  -H "Content-Type: application/json" \
  -d '{"login": "user@example.com", "password": "pass123", "provider": "credentials"}' \
  -c cookies.txt -v
# → Set-Cookie: refresh_token=...; HttpOnly; Secure; SameSite=Strict; Path=/api/v3/auth
# → { "data": { "access_token": "...", "session_id": "sess_abc", "expires_at": "2026-06-08T...", "user": {...} }, "meta": {...}, "error": null }

# ── Refresh ──
# v2:
curl -X POST https://flowmanner.com/api/v2/auth/refresh \
  -d '{"refresh_token": "old-token"}'

# v3 (cookie-based):
curl -X POST https://flowmanner.com/api/v3/auth/sessions/refresh \
  -b cookies.txt -c cookies.txt
# Browser auto-sends httpOnly cookie; new cookie set in response

# v3 (body-based fallback):
curl -X POST https://flowmanner.com/api/v3/auth/sessions/refresh?token_response=body \
  -d '{"refresh_token": "old-token"}'

# ── Logout ──
# v2:
curl -X POST https://flowmanner.com/api/v2/auth/logout \
  -H "Authorization: Bearer <token>" \
  -d '{"refresh_token": "token-to-revoke"}'

# v3:
curl -X DELETE https://flowmanner.com/api/v3/auth/sessions/sess_abc123 \
  -H "Authorization: Bearer <token>" \
  -b cookies.txt
# → Clear refresh_token cookie in response

# ── Register ──
# v2:
curl -X POST https://flowmanner.com/api/v2/auth/register \
  -d '{"email": "new@example.com", "password": "Str0ngP@ss!", "full_name": "New User"}'

# v3:
curl -X POST https://flowmanner.com/api/v3/auth/users \
  -d '{"email": "new@example.com", "password": "Str0ngP@ss!", "username": "newuser", "full_name": "New User"}'

# ── 2FA Verify ──
# v2:
curl -X POST https://flowmanner.com/api/v2/auth/login/2fa \
  -d '{"temp_token": "...", "code": "123456"}'

# v3:
curl -X POST https://flowmanner.com/api/v3/auth/sessions/verify \
  -d '{"temp_token": "...", "code": "123456"}'

# ── List Sessions (NEW in v3) ──
curl https://flowmanner.com/api/v3/auth/sessions \
  -H "Authorization: Bearer <token>"
# → { "data": [{ "id": "sess_abc", "device_name": "Chrome macOS", "ip_address": "...", "is_current": true, ... }], ... }

# ── Create API Key (NEW in v3) ──
curl -X POST https://flowmanner.com/api/v3/auth/api-keys \
  -H "Authorization: Bearer <token>" \
  -d '{"name": "CI/CD Pipeline", "scopes": ["missions:read", "missions:write"], "expires_in_days": 90}'
# → { "data": { "id": "key_xyz", "name": "CI/CD Pipeline", "key": "fm_a1b2c3d4e5f6...", "key_prefix": "fm_a1b2c3d4", ... }, ... }
# ⚠️  The full key is shown ONLY in this response.
```

---

## Appendix B: Security Considerations

1. **Refresh token hashing:** `auth_sessions.refresh_token_hash` stores SHA-256 of refresh token, not plaintext. This means if the sessions table is compromised, refresh tokens cannot be used directly.
2. **API key encryption:** Full API keys are AES-256 encrypted at rest. Only the SHA-256 hash is indexed for lookup. The plaintext key is returned ONCE on creation.
3. **Token reuse detection:** Carried forward from v2 — if a revoked refresh token is used, the entire family is revoked.
4. **Cookie attributes:** `HttpOnly`, `Secure`, `SameSite=Strict` — prevents XSS token theft, CSRF attacks.
5. **Separate cookie paths:** Refresh cookie scoped to `/api/v3/auth` — not sent with every API call; only on auth endpoints.
