"""Mission error hierarchy — used by mission_executor and its sub-services.

All mission errors inherit from ``AppError`` (typed error hierarchy) so the
unified exception handler in ``main_fastapi.py`` can build the correct
envelope for any API version.

.. note:: **``http_status`` is authoritative for v1/unversioned paths only.**
   For ``/api/v2/*`` and ``/api/v3/*`` routes, more-specific exception
   handlers registered in ``api/v2/middleware.py`` and ``api/v3/middleware.py``
   catch MissionError subclasses before the unified ``AppError`` handler
   and return their own hardcoded status codes.  Do not assume ``http_status``
   on these classes will be the actual HTTP status for v2/v3 requests.
"""

from __future__ import annotations

from typing import Any

from app.core.exceptions import AppError, ConflictAppError, ForbiddenAppError, NotFoundAppError, ValidationAppError


class MissionError(AppError):
    """Base for all mission errors."""

    code = "MISSION_ERROR"
    http_status = 400


class RetryableMissionError(MissionError):
    """Transient error — retry may fix it (timeout, rate limit, 5xx)."""

    code = "MISSION_RETRYABLE"
    http_status = 503


class PermanentMissionError(MissionError):
    """Bad input or state — must be fixed by user (401, 403, 404, bad config)."""

    code = "MISSION_PERMANENT"
    http_status = 400


# ── API-layer exceptions ──────────────────────────────────────────────────────


class MissionNotFoundError(MissionError, NotFoundAppError):
    """Mission not found — maps to HTTP 404."""

    code = "MISSION_NOT_FOUND"  # explicit: MRO would pick MissionError.code without this
    http_status = 404


class MissionTransitionConflictError(MissionError, ConflictAppError):
    """Invalid status transition — maps to HTTP 409."""

    code = "MISSION_TRANSITION_CONFLICT"  # explicit: MissionError.code = MISSION_ERROR
    http_status = 409


class MissionForbiddenError(MissionError, ForbiddenAppError):
    """User does not own or have access to mission — maps to HTTP 403."""

    code = "MISSION_FORBIDDEN"  # explicit: MissionError.code = MISSION_ERROR
    http_status = 403


class MissionValidationError(MissionError, ValidationAppError):
    """Bad request / validation failure — maps to HTTP 422."""

    code = "MISSION_VALIDATION_ERROR"  # explicit: MissionError.code = MISSION_ERROR
    http_status = 422


class GraphNotFoundError(MissionError, NotFoundAppError):
    """Graph workflow not found or access denied — maps to HTTP 404."""

    code = "GRAPH_NOT_FOUND"  # explicit: MissionError.code = MISSION_ERROR
    http_status = 404
