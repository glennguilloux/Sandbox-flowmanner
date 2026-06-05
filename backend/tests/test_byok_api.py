import os

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main_fastapi import app

client = TestClient(app)

VALIDATE_URL = "/api/api-keys/validate"
MODELS_URL = "/api/api-keys/models"


def _mock_httpx_response(status_code: int, body: dict):
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.is_success = status_code < 400
    mock_response.json.return_value = body
    return mock_response


class _FakeAsyncClient:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def get(self, url, **kwargs):
        return self._response


def test_validate_returns_valid_with_models():
    provider_response = {
        "data": [
            {"id": "gpt-4o"},
            {"id": "gpt-4o-mini"},
            {"id": "gpt-3.5-turbo"},
        ]
    }
    mock_resp = _mock_httpx_response(200, provider_response)

    with patch("app.api.v1.api_keys.httpx.AsyncClient", return_value=_FakeAsyncClient(mock_resp)):
        response = client.post(
            VALIDATE_URL,
            json={"provider": "openai", "api_key": "sk-valid-key"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "valid"
    assert data["error"] is None
    model_ids = [m["id"] for m in data["models"]]
    assert "gpt-4o" in model_ids
    assert "gpt-4o-mini" in model_ids


def test_validate_returns_invalid_on_401():
    error_response = {"error": {"message": "Incorrect API key provided"}}
    mock_resp = _mock_httpx_response(401, error_response)

    with patch("app.api.v1.api_keys.httpx.AsyncClient", return_value=_FakeAsyncClient(mock_resp)):
        response = client.post(
            VALIDATE_URL,
            json={"provider": "openai", "api_key": "sk-bad-key"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "invalid"
    assert data["models"] == []
    assert "Incorrect API key" in data["error"]


def test_validate_returns_invalid_on_403():
    mock_resp = _mock_httpx_response(403, {"error": {"message": "Forbidden"}})

    with patch("app.api.v1.api_keys.httpx.AsyncClient", return_value=_FakeAsyncClient(mock_resp)):
        response = client.post(
            VALIDATE_URL,
            json={"provider": "openai-compatible", "api_key": "sk-forbidden"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "invalid"
    assert data["models"] == []


def test_validate_returns_invalid_on_timeout():
    import httpx as _httpx

    class _TimeoutClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, **kwargs):
            raise _httpx.TimeoutException("timed out")

    with patch("app.api.v1.api_keys.httpx.AsyncClient", return_value=_TimeoutClient()):
        response = client.post(
            VALIDATE_URL,
            json={"provider": "openai", "api_key": "sk-slow"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "invalid"
    assert "timed out" in data["error"].lower()


def test_validate_rejects_unsupported_provider():
    response = client.post(
        VALIDATE_URL,
        json={"provider": "anthropic", "api_key": "sk-ant-xxx"},
    )
    assert response.status_code == 400


def test_get_models_openai():
    response = client.get(f"{MODELS_URL}/openai")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    ids = [m["id"] for m in data]
    assert "gpt-4o" in ids
    assert "gpt-4o-mini" in ids
    assert "gpt-3.5-turbo" in ids
    for m in data:
        assert m["provider"] == "openai"


def test_get_models_openai_compatible():
    response = client.get(f"{MODELS_URL}/openai-compatible")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    for m in data:
        assert m["provider"] == "openai-compatible"


def test_get_models_unknown_provider_returns_404():
    response = client.get(f"{MODELS_URL}/unknown-provider")
    assert response.status_code == 404


def test_no_key_storage_in_validate():
    provider_response = {"data": [{"id": "gpt-4o"}]}
    mock_resp = _mock_httpx_response(200, provider_response)

    with patch("app.api.v1.api_keys.httpx.AsyncClient", return_value=_FakeAsyncClient(mock_resp)):
        response = client.post(
            VALIDATE_URL,
            json={"provider": "openai", "api_key": "sk-should-not-be-stored"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "valid"


DISCOVER_URL = "/api/api-keys/discover-models"


def test_discover_models_success():
    import app.api.v1.api_keys as api_keys_module

    api_keys_module._model_cache.clear()

    provider_response = {
        "data": [
            {"id": "gpt-4o"},
            {"id": "gpt-4o-mini"},
            {"id": "text-embedding-ada-002"},
            {"id": "whisper-1"},
            {"id": "dall-e-3"},
            {"id": "tts-1"},
        ]
    }
    mock_resp = _mock_httpx_response(200, provider_response)

    with patch("app.api.v1.api_keys.httpx.AsyncClient", return_value=_FakeAsyncClient(mock_resp)):
        response = client.post(
            DISCOVER_URL,
            json={"provider": "openai", "api_key": "sk-valid-key"},
        )

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    model_ids = [m["id"] for m in data]
    assert "gpt-4o" in model_ids
    assert "gpt-4o-mini" in model_ids
    assert "text-embedding-ada-002" not in model_ids
    assert "whisper-1" not in model_ids
    assert "dall-e-3" not in model_ids
    assert "tts-1" not in model_ids


def test_discover_models_invalid_key():
    import app.api.v1.api_keys as api_keys_module

    api_keys_module._model_cache.clear()

    mock_resp = _mock_httpx_response(401, {"error": {"message": "Invalid API key"}})

    with patch("app.api.v1.api_keys.httpx.AsyncClient", return_value=_FakeAsyncClient(mock_resp)):
        response = client.post(
            DISCOVER_URL,
            json={"provider": "openai", "api_key": "sk-bad-key"},
        )

    assert response.status_code == 401


def test_model_cache():
    import app.api.v1.api_keys as api_keys_module

    api_keys_module._model_cache.clear()

    provider_response = {"data": [{"id": "gpt-4o"}]}
    mock_resp = _mock_httpx_response(200, provider_response)

    call_count = 0

    class _CountingFakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, **kwargs):
            nonlocal call_count
            call_count += 1
            return mock_resp

    with patch("app.api.v1.api_keys.httpx.AsyncClient", return_value=_CountingFakeClient()):
        client.post(DISCOVER_URL, json={"provider": "openai", "api_key": "sk-key-1"})
        client.post(DISCOVER_URL, json={"provider": "openai", "api_key": "sk-key-2"})

    assert call_count == 1, f"Expected 1 HTTP call (cache hit on 2nd), got {call_count}"
