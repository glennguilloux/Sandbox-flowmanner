"""Comment 12: v1 graph execute/resume are retired (410), not doomed background runs.

The v1 graph execution engine was removed (commit 1f4df6ec, "dead code"). The
execute/resume endpoints must therefore refuse with a hard 410 and point
callers at the v2 blueprints/runs source of truth, instead of creating a
background execution that can only fail with "graph execution engine retired".

The endpoints are exercised by calling the route functions directly with a
``Response`` (and ``user=None`` to bypass the auth dependency, which otherwise
needs a running Postgres). This validates the HTTP contract (status, headers)
and proves the graph execution service is never invoked.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException, Response

import app.api.v1.graph as graph_module
from app.api.v1.graph import resume_graph, run_graph


def test_run_graph_returns_410(monkeypatch):
    monkeypatch.setattr(graph_module, "require_graph_access", lambda *a, **k: None)
    resp = Response()
    with pytest.raises(HTTPException) as exc:
        # user=None bypasses the get_current_user DB dependency.
        asyncio.get_event_loop().run_until_complete(graph_module.run_graph(None, None, resp, user=None))
    assert exc.value.status_code == 410
    assert "retired" in exc.value.detail.lower()
    # Deprecation headers are still injected by the router dependency contract.
    assert resp.headers.get("Deprecation") == "true"


def test_resume_graph_returns_410(monkeypatch):
    monkeypatch.setattr(graph_module, "require_graph_access", lambda *a, **k: None)
    resp = Response()
    with pytest.raises(HTTPException) as exc:
        asyncio.get_event_loop().run_until_complete(graph_module.resume_graph(None, None, resp, user=None))
    assert exc.value.status_code == 410
    assert "retired" in exc.value.detail.lower()
    assert "/api/v2/blueprints" in resp.headers.get("Link", "")


def test_execute_does_not_create_doomed_execution(monkeypatch):
    """The retired endpoint must not invoke the graph execution service."""
    captured = {"called": False}

    async def _fake_execute(db, workflow_id, user_id, input_data=None):
        captured["called"] = True
        return None

    monkeypatch.setattr(graph_module, "require_graph_access", lambda *a, **k: None)
    import app.services.graph_service as gs_mod

    monkeypatch.setattr(gs_mod, "execute_graph_workflow", _fake_execute)

    resp = Response()
    with pytest.raises(HTTPException) as exc:
        asyncio.get_event_loop().run_until_complete(graph_module.run_graph(None, None, resp, user=None))

    assert exc.value.status_code == 410
    assert captured["called"] is False
