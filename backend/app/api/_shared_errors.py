"""Shared error-envelope serializer for v2/v3 exception handlers.

This centralizes the one serializer that produces the three possible error
shapes a Flowmanner error response can take:

- ``/api/v2/*``  -> v2 envelope  ``{data, meta, error}``  (no trace_id)
- ``/api/v3/*``  -> v3 envelope  ``{data, meta, error}``  (trace_id from request.state)
- everything else   -> flat ``{"detail": ...}``  (v1 / unversioned compat)

Previously the v2 and v3 middleware modules each defined a private
``_make_error_response`` and a pair of path-guarded ``app.exception_handler``
registrations. Because FastAPI keys handlers by exception class (a dict),
the *last* registration per class won, and the two tiers only produced the
right shape because each guarded on ``request.url.path.startswith(...)``.
That made correctness depend on fragile, implicit registration order.

This module collapses that into a single path-aware serializer reused by one
HTTPException handler and one Exception handler (see registration in
``app/main_fastapi.py``).
"""

from __future__ import annotations

import structlog
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

logger = structlog.get_logger()

# Status code -> stable canonical error code (used by both v2 and v3 envelopes).
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


def status_to_code(status_code: int) -> str:
    """Map an HTTP status to a canonical error code (v2 + v3 share this map)."""
    return _STATUS_CODE_MAP.get(status_code, f"HTTP_{status_code}")


def _build_v2_error(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str | None,
) -> JSONResponse:
    from app.api.v2.base import ErrorDetail, ResponseMeta

    error = ErrorDetail(code=code, message=message)
    meta = ResponseMeta()
    if request_id:
        meta.request_id = request_id
    body = {"data": None, "meta": meta.model_dump(), "error": error.model_dump()}
    return JSONResponse(status_code=status_code, content=body)


def _build_v3_error(
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str | None,
    trace_id: str | None,
) -> JSONResponse:
    from app.api.v3.base import ErrorDetail as V3ErrorDetail
    from app.api.v3.base import ResponseMeta as V3ResponseMeta

    error = V3ErrorDetail(code=code, message=message)
    if trace_id:
        error.trace_id = trace_id
    meta = V3ResponseMeta()
    if request_id:
        meta.request_id = request_id
    body = {"data": None, "meta": meta.model_dump(), "error": error.model_dump()}
    return JSONResponse(status_code=status_code, content=body)


def make_error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    request_id: str | None = None,
) -> JSONResponse:
    """Path-aware error envelope builder (single source of truth).

    Preserves the exact response shapes that existed before consolidation:

    - ``/api/v2/*``  -> v2 envelope, no trace_id
    - ``/api/v3/*``  -> v3 envelope, trace_id from ``request.state.trace_id``
      (defaults to ``None``; the v3 ErrorDetail then generates its own random
      trace_id via the pydantic default_factory — preserved behavior)
    - everything else   -> flat ``{"detail": message}`` (v1 / unversioned)
    """
    path = request.url.path

    if path.startswith("/api/v2"):
        return _build_v2_error(
            status_code=status_code,
            code=code,
            message=message,
            request_id=request_id,
        )

    if path.startswith("/api/v3"):
        trace_id = getattr(request.state, "trace_id", None)
        return _build_v3_error(
            status_code=status_code,
            code=code,
            message=message,
            request_id=request_id,
            trace_id=trace_id,
        )

    # v1 / unversioned — flat detail (backward compatible forever).
    return JSONResponse(status_code=status_code, content={"detail": message})


def make_unhandled_response(
    request: Request,
    *,
    message: str = "An error occurred. Please try again later.",
) -> JSONResponse:
    """Build the 500 response for an unhandled ``Exception``.

    Same path-aware shape rules as :func:`make_error_response`, but always
    status 500 with ``INTERNAL_ERROR``. Preserves the prior per-tier log
    lines (``"Unhandled v2 exception"`` / ``"Unhandled v3 exception"``)
    so log-based alerting keeps working.
    """
    path = request.url.path
    request_id = request.headers.get("X-Request-ID")

    if path.startswith("/api/v3"):
        trace_id = getattr(request.state, "trace_id", None)
        logger.error("Unhandled v3 exception", error=message, exc_info=True, trace_id=trace_id)
        return _build_v3_error(
            status_code=500,
            code="INTERNAL_ERROR",
            message=message,
            request_id=request_id,
            trace_id=trace_id,
        )

    if path.startswith("/api/v2"):
        logger.error("Unhandled v2 exception", error=message, exc_info=True)
        return _build_v2_error(
            status_code=500,
            code="INTERNAL_ERROR",
            message=message,
            request_id=request_id,
        )

    logger.error("Unhandled exception", error=message, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": message})


def register_unified_exception_handlers(app) -> None:
    """Register ONE path-aware handler per exception class (v2 + v3 + unversioned).

    Replaces the previous three-tier approach where v2 and v3 each registered
    their own ``HTTPException`` / ``Exception`` handlers and correctness
    depended on dict last-wins + ``startswith`` guards + registration order.

    Now there is exactly one ``HTTPException`` handler and one ``Exception``
    handler. Each delegates to :func:`make_error_response` /
    :func:`make_unhandled_response`, which branch on the request path to pick
    the correct envelope. No duplicate ``app.exception_handler`` calls across
    the v2/v3 middleware modules any more.
    """

    @app.exception_handler(HTTPException)
    async def unified_http_exception_handler(request: Request, exc: HTTPException):
        return make_error_response(
            request,
            status_code=exc.status_code,
            code=status_to_code(exc.status_code),
            message=str(exc.detail),
            request_id=request.headers.get("X-Request-ID"),
        )

    @app.exception_handler(Exception)
    async def unified_exception_handler(request: Request, exc: Exception):
        return make_unhandled_response(request, message="An error occurred. Please try again later.")
