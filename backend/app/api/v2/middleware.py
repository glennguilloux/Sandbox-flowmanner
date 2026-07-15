"""V2 middleware and exception handlers.

The generic ``HTTPException`` / ``Exception`` handlers that used to live here
(now duplicate path-guarded ``app.exception_handler`` registrations) have
been consolidated into a single path-aware dispatcher in
``app/api/_shared_errors.py`` and are registered once in
``app/main_fastapi.py``. That removes the fragile, implicit registration-order
dependency between the v2 and v3 tiers.

This module keeps the **mission-specific** handlers (separate exception
classes, so they are unaffected by the consolidation) and exposes
``register_v2_exception_handlers(app)`` for backward compatibility (delegates
to the shared dispatcher so a v2-only app still gets the v2 envelope).
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.api._shared_errors import register_unified_exception_handlers

logger = structlog.get_logger()

# HTTP status code to mission error-code mapping (mission-specific only).
_MISSION_ERROR_STATUS_MAP = {
    "MissionNotFoundError": (404, "MISSION_NOT_FOUND"),
    "MissionForbiddenError": (403, "MISSION_FORBIDDEN"),
    "MissionTransitionConflictError": (409, "MISSION_TRANSITION_CONFLICT"),
    "MissionValidationError": (400, "MISSION_VALIDATION_ERROR"),
}


def _is_streaming_response(response) -> bool:
    return isinstance(response, StreamingResponse)


def register_v2_exception_handlers(app: FastAPI) -> None:
    """Register v2 error handling (delegates to the unified dispatcher).

    Kept for backward compatibility / v2-only apps. The dispatcher is
    path-aware, so ``/api/v2/*`` paths still produce the v2 envelope.
    """
    register_unified_exception_handlers(app)

    # ── Mission-specific exception handlers ──────────────────────────────
    # These are distinct exception classes (not HTTPException/Exception), so
    # they are keyed separately in FastAPI's handler dict and never collide
    # with the unified dispatcher above.
    try:
        from app.services.mission_errors import (
            MissionForbiddenError,
            MissionNotFoundError,
            MissionTransitionConflictError,
            MissionValidationError,
        )

        @app.exception_handler(MissionNotFoundError)
        async def mission_not_found_handler(request: Request, exc: MissionNotFoundError):
            return _mission_error(
                request, status=404, code="MISSION_NOT_FOUND", message=str(exc) or "Mission not found"
            )

        @app.exception_handler(MissionForbiddenError)
        async def mission_forbidden_handler(request: Request, exc: MissionForbiddenError):
            return _mission_error(request, status=403, code="MISSION_FORBIDDEN", message=str(exc) or "Access denied")

        @app.exception_handler(MissionTransitionConflictError)
        async def mission_conflict_handler(request: Request, exc: MissionTransitionConflictError):
            return _mission_error(
                request, status=409, code="MISSION_TRANSITION_CONFLICT", message=str(exc) or "Invalid status transition"
            )

        @app.exception_handler(MissionValidationError)
        async def mission_validation_handler(request: Request, exc: MissionValidationError):
            return _mission_error(
                request, status=400, code="MISSION_VALIDATION_ERROR", message=str(exc) or "Validation error"
            )

    except ImportError:
        pass


def _mission_error(request: Request, *, status: int, code: str, message: str):
    """Render a mission error as the v2 envelope (overrides the generic dispatcher).

    Mission errors are always v2-shaped (they only originate from v2 routes),
    so we build the v2 envelope directly regardless of path.
    """
    from app.api.v2.base import ErrorDetail, ResponseMeta

    request_id = request.headers.get("X-Request-ID")
    error = ErrorDetail(code=code, message=message)
    meta = ResponseMeta()
    if request_id:
        meta.request_id = request_id
    body = {"data": None, "meta": meta.model_dump(), "error": error.model_dump()}
    return JSONResponse(status_code=status, content=body)
