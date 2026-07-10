"""Tests for the /api/hermes-studio router.

Run from backend root:
    PYTHONPATH=. python -m pytest app/tests/test_hermes_studio_router.py -q
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import TestClient as StarletteClient

from app.api.deps import get_current_user
from app.api.v1.hermes_studio import router as hermes_studio_router
from app.main_fastapi import app

LIVE_DB = Path.home() / ".hermes" / "state.db"


@pytest.fixture
def client(monkeypatch):
    # Bypass auth for the router-under-test with a sync override.
    class _FakeUser:
        id = 1
        is_active = True

    def _fake_user():
        return _FakeUser()

    app.dependency_overrides[get_current_user] = _fake_user
    # Point the reader at the live DB if present, else skip.
    if LIVE_DB.exists():
        monkeypatch.setenv("HERMES_STUDIO_STATE_DB", str(LIVE_DB))
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_router_registered():
    paths = [r.path for r in app.routes]
    assert any(p.startswith("/api/hermes-studio/sessions") for p in paths)
    assert "/api/hermes-studio/checkpoint" in paths
    assert "/api/hermes-studio/workspace-diff" in paths


def test_list_sessions(client):
    if not LIVE_DB.exists():
        pytest.skip("no live state.db")
    resp = client.get("/api/hermes-studio/sessions?limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert "sessions" in body
    assert len(body["sessions"]) > 0


def test_get_session_and_chain(client):
    if not LIVE_DB.exists():
        pytest.skip("no live state.db")
    listing = client.get("/api/hermes-studio/sessions?limit=3").json()
    sid = listing["sessions"][0]["id"]
    resp = client.get(f"/api/hermes-studio/sessions/{sid}")
    assert resp.status_code == 200
    assert "session" in resp.json()
    chain = client.get(f"/api/hermes-studio/sessions/{sid}/chain")
    assert chain.status_code == 200
    assert chain.json()["root_id"] == sid


def test_checkpoint_returns_prompt(client):
    payload = {
        "messages": [
            {"role": "user", "content": "word " * 40000},
            {"role": "assistant", "content": "word " * 40000},
            {"role": "user", "content": "final question?"},
        ],
        "trigger_tokens": 10_000,
        "tail_message_count": 1,
    }
    resp = client.post("/api/hermes-studio/checkpoint", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["under_threshold"] is False
    assert "prompt" in body
    assert "summary_prefix" in body
    # tail (final question) preserved
    assert any(m["content"] == "final question?" for m in body["tail_messages"])


def test_workspace_diff_endpoint(client):
    with tempfile.TemporaryDirectory() as d:
        before = Path(d) / "before"
        after = Path(d) / "after"
        before.mkdir()
        after.mkdir()
        (before / "a.txt").write_text("one")
        (after / "a.txt").write_text("one-changed")
        (after / "c.txt").write_text("new")
        payload = {
            "before_root": str(before),
            "after_root": str(after),
            "workspace": str(after),
        }
        resp = client.post("/api/hermes-studio/workspace-diff", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["kind"] in ("git", "filesystem")
        paths = {c["path"] for c in body["changes"]}
        assert "c.txt" in paths  # added
        assert "a.txt" in paths  # modified


def test_unauthorized_without_override():
    # Fresh client with no auth override -> 401 (auth enforced in production).
    with StarletteClient(app) as c:
        resp = c.get("/api/hermes-studio/sessions")
    assert resp.status_code in (401, 403)
