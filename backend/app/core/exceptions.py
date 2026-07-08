"""Typed error hierarchy for Flowmanner API.

All API-facing errors inherit from ``AppError``.  Each subclass sets
``code`` (machine-readable string) and ``http_status`` (HTTP status code)
as class attributes so a single exception handler can build the correct
envelope for any version (v2/v3).

Usage::

    raise NotFoundAppError("Mission not found", details={"mission_id": "123"})
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base for all API-facing errors.

    Subclasses override ``code`` and ``http_status`` class attributes.
    """

    code: str = "APP_ERROR"
    http_status: int = 400

    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details


class ValidationAppError(AppError):
    """Bad input / schema violation — HTTP 422."""

    code = "VALIDATION_ERROR"
    http_status = 422


class NotFoundAppError(AppError):
    """Resource not found — HTTP 404."""

    code = "NOT_FOUND"
    http_status = 404


class ConflictAppError(AppError):
    """State conflict (e.g. duplicate, invalid transition) — HTTP 409."""

    code = "CONFLICT"
    http_status = 409


class AuthAppError(AppError):
    """Authentication / authorization failure — HTTP 401."""

    code = "UNAUTHORIZED"
    http_status = 401


class ForbiddenAppError(AppError):
    """Insufficient permissions — HTTP 403."""

    code = "FORBIDDEN"
    http_status = 403


class BudgetAppError(AppError):
    """Budget exceeded — HTTP 402."""

    code = "BUDGET_EXHAUSTED"
    http_status = 402


class ProviderAppError(AppError):
    """Upstream LLM provider failure — HTTP 502."""

    code = "PROVIDER_ERROR"
    http_status = 502


class RateLimitAppError(AppError):
    """Rate limit exceeded — HTTP 429."""

    code = "RATE_LIMITED"
    http_status = 429
