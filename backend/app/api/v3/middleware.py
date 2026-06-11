"""V3 middleware and exception handlers.

Catches HTTPException and unhandled errors for v3 routes, converts them to the
v3 error envelope with trace_id. Only active for routes under /api/v3/.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.v3.base import ErrorDetail, ResponseMeta

logger = structlog.get_logger()


def _make_error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict | None = None,
    request_id: str | None = None,
    trace_id: str | None = None,
) -> JSONResponse:
    error = ErrorDetail(code=code, message=message, details=details)
    if trace_id:
        error.trace_id = trace_id
    meta = ResponseMeta()
    if request_id:
        meta.request_id = request_id
    body = {"data": None, "meta": meta.model_dump(), "error": error.model_dump()}
    return JSONResponse(status_code=status_code, content=body)


def register_v3_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers that produce v3 error envelopes.

    Only active for routes under /api/v3/.
    """

    @app.exception_handler(HTTPException)
    async def v3_http_exception_handler(request: Request, exc: HTTPException):
        if not request.url.path.startswith("/api/v3"):
            # Let the v2 handler or default handler deal with it
            from fastapi.responses import JSONResponse as PlainJSON

            return PlainJSON(
                status_code=exc.status_code,
                content={"detail": exc.detail},
            )

        code = _status_to_code(exc.status_code)
        trace_id = getattr(request.state, "trace_id", None)
        return _make_error_response(
            status_code=exc.status_code,
            code=code,
            message=str(exc.detail),
            request_id=request.headers.get("X-Request-ID"),
            trace_id=trace_id,
        )

    @app.exception_handler(Exception)
    async def v3_general_exception_handler(request: Request, exc: Exception):
        if not request.url.path.startswith("/api/v3"):
            from fastapi.responses import JSONResponse as PlainJSON

            return PlainJSON(
                status_code=500,
                content={"detail": "An error occurred. Please try again later."},
            )

        trace_id = getattr(request.state, "trace_id", None)
        logger.error("Unhandled v3 exception", error=str(exc), exc_info=True, trace_id=trace_id)
        return _make_error_response(
            status_code=500,
            code="INTERNAL_ERROR",
            message="An error occurred. Please try again later.",
            request_id=request.headers.get("X-Request-ID"),
            trace_id=trace_id,
        )


_STATUS_CODE_MAP: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    423: "ACCOUNT_LOCKED",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    502: "BAD_GATEWAY",
}


def _status_to_code(status_code: int) -> str:
    return _STATUS_CODE_MAP.get(status_code, f"HTTP_{status_code}")
