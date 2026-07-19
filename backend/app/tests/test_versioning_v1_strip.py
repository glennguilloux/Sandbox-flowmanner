"""Tests for the Phase-1 ``/v1`` strip in ``APIVersioningMiddleware``.

Before the fix, ``/api/v1/<router>`` reached the v1 router literally
(no ``/v1`` segment is registered) and 404'd for every plain-mounted
router. After the fix, the middleware rewrites ``/api/v1/<x>`` ->
``/api/<x>`` in ``request.scope["path"]`` *before* routing, so that
BOTH ``/api/v1/<x>`` and ``/api/<x>`` resolve to the same router.

These tests prove:
  * ``/api/v1/workspaces`` reaches ``/api/workspaces`` (200/401, not 404)
  * ``/api/v2/...`` and ``/api/v3/...`` are UNTOUCHED
  * ``/api/v2/graphql`` is UNTOUCHED
  * ``/docs`` / ``/openapi.json`` / ``/health`` are UNTOUCHED
"""

from __future__ import annotations

import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import TestClient as StarletteTestClient

from app.api.deps import get_current_user, get_db
from app.main_fastapi import app

pytestmark = pytest.mark.integration


@pytest.fixture
def unauth_client():
    """Client with DB stubbed but NO auth — so the route is reached
    (the middleware rewrite is what we are testing, not auth)."""

    async def _override_get_db():
        yield None  # type: ignore[return-value]

    # Provide a permissive current-user so we get PAST the auth dependency
    # and can distinguish "route matched (200/2xx)" from "404 no route".
    async def _override_get_current_user():
        user = type("U", (), {"id": "1", "is_superuser": True})()
        return user

    saved = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    # raise_server_exceptions=False: if a route is reached but its handler
    # crashes on the stubbed (None) DB session, we get a 500 response rather
    # than a propagated exception. 500 != 404 proves the path RESOLVED (the
    # middleware rewrite worked); only 404 means the rewrite failed.
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()
    app.dependency_overrides.update(saved)


class TestV1StripMiddleware:
    def test_v1_prefixed_plain_router_resolves_to_unprefixed_mount(self, unauth_client):
        """/api/v1/workspaces must NOT 404; it must reach /api/workspaces."""
        r = unauth_client.get("/api/v1/workspaces")
        # 401/403/200/405/422 = the route matched (path resolved).
        # 404 = the path matched NO mounted route (the bug we fixed).
        assert r.status_code != 404, (
            f"/api/v1/workspaces returned 404 -- middleware did not strip /v1; " f"body={r.text[:200]}"
        )

    def test_unprefixed_variant_still_resolves(self, unauth_client):
        r = unauth_client.get("/api/workspaces")
        assert r.status_code != 404

    def test_v2_untouched(self, unauth_client):
        """A real /api/v2 route must be reached unchanged."""
        r = unauth_client.get("/api/v2/blueprints")
        assert r.status_code != 404

    def test_v3_untouched(self, unauth_client):
        r = unauth_client.get("/api/v3/health")
        assert r.status_code != 404

    def test_v2_graphql_untouched(self, unauth_client):
        """The legacy /api/v2/graphql endpoint must NOT be rewritten."""
        r = unauth_client.post(
            "/api/v2/graphql",
            json={"query": "{ __typename }"},
        )
        # It should reach the graphql handler, not be rewritten to /api/graphql
        # (which does not exist). 404 means the rewrite wrongly fired.
        assert r.status_code != 404, "/api/v2/graphql was rewritten to /api/graphql (404) -- v2 must be untouched"

    def test_docs_untouched(self, unauth_client):
        r = unauth_client.get("/docs")
        assert r.status_code == 200

    def test_openapi_untouched(self, unauth_client):
        r = unauth_client.get("/openapi.json")
        assert r.status_code == 200

    def test_health_untouched(self, unauth_client):
        r = unauth_client.get("/api/health")
        assert r.status_code == 200

    def test_v1_usage_rewrites_to_usage_mount(self, unauth_client):
        """usage.py prefix was /v1/usage -> now /usage. /api/v1/usage/summary
        must reach /api/usage/summary (200/401, not 404)."""
        r = unauth_client.get("/api/v1/usage/summary")
        assert r.status_code != 404, "/api/v1/usage/summary 404 -- usage prefix normalization broken"

    def test_v1_rag_rewrites_to_rag_mount(self, unauth_client):
        r = unauth_client.get("/api/v1/rag/books")
        assert r.status_code != 404, "/api/v1/rag/books 404 -- rag prefix normalization broken"
