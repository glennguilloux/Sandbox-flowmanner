"""Tests for DELETE /api/v2/chat/messages/{id}.

Comment 2: a user message referenced by a chat branch must return HTTP 409
rather than a silent delete (the FK is ondelete="SET NULL", so the
IntegrityError path never fires — the handler does an explicit pre-delete
branch query).
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from app.api.deps import get_current_user, get_db
from app.main_fastapi import app

pytestmark = pytest.mark.integration


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


def _owned_user_message(message_id: int = 7, thread_id: int = 42):
    return SimpleNamespace(
        id=message_id,
        thread_id=thread_id,
        user_id=1,
        role="user",
        content="hello",
    )


def _owned_thread(thread_id: int = 42, user_id: int = 1):
    return SimpleNamespace(id=thread_id, user_id=user_id, username="testuser")


class TestDeleteMessageBranchConflict:
    def test_returns_409_when_branch_references_message(self, auth_client, mock_db_session):
        """Deleting a user message that a branch points at must 409."""
        msg_result = MagicMock()
        msg_result.scalar_one_or_none.return_value = _owned_user_message()

        branch_result = MagicMock()
        # A branch exists referencing this message → non-None → 409.
        branch_result.scalar_one_or_none.return_value = 99

        def _execute_side_effect(statement, *args, **kwargs):
            # The branch-conflict query targets chat_branches; everything else
            # (the message lookup, and delete_chat_message's own lookup) is a
            # ChatMessage query.
            if "chat_branches" in str(statement).lower():
                return branch_result
            return msg_result

        mock_db_session.execute.side_effect = _execute_side_effect

        with patch(
            "app.api.v2.chat.get_chat_thread",
            new=AsyncMock(return_value=_owned_thread()),
        ):
            response = auth_client.delete("/api/v2/chat/messages/7")

        assert response.status_code == 409
        # delete_chat_message must NOT be reached on the conflict path.
        mock_db_session.delete.assert_not_called()

    def test_returns_204_when_no_branch_references_message(self, auth_client, mock_db_session):
        """Deleting a user message with no referencing branch succeeds (204)."""
        msg_result = MagicMock()
        msg_result.scalar_one_or_none.return_value = _owned_user_message()

        branch_result = MagicMock()
        # No branch references this message → None → allow delete.
        branch_result.scalar_one_or_none.return_value = None

        def _execute_side_effect(statement, *args, **kwargs):
            if "chat_branches" in str(statement).lower():
                return branch_result
            return msg_result

        mock_db_session.execute.side_effect = _execute_side_effect
        mock_db_session.delete = AsyncMock()

        with patch(
            "app.api.v2.chat.get_chat_thread",
            new=AsyncMock(return_value=_owned_thread()),
        ):
            response = auth_client.delete("/api/v2/chat/messages/7")

        assert response.status_code == 204
        mock_db_session.delete.assert_called_once()

    def test_returns_404_when_message_missing(self, auth_client, mock_db_session):
        msg_result = MagicMock()
        msg_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = msg_result

        response = auth_client.delete("/api/v2/chat/messages/999")
        assert response.status_code == 404
