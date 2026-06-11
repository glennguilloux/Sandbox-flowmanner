"""V2 middleware and exception handlers.

Catches HTTPException and unhandled errors, converts them to the v2 error envelope.
Streaming responses are left untouched.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.v2.base import ErrorDetail, ResponseMeta

logger = structlog.get_logger()


# HTTP status code to v2 error code mapping
_MISSION_ERROR_STATUS_MAP = {
    "MissionNotFoundError": (404, "MISSION_NOT_FOUND"),
    "MissionForbiddenError": (403, "MISSION_FORBIDDEN"),
    "MissionTransitionConflictError": (409, "MISSION_TRANSITION_CONFLICT"),
    "MissionValidationError": (400, "MISSION_VALIDATION_ERROR"),
}


def _is_streaming_response(response) -> bool:
    return isinstance(response, StreamingResponse)


def _make_error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    error = ErrorDetail(code=code, message=message, details=details)
    meta = ResponseMeta()
    if request_id:
        meta.request_id = request_id
    body = {"data": None, "meta": meta.model_dump(), "error": error.model_dump()}
    return JSONResponse(status_code=status_code, content=body)


def register_v2_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers that produce v2 error envelopes.

    Only active for routes under /api/v2/.
    """

    # ── Mission-specific exception handlers ───────────────────────────────
    try:
        from app.services.mission_errors import (
            MissionForbiddenError,
            MissionNotFoundError,
            MissionTransitionConflictError,
            MissionValidationError,
        )

        @app.exception_handler(MissionNotFoundError)
        async def mission_not_found_handler(request: Request, exc: MissionNotFoundError):
            if not request.url.path.startswith("/api/v2"):
                return JSONResponse(status_code=404, content={"detail": str(exc) or "Mission not found"})
            return _make_error_response(
                status_code=404,
                code="MISSION_NOT_FOUND",
                message=str(exc) or "Mission not found",
                request_id=request.headers.get("X-Request-ID"),
            )

        @app.exception_handler(MissionForbiddenError)
        async def mission_forbidden_handler(request: Request, exc: MissionForbiddenError):
            if not request.url.path.startswith("/api/v2"):
                return JSONResponse(status_code=403, content={"detail": str(exc) or "Access denied"})
            return _make_error_response(
                status_code=403,
                code="MISSION_FORBIDDEN",
                message=str(exc) or "Access denied",
                request_id=request.headers.get("X-Request-ID"),
            )

        @app.exception_handler(MissionTransitionConflictError)
        async def mission_conflict_handler(request: Request, exc: MissionTransitionConflictError):
            if not request.url.path.startswith("/api/v2"):
                return JSONResponse(
                    status_code=409,
                    content={"detail": str(exc) or "Invalid status transition"},
                )
            return _make_error_response(
                status_code=409,
                code="MISSION_TRANSITION_CONFLICT",
                message=str(exc) or "Invalid status transition",
                request_id=request.headers.get("X-Request-ID"),
            )

        @app.exception_handler(MissionValidationError)
        async def mission_validation_handler(request: Request, exc: MissionValidationError):
            if not request.url.path.startswith("/api/v2"):
                return JSONResponse(status_code=400, content={"detail": str(exc) or "Validation error"})
            return _make_error_response(
                status_code=400,
                code="MISSION_VALIDATION_ERROR",
                message=str(exc) or "Validation error",
                request_id=request.headers.get("X-Request-ID"),
            )

    except ImportError:
        pass

    # ── Generic HTTP exception handler ────────────────────────────────────
    @app.exception_handler(HTTPException)
    async def v2_http_exception_handler(request: Request, exc: HTTPException):
        if not request.url.path.startswith("/api/v2"):
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail},
            )

        code = _status_to_code(exc.status_code)
        return _make_error_response(
            status_code=exc.status_code,
            code=code,
            message=str(exc.detail),
            request_id=request.headers.get("X-Request-ID"),
        )

    @app.exception_handler(Exception)
    async def v2_general_exception_handler(request: Request, exc: Exception):
        if not request.url.path.startswith("/api/v2"):
            return JSONResponse(
                status_code=500,
                content={"detail": "An error occurred. Please try again later."},
            )

        logger.error("Unhandled v2 exception", error=str(exc), exc_info=True)
        return _make_error_response(
            status_code=500,
            code="INTERNAL_ERROR",
            message="An error occurred. Please try again later.",
            request_id=request.headers.get("X-Request-ID"),
        )


_STATUS_CODE_MAP = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    502: "BAD_GATEWAY",
}


def _status_to_code(status_code: int) -> str:
    return _STATUS_CODE_MAP.get(status_code, f"HTTP_{status_code}")
