"""Cursor-based (keyset) pagination for API v2.

Every v2 list endpoint that accepts cursor pagination returns:
    { "data": { "items": [...], "next_cursor": "..." | null, "prev_cursor": "..." | null },
      "meta": { ... }, "error": null }

The cursor is a base64-encoded JSON object: {"id": "<last_item_id>", "ts": "<iso_ts>"}
Consumers pass `cursor=<token>&direction=after|before&limit=N`.

Keyset pagination is more efficient than offset for large tables because
it leverages indexed (id, created_at) ordering without scanning skipped rows.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastapi import Query
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from collections.abc import Callable

# ── Cursor encoding / decoding ────────────────────────────────────────────────


def encode_cursor(item_id: str, created_at: datetime | str | None = None) -> str:
    """Encode a cursor token from an item's ID and timestamp."""
    ts = None
    if created_at is not None:
        ts = created_at.isoformat() if isinstance(created_at, datetime) else str(created_at)
    payload = {"id": str(item_id), "ts": ts}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()


def decode_cursor(cursor: str) -> dict[str, Any]:
    """Decode a cursor token back to {"id": ..., "ts": ...}.

    Raises ValueError on malformed cursors.
    """
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except Exception as exc:
        raise ValueError(f"Invalid cursor token: {exc}") from exc
    if not isinstance(payload, dict) or "id" not in payload:
        raise ValueError("Cursor missing required 'id' field")
    return payload


# ── Pydantic models ───────────────────────────────────────────────────────────


class CursorPageData(BaseModel):
    """Paginated data with cursor navigation."""

    items: list[Any] = Field(default_factory=list)
    next_cursor: str | None = None
    prev_cursor: str | None = None


class CursorPaginatedEnvelope(BaseModel):
    """Standard v2 cursor-paginated response envelope."""

    data: CursorPageData = Field(default_factory=CursorPageData)
    meta: dict[str, Any] = Field(default_factory=dict)
    error: Any = None


# ── Dependency ────────────────────────────────────────────────────────────────


@dataclass
class CursorParams:
    """Resolved cursor pagination parameters."""

    cursor: str | None
    direction: str  # "after" or "before"
    limit: int

    @property
    def decoded(self) -> dict[str, Any] | None:
        if self.cursor is None:
            return None
        return decode_cursor(self.cursor)


def cursor_pagination(
    default_limit: int = 20,
    max_limit: int = 100,
):
    """FastAPI dependency factory for cursor-based pagination.

    Usage in endpoint:
        @router.get("/items")
        async def list_items(cp: CursorParams = Depends(cursor_pagination())):
            ...
    """

    def _dependency(
        cursor: str | None = Query(None, description="Opaque cursor token from a previous response"),
        direction: str = Query(
            "after",
            description="Pagination direction: 'after' (next page) or 'before' (previous page)",
        ),
        limit: int = Query(
            default_limit,
            ge=1,
            le=max_limit,
            description=f"Items per page (1-{max_limit})",
        ),
    ) -> CursorParams:
        if direction not in ("after", "before"):
            direction = "after"
        return CursorParams(cursor=cursor, direction=direction, limit=limit)

    return _dependency


# ── Envelope builder ──────────────────────────────────────────────────────────


def cursor_paginated(
    items: list[Any],
    *,
    limit: int,
    cursor_params: CursorParams,
    item_id_fn: Callable[[Any], Any],
    item_ts_fn: Callable[[Any], Any] | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a cursor-paginated response envelope.

    Args:
        items: The items returned from the query (already limited).
        limit: The requested page size.
        cursor_params: The original pagination parameters.
        item_id_fn: Callable that extracts the ID from an item (dict or model).
        item_ts_fn: Optional callable that extracts the created_at from an item.
        extra_meta: Additional metadata to include.

    Returns:
        Dict matching the v2 cursor-paginated envelope.
    """
    has_more = len(items) > limit
    if has_more:
        items = items[:limit]

    next_cursor = None
    prev_cursor = None

    if items:
        if cursor_params.direction == "after":
            if has_more:
                # More items ahead → next_cursor points to last item
                next_cursor = encode_cursor(
                    item_id_fn(items[-1]),
                    item_ts_fn(items[-1]) if item_ts_fn else None,
                )
            if cursor_params.cursor:
                # We navigated forward → prev_cursor points to first item (to go back)
                prev_cursor = encode_cursor(
                    item_id_fn(items[0]),
                    item_ts_fn(items[0]) if item_ts_fn else None,
                )
        elif cursor_params.direction == "before":
            if has_more:
                # More items further back → prev_cursor points to oldest item (last in DESC)
                prev_cursor = encode_cursor(
                    item_id_fn(items[-1]),
                    item_ts_fn(items[-1]) if item_ts_fn else None,
                )
            # After reversal, next_cursor points to the item AFTER the original cursor
            next_cursor = (
                encode_cursor(
                    item_id_fn(items[0]),
                    item_ts_fn(items[0]) if item_ts_fn else None,
                )
                if cursor_params.cursor
                else None
            )
            # Reverse items so they appear in ascending order
            items = list(reversed(items))

    from app.api.v2.base import ResponseMeta

    meta = ResponseMeta().model_dump()
    if extra_meta:
        meta.update(extra_meta)

    return {
        "data": {
            "items": items,
            "next_cursor": next_cursor,
            "prev_cursor": prev_cursor,
        },
        "meta": meta,
        "error": None,
    }
