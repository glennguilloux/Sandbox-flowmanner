"""Guard: no top-level ``/api/swarm`` backend feature routes exist.

Phase 1 (DELETE path) decision — Glenn, 2026-07-19: swarm is NOT on the
near-term roadmap, so no backend route build for a ``/api/swarm`` feature
surface. This test LOCKS IN that absence: if a future developer mounts a
swarm *feature* router at ``/api/swarm`` (or ``/api/swarm/<resource>``),
this test must fail and force an intentional decision instead of a silent
reuse of the dead ``/api/swarm`` name.

What is explicitly permitted (and must keep passing):
- ``app.api.v1.swarm_protocol`` is mounted with internal ``prefix="/protocol"``
  and an ``include_router`` override of ``prefix="/swarm"``, so its real paths
  are ``/api/swarm/protocol/...`` — a legacy *protocol* endpoint, not a swarm
  *feature* namespace. It is flagged in ``app/api/v1/AGENTS.md`` as a
  migration candidate, but is NOT the ``/api/swarm`` feature surface this guard
  protects against.

What this guard catches:
- Any new route whose path starts with ``/api/swarm/`` and is NOT under the
  legacy ``/api/swarm/protocol/`` subtree (e.g. ``/api/swarm/tasks``,
  ``/api/swarm/agents``, ``/api/swarm/runs``).

Verification (run from backend/):
    PYTHONPATH=. python -m pytest app/tests/test_no_swarm_routes.py -q
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

# Canonical app entry point (matches app/tests/conftest.py import).
from app.main_fastapi import app as real_app

# Legacy swarm-protocol subtree that is allowed to keep the ``swarm`` segment.
# Everything else under ``/api/swarm/...`` is treated as a forbidden feature
# namespace.
_ALLOWED_SWARM_PREFIX = "/api/swarm/protocol"


def _route_paths(application: FastAPI) -> list[str]:
    """Return every registered route path on the app (flattened)."""
    paths: list[str] = []
    for route in application.routes:
        path = getattr(route, "path", None)
        if path:
            paths.append(path)
    return paths


def _forbidden_swarm_routes(application: FastAPI) -> list[str]:
    """Return swarm-feature routes that violate the DELETE-path guard.

    A route is forbidden when its path contains ``swarm`` (case-insensitive)
    but it is NOT the allowed legacy ``/api/swarm/protocol`` subtree.
    """
    forbidden: list[str] = []
    for path in _route_paths(application):
        if "swarm" not in path.lower():
            continue
        if path == _ALLOWED_SWARM_PREFIX or path.startswith(_ALLOWED_SWARM_PREFIX + "/"):
            continue
        forbidden.append(path)
    return forbidden


def test_no_top_level_swarm_feature_routes() -> None:
    """No /api/swarm/<feature> route may exist (DELETE-path guard).

    The legacy /api/swarm/protocol subtree is the only permitted use of the
    ``swarm`` path segment.
    """
    forbidden = _forbidden_swarm_routes(real_app)
    assert forbidden == [], (
        "Found backend route(s) under the /api/swarm feature namespace, which "
        "violates the Phase 1 DELETE-path decision (no /api/swarm route build). "
        f"Offending routes: {forbidden}. If a swarm feature is intentionally "
        "being added, remove this guard deliberately and record the decision."
    )


def test_legacy_swarm_protocol_still_present_but_scoped() -> None:
    """Sanity check: the legacy protocol endpoint remains at /api/swarm/protocol.

    This proves the guard is not trivially passing because swarm_protocol was
    removed — it is specifically scoped to the protocol subtree.
    """
    paths = _route_paths(real_app)
    protocol_routes = [p for p in paths if p.startswith(_ALLOWED_SWARM_PREFIX)]
    assert protocol_routes, (
        "Expected legacy swarm_protocol routes under "
        f"{_ALLOWED_SWARM_PREFIX!r}, but none found. The guard's allowed-prefix "
        "assumption is stale — update the test."
    )
    # And confirm none of them leak into a forbidden feature namespace.
    assert _forbidden_swarm_routes(real_app) == []


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
