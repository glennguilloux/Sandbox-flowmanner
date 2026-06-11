"""Integration v2 schemas — HTTP outbound configs, OAuth apps, and connections."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class HttpIntegrationConfigCreate(BaseModel):
    """Request body for creating an HTTP integration config."""

    name: str = Field(..., min_length=1, max_length=255)
    base_url: str = Field(..., min_length=1)
    default_headers: dict[str, str] | None = None
    auth_type: str | None = None  # none, basic, bearer, api_key
    auth_config: dict[str, str] | None = None  # {"username": "...", "password": "..."} or {"token": "..."} etc.
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_retries: int = Field(default=3, ge=0, le=10)


class HttpIntegrationConfigUpdate(BaseModel):
    """Request body for updating an HTTP integration config."""

    name: str | None = None
    base_url: str | None = None
    default_headers: dict[str, str] | None = None
    auth_type: str | None = None
    auth_config: dict[str, str] | None = None
    timeout_seconds: int | None = None
    max_retries: int | None = None
    is_active: bool | None = None


class HttpIntegrationConfigResponse(BaseModel):
    """Response model for an HTTP integration config."""

    id: str
    user_id: int
    name: str
    base_url: str
    default_headers: dict[str, str] | None = None
    auth_type: str | None = None
    # auth_config is never returned to avoid leaking secrets
    timeout_seconds: int = 30
    max_retries: int = 3
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True}


class HttpIntegrationLogResponse(BaseModel):
    """Response model for an HTTP integration execution log."""

    id: str
    integration_id: str
    request_method: str
    request_url: str
    request_headers: dict[str, Any] | None = None
    response_status: int | None = None
    response_body_preview: str | None = None  # truncated to 1KB
    status: str  # success, failed, timeout
    error_message: str | None = None
    duration_ms: int | None = None
    timestamp: str | None = None

    model_config = {"from_attributes": True}


# ── OAuth App Schemas ─────────────────────────────────────────────────────────


class OAuthAppCreate(BaseModel):
    """Request body for registering a user-provided OAuth app."""

    provider: str = Field(..., min_length=1, max_length=50)
    client_id: str = Field(..., min_length=1)
    client_secret: str = Field(..., min_length=1)
    scopes: list[str] | None = None


class OAuthAppUpdate(BaseModel):
    """Request body for updating an OAuth app."""

    client_id: str | None = None
    client_secret: str | None = None
    scopes: list[str] | None = None
    is_active: bool | None = None


class OAuthAppResponse(BaseModel):
    """Response model for an OAuth app — never includes secrets."""

    id: str
    provider: str
    scopes: list[str] | None = None
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True}


# ── OAuth Connection Schemas ──────────────────────────────────────────────────


class OAuthInitiateRequest(BaseModel):
    """Request to start an OAuth authorization flow."""

    provider: str = Field(..., min_length=1, max_length=50)
    app_id: str = Field(..., min_length=1)
    redirect_uri: str | None = None  # override callback URL if needed


class OAuthInitiateResponse(BaseModel):
    """Response from OAuth initiate — contains the authorization URL."""

    authorization_url: str
    state: str  # CSRF state parameter for callback validation


class OAuthConnectionResponse(BaseModel):
    """Response model for an OAuth connection — never includes tokens."""

    id: str
    provider: str
    app_id: str
    token_type: str | None = None
    expires_at: str | None = None
    provider_account_id: str | None = None
    provider_account_name: str | None = None
    scopes: list[str] | None = None
    status: str = "active"
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True}
