"""Regression tests for the unified v2/v3 exception-envelope dispatcher.

These pin the three error shapes produced by ``app/api/_shared_errors.py`` so a
future change (e.g. dropping a path guard or re-adding a per-tier handler)
cannot silently clobber another tier's envelope:

- ``GET /api/v2/<unmatched>`` -> v2 envelope ``{data, meta, error}`` (NO trace_id)
- ``GET /api/v3/<unmatched>`` -> v3 envelope WITH ``error.trace_id``
- ``GET /<unmatched>``            -> flat ``{"detail": ...}`` (v1 / unversioned)
"""

import os

os.environ.setdefault("OPENAI_API_KEY", "***")

import pytest
from fastapi.testclient import TestClient

from app.main_fastapi import app

pytestmark = pytest.mark.integration


def _classify(resp):
    try:
        j = resp.json()
    except Exception:
        return "NONJSON", False, None
    if isinstance(j, dict) and "error" in j and "data" in j and "meta" in j:
        err = j.get("error") or {}
        return "ENVELOPE", bool(err.get("trace_id")), err.get("code")
    if isinstance(j, dict) and "detail" in j:
        return "FLAT", False, None
    return "OTHER", False, None


def test_v2_route_404_uses_v2_envelope_without_trace_id():
    with TestClient(app) as client:
        resp = client.get("/api/v2/this/path/does/not/exist/zzz")
    shape, has_trace, code = _classify(resp)
    assert resp.status_code == 404, resp.text
    assert shape == "ENVELOPE", resp.text
    assert has_trace is False, "v2 errors must NOT carry a trace_id"
    assert code == "NOT_FOUND", resp.text


def test_v3_route_unauthenticated_returns_401():
    """R2 fail-closed middleware: an unauthenticated /api/v3/* request must be
    rejected with 401 BEFORE reaching the router (no silent pass-through)."""
    with TestClient(app) as client:
        resp = client.get("/api/v3/this/path/does/not/exist/zzz")
    assert resp.status_code == 401, resp.text
    shape, _, code = _classify(resp)
    assert shape == "ENVELOPE", resp.text
    assert code == "UNAUTHENTICATED", resp.text


def test_v3_route_404_uses_v3_envelope_with_trace_id():
    """With a valid Bearer token, an unmatched /api/v3/* path still resolves to
    the router and returns the v3 404 envelope (WITH trace_id)."""
    import jwt

    from app.config import settings

    token = jwt.encode({"sub": 1, "scopes": []}, settings.JWT_SECRET_KEY, algorithm="HS256")
    with TestClient(app) as client:
        resp = client.get(
            "/api/v3/this/path/does/not/exist/zzz",
            headers={"Authorization": f"Bearer {token}"},
        )
    shape, has_trace, code = _classify(resp)
    assert resp.status_code == 404, resp.text
    assert shape == "ENVELOPE", resp.text
    assert has_trace is True, "v3 errors must carry a trace_id"
    assert code == "NOT_FOUND", resp.text


def test_unversioned_404_is_flat_detail():
    with TestClient(app) as client:
        resp = client.get("/this/is/not/a/versioned/route-zzz")
    shape, has_trace, _ = _classify(resp)
    assert resp.status_code == 404, resp.text
    assert shape == "FLAT", resp.text
    assert has_trace is False


def test_only_one_handler_registered_per_exception_class():
    from starlette.exceptions import HTTPException as StarletteHTTPException

    # There must be exactly one HTTPException handler and one Exception handler
    # in the whole app (the unified dispatcher) — no leftover per-tier dupes.
    http_keys = [k for k in app.exception_handlers if k is StarletteHTTPException]
    assert len(http_keys) == 1, app.exception_handlers.keys()

    exc_handlers = [v for k, v in app.exception_handlers.items() if k is Exception]
    assert len(exc_handlers) == 1, app.exception_handlers.keys()

    # Sanity: the bound HTTPException handler is the unified one
    # (registered by register_unified_exception_handlers in main_fastapi).
    bound = app.exception_handlers.get(StarletteHTTPException)
    assert bound is not None
    assert "unified_http_exception_handler" in bound.__qualname__
