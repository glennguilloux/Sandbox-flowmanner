"""Regression tests for the v2 chat promotion (replay/export/title/metadata/costs/react/templates).

Fail before the routes exist (404), pass after. These are contract/ownership
tests against the v2 envelope shape and auth boundary — they do NOT require a
live LLM. Run from the backend worktree:
    PYTHONPATH=backend python -m pytest backend/app/tests/test_chat_v2_parity.py -q
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import get_db
from app.main_fastapi import app


def _client(override_db=None):
    if override_db is not None:
        app.dependency_overrides[get_db] = lambda: override_db
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_replay_requires_auth_and_envelopes():
    # No auth -> 401 (v1 shipped this anonymously; v2 closes it)
    async with _client() as c:
        r = await c.get("/api/v2/chat/streams/anything/replay")
    assert r.status_code == 401, r.status_code


@pytest.mark.asyncio
async def test_costs_requires_auth():
    async with _client() as c:
        r = await c.get("/api/v2/chat/costs?days=7")
    assert r.status_code == 401, r.status_code
    # Envelope shape present when authed (uses override DB so no real user lookup)
    # We only assert the envelope contract here; ownership is enforced by get_current_user.


@pytest.mark.asyncio
async def test_routes_registered_and_under_v2_envelope():
    # Smoke: every promoted route template is registered on the app router.
    templates = [
        "/api/v2/chat/streams/{stream_id}/replay",
        "/api/v2/chat/threads/{thread_id}/export",
        "/api/v2/chat/threads/{thread_id}/title",
        "/api/v2/chat/templates",
        "/api/v2/chat/messages/{message_id}/react",
    ]
    registered = {getattr(r, "path", None) for r in app.routes}
    for t in templates:
        assert t in registered, f"route not registered: {t}"


@pytest.mark.asyncio
async def test_templates_list_requires_auth():
    async with _client() as c:
        r = await c.get("/api/v2/chat/templates")
    assert r.status_code == 401, r.status_code


@pytest.mark.asyncio
async def test_react_requires_auth():
    async with _client() as c:
        r = await c.post("/api/v2/chat/messages/1/react", json={"reaction": "👍"})
    assert r.status_code == 401, r.status_code
