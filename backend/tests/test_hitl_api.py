"""Tests for HITL Inbox API (Q1-B Chunk 3 hardening).

Covers:
- GET /inbox/ — workspace filtering, interrupt_type validation, pagination
- GET /inbox/{item_id} — cross-workspace 404, missing 404
- POST /inbox/{item_id}/approve — dispatches resume
- POST /inbox/{item_id}/reject — dispatches abort
- POST /inbox/{item_id}/clarify — wrong type returns 400
- POST /inbox/bulk-resolve — happy path, partial skip, too-large
- GET /inbox/by-mission/{mission_id} — user-scoped results
- GET /inbox/counts — workspace-scoped
- SSE wrapper — publish_hitl_inbox_event
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.hitl import router
from app.services.hitl_service import HITLService

# ── Helpers ──────────────────────────────────────────────────────────


def _make_inbox_item(
    status: str = "pending",
    inbox_item_id: str | None = None,
    workspace_id: str | None = None,
    mission_id: str | None = None,
    user_id: int = 1,
    interrupt_type: str = "approval",
    run_id: str | None = None,
    resolved_at: datetime | None = None,
    resolved_by: int | None = None,
) -> MagicMock:
    """Create a mock InboxItem."""
    item = MagicMock()
    item.id = inbox_item_id or str(uuid4())
    item.status = status
    item.workspace_id = workspace_id or "ws-123"
    item.mission_id = mission_id or str(uuid4())
    item.user_id = user_id
    item.interrupt_type = interrupt_type
    item.run_id = run_id if run_id is not None else str(uuid4())
    item.node_id = str(uuid4())
    item.title = "Test approval"
    item.description = "Test"
    item.proposed_action = None
    item.context = None
    item.resolved_at = resolved_at
    item.resolved_by = resolved_by
    item.resolution_payload = None
    item.resolution_note = None
    item.expires_at = None
    item.created_at = datetime.now(UTC)
    item.updated_at = datetime.now(UTC)
    item.task_id = None
    return item




# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def test_app():
    """FastAPI app with hitl router at the correct prefix.

    Router itself has prefix="/inbox", so include at "/api/v1" to get
    /api/v1/inbox/* routes.
    """
    _app = FastAPI()
    _app.include_router(router, prefix="/api/v1")
    return _app


@pytest.fixture
def fake_user():
    return MagicMock(id=1, email="test@example.com", is_active=True)


@pytest.fixture
def fake_workspace_id():
    return "ws-123"


@pytest.fixture
def mock_service():
    return MagicMock()


@pytest.fixture
async def client(test_app, fake_user, fake_workspace_id, mock_service):
    """AsyncClient with all dependencies overridden and HITLService mocked."""

    async def _fake_user():
        return fake_user

    async def _fake_workspace():
        return fake_workspace_id

    async def _fake_db():
        return AsyncMock()

    from app.api.deps import get_current_user, get_workspace_id
    from app.database import get_db

    test_app.dependency_overrides[get_current_user] = _fake_user
    test_app.dependency_overrides[get_workspace_id] = _fake_workspace
    test_app.dependency_overrides[get_db] = _fake_db

    # Wire up _item_to_dict so endpoints that call HITLService._item_to_dict
    # get a real dict instead of a MagicMock (which can't be JSON-serialized).
    mock_hitl_class = MagicMock(return_value=mock_service)
    mock_hitl_class._item_to_dict = staticmethod(HITLService._item_to_dict)

    with patch("app.api.v1.hitl.HITLService", mock_hitl_class):
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c

    test_app.dependency_overrides.clear()




# ── Test 1: list_inbox filters by workspace ─────────────────────────


@pytest.mark.anyio
async def test_list_inbox_filters_by_workspace(client, mock_service, fake_workspace_id):
    """workspace_id query param is enforced on list_inbox."""
    item = _make_inbox_item(workspace_id=fake_workspace_id)
    mock_service.list_pending = AsyncMock(
        return_value={"items": [HITLService._item_to_dict(item)], "total": 1}
    )

    resp = await client.get("/api/v1/inbox/")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    mock_service.list_pending.assert_called_once()
    call = mock_service.list_pending.call_args
    assert call.kwargs["workspace_id"] == fake_workspace_id


# ── Test 2: list_inbox invalid interrupt_type returns 422 ───────────


@pytest.mark.anyio
async def test_list_inbox_invalid_interrupt_type_returns_422(client, mock_service):
    """Invalid interrupt_type returns 422 with VALIDATION_ERROR code."""
    resp = await client.get("/api/v1/inbox/?interrupt_type=invalid_type")

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "VALIDATION_ERROR"
    assert "invalid_type" in detail["error"]
    mock_service.list_pending.assert_not_called()


# ── Test 3: list_inbox returns paginated results ────────────────────


@pytest.mark.anyio
async def test_list_inbox_returns_paginated(client, mock_service):
    """limit/offset are passed through to list_pending."""
    mock_service.list_pending = AsyncMock(return_value={"items": [], "total": 0})

    resp = await client.get("/api/v1/inbox/?limit=10&offset=5")

    assert resp.status_code == 200
    call = mock_service.list_pending.call_args
    assert call.kwargs["limit"] == 10
    assert call.kwargs["offset"] == 5


# ── Test 4: get_inbox_item cross-workspace returns 404 ──────────────


@pytest.mark.anyio
async def test_get_inbox_item_cross_workspace_returns_404(client, mock_service):
    """Item in different workspace returns 404 (not 403) — no existence leak."""
    item = _make_inbox_item(workspace_id="ws-other", user_id=1)
    mock_service.get_item = AsyncMock(return_value=item)

    resp = await client.get(f"/api/v1/inbox/{item.id}")

    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert detail["code"] == "INBOX_ITEM_NOT_FOUND"


# ── Test 5: get_inbox_item 404 when missing ─────────────────────────


@pytest.mark.anyio
async def test_get_inbox_item_404_when_missing(client, mock_service):
    """Missing item returns 404."""
    mock_service.get_item = AsyncMock(return_value=None)

    resp = await client.get("/api/v1/inbox/nonexistent-id")

    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert detail["code"] == "INBOX_ITEM_NOT_FOUND"


# ── Test 6: approve_item dispatches resume ──────────────────────────


@pytest.mark.anyio
async def test_approve_item_dispatches_resume(client, mock_service):
    """Approving an item triggers _signal_executor_resume."""
    item = _make_inbox_item(status="pending")
    resolved_item = _make_inbox_item(
        status="approved",
        inbox_item_id=item.id,
        workspace_id=item.workspace_id,
        mission_id=item.mission_id,
        user_id=item.user_id,
    )
    mock_service.get_item = AsyncMock(return_value=item)
    mock_service.resolve_interrupt = AsyncMock(return_value=resolved_item)

    with patch("app.api.v1.hitl._signal_executor_resume", new_callable=AsyncMock) as mock_resume:
        resp = await client.post(
            f"/api/v1/inbox/{item.id}/approve",
            json={"resolution_note": "Looks good"},
        )

    assert resp.status_code == 200
    mock_resume.assert_called_once()
    # First positional arg is mission_id
    assert mock_resume.call_args[0][0] == item.mission_id


# ── Test 7: reject_item dispatches abort ────────────────────────────


@pytest.mark.anyio
async def test_reject_item_dispatches_abort(client, mock_service):
    """Rejecting an item triggers _signal_executor_abort."""
    item = _make_inbox_item(status="pending")
    resolved_item = _make_inbox_item(
        status="rejected",
        inbox_item_id=item.id,
        workspace_id=item.workspace_id,
        mission_id=item.mission_id,
        user_id=item.user_id,
    )
    mock_service.get_item = AsyncMock(return_value=item)
    mock_service.resolve_interrupt = AsyncMock(return_value=resolved_item)

    with patch("app.api.v1.hitl._signal_executor_abort", new_callable=AsyncMock) as mock_abort:
        resp = await client.post(
            f"/api/v1/inbox/{item.id}/reject",
            json={"resolution_note": "Too risky"},
        )

    assert resp.status_code == 200
    mock_abort.assert_called_once()
    args = mock_abort.call_args[0]
    assert args[0] == item.mission_id
    assert args[2] == "rejected_by_human"


# ── Test 8: resolve wrong status returns 409 ────────────────────────


@pytest.mark.anyio
async def test_resolve_wrong_status_returns_409(client, mock_service):
    """Already-resolved item returns 409 with INBOX_ITEM_WRONG_STATUS."""
    item = _make_inbox_item(status="approved")
    mock_service.get_item = AsyncMock(return_value=item)

    resp = await client.post(f"/api/v1/inbox/{item.id}/approve")

    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["code"] == "INBOX_ITEM_WRONG_STATUS"
    assert "approved" in detail["error"]


# ── Test 9: clarify wrong type returns 400 ──────────────────────────


@pytest.mark.anyio
async def test_clarify_wrong_type_returns_400(client, mock_service):
    """Clarifying an approval item returns 400 with INBOX_ITEM_WRONG_TYPE."""
    item = _make_inbox_item(status="pending", interrupt_type="approval")
    mock_service.get_item = AsyncMock(return_value=item)

    resp = await client.post(
        f"/api/v1/inbox/{item.id}/clarify",
        json={"response_text": "Here's more info"},
    )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "INBOX_ITEM_WRONG_TYPE"
    assert detail["details"]["actual_type"] == "approval"


# ── Test 10: bulk_resolve happy path ────────────────────────────────


@pytest.mark.anyio
async def test_bulk_resolve_happy_path(client, mock_service):
    """3 items all approved — returns resolved list with all IDs."""
    ids = [str(uuid4()) for _ in range(3)]
    mock_service.bulk_resolve = AsyncMock(
        return_value={"resolved": ids, "skipped": [], "failed": []}
    )

    resp = await client.post(
        "/api/v1/inbox/bulk-resolve",
        json={"item_ids": ids, "action": "approve", "resolution_note": "LGTM"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["resolved"]) == 3
    assert data["skipped"] == []
    assert data["failed"] == []


# ── Test 11: bulk_resolve partial skip ──────────────────────────────


@pytest.mark.anyio
async def test_bulk_resolve_partial_skip(client, mock_service):
    """1 success, 1 not-found, 1 already-resolved — shape matches spec."""
    id_ok = str(uuid4())
    id_missing = str(uuid4())
    id_resolved = str(uuid4())

    mock_service.bulk_resolve = AsyncMock(
        return_value={
            "resolved": [id_ok],
            "skipped": [
                {"id": id_missing, "reason": "not_found"},
                {"id": id_resolved, "reason": "already_approved"},
            ],
            "failed": [],
        }
    )

    resp = await client.post(
        "/api/v1/inbox/bulk-resolve",
        json={"item_ids": [id_ok, id_missing, id_resolved], "action": "approve"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["resolved"]) == 1
    assert len(data["skipped"]) == 2
    assert data["skipped"][0]["reason"] == "not_found"
    assert data["skipped"][1]["reason"] == "already_approved"
    assert data["failed"] == []


# ── Test 12: bulk_resolve too large returns 422 ─────────────────────


@pytest.mark.anyio
async def test_bulk_resolve_too_large_returns_422(client, mock_service):
    """101 items exceeds max_length and returns 422 (Pydantic validation)."""
    ids = [str(uuid4()) for _ in range(101)]

    resp = await client.post(
        "/api/v1/inbox/bulk-resolve",
        json={"item_ids": ids, "action": "approve"},
    )

    assert resp.status_code == 422
    mock_service.bulk_resolve.assert_not_called()


# ── Test 13: get_by_mission returns user-scoped results ─────────────


@pytest.mark.anyio
async def test_get_by_mission_returns_user_scoped(client, mock_service, fake_user):
    """Items from another user are excluded (service handles scoping)."""
    items = [_make_inbox_item(user_id=fake_user.id)]
    mock_service.get_by_mission = AsyncMock(return_value=items)

    mission_id = str(uuid4())
    resp = await client.get(f"/api/v1/inbox/by-mission/{mission_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["user_id"] == fake_user.id

    # Verify the service was called with the right user_id
    call = mock_service.get_by_mission.call_args
    assert call.kwargs["user_id"] == fake_user.id
    assert call.kwargs["mission_id"] == mission_id


# ── Test 14: inbox_counts scoped to workspace ───────────────────────


@pytest.mark.anyio
async def test_inbox_counts_scoped_to_workspace(client, mock_service, fake_workspace_id):
    """workspace_id filter changes count (passed to count_pending)."""
    mock_service.count_pending = AsyncMock(return_value=5)

    resp = await client.get("/api/v1/inbox/counts")

    assert resp.status_code == 200
    data = resp.json()
    assert data["pending_count"] == 5

    call = mock_service.count_pending.call_args
    assert call.kwargs["workspace_id"] == fake_workspace_id


# ── Bonus: SSE wrapper publishes hitl_inbox event ───────────────────


@pytest.mark.anyio
async def test_sse_wrapper_publishes_hitl_inbox_event():
    """publish_hitl_inbox_event wraps data with hitl_inbox event type."""
    from app.services.sse_service import publish_hitl_inbox_event

    mock_redis = AsyncMock()
    mock_redis.aclose = AsyncMock()

    item_data = {"id": "item-1", "mission_id": "m-1", "interrupt_type": "approval", "status": "pending"}

    with patch("app.services.sse_service.get_redis_client", return_value=mock_redis):
        await publish_hitl_inbox_event(42, "interrupt_raised", item_data)

    mock_redis.publish.assert_called_once()
    channel, message_raw = mock_redis.publish.call_args[0]
    assert channel == "user:42:notifications"

    message = json.loads(message_raw)
    assert message["event"] == "hitl_inbox"
    assert message["data"]["kind"] == "hitl_inbox"
    assert message["data"]["sub_event"] == "interrupt_raised"
    assert message["data"]["id"] == "item-1"
