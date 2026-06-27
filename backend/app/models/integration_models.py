"""Integration models — HTTP outbound configs, OAuth apps, and connections."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class HttpIntegrationConfig(Base, TimestampMixin):
    """User-configured HTTP outbound integration.

    Stores connection details for external HTTP APIs that missions
    can call during execution. Auth secrets are encrypted at rest
    via the same mechanism used for BYOK keys.
    """

    __tablename__ = "http_integration_configs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    default_headers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    auth_type: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )  # none, basic, bearer, api_key
    auth_config_encrypted: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )  # encrypted JSON blob with credentials
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class HttpIntegrationLog(Base, TimestampMixin):
    """Execution log for HTTP outbound integration calls."""

    __tablename__ = "http_integration_logs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    integration_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("http_integration_configs.id"),
        nullable=False,
        index=True,
    )
    mission_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("missions.id"),
        nullable=True,
        index=True,
    )
    task_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    request_method: Mapped[str] = mapped_column(String(10), nullable=False)
    request_url: Mapped[str] = mapped_column(String(4096), nullable=False)
    request_headers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    request_body_preview: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )  # truncated to 1KB
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_headers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    response_body_preview: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )  # truncated to 1KB
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
    )  # pending, success, failed, timeout
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )


# ── OAuth User-Provided App & Connection Models ───────────────────────────────


class IntegrationHealthRecord(Base, TimestampMixin):
    """Per-integration health check result stored by the periodic Celery task."""

    __tablename__ = "integration_health_records"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    integration_slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )  # healthy, degraded, down, unknown
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )


class UserOAuthApp(Base, TimestampMixin):
    """User-provided OAuth application credentials (per service, per user).

    Users register their own OAuth apps (client_id/secret) for services
    like Slack, GitHub, Notion, Google Drive, and Linear.  Secrets are
    encrypted at rest using Fernet encryption.
    """

    __tablename__ = "user_oauth_apps"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )  # slack, github, notion, google_drive, linear
    encrypted_client_id: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_client_secret: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def get_client_id(self) -> str:
        """Decrypt and return the OAuth client_id."""
        from app.integrations.oauth import decrypt_token

        return decrypt_token(self.encrypted_client_id)

    def get_client_secret(self) -> str:
        """Decrypt and return the OAuth client_secret."""
        from app.integrations.oauth import decrypt_token

        return decrypt_token(self.encrypted_client_secret)


class UserOAuthConnection(Base, TimestampMixin):
    """User OAuth connections to external services.

    Stores encrypted access/refresh tokens after a user completes the OAuth
    authorization flow.  Each connection links back to a registered
    UserOAuthApp.
    """

    __tablename__ = "user_oauth_connections"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )  # slack, github, notion, google_drive, linear
    app_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_oauth_apps.id"),
        nullable=False,
        index=True,
    )
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_type: Mapped[str | None] = mapped_column(String(50), nullable=True, default="Bearer")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_account_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scopes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        index=True,
    )  # active, expired, revoked

    def get_access_token(self) -> str:
        """Decrypt and return the OAuth access token."""
        from app.integrations.oauth import decrypt_token

        return decrypt_token(self.encrypted_access_token)

    def get_refresh_token(self) -> str | None:
        """Decrypt and return the OAuth refresh token, or None if not set."""
        if not self.encrypted_refresh_token:
            return None
        from app.integrations.oauth import decrypt_token

        return decrypt_token(self.encrypted_refresh_token)


class IntegrationUsageLog(Base, TimestampMixin):
    """Per-user, per-integration usage log for analytics.

    Records each integration action execution (success or failure) with
    timing and error details.  Aggregated by IntegrationUsageService to
    power the usage dashboard on the frontend.

    Privacy: No request/response bodies or PII are stored — only slug,
    action, status code, latency, and user_id.
    """

    __tablename__ = "integration_usage_logs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    integration_slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    action: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )  # e.g. "send_message", "create_issue"
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="success",
    )  # success, failed, timeout
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )


class IntegrationIncident(Base, TimestampMixin):
    """Integration incident record.

    Created automatically when a health check detects a status transition
    from ``healthy`` to ``degraded`` or ``down``.  Resolved when the
    integration returns to ``healthy``.  Exposed on the public status page.
    """

    __tablename__ = "integration_incidents"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    integration_slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )  # minor, major, critical
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="open",
    )  # open, monitoring, resolved
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        index=True,
    )
