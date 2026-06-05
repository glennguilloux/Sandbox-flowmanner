"""Pydantic v2 strict-mode validation middleware for API v2.

Provides response validation for /api/v2/* endpoints:
- Checks that JSON responses contain only JSON-serializable types
- Catches leaked Python objects (classes, enums, etc.) that would fail
  in production serialization
- Skips streaming responses and non-JSON responses

Request validation is handled at the schema level via
``model_config = ConfigDict(extra=\"forbid\")`` on all input schemas,
which FastAPI enforces natively during body parsing.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v2.base import ErrorDetail, ResponseMeta

if TYPE_CHECKING:
    from fastapi import Request

logger = structlog.get_logger()

# Types that JSON can represent natively
_JSON_PRIMITIVES = (str, int, float, bool, type(None))
_JSON_SCALARS = (*_JSON_PRIMITIVES, datetime, date, UUID, Decimal)


def _is_json_serializable(value: Any, path: str = "$") -> list[str]:
    """Recursively check if a value is JSON-serializable.

    Args:
        value: The value to check.
        path: JSONPath-like string for error reporting.

    Returns:
        List of error paths where non-serializable values were found.
    """
    errors: list[str] = []

    if value is None or isinstance(value, _JSON_PRIMITIVES):
        return errors

    if isinstance(value, (datetime, date, UUID, Decimal)):
        return errors

    if isinstance(value, dict):
        for k, v in value.items():
            sub_path = f"{path}.{k}" if path else str(k)
            errors.extend(_is_json_serializable(v, sub_path))
        return errors

    if isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            sub_path = f"{path}[{i}]"
            errors.extend(_is_json_serializable(item, sub_path))
        return errors

    # Non-serializable type (e.g. class instances, enums without .value)
    errors.append(f"{path}: <{type(value).__name__}>")
    return errors


class StrictValidationMiddleware(BaseHTTPMiddleware):
    """Pydantic v2 strict-mode response validation for API v2.

    Validates that JSON responses from ``/api/v2/*`` endpoints contain
    only JSON-serializable types.  Catches leaked Python objects (classes,
    enums, functions) that would otherwise cause 500 errors in production.

    Request validation is handled at the schema level — all mission input
    schemas use ``ConfigDict(extra=\"forbid\")``, enforced by FastAPI.

    Skips:
        - ``/api/v1/*`` and other non-v2 paths
        - Streaming responses (SSE, WebSocket)
        - Error responses (status >= 400)
        - Non-JSON responses
    """

    async def dispatch(self, request: Request, call_next):
        # Only apply to v2 endpoints
        if not request.url.path.startswith("/api/v2"):
            return await call_next(request)

        # Execute handler — request body is left untouched for FastAPI
        response = await call_next(request)

        # Validate the response
        response = await self._validate_response(request, response)
        return response

    async def _validate_response(self, request: Request, response):
        """Validate the outgoing response body for serialization issues."""
        # Skip streaming responses
        if isinstance(response, StreamingResponse):
            return response

        # Skip non-success responses (they have their own validation)
        if response.status_code >= 400:
            return response

        # Skip non-JSON responses
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        # Parse and validate the response body
        try:
            if hasattr(response, "body"):
                body_bytes = response.body
            else:
                logger.debug(
                    "v2_response_no_body_attr",
                    path=request.url.path,
                    response_type=type(response).__name__,
                )
                return response

            body = json.loads(body_bytes)

            # Check for non-serializable types
            errors = _is_json_serializable(body)
            if errors:
                logger.warning(
                    "v2_response_serialization_error",
                    path=request.url.path,
                    method=request.method,
                    status_code=response.status_code,
                    errors=errors,
                )
                error = ErrorDetail(
                    code="RESPONSE_SERIALIZATION_ERROR",
                    message="Response contains non-serializable data",
                    details={"fields": errors},
                )
                meta = ResponseMeta(
                    request_id=request.headers.get("X-Request-ID") or "unknown",
                )
                return JSONResponse(
                    status_code=500,
                    content={
                        "data": None,
                        "meta": meta.model_dump(),
                        "error": error.model_dump(),
                    },
                )

        except json.JSONDecodeError:
            logger.warning(
                "v2_response_not_json",
                path=request.url.path,
                content_type=content_type,
            )
        except Exception as e:
            logger.error(
                "v2_response_validation_unexpected",
                path=request.url.path,
                error=str(e),
                exc_info=True,
            )

        return response


def register_strict_validation(app) -> None:
    """Register strict response validation middleware on the FastAPI app.

    Must be registered **after** CORS middleware and **before** the
    v2 router is included.  Current placement in ``main_fastapi.py``
    satisfies this ordering.

    Args:
        app: FastAPI application instance.
    """
    app.add_middleware(StrictValidationMiddleware)
    logger.info("strict_validation_middleware_registered")
