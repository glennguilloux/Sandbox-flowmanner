"""Regression tests for chunk 4 routing fix (orchestrator 2026-06-12).

The sub-agent's chunk 4 placed the GET /missions/{id}/depth-events endpoint
on a router that had prefix="/depth", which made the actual mount
/api/depth/missions/{mission_id}/depth-events — NOT the documented
/api/missions/{mission_id}/depth-events path.  This test file pins the
correct mount so the bug cannot regress.

These tests only check the FastAPI route table — they do not hit any
endpoints, do not open DB sessions, and do not require the app to be
fully started.  They fail fast if either path is wrong.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def fastapi_app():
    """Import the FastAPI app.  Module-scoped so we only do it once.

    Named `fastapi_app` (not `app`) to avoid pytest-flask's auto-fixture
    handling which monkeypatches `response_class` — an attribute that
    doesn't exist on FastAPI.
    """
    from app.main_fastapi import app as _app  # noqa: PLC0415

    return _app


def _route_paths(app) -> set[str]:
    """Return the set of HTTP route paths registered on the app."""
    return {
        r.path
        for r in app.routes
        if getattr(r, "methods", None) and "depth" in r.path
    }


class TestDepthRouteMount:
    """The depth endpoints must mount at the documented paths."""

    def test_post_decide_at_depth_prefix(self, fastapi_app):
        paths = _route_paths(fastapi_app)
        assert "/api/depth/decide" in paths, (
            f"POST /api/depth/decide is missing. Actual depth paths: {sorted(paths)}"
        )

    def test_get_events_under_missions_not_depth(self, fastapi_app):
        """The events endpoint must be at /api/missions/..., NOT /api/depth/missions/...

        This is the regression test for the chunk 4 routing bug.
        """
        paths = _route_paths(fastapi_app)
        assert "/api/missions/{mission_id}/depth-events" in paths, (
            f"GET /api/missions/{{mission_id}}/depth-events is missing. "
            f"Actual depth paths: {sorted(paths)}"
        )

    def test_no_buggy_path_under_depth_prefix(self, fastapi_app):
        """The buggy /api/depth/missions/.../depth-events path must NOT exist."""
        paths = _route_paths(fastapi_app)
        assert "/api/depth/missions/{mission_id}/depth-events" not in paths, (
            f"BUG REGRESSION: /api/depth/missions/{{mission_id}}/depth-events is "
            f"registered but should not be. Actual depth paths: {sorted(paths)}"
        )
