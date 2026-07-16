"""Tests for the strategy metadata endpoint (P1-2).

The primary ``strategies`` list advertises ONLY working strategies.
Deprecated strategies (0% success with the 27B model per the
2026-07-04 profiling run) are reported separately under ``deprecated`` so
the UI never offers them as selectable, while they remain discoverable
(and executable behind STRATEGY_ALLOW_DEPRECATED).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.v1.strategies import router as strategies_router


@pytest.fixture
def client():
    """Minimal FastAPI test client with only the strategies router."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(strategies_router, prefix="/api")
    return TestClient(app)


class TestStrategiesEndpoint:
    """Verify GET /api/strategies returns correct metadata."""

    def test_returns_required_keys(self, client: TestClient):
        resp = client.get("/api/strategies")
        assert resp.status_code == 200
        data = resp.json()
        assert "strategies" in data
        assert "deprecated" in data
        assert "total" in data
        assert "available" in data

    def test_primary_list_only_working_strategies(self, client: TestClient):
        resp = client.get("/api/strategies")
        data = resp.json()
        types = {s["type"] for s in data["strategies"]}
        assert types == {"solo", "dag", "graph"}
        # No deprecated strategy leaks into the primary list.
        assert all(not s["deprecated"] for s in data["strategies"])

    def test_deprecated_strategies_in_separate_section(self, client: TestClient):
        resp = client.get("/api/strategies")
        data = resp.json()
        deprecated_types = {s["type"] for s in data["deprecated"]}
        assert deprecated_types == {"swarm", "pipeline", "meta", "langgraph"}
        assert all(s["deprecated"] for s in data["deprecated"])

    def test_counts(self, client: TestClient):
        resp = client.get("/api/strategies")
        data = resp.json()
        # 7 registered total (3 working + 4 deprecated).
        assert data["total"] == 7
        assert data["available"] == 3
        assert len(data["strategies"]) == 3
        assert len(data["deprecated"]) == 4

    def test_each_strategy_has_required_fields(self, client: TestClient):
        resp = client.get("/api/strategies")
        data = resp.json()
        for section in ("strategies", "deprecated"):
            for s in data[section]:
                assert "type" in s
                assert "deprecated" in s
                assert "experimental" in s
                assert "description" in s
                assert isinstance(s["type"], str)
                assert isinstance(s["deprecated"], bool)
                assert isinstance(s["experimental"], bool)
