"""V2 standardized response models.

Every v2 response follows one of these shapes:
    Success:  { "data": <payload>, "meta": { "request_id": "...", "timestamp": "..." }, "error": null }
    Paginated: { "data": { "items": [...], "total": N, "page": N, "per_page": N, "pages": N }, "meta": {...}, "error": null }
    Error:    { "data": null, "error": { "code": "...", "message": "...", "details": {...} }, "meta": {...} }
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ResponseMeta(BaseModel):
    """Metadata included in every v2 response."""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ErrorDetail(BaseModel):
    """Structured error information."""

    code: str
    message: str
    details: dict[str, Any] | None = None


class ResponseEnvelope(BaseModel):
    """Standard v2 response envelope."""

    data: Any = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)
    error: ErrorDetail | None = None


class PaginatedData(BaseModel):
    """Pagination wrapper for list endpoints."""

    items: list[Any] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 20
    pages: int = 0


class PaginatedEnvelope(BaseModel):
    """Standard v2 paginated response envelope."""

    data: PaginatedData = Field(default_factory=PaginatedData)
    meta: ResponseMeta = Field(default_factory=ResponseMeta)
    error: ErrorDetail | None = None


def ok(data: Any, request_id: str | None = None, **extra_meta: Any) -> dict[str, Any]:
    """Build a success envelope."""
    meta = ResponseMeta()
    if request_id:
        meta.request_id = request_id
    if extra_meta:
        meta_dict = meta.model_dump()
        meta_dict.update(extra_meta)
        return {"data": data, "meta": meta_dict, "error": None}
    return {"data": data, "meta": meta.model_dump(), "error": None}


def paginated(
    items: list[Any],
    total: int,
    page: int,
    per_page: int,
    request_id: str | None = None,
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
    return {"data": data.model_dump(), "meta": meta.model_dump(), "error": None}


def err(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    status_code: int = 400,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Build an error envelope."""
    error = ErrorDetail(code=code, message=message, details=details)
    meta = ResponseMeta()
    if request_id:
        meta.request_id = request_id
    return {"data": None, "meta": meta.model_dump(), "error": error.model_dump()}
