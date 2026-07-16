"""
v1 graph execution is retired (hard 410).

The v1 graph execution engine was removed as dead code (commit 1f4df6ec,
"Comment 12"). The ``/api/graphs/{id}/execute`` and
``/api/graphs/{id}/resume/{eid}`` endpoints therefore refuse with a hard
``410 GONE`` and point callers at the v2 blueprints/runs source of truth
(see ``app/api/v1/graph.py``).

This module previously integration-tested the end-to-end execution engine
(create linear workflow -> execute -> poll -> assert per-node outputs).
Since the engine no longer exists, those tests can only ever hit the 410,
which is exactly the regression the field hit when the engine was pulled.
They are preserved here as **contract tests** that drive the *real* app
through ``TestClient`` — so the ``APIVersioningMiddleware`` + the router's
deprecation dependency + FastAPI's exception handler all execute — and
assert the v1 graph execute/resume endpoints refuse with 410 and direct
callers to ``/api/v2/blueprints`` / ``/api/v2/runs``.

Complement, don't duplicate: ``app/tests/test_v1_graph_retired.py`` already
exercises the route functions directly (bypassing middleware/auth). This
file asserts the same contract as a real client sees it through the full
middleware stack — which is the surface that actually broke.

No database required: the 410 is raised before any graph I/O, so these
tests run green on a host shell without PostgreSQL (the old integration
tests needed a live DB and were auto-skipped otherwise).

Run:
    pytest tests/test_integration_graph_execution.py -v
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.main_fastapi import app

# ── Auth override (no DB needed) ───────────────────────────────────────────
# The 410 is raised inside the endpoint before any graph lookup, so the only
# dependency we must satisfy is ``get_current_user``. A lightweight fake user
# lets the endpoint reach its 410 without touching PostgreSQL.


class _FakeUser:
    id = 1
    is_active = True
    is_admin = False
    role = "free"


@pytest.fixture
def retired_client():
    """TestClient over the real app with auth mocked; no DB required."""

    async def _fake_user():
        return _FakeUser()

    app.dependency_overrides[get_current_user] = _fake_user
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_current_user, None)


# ── Shared assertions ──────────────────────────────────────────────────────


def _assert_retired(resp):
    """The v1 graph execute/resume contract: hard 410 + v2 successor pointer."""
    assert resp.status_code == 410, f"expected 410, got {resp.status_code}: {resp.text}"
    detail = (resp.json().get("detail") or "").lower()
    assert "retired" in detail, f"410 detail should mention retirement, got: {resp.text}"
    # The detail points callers at the v2 blueprints/runs replacement.
    assert (
        "/api/v2/blueprints" in resp.text or "/api/v2/runs" in resp.text
    ), f"410 detail should point at v2 successor, got: {resp.text}"


# ── Tests (one per retired execution scenario, mapped 1:1 from the old suite) ─


class TestGraphExecutionRetired:
    """v1 graph execute/resume are gone — every call must return 410."""

    def test_execute_full_workflow_is_410(self, retired_client):
        """Old: test_create_and_execute_full_workflow — full linear execution."""
        wid = uuid.uuid4()
        resp = retired_client.post(
            f"/api/graphs/{wid}/execute",
            json={"input_data": {"message": "test"}},
        )
        _assert_retired(resp)

    def test_resume_execution_is_410(self, retired_client):
        """Old: test_execution_detail_has_node_states — implied resume/detail path."""
        wid = uuid.uuid4()
        eid = uuid.uuid4()
        resp = retired_client.post(f"/api/graphs/{wid}/resume/{eid}", json={})
        _assert_retired(resp)

    def test_execute_subgraph_from_task_is_410(self, retired_client):
        """Old: test_subgraph_from_task_skips_start — start_node_id=transform-1."""
        wid = uuid.uuid4()
        resp = retired_client.post(
            f"/api/graphs/{wid}/execute",
            json={"input_data": {"start_node_id": "transform-1"}},
        )
        _assert_retired(resp)

    def test_execute_subgraph_from_log_is_410(self, retired_client):
        """Old: test_subgraph_from_log_only_log_and_end_execute — start_node_id=log-1."""
        wid = uuid.uuid4()
        resp = retired_client.post(
            f"/api/graphs/{wid}/execute",
            json={"input_data": {"start_node_id": "log-1"}},
        )
        _assert_retired(resp)

    def test_execute_subgraph_from_end_is_410(self, retired_client):
        """Old: test_subgraph_from_end_executes_only_end — start_node_id=end-1."""
        wid = uuid.uuid4()
        resp = retired_client.post(
            f"/api/graphs/{wid}/execute",
            json={"input_data": {"start_node_id": "end-1"}},
        )
        _assert_retired(resp)

    def test_execute_nonexistent_workflow_is_410(self, retired_client):
        """Old: test_execute_nonexistent_workflow — unknown workflow id."""
        wid = uuid.uuid4()
        resp = retired_client.post(
            f"/api/graphs/{wid}/execute",
            json={"input_data": {}},
        )
        _assert_retired(resp)

    def test_execute_with_unknown_start_node_is_410(self, retired_client):
        """Old: test_subgraph_nonexistent_node — start_node_id not in the graph."""
        wid = uuid.uuid4()
        resp = retired_client.post(
            f"/api/graphs/{wid}/execute",
            json={"input_data": {"start_node_id": "nonexistent-node"}},
        )
        _assert_retired(resp)

    def test_execute_empty_workflow_is_410(self, retired_client):
        """Old: test_create_workflow_without_nodes — executing an empty graph."""
        wid = uuid.uuid4()
        resp = retired_client.post(
            f"/api/graphs/{wid}/execute",
            json={"input_data": {}},
        )
        _assert_retired(resp)
