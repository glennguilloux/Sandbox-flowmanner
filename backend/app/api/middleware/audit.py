"""Audit logging middleware and utilities."""

import json
import logging
import time
from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Auth-related actions that should always be logged
AUTH_ACTIONS = {
    "POST": {
        "/api/auth/login": "login",
        "/api/auth/register": "register",
        "/api/auth/refresh": "token_refresh",
        "/api/auth/logout": "logout",
        "/api/auth/2fa/setup": "2fa_setup",
        "/api/auth/2fa/verify-setup": "2fa_verify_setup",
        "/api/auth/2fa/disable": "2fa_disable",
        "/api/auth/2fa/backup-codes/regenerate": "2fa_backup_regenerate",
        "/api/auth/login/2fa": "2fa_login",
    },
}


async def log_auth_event(
    db_session_factory,
    user_id: int | None,
    user_email: str | None,
    action: str,
    success: bool,
    ip_address: str | None = None,
    user_agent: str | None = None,
    endpoint: str | None = None,
    method: str | None = None,
    details: dict | None = None,
):
    """Log an authentication event to the audit log.

    This is a convenience function for manual audit logging.
    The AuditMiddleware handles automatic logging for auth endpoints.
    """
    try:
        # Import here to avoid circular imports
        from sqlalchemy import text

        async with db_session_factory() as db:
            await db.execute(
                text(
                    """
                    INSERT INTO audit_logs (id, action, action_details, ip_address, user_id, user_email, endpoint, method, user_agent, timestamp, created_at, updated_at)
                    VALUES (:id, :action, :action_details, :ip_address, :user_id, :user_email, :endpoint, :method, :user_agent, :timestamp, :timestamp, :timestamp)
                    """
                ),
                {
                    "id": str(__import__("uuid").uuid4()),
                    "action": action,
                    "action_details": json.dumps(
                        {**(details or {}), "success": success}
                    ),
                    "ip_address": ip_address,
                    "user_id": str(user_id) if user_id else None,
                    "user_email": user_email,
                    "endpoint": endpoint,
                    "method": method,
                    "user_agent": user_agent,
                    "timestamp": datetime.now(UTC),
                },
            )
            await db.commit()
    except Exception as e:
        # Audit logging should never break the application
        logger.error('Failed to write audit log: %s', e)


async def log_event(
    user_id: int | str | None,
    action: str,
    details: dict | None = None,
    ip_address: str | None = None,
    endpoint: str | None = None,
):
    """Convenience wrapper for non-auth audit events (BYOK, missions, etc.)."""
    from app.database import AsyncSessionLocal

    await log_auth_event(
        db_session_factory=AsyncSessionLocal,
        user_id=user_id,
        user_email=None,
        action=action,
        success=True,
        ip_address=ip_address,
        endpoint=endpoint,
        details=details,
    )


class AuditMiddleware(BaseHTTPMiddleware):
    """Automatically log authentication-related events."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.monotonic()
        response = await call_next(request)
        duration_ms = (time.monotonic() - start_time) * 1000

        # Only log auth endpoints
        method = request.method
        path = request.url.path

        action = None
        if method in AUTH_ACTIONS:
            action = AUTH_ACTIONS[method].get(path)

        if action:
            # Extract user info from request state (set by auth middleware or deps)
            user_id = getattr(request.state, "user_id", None)
            user_email = getattr(request.state, "user_email", None)

            # Determine success from status code
            success = response.status_code < 400

            # Get client info
            ip = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")

            # Log asynchronously (fire and forget)
            try:
                import asyncio

                from app.database import AsyncSessionLocal

                asyncio.create_task(
                    log_auth_event(
                        db_session_factory=AsyncSessionLocal,
                        user_id=user_id,
                        user_email=user_email,
                        action=action,
                        success=success,
                        ip_address=ip,
                        user_agent=user_agent,
                        endpoint=path,
                        method=method,
                        details={
                            "status_code": response.status_code,
                            "duration_ms": round(duration_ms, 2),
                        },
                    )
                )
            except Exception:
                pass  # Never let audit logging break the request (already logged above)

        return response
