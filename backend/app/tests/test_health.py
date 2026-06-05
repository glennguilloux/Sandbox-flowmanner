import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main_fastapi import app

os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-123")

pytestmark = pytest.mark.integration


@pytest.fixture
def test_client():
    with TestClient(app) as client:
        yield client


def test_health_endpoint_returns_healthy(test_client):
    """Test /health endpoint returns 200 with healthy status."""
    with patch("app.database.engine") as mock_engine:
        mock_conn = AsyncMock()
        mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.execute.return_value = None
        with patch("redis.asyncio.Redis") as mock_redis_class:
            mock_redis = AsyncMock()
            mock_redis.ping.return_value = True
            mock_redis.aclose = AsyncMock()
            mock_redis_class.from_url.return_value = mock_redis
            with patch("qdrant_client.AsyncQdrantClient") as mock_qdrant_class:
                mock_qdrant = AsyncMock()
                mock_qdrant.get_collections.return_value = None
                mock_qdrant.close = AsyncMock()
                mock_qdrant_class.return_value = mock_qdrant
                with patch("app.api.v1.health.settings") as mock_settings:
                    mock_settings.LLM_API_KEY = "sk-test"
                    mock_settings.APP_NAME = "test-app"
                    mock_settings.APP_ENV = "test"
                    mock_settings.REDIS_URL = "redis://localhost"
                    mock_settings.QDRANT_URL = "http://localhost:6333"
                    mock_settings.LANGFUSE_ENABLED = False
                    mock_settings.LLM_MODEL_NAME = "test-model"
                    mock_settings.LLM_API_BASE = "http://localhost:8000"

                    response = test_client.get("/health")
                    assert response.status_code == 200
                    data = response.json()
                    assert data["status"] == "ok"
                    assert "components" in data


def test_ready_endpoint(test_client):
    """Test /ready endpoint returns 200 with ok status."""
    with patch("app.database.engine") as mock_engine:
        mock_conn = AsyncMock()
        mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.execute.return_value = None
        with patch("redis.asyncio.Redis") as mock_redis_class:
            mock_redis = AsyncMock()
            mock_redis.ping.return_value = True
            mock_redis.aclose = AsyncMock()
            mock_redis_class.from_url.return_value = mock_redis
            with patch("qdrant_client.AsyncQdrantClient") as mock_qdrant_class:
                mock_qdrant = AsyncMock()
                mock_qdrant.get_collections.return_value = None
                mock_qdrant.close = AsyncMock()
                mock_qdrant_class.return_value = mock_qdrant
                with patch("app.api.v1.health.settings") as mock_settings:
                    mock_settings.REDIS_URL = "redis://localhost"
                    mock_settings.QDRANT_URL = "http://localhost:6333"

                    response = test_client.get("/ready")
                    assert response.status_code == 200
                    data = response.json()
                    assert data["status"] == "ok"


def test_health_full_endpoint(test_client):
    """Test /health/full endpoint returns 200."""
    with patch("app.database.engine") as mock_engine:
        mock_conn = AsyncMock()
        mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.execute.return_value = None
        with patch("redis.asyncio.Redis") as mock_redis_class:
            mock_redis = AsyncMock()
            mock_redis.ping.return_value = True
            mock_redis.aclose = AsyncMock()
            mock_redis_class.from_url.return_value = mock_redis
            with patch("qdrant_client.AsyncQdrantClient") as mock_qdrant_class:
                mock_qdrant = AsyncMock()
                mock_qdrant.get_collections.return_value = None
                mock_qdrant.close = AsyncMock()
                mock_qdrant_class.return_value = mock_qdrant
                with patch("app.api.v1.health.settings") as mock_settings:
                    mock_settings.LLM_API_KEY = "sk-test"
                    mock_settings.APP_NAME = "test-app"
                    mock_settings.APP_ENV = "test"
                    mock_settings.REDIS_URL = "redis://localhost"
                    mock_settings.QDRANT_URL = "http://localhost:6333"

                    response = test_client.get("/health/full")
                    assert response.status_code == 200
