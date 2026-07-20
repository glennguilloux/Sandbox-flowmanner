"""Regression guard: ``GET /api/inbox/stream`` must not be shadowed by ``/{item_id}``.

Root cause (2026-07-20): both ``@router.get("/stream")`` (``inbox_stream``) and
``@router.get("/{item_id}")`` (``get_inbox_item``) live on the same ``hitl_router``
(``prefix="/inbox"``). Starlette matches routes in **declaration order** and returns
the first FULL match. When the parameterized ``/{item_id}`` route was declared BEFORE
the static ``/stream`` route, ``GET /api/inbox/stream`` matched ``get_inbox_item`` with
``item_id="stream"`` -> ``service.get_item("stream")`` -> ``None`` -> 404
``INBOX_ITEM_NOT_FOUND``. The frontend ``useInboxSSE`` retry loop then spammed 404/401
every 5s.

The fix is a pure declaration-order reorder: ``/stream`` is now declared before
``/{item_id}``. This guard locks that in two ways:

1. The registered ``/api/inbox/stream`` route resolves to ``inbox_stream`` (not
   ``get_inbox_item``) — catches the route being removed or renamed.
2. On the app's flattened route table, the ``/api/inbox/stream`` entry appears BEFORE
   the ``/api/inbox/{item_id}`` entry — catches a future re-introduction of the
   shadow via reordering.

Verification (run from backend/):
    PYTHONPATH=. python -m pytest app/tests/test_inbox_stream_routing.py -q
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# Canonical app entry point (matches app/tests/conftest.py import).
from app.main_fastapi import app as real_app

if TYPE_CHECKING:
    from fastapi import FastAPI

_STREAM_PATH = "/api/inbox/stream"
_ITEM_PATH = "/api/inbox/{item_id}"


def _route_index(application: FastAPI, path: str) -> int:
    """Return the index of the first route whose path equals ``path``, or -1."""
    for i, route in enumerate(application.routes):
        if getattr(route, "path", None) == path:
            return i
    return -1


def test_inbox_stream_route_resolves_to_inbox_stream() -> None:
    """The /api/inbox/stream route must dispatch to inbox_stream, not get_inbox_item."""
    for route in real_app.routes:
        if getattr(route, "path", None) == _STREAM_PATH:
            endpoint = getattr(route, "endpoint", None)
            assert endpoint is not None, f"{_STREAM_PATH} has no endpoint"
            assert endpoint.__name__ == "inbox_stream", (
                f"{_STREAM_PATH} resolves to {endpoint.__name__!r}, expected "
                "'inbox_stream' — the static /stream route is being shadowed by "
                "the parameterized /{item_id} route (declaration-order collision)."
            )
            return
    raise AssertionError(f"{_STREAM_PATH} route is not registered")


def test_inbox_stream_declared_before_item_id() -> None:
    """Static /stream must be declared before parameterized /{item_id}.

    Starlette matches in declaration order; if /{item_id} comes first it swallows
    GET /stream as item_id='stream'. Both routes must exist and /stream must win.
    """
    stream_idx = _route_index(real_app, _STREAM_PATH)
    item_idx = _route_index(real_app, _ITEM_PATH)

    assert stream_idx != -1, f"{_STREAM_PATH} route is not registered"
    assert item_idx != -1, f"{_ITEM_PATH} route is not registered"
    assert stream_idx < item_idx, (
        f"{_STREAM_PATH} (index {stream_idx}) is declared AFTER {_ITEM_PATH} "
        f"(index {item_idx}); the parameterized route will shadow the static SSE "
        "route. Declare @router.get('/stream') before @router.get('/{item_id}')."
    )
