"""Auth v3 Pydantic schemas — typed request/response models.

All request/response schemas for the v3 auth API. Follow the { data, meta, error }
envelope pattern. Response schemas use from_attributes=True for ORM serialization.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

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

    @model_validator(mode="after")
    def validate_login(self):
        """Basic email format check — only for credentials provider."""
        if self.provider == "credentials" and "@" in self.login and self.login.count("@") != 1:
            raise ValueError("Invalid email format")
        return self


class RegisterRequest(BaseModel):
    """POST /auth/users — register a new user."""

    email: EmailStr = Field(..., max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    username: str | None = Field(default=None, max_length=100)
    full_name: str | None = Field(default=None, max_length=200)


class Verify2FARequest(BaseModel):
    """POST /auth/sessions/verify — verify 2FA after login challenge."""

    temp_token: str
    code: str = Field(..., min_length=6, max_length=8)


class RefreshSessionRequest(BaseModel):
    """POST /auth/sessions/refresh — refresh access token.

    Refresh token read from httpOnly cookie (primary) or request body (fallback
    with ?token_response=body).
    """

    refresh_token: str | None = Field(default=None, description="Required if not using cookies")


class CreateApiKeyRequest(BaseModel):
    """POST /auth/api-keys — create a scoped API key."""

    name: str = Field(..., min_length=1, max_length=100)
    scopes: list[str] = Field(default_factory=lambda: ["missions:read"])
    workspace_id: str | None = Field(default=None)
    expires_in_days: int | None = Field(default=None, ge=1, le=365)


class UpdateUserRequest(BaseModel):
    """PATCH /auth/users/me — update current user profile."""

    full_name: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    avatar_url: str | None = Field(default=None, max_length=500)


class CreateWebhookRequest(BaseModel):
    """POST /auth/webhooks — create auth event webhook subscription."""

    url: str = Field(..., max_length=2000)
    events: list[str] = Field(..., min_length=1)
    workspace_id: str = Field(..., min_length=36)


class UpdateWebhookRequest(BaseModel):
    """PATCH /auth/webhooks/{id} — update webhook subscription."""

    url: str | None = Field(default=None)
    events: list[str] | None = Field(default=None)
    is_active: bool | None = Field(default=None)


class OIDCLoginRequest(BaseModel):
    """POST /auth/oidc/{provider}/login — initiate OIDC login flow."""

    workspace_id: str | None = Field(default=None)
    redirect_uri: str = Field(..., max_length=2000)


# ═══════════════════════════════════════════════
# Response Schemas
# ═══════════════════════════════════════════════


class UserSummary(BaseModel):
    """Brief user info embedded in session responses."""

    id: int
    email: str
    username: str | None
    full_name: str | None
    role: str
    avatar_url: str | None
    totp_enabled: bool

    model_config = ConfigDict(from_attributes=True)


class SessionResponse(BaseModel):
    """Returned after successful login/register/refresh."""

    access_token: str
    session_id: str
    expires_at: datetime
    user: UserSummary


class UserResponse(BaseModel):
    """GET /auth/users/me — full user profile."""

    id: int
    email: str
    username: str | None
    full_name: str | None
    role: str
    is_admin: bool
    is_active: bool
    avatar_url: str | None
    totp_enabled: bool
    created_at: datetime
    last_login_at: datetime | None
    onboarding_step: str | None
    onboarding_completed: bool

    model_config = ConfigDict(from_attributes=True)


class SessionListResponse(BaseModel):
    """GET /auth/sessions — list active sessions."""

    id: str
    device_name: str | None
    device_os: str | None
    browser: str | None
    ip_address: str | None
    location: str | None
    is_current: bool = False  # True if this is the session making the request
    last_used_at: datetime | None
    created_at: datetime
    expires_at: datetime


class ApiKeyResponse(BaseModel):
    """Returned on API key creation (only time full key is shown)."""

    id: str
    name: str
    key: str  # Full key — shown ONCE
    key_prefix: str
    scopes: list[str]
    expires_at: datetime | None
    created_at: datetime


class ApiKeyListResponse(BaseModel):
    """GET /auth/api-keys — list user's API keys (key never shown)."""

    id: str
    name: str
    key_prefix: str
    scopes: list[str]
    is_active: bool
    last_used_at: datetime | None
    expires_at: datetime | None
    created_at: datetime


class WebhookResponse(BaseModel):
    """Webhook subscription detail."""

    id: str
    workspace_id: str
    url: str
    events: list[str]
    is_active: bool
    created_at: datetime
    last_delivery_at: datetime | None
    failure_count: int


class TempTokenResponse(BaseModel):
    """Returned when 2FA is required after login."""

    requires_2fa: bool = True
    temp_token: str
    methods: list[str] = ["totp"]  # Future: ["totp", "webauthn"]
