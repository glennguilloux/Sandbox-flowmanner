"""Regression tests for DELETE /api/chat/threads/{id} idempotency.

A thread that is already gone (already deleted, or deleted elsewhere / a
stale request from a double-click) must return 204, NOT 404. Otherwise the
frontend's catch block treats the repeat delete as a failure and leaves the
row orphaned in the sidebar ("Failed to delete thread").

Access-denied is still intentionally masked as 404 by the owner/access checks.
"""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.main_fastapi import app


def _authed(client: TestClient) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    return client


class _FakeUser:
    id = 33
    username = "guillouxglenn4"
    role = "admin"


def test_v1_delete_existing_thread_returns_204():
    with (
        patch("app.api.v1.chat.get_chat_thread", new=AsyncMock(return_value=_thread())) as g,
        patch("app.api.v1.chat.require_chat_thread_access", new=AsyncMock()) as req,
        patch("app.api.v1.chat.delete_chat_thread", new=AsyncMock(return_value=True)) as del_,
    ):
        client = _authed(TestClient(app))
        resp = client.delete("/api/chat/threads/146")
        assert resp.status_code == 204
        g.assert_awaited_once()
        req.assert_awaited_once()
        del_.assert_awaited_once()


def test_v1_delete_missing_thread_is_idempotent_returns_204():
    with (
        patch("app.api.v1.chat.get_chat_thread", new=AsyncMock(return_value=None)) as g,
        patch("app.api.v1.chat.require_chat_thread_access", new=AsyncMock()) as req,
        patch("app.api.v1.chat.delete_chat_thread", new=AsyncMock(return_value=False)) as del_,
    ):
        client = _authed(TestClient(app))
        resp = client.delete("/api/chat/threads/146")
        assert resp.status_code == 204
        g.assert_awaited_once()
        # Never reached the access check or the delete for an absent thread.
        req.assert_not_awaited()
        del_.assert_not_awaited()


def test_v2_delete_existing_thread_returns_204():
    with (
        patch("app.api.v2.chat.get_chat_thread", new=AsyncMock(return_value=_thread())) as g,
        patch("app.api.v2.chat.delete_chat_thread", new=AsyncMock(return_value=True)) as del_,
    ):
        client = _authed(TestClient(app))
        resp = client.delete("/api/v2/chat/threads/146")
        assert resp.status_code == 204
        g.assert_awaited_once()
        del_.assert_awaited_once()


def test_v2_delete_missing_thread_is_idempotent_returns_204():
    with (
        patch("app.api.v2.chat.get_chat_thread", new=AsyncMock(return_value=None)) as g,
        patch("app.api.v2.chat.delete_chat_thread", new=AsyncMock(return_value=False)) as del_,
    ):
        client = _authed(TestClient(app))
        resp = client.delete("/api/v2/chat/threads/146")
        assert resp.status_code == 204
        g.assert_awaited_once()
        del_.assert_not_awaited()


def _thread():
    class _T:
        id = 146
        user_id = 33
        workspace_id = None

    return _T()
