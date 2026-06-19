import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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
        title="Test Thread",
        is_archived=False,
        metadata_=None,
        workspace_id=None,
    )


async def _fake_stream(*tokens):
    for token in tokens:
        yield json.dumps({"type": "token", "content": token})
    yield json.dumps(
        {
            "type": "complete",
            "full_response": "".join(tokens),
            "message_id": 99,
            "model": "glm-4-plus",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
    )


@pytest.fixture
def auth_client(mock_db_session, sample_user):
    async def override_get_db():
        yield mock_db_session

    async def override_get_current_user():
        return sample_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


def _parse_sse_events(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            data_str = line[len("data:") :].strip()
            if data_str and data_str != "[DONE]":
                events.append(json.loads(data_str))
    return events


class TestSSEStreamEndpointExists:
    def test_stream_endpoint_returns_200_and_text_event_stream(self, auth_client):
        thread = _make_thread(user_id=1)
        with (
            patch(
                "app.services.chat_service.get_chat_thread",
                new=AsyncMock(return_value=thread),
            ),
            patch(
                "app.api.v1.chat.stream_message_to_llm",
                return_value=_fake_stream("Hello", " world"),
            ),
        ):
            response = auth_client.post(
                "/api/chat/threads/42/chat/stream",
                json={"role": "user", "content": "Hi"},
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]


class TestSSEEventFormat:
    def test_token_events_have_correct_format(self, auth_client):
        thread = _make_thread(user_id=1)
        with (
            patch(
                "app.services.chat_service.get_chat_thread",
                new=AsyncMock(return_value=thread),
            ),
            patch(
                "app.api.v1.chat.stream_message_to_llm",
                return_value=_fake_stream("Hello", " world"),
            ),
        ):
            response = auth_client.post(
                "/api/chat/threads/42/chat/stream",
                json={"role": "user", "content": "Hi"},
            )

        events = _parse_sse_events(response.text)
        token_events = [e for e in events if e.get("type") == "token"]
        assert len(token_events) == 2
        assert token_events[0]["content"] == "Hello"
        assert token_events[1]["content"] == " world"

    def test_complete_event_has_usage_dict(self, auth_client):
        thread = _make_thread(user_id=1)
        with (
            patch(
                "app.services.chat_service.get_chat_thread",
                new=AsyncMock(return_value=thread),
            ),
            patch(
                "app.api.v1.chat.stream_message_to_llm",
                return_value=_fake_stream("Hi"),
            ),
        ):
            response = auth_client.post(
                "/api/chat/threads/42/chat/stream",
                json={"role": "user", "content": "Hey"},
            )

        events = _parse_sse_events(response.text)
        complete_events = [e for e in events if e.get("type") == "complete"]
        assert len(complete_events) == 1
        complete = complete_events[0]
        assert "usage" in complete
        assert isinstance(complete["usage"], dict)

    def test_sse_lines_have_data_prefix_and_double_newline(self, auth_client):
        thread = _make_thread(user_id=1)
        with (
            patch(
                "app.services.chat_service.get_chat_thread",
                new=AsyncMock(return_value=thread),
            ),
            patch(
                "app.api.v1.chat.stream_message_to_llm",
                return_value=_fake_stream("x"),
            ),
        ):
            response = auth_client.post(
                "/api/chat/threads/42/chat/stream",
                json={"role": "user", "content": "test"},
            )

        assert "data: " in response.text
        assert "\n\n" in response.text


class TestSSEAuthAndOwnership:
    def test_returns_404_for_thread_owned_by_other_user(self, auth_client):
        thread = _make_thread(user_id=999)
        with patch(
            "app.services.chat_service.get_chat_thread",
            new=AsyncMock(return_value=thread),
        ):
            response = auth_client.post(
                "/api/chat/threads/42/chat/stream",
                json={"role": "user", "content": "Hi"},
            )

        assert response.status_code == 404

    def test_byok_header_accepted_without_error(self, auth_client):
        thread = _make_thread(user_id=1)
        with (
            patch(
                "app.services.chat_service.get_chat_thread",
                new=AsyncMock(return_value=thread),
            ),
            patch(
                "app.api.v1.chat.stream_message_to_llm",
                return_value=_fake_stream("ok"),
            ),
        ):
            response = auth_client.post(
                "/api/chat/threads/42/chat/stream",
                json={"role": "user", "content": "Hi"},
                headers={"X-User-API-Key": "sk-byok-test-key"},
            )

        assert response.status_code == 200
