"""API v3 base response helpers — standardized envelope, trace_id, error formatting.

Every v3 response follows the same envelope pattern as v2:
    Success:  { "data": <payload>, "meta": { "request_id": "...", "timestamp": "..." }, "error": null }
    Paginated: { "data": { "items": [...], "total": N, "page": N, "per_page": N, "pages": N }, "meta": {...}, "error": null }
    Error:    { "data": null, "error": { "code": "...", "message": "...", "details": {...}, "trace_id": "..." }, "meta": {...} }

v3 additions over v2:
- trace_id in error responses for correlation with logs
- RateLimit-* headers via paginated() meta extras
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class ResponseMeta(BaseModel):
    """Metadata included in every v3 response."""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ErrorDetail(BaseModel):
    """Structured error information with trace_id for log correlation."""

    code: str
    message: str
    details: dict[str, Any] | None = None
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class PaginatedData(BaseModel):
    """Pagination wrapper for list endpoints."""

    items: list[Any] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 20
    pages: int = 0


def ok(data: Any, request_id: str | None = None, **extra_meta: Any) -> dict[str, Any]:
    """Build a success envelope."""
    meta = ResponseMeta()
    if request_id:
        meta.request_id = request_id
    meta_dict = meta.model_dump()
    if extra_meta:
        meta_dict.update(extra_meta)
    return {"data": data, "meta": meta_dict, "error": None}


def paginated(
    items: list[Any],
    total: int,
    page: int,
    per_page: int,
    request_id: str | None = None,
    **extra_meta: Any,
) -> dict[str, Any]:
    """Build a paginated success envelope."""
    pages = (total + per_page - 1) // per_page if per_page > 0 else 0
    data = PaginatedData(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )
    meta = ResponseMeta()
    if request_id:
        meta.request_id = request_id
    meta_dict = meta.model_dump()
    if extra_meta:
        meta_dict.update(extra_meta)
    return {"data": data.model_dump(), "meta": meta_dict, "error": None}


def err(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    status_code: int = 400,
    request_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Build an error envelope with trace_id for log correlation."""
    error = ErrorDetail(code=code, message=message, details=details)
    if trace_id:
        error.trace_id = trace_id
    meta = ResponseMeta()
    if request_id:
        meta.request_id = request_id
    return {"data": None, "meta": meta.model_dump(), "error": error.model_dump()}
