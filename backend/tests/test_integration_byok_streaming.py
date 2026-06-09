import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from app.api.deps import get_current_user, get_db
from app.main_fastapi import app

pytestmark = pytest.mark.integration


def _make_thread(user_id: int = 1):
    return SimpleNamespace(
        id=42,
        user_id=user_id,
        username="testuser",
        title="BYOK Thread",
        is_archived=False,
        metadata_=None,
    )


async def _fake_stream_with_usage(*tokens):
    for token in tokens:
        yield json.dumps({"type": "token", "content": token})
    yield json.dumps(
        {
            "type": "complete",
            "full_response": "".join(tokens),
            "message_id": 99,
            "model": "gpt-4o",
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
        }
    )


def _parse_sse_events(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            data_str = line[len("data:") :].strip()
            if data_str and data_str != "[DONE]":
                events.append(json.loads(data_str))
    return events


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


@pytest.fixture
def sample_user():
    return SimpleNamespace(
        id=1,
        email="user@example.com",
        username="testuser",
        full_name="Test User",
        hashed_password="hashed",
        avatar_url=None,
        is_active=True,
        is_admin=False,
        is_superuser=False,
        bio=None,
        api_key="sk-test-key-123",
        role="user",
    )


@pytest.fixture
def auth_client(sample_user):
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    mock_db.close = AsyncMock()

    async def override_get_db():
        yield mock_db

    async def override_get_current_user():
        return sample_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


class TestBYOKValidateFlow:
    def test_validate_openai_key_returns_valid_with_models(self, auth_client):
        provider_response = {
            "data": [
                {"id": "gpt-4o"},
                {"id": "gpt-4o-mini"},
            ]
        }
        mock_resp = _mock_httpx_response(200, provider_response)

        with patch(
            "app.api.v1.api_keys.httpx.AsyncClient",
            return_value=_FakeAsyncClient(mock_resp),
        ):
            response = auth_client.post(
                "/api/api-keys/validate",
                json={"provider": "openai", "api_key": "sk-byok-valid-key"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "valid"
        assert data["error"] is None
        model_ids = [m["id"] for m in data["models"]]
        assert "gpt-4o" in model_ids

    def test_validate_bad_key_returns_invalid(self, auth_client):
        mock_resp = _mock_httpx_response(401, {"error": {"message": "Invalid API key"}})

        with patch(
            "app.api.v1.api_keys.httpx.AsyncClient",
            return_value=_FakeAsyncClient(mock_resp),
        ):
            response = auth_client.post(
                "/api/api-keys/validate",
                json={"provider": "openai", "api_key": "sk-bad-key"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "invalid"
        assert data["models"] == []


class TestBYOKStreamingHeaderAccepted:
    def test_byok_header_accepted_returns_200(self, auth_client):
        thread = _make_thread(user_id=1)
        with (
            patch(
                "app.api.v1.chat.get_chat_thread", new=AsyncMock(return_value=thread)
            ),
            patch(
                "app.api.v1.chat.stream_message_to_llm",
                return_value=_fake_stream_with_usage("Hello", " world"),
            ),
        ):
            response = auth_client.post(
                "/api/chat/threads/42/chat/stream",
                json={"role": "user", "content": "Hi"},
                headers={"X-User-API-Key": "sk-byok-test-key"},
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    def test_byok_header_stream_returns_token_events(self, auth_client):
        thread = _make_thread(user_id=1)
        with (
            patch(
                "app.api.v1.chat.get_chat_thread", new=AsyncMock(return_value=thread)
            ),
            patch(
                "app.api.v1.chat.stream_message_to_llm",
                return_value=_fake_stream_with_usage("Hello", " world"),
            ),
        ):
            response = auth_client.post(
                "/api/chat/threads/42/chat/stream",
                json={"role": "user", "content": "Hi"},
                headers={"X-User-API-Key": "sk-byok-test-key"},
            )

        events = _parse_sse_events(response.text)
        token_events = [e for e in events if e.get("type") == "token"]
        assert len(token_events) == 2
        assert token_events[0]["content"] == "Hello"
        assert token_events[1]["content"] == " world"

    def test_no_byok_header_also_works(self, auth_client):
        thread = _make_thread(user_id=1)
        with (
            patch(
                "app.api.v1.chat.get_chat_thread", new=AsyncMock(return_value=thread)
            ),
            patch(
                "app.api.v1.chat.stream_message_to_llm",
                return_value=_fake_stream_with_usage("ok"),
            ),
        ):
            response = auth_client.post(
                "/api/chat/threads/42/chat/stream",
                json={"role": "user", "content": "Hi"},
            )

        assert response.status_code == 200


class TestStreamingCompleteEvent:
    def test_complete_event_present_with_usage(self, auth_client):
        thread = _make_thread(user_id=1)
        with (
            patch(
                "app.api.v1.chat.get_chat_thread", new=AsyncMock(return_value=thread)
            ),
            patch(
                "app.api.v1.chat.stream_message_to_llm",
                return_value=_fake_stream_with_usage("Test"),
            ),
        ):
            response = auth_client.post(
                "/api/chat/threads/42/chat/stream",
                json={"role": "user", "content": "ping"},
            )

        events = _parse_sse_events(response.text)
        complete_events = [e for e in events if e.get("type") == "complete"]
        assert len(complete_events) == 1
        complete = complete_events[0]
        assert "usage" in complete
        assert isinstance(complete["usage"], dict)

    def test_sse_format_has_data_prefix_and_double_newline(self, auth_client):
        thread = _make_thread(user_id=1)
        with (
            patch(
                "app.api.v1.chat.get_chat_thread", new=AsyncMock(return_value=thread)
            ),
            patch(
                "app.api.v1.chat.stream_message_to_llm",
                return_value=_fake_stream_with_usage("x"),
            ),
        ):
            response = auth_client.post(
                "/api/chat/threads/42/chat/stream",
                json={"role": "user", "content": "test"},
            )

        assert "data: " in response.text
        assert "\n\n" in response.text
