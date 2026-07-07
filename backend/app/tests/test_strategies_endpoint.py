"""Tests for the strategy metadata endpoint (P1-2)."""

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

    def test_returns_all_strategies(self, client: TestClient):
        resp = client.get("/api/strategies")
        assert resp.status_code == 200
        data = resp.json()
        assert "strategies" in data
        assert "total" in data
        assert "available" in data
        assert data["total"] == 7  # solo, dag, graph, swarm, pipeline, meta, langgraph

    def test_deprecated_strategies_flagged(self, client: TestClient):
        resp = client.get("/api/strategies")
        data = resp.json()
        deprecated = [s for s in data["strategies"] if s["deprecated"]]
        deprecated_types = {s["type"] for s in deprecated}
        assert deprecated_types == {"swarm", "pipeline", "meta", "langgraph"}

    def test_production_strategies_not_deprecated(self, client: TestClient):
        resp = client.get("/api/strategies")
        data = resp.json()
        available = [s for s in data["strategies"] if not s["deprecated"]]
        available_types = {s["type"] for s in available}
        assert available_types == {"solo", "dag", "graph"}

    def test_available_count(self, client: TestClient):
        resp = client.get("/api/strategies")
        data = resp.json()
        assert data["available"] == 3

    def test_each_strategy_has_required_fields(self, client: TestClient):
        resp = client.get("/api/strategies")
        data = resp.json()
        for s in data["strategies"]:
            assert "type" in s
            assert "deprecated" in s
            assert "experimental" in s
            assert "description" in s
            assert isinstance(s["type"], str)
            assert isinstance(s["deprecated"], bool)
            assert isinstance(s["experimental"], bool)
