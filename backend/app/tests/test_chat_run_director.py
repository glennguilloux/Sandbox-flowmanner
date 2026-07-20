"""Phase 2 — Director controls for chat-launched substrate runs.

Tests the owner-bound Pause / Resume / Abort routes added to
``app.api.v2.chat``:

    POST /api/v2/chat/threads/{thread_id}/runs/{run_id}/pause
    POST /api/v2/chat/threads/{thread_id}/runs/{run_id}/resume
    POST /api/v2/chat/threads/{thread_id}/runs/{run_id}/abort

Owner-binding is the core security property: a user who does NOT own the
thread must receive 404 (never 403 — we must not leak that the resource
exists), so a cross-user caller can neither discover nor steer another
user's run.

No real DB / docker / alembic is touched — ``get_db`` is overridden with an
``AsyncMock`` session and the substrate ``UnifiedExecutor`` is mocked so the
control routes straight to a spy.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api.deps import get_current_user
from app.database import get_db
from app.main_fastapi import app

# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_user(user_id: int) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    return user


def _make_thread(owner_id: int, run_id: str | None = "run_abc123") -> MagicMock:
    thread = MagicMock()
    thread.user_id = owner_id
    thread.metadata_ = {"source_run_id": run_id} if run_id else {}
    return thread


@pytest.fixture
def mock_db_session():
    mock = MagicMock()
    mock.execute = AsyncMock()
    mock.execute.return_value = MagicMock()
    return mock


@pytest.fixture
def test_client(mock_db_session):
    saved = dict(app.dependency_overrides)

    async def _override_get_db():
        yield mock_db_session

    app.dependency_overrides[get_db] = _override_get_db
    client = __import__("fastapi.testclient", fromlist=["TestClient"]).TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(saved)


# ── Owner pause works ─────────────────────────────────────────────────────────


def test_owner_can_pause_run(test_client, mock_db_session):
    owner = _make_user(1)
    thread = _make_thread(owner_id=1, run_id="run_abc123")
    executor = MagicMock()
    executor.pause = AsyncMock(return_value=True)

    app.dependency_overrides[get_current_user] = lambda: owner
    with (
        __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.api.v2.chat.get_chat_thread", new=AsyncMock(return_value=thread)
        ) as _gt,
        __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.api.v2.chat.get_unified_executor", new=lambda: executor
        ) as _ge,
    ):
        resp = test_client.post("/api/v2/chat/threads/1/runs/run_abc123/pause")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["run_id"] == "run_abc123"
    assert body["data"]["action"] == "pause"
    assert body["data"]["paused"] is True
    assert body["data"]["thread_bound"] is True
    executor.pause.assert_awaited_once_with("run_abc123", db=mock_db_session)
    _gt.assert_awaited_once()


# ── Owner resume works ────────────────────────────────────────────────────────


def test_owner_can_resume_run(test_client, mock_db_session):
    owner = _make_user(1)
    thread = _make_thread(owner_id=1, run_id="run_abc123")
    executor = MagicMock()
    executor.resume = AsyncMock(return_value=True)

    app.dependency_overrides[get_current_user] = lambda: owner
    with (
        __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.api.v2.chat.get_chat_thread", new=AsyncMock(return_value=thread)
        ),
        __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.api.v2.chat.get_unified_executor", new=lambda: executor
        ),
    ):
        resp = test_client.post("/api/v2/chat/threads/1/runs/run_abc123/resume")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["action"] == "resume"
    assert body["data"]["paused"] is False
    executor.resume.assert_awaited_once_with("run_abc123", db=mock_db_session)


# ── Owner abort routes to substrate ───────────────────────────────────────────


def test_owner_can_abort_run_routes_to_substrate(test_client, mock_db_session):
    owner = _make_user(1)
    thread = _make_thread(owner_id=1, run_id="run_abc123")
    executor = MagicMock()
    executor.abort = AsyncMock(return_value=True)

    app.dependency_overrides[get_current_user] = lambda: owner
    with (
        __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.api.v2.chat.get_chat_thread", new=AsyncMock(return_value=thread)
        ),
        __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.api.v2.chat.get_unified_executor", new=lambda: executor
        ),
    ):
        resp = test_client.post("/api/v2/chat/threads/1/runs/run_abc123/abort")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"]["action"] == "abort"
    assert body["data"]["paused"] is True
    executor.abort.assert_awaited_once_with("run_abc123", reason="user_requested", db=mock_db_session)


# ── Cross-user rejected (404, not 403) ────────────────────────────────────────


def test_cross_user_pause_rejected_404(test_client, mock_db_session):
    owner = _make_user(1)
    thread = _make_thread(owner_id=1, run_id="run_abc123")
    # The caller is a DIFFERENT user (id=99). _require_owner must 404.
    intruder = _make_user(99)
    executor = MagicMock()
    executor.pause = AsyncMock(return_value=True)

    app.dependency_overrides[get_current_user] = lambda: intruder
    with (
        __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.api.v2.chat.get_chat_thread", new=AsyncMock(return_value=thread)
        ),
        __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.api.v2.chat.get_unified_executor", new=lambda: executor
        ),
    ):
        resp = test_client.post("/api/v2/chat/threads/1/runs/run_abc123/pause")

    assert resp.status_code == 404, resp.text
    # The substrate must NEVER be signalled for a non-owner.
    executor.pause.assert_not_awaited()


# ── run_id mismatch rejected (404) ────────────────────────────────────────────


def test_pause_rejected_when_run_id_mismatch(test_client, mock_db_session):
    owner = _make_user(1)
    # Thread is bound to a different run than the one in the path.
    thread = _make_thread(owner_id=1, run_id="run_other999")
    executor = MagicMock()
    executor.pause = AsyncMock(return_value=True)

    app.dependency_overrides[get_current_user] = lambda: owner
    with (
        __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.api.v2.chat.get_chat_thread", new=AsyncMock(return_value=thread)
        ),
        __import__("unittest.mock", fromlist=["patch"]).patch(
            "app.api.v2.chat.get_unified_executor", new=lambda: executor
        ),
    ):
        resp = test_client.post("/api/v2/chat/threads/1/runs/run_abc123/pause")

    assert resp.status_code == 404, resp.text
    executor.pause.assert_not_awaited()


# ── Substrate executor pause/resume/abort unit behaviour ──────────────────────


@pytest.mark.asyncio
async def test_executor_pause_resume_lifecycle():
    """Pause sets the signal + emits PAUSE_REQUESTED; resume clears it."""
    from app.models.substrate_models import SubstrateEventType
    from app.services.substrate.executor import UnifiedExecutor

    executor = UnifiedExecutor()
    captured = {}

    async def _append(db_arg, run_id, events):
        captured["events"] = events

    executor.event_log.append = _append

    # Pause
    signaled = await executor.pause("r1", db=MagicMock())
    assert signaled is True
    assert executor.is_paused("r1") is True
    assert captured["events"][0]["type"] == SubstrateEventType.PAUSE_REQUESTED

    # Resume
    resumed = await executor.resume("r1", db=MagicMock())
    assert resumed is True
    assert executor.is_paused("r1") is False
    assert captured["events"][-1]["type"] == SubstrateEventType.RESUME_REQUESTED

    # Idempotency: pausing again sets, resuming a non-paused run is False
    await executor.pause("r2", db=MagicMock())
    assert await executor.resume("r2", db=MagicMock()) is True
    assert await executor.resume("r2", db=MagicMock()) is False
