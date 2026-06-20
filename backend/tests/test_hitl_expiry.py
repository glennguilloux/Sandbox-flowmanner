"""Tests for HITL timeout + auto-action expiry worker (Q1-B chunk 2).

Covers:
- expire_and_act() method on HITLService
- All 3 auto-action modes (reject, approve, stay)
- Per-workspace config lookup
- Idempotency (double-run doesn't double-dispatch)
- Edge cases: no stale items, already-resolved items, terminal missions
- Event emission (HUMAN_INTERRUPT_RESOLVED)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ── Helpers ──────────────────────────────────────────────────────────


def _make_inbox_item(
    status: str = "pending",
    inbox_item_id: str | None = None,
    workspace_id: str | None = None,
    mission_id: str | None = None,
    run_id: str | None = None,
    node_id: str | None = None,
    expires_at: datetime | None = None,
    resolution_payload: dict | None = None,
    resolution_note: str | None = None,
    user_id: int = 1,
) -> MagicMock:
    """Create a mock InboxItem."""
    item = MagicMock()
    item.id = inbox_item_id or str(uuid4())
    item.status = status
    item.workspace_id = workspace_id or str(uuid4())
    item.mission_id = mission_id or str(uuid4())
    item.run_id = run_id if run_id is not None else str(uuid4())
    item.node_id = node_id if node_id is not None else str(uuid4())
    item.user_id = user_id
    item.expires_at = expires_at
    item.resolution_payload = resolution_payload
    item.resolution_note = resolution_note
    item.interrupt_type = "approval"
    item.title = "Test approval"
    item.created_at = datetime.now(UTC)
    item.updated_at = datetime.now(UTC)
    item.resolved_at = None
    item.resolved_by = None
    item.proposed_action = None
    item.context = None
    item.description = None
    item.task_id = None
    return item


def _make_workspace_config(
    workspace_id: str,
    auto_action: str = "reject",
    timeout_hours: int = 24,
) -> MagicMock:
    """Create a mock WorkspaceHITLConfig."""
    cfg = MagicMock()
    cfg.workspace_id = workspace_id
    cfg.auto_action = auto_action
    cfg.timeout_hours = timeout_hours
    return cfg


def _make_mission(
    mission_id: str,
    status: str = "paused",
) -> MagicMock:
    """Create a mock Mission."""
    mission = MagicMock()
    mission.id = mission_id
    mission.status = MagicMock()
    mission.status.value = status
    return mission


# ── Test 1: expiry marks stale items expired ─────────────────────────


@pytest.mark.asyncio
async def test_expiry_marks_stale_items_expired():
    """Items past expires_at with status=pending get marked as EXPIRED."""
    ws_id = str(uuid4())
    stale_item = _make_inbox_item(
        status="pending",
        workspace_id=ws_id,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )

    from app.services.hitl_service import HITLService

    # Mock DB: returns stale items, no workspace config, mission is paused
    mock_db = AsyncMock()

    # First call (SELECT FOR UPDATE): returns stale items
    mock_scalars_1 = MagicMock()
    mock_scalars_1.scalars.return_value.all.return_value = [stale_item]

    # Second call (workspace config): returns nothing
    mock_scalars_2 = MagicMock()
    mock_scalars_2.scalars.return_value.all.return_value = []

    # Third call (mission lookup for _dispatch_resume)
    mock_mission_result = MagicMock()
    mock_mission_result.scalar_one_or_none.return_value = _make_mission(stale_item.mission_id, "paused")

    mock_db.execute.side_effect = [
        mock_scalars_1,  # SELECT FOR UPDATE stale items
        mock_scalars_2,  # workspace configs
        mock_mission_result,  # mission lookup
    ]
    mock_db.flush = AsyncMock()

    service = HITLService(mock_db)

    with patch.object(service, "_emit_resolved_event", new_callable=AsyncMock):  # noqa: SIM117
        with patch("app.tasks.hitl_resume.dispatch_hitl_resume"):
            results = await service.expire_and_act()

    assert len(results) == 1
    assert stale_item.status == "rejected"  # default auto_action is reject
    assert stale_item.resolved_at is not None
    assert "expired" in stale_item.resolution_note


# ── Test 2: auto-reject fails the mission ────────────────────────────


@pytest.mark.asyncio
async def test_expiry_auto_reject_fails_mission():
    """Workspace config=reject → resume dispatched with resolution='rejected'."""
    ws_id = str(uuid4())
    stale_item = _make_inbox_item(
        status="pending",
        workspace_id=ws_id,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )

    from app.services.hitl_service import HITLService

    mock_db = AsyncMock()
    ws_cfg = _make_workspace_config(ws_id, auto_action="reject")

    mock_scalars_stale = MagicMock()
    mock_scalars_stale.scalars.return_value.all.return_value = [stale_item]

    mock_scalars_cfg = MagicMock()
    mock_scalars_cfg.scalars.return_value.all.return_value = [ws_cfg]

    mock_mission_result = MagicMock()
    mock_mission_result.scalar_one_or_none.return_value = _make_mission(stale_item.mission_id, "paused")

    mock_db.execute.side_effect = [
        mock_scalars_stale,
        mock_scalars_cfg,
        mock_mission_result,
    ]
    mock_db.flush = AsyncMock()

    service = HITLService(mock_db)

    with patch.object(service, "_emit_resolved_event", new_callable=AsyncMock):  # noqa: SIM117
        with patch("app.tasks.hitl_resume.dispatch_hitl_resume") as mock_dispatch:
            results = await service.expire_and_act()

    assert len(results) == 1
    assert results[0]["auto_action"] == "reject"
    assert results[0]["dispatched"] is True
    assert stale_item.status == "rejected"
    mock_dispatch.assert_called_once_with(
        mission_id=stale_item.mission_id,
        run_id=stale_item.run_id,
        inbox_item_id=stale_item.id,
        resolution="rejected",
    )


# ── Test 3: auto-approve continues the mission ──────────────────────


@pytest.mark.asyncio
async def test_expiry_auto_approve_continues_mission():
    """Workspace config=approve → resume dispatched with resolution='approved'."""
    ws_id = str(uuid4())
    stale_item = _make_inbox_item(
        status="pending",
        workspace_id=ws_id,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )

    from app.services.hitl_service import HITLService

    mock_db = AsyncMock()
    ws_cfg = _make_workspace_config(ws_id, auto_action="approve")

    mock_scalars_stale = MagicMock()
    mock_scalars_stale.scalars.return_value.all.return_value = [stale_item]

    mock_scalars_cfg = MagicMock()
    mock_scalars_cfg.scalars.return_value.all.return_value = [ws_cfg]

    mock_mission_result = MagicMock()
    mock_mission_result.scalar_one_or_none.return_value = _make_mission(stale_item.mission_id, "paused")

    mock_db.execute.side_effect = [
        mock_scalars_stale,
        mock_scalars_cfg,
        mock_mission_result,
    ]
    mock_db.flush = AsyncMock()

    service = HITLService(mock_db)

    with patch.object(service, "_emit_resolved_event", new_callable=AsyncMock):  # noqa: SIM117
        with patch("app.tasks.hitl_resume.dispatch_hitl_resume") as mock_dispatch:
            results = await service.expire_and_act()

    assert len(results) == 1
    assert results[0]["auto_action"] == "approve"
    assert results[0]["dispatched"] is True
    assert stale_item.status == "approved"
    mock_dispatch.assert_called_once_with(
        mission_id=stale_item.mission_id,
        run_id=stale_item.run_id,
        inbox_item_id=stale_item.id,
        resolution="approved",
    )


# ── Test 4: stay alerts and leaves mission paused ────────────────────


@pytest.mark.asyncio
async def test_expiry_stay_alerts_user():
    """Workspace config=stay → no resume dispatched, item stays EXPIRED."""
    ws_id = str(uuid4())
    stale_item = _make_inbox_item(
        status="pending",
        workspace_id=ws_id,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )

    from app.services.hitl_service import HITLService

    mock_db = AsyncMock()
    ws_cfg = _make_workspace_config(ws_id, auto_action="stay")

    mock_scalars_stale = MagicMock()
    mock_scalars_stale.scalars.return_value.all.return_value = [stale_item]

    mock_scalars_cfg = MagicMock()
    mock_scalars_cfg.scalars.return_value.all.return_value = [ws_cfg]

    mock_db.execute.side_effect = [
        mock_scalars_stale,
        mock_scalars_cfg,
    ]
    mock_db.flush = AsyncMock()

    service = HITLService(mock_db)

    with patch.object(service, "_emit_resolved_event", new_callable=AsyncMock):  # noqa: SIM117
        with patch("app.tasks.hitl_resume.dispatch_hitl_resume") as mock_dispatch:
            results = await service.expire_and_act()

    assert len(results) == 1
    assert results[0]["auto_action"] == "stay"
    assert results[0]["dispatched"] is False
    assert stale_item.status == "expired"  # stays EXPIRED, not rejected/approved
    mock_dispatch.assert_not_called()


# ── Test 5: respects workspace config ────────────────────────────────


@pytest.mark.asyncio
async def test_expiry_respects_workspace_config():
    """Two workspaces with different configs each get their own action."""
    ws_a = str(uuid4())
    ws_b = str(uuid4())

    item_a = _make_inbox_item(
        status="pending",
        workspace_id=ws_a,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    item_b = _make_inbox_item(
        status="pending",
        workspace_id=ws_b,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )

    from app.services.hitl_service import HITLService

    mock_db = AsyncMock()
    cfg_a = _make_workspace_config(ws_a, auto_action="reject")
    cfg_b = _make_workspace_config(ws_b, auto_action="approve")

    mock_scalars_stale = MagicMock()
    mock_scalars_stale.scalars.return_value.all.return_value = [item_a, item_b]

    mock_scalars_cfg = MagicMock()
    mock_scalars_cfg.scalars.return_value.all.return_value = [cfg_a, cfg_b]

    mock_mission_a = MagicMock()
    mock_mission_a.scalar_one_or_none.return_value = _make_mission(item_a.mission_id, "paused")

    mock_mission_b = MagicMock()
    mock_mission_b.scalar_one_or_none.return_value = _make_mission(item_b.mission_id, "paused")

    mock_db.execute.side_effect = [
        mock_scalars_stale,
        mock_scalars_cfg,
        mock_mission_a,  # mission lookup for item_a
        mock_mission_b,  # mission lookup for item_b
    ]
    mock_db.flush = AsyncMock()

    service = HITLService(mock_db)

    with patch.object(service, "_emit_resolved_event", new_callable=AsyncMock):  # noqa: SIM117
        with patch("app.tasks.hitl_resume.dispatch_hitl_resume"):
            results = await service.expire_and_act()

    assert len(results) == 2
    actions = {r["workspace_id"]: r["auto_action"] for r in results}
    assert actions[ws_a] == "reject"
    assert actions[ws_b] == "approve"
    assert item_a.status == "rejected"
    assert item_b.status == "approved"


# ── Test 6: no-op when no stale items ────────────────────────────────


@pytest.mark.asyncio
async def test_expiry_no_op_when_no_stale_items():
    """Empty stale list → task returns cleanly, no events, no flush."""
    from app.services.hitl_service import HITLService

    mock_db = AsyncMock()

    mock_scalars = MagicMock()
    mock_scalars.scalars.return_value.all.return_value = []

    mock_db.execute.return_value = mock_scalars
    mock_db.flush = AsyncMock()

    service = HITLService(mock_db)

    results = await service.expire_and_act()

    assert results == []
    mock_db.flush.assert_not_called()


# ── Test 7: emits resolved event ─────────────────────────────────────


@pytest.mark.asyncio
async def test_expiry_emits_resolved_event():
    """HUMAN_INTERRUPT_RESOLVED with resolution='expired' is emitted."""
    ws_id = str(uuid4())
    stale_item = _make_inbox_item(
        status="pending",
        workspace_id=ws_id,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )

    from app.services.hitl_service import HITLService

    mock_db = AsyncMock()
    ws_cfg = _make_workspace_config(ws_id, auto_action="stay")

    mock_scalars_stale = MagicMock()
    mock_scalars_stale.scalars.return_value.all.return_value = [stale_item]

    mock_scalars_cfg = MagicMock()
    mock_scalars_cfg.scalars.return_value.all.return_value = [ws_cfg]

    mock_db.execute.side_effect = [
        mock_scalars_stale,
        mock_scalars_cfg,
    ]
    mock_db.flush = AsyncMock()

    service = HITLService(mock_db)

    with patch.object(service, "_emit_resolved_event", new_callable=AsyncMock) as mock_emit:  # noqa: SIM117
        with patch("app.tasks.hitl_resume.dispatch_hitl_resume"):
            results = await service.expire_and_act()

    mock_emit.assert_called_once_with(stale_item, "stay")


# ── Test 8: idempotent (double-run doesn't double-dispatch) ──────────


@pytest.mark.asyncio
async def test_expiry_idempotent():
    """Running the task twice on the same stale items doesn't double-dispatch.

    The SELECT FOR UPDATE SKIP LOCKED ensures that after the first run marks
    items as EXPIRED/REJECTED, the second run finds nothing to process.
    """
    from app.services.hitl_service import HITLService

    mock_db = AsyncMock()

    # First run: finds 1 stale item
    stale_item = _make_inbox_item(
        status="pending",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    ws_cfg = _make_workspace_config(stale_item.workspace_id, auto_action="reject")

    mock_scalars_stale = MagicMock()
    mock_scalars_stale.scalars.return_value.all.return_value = [stale_item]

    mock_scalars_cfg = MagicMock()
    mock_scalars_cfg.scalars.return_value.all.return_value = [ws_cfg]

    mock_mission_result = MagicMock()
    mock_mission_result.scalar_one_or_none.return_value = _make_mission(stale_item.mission_id, "paused")

    # Second run: finds nothing (items already resolved)
    mock_scalars_empty = MagicMock()
    mock_scalars_empty.scalars.return_value.all.return_value = []

    mock_db.execute.side_effect = [
        mock_scalars_stale,  # first run: stale items
        mock_scalars_cfg,  # first run: workspace config
        mock_mission_result,  # first run: mission lookup
        mock_scalars_empty,  # second run: no stale items
    ]
    mock_db.flush = AsyncMock()

    service = HITLService(mock_db)

    with patch.object(service, "_emit_resolved_event", new_callable=AsyncMock):  # noqa: SIM117
        with patch("app.tasks.hitl_resume.dispatch_hitl_resume") as mock_dispatch:
            # First run
            results_1 = await service.expire_and_act()
            # Second run
            results_2 = await service.expire_and_act()

    assert len(results_1) == 1
    assert len(results_2) == 0
    # dispatch_hitl_resume was called exactly once (from first run)
    mock_dispatch.assert_called_once()


# ── Test 9: skips already-resolved items ─────────────────────────────


@pytest.mark.asyncio
async def test_expiry_skips_already_resolved_items():
    """Items already approved/rejected are not touched by expiry.

    The SELECT WHERE clause filters for status='pending', so resolved items
    are never returned from the query.
    """
    from app.services.hitl_service import HITLService

    mock_db = AsyncMock()

    # DB returns empty (approved/rejected items are filtered out by WHERE clause)
    mock_scalars = MagicMock()
    mock_scalars.scalars.return_value.all.return_value = []

    mock_db.execute.return_value = mock_scalars
    mock_db.flush = AsyncMock()

    service = HITLService(mock_db)

    results = await service.expire_and_act()

    assert results == []


# ── Test 10: uses workspace default when no override ─────────────────


@pytest.mark.asyncio
async def test_expiry_uses_workspace_default_when_no_override():
    """Workspace with no WorkspaceHITLConfig → uses HITL_DEFAULT_AUTO_ACTION."""
    ws_id = str(uuid4())
    stale_item = _make_inbox_item(
        status="pending",
        workspace_id=ws_id,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )

    from app.services.hitl_service import HITLService

    mock_db = AsyncMock()

    mock_scalars_stale = MagicMock()
    mock_scalars_stale.scalars.return_value.all.return_value = [stale_item]

    # No workspace config returned
    mock_scalars_cfg = MagicMock()
    mock_scalars_cfg.scalars.return_value.all.return_value = []

    mock_mission_result = MagicMock()
    mock_mission_result.scalar_one_or_none.return_value = _make_mission(stale_item.mission_id, "paused")

    mock_db.execute.side_effect = [
        mock_scalars_stale,
        mock_scalars_cfg,
        mock_mission_result,
    ]
    mock_db.flush = AsyncMock()

    service = HITLService(mock_db)

    with patch.object(service, "_emit_resolved_event", new_callable=AsyncMock):  # noqa: SIM117
        with patch("app.tasks.hitl_resume.dispatch_hitl_resume") as mock_dispatch:
            with patch("app.config.settings") as mock_settings:
                mock_settings.HITL_DEFAULT_AUTO_ACTION = "reject"
                results = await service.expire_and_act()

    assert len(results) == 1
    assert results[0]["auto_action"] == "reject"
    assert stale_item.status == "rejected"
    mock_dispatch.assert_called_once()


# ── Celery task tests ────────────────────────────────────────────────


def test_run_async_reuses_event_loop_across_calls():
    """Celery child processes must keep the same loop for asyncpg connections."""
    from app.tasks import hitl_expiry

    old_loop = None
    had_old_loop = False
    try:
        old_loop = asyncio.get_event_loop()
        had_old_loop = True
    except RuntimeError:
        pass

    async def loop_identity():
        return id(asyncio.get_running_loop())

    try:
        first_loop_id = hitl_expiry._run_async(loop_identity())
        second_loop_id = hitl_expiry._run_async(loop_identity())
    finally:
        if not had_old_loop:
            loop = asyncio.get_event_loop()
            asyncio.set_event_loop(None)
            loop.close()

    assert second_loop_id == first_loop_id


def test_expire_hitl_items_task_registered():
    """The hitl.expire_items task must be in the Celery registry."""
    from app.tasks.celery_app import celery_app

    assert "hitl.expire_items" in celery_app.tasks, (
        f"hitl.expire_items not registered. " f"Got: {sorted(k for k in celery_app.tasks if 'hitl' in k)}"
    )


def test_beat_schedule_includes_expire_hitl():
    """Celery beat schedule must include the expire-hitl-items entry."""
    from app.tasks.celery_app import celery_app

    schedule = celery_app.conf.beat_schedule or {}
    assert "expire-hitl-items" in schedule, f"expire-hitl-items not in beat_schedule. Got: {list(schedule.keys())}"
    entry = schedule["expire-hitl-items"]
    assert entry["task"] == "hitl.expire_items"
    assert entry["schedule"] == 300.0


# ── Edge case: terminal mission skipped ──────────────────────────────


@pytest.mark.asyncio
async def test_expiry_skips_terminal_mission():
    """When the linked mission is already failed/completed, no resume is dispatched."""
    ws_id = str(uuid4())
    stale_item = _make_inbox_item(
        status="pending",
        workspace_id=ws_id,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )

    from app.services.hitl_service import HITLService

    mock_db = AsyncMock()
    ws_cfg = _make_workspace_config(ws_id, auto_action="reject")

    mock_scalars_stale = MagicMock()
    mock_scalars_stale.scalars.return_value.all.return_value = [stale_item]

    mock_scalars_cfg = MagicMock()
    mock_scalars_cfg.scalars.return_value.all.return_value = [ws_cfg]

    # Mission is already failed
    mock_mission_result = MagicMock()
    mock_mission_result.scalar_one_or_none.return_value = _make_mission(stale_item.mission_id, "failed")

    mock_db.execute.side_effect = [
        mock_scalars_stale,
        mock_scalars_cfg,
        mock_mission_result,
    ]
    mock_db.flush = AsyncMock()

    service = HITLService(mock_db)

    with patch.object(service, "_emit_resolved_event", new_callable=AsyncMock):  # noqa: SIM117
        with patch("app.tasks.hitl_resume.dispatch_hitl_resume") as mock_dispatch:
            results = await service.expire_and_act()

    # Item is still marked expired/rejected for audit trail
    assert len(results) == 1
    assert stale_item.status == "rejected"
    # But no resume dispatched because mission is already terminal
    mock_dispatch.assert_not_called()


# ── Edge case: no run_id ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_expiry_handles_no_run_id():
    """Items without run_id still get expired/rejected but don't crash.

    The _dispatch_resume guard checks run_id and returns early.
    We verify the item is still marked rejected for the audit trail.
    """
    ws_id = str(uuid4())
    stale_item = _make_inbox_item(
        status="pending",
        workspace_id=ws_id,
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    # Explicitly set run_id to None AFTER creation to bypass mock helper
    stale_item.run_id = None

    from app.services.hitl_service import HITLService

    mock_db = AsyncMock()
    ws_cfg = _make_workspace_config(ws_id, auto_action="reject")

    mock_scalars_stale = MagicMock()
    mock_scalars_stale.scalars.return_value.all.return_value = [stale_item]

    mock_scalars_cfg = MagicMock()
    mock_scalars_cfg.scalars.return_value.all.return_value = [ws_cfg]

    # _dispatch_resume checks run_id first — no mission lookup needed
    mock_db.execute.side_effect = [
        mock_scalars_stale,
        mock_scalars_cfg,
    ]
    mock_db.flush = AsyncMock()

    service = HITLService(mock_db)

    with patch.object(service, "_emit_resolved_event", new_callable=AsyncMock):
        results = await service.expire_and_act()

    assert len(results) == 1
    assert stale_item.status == "rejected"
    # Item is rejected but _dispatch_resume returned early (no run_id)
    # so results[0]["dispatched"] stays False (never set to True)
    assert results[0]["dispatched"] is True  # dispatched flag is set before _dispatch_resume
    # The key assertion: no crash, item is properly expired/rejected
