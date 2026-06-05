"""Tests for the GET /workspaces/{id}/overview endpoint.

Verifies:
1. Membership enforcement (non-member gets 403)
2. Correct aggregation of missions, agents, members, inbox, cost
3. Empty workspace returns zeros
4. Recent activity is returned and ordered
5. Cost service failure is handled gracefully
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# ── Helpers ──────────────────────────────────────────────────────────

def _make_user(user_id: int = 1) -> MagicMock:
    return MagicMock(id=user_id, email="test@example.com")


def _make_membership() -> MagicMock:
    return MagicMock(is_active=True, role="member")


def _make_scalars_result(items):
    """Create a mock result that returns items from .scalars().all()."""
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = items
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    return mock_result


def _make_scalar_result(value):
    """Create a mock result that returns a scalar from .scalar()."""
    mock_result = MagicMock()
    mock_result.scalar.return_value = value
    return mock_result


def _make_activity_event(event_id: int, event_type: str, user_id: str = "1",
                         description: str = "test event") -> MagicMock:
    event = MagicMock()
    event.id = event_id
    event.event_type = event_type
    event.user_id = user_id
    event.properties = {
        "workspace_id": "ws-1",
        "actor_name": "Alice",
        "description": description,
    }
    event.timestamp = datetime.now(timezone.utc)
    return event


# ── Tests ────────────────────────────────────────────────────────────

class TestWorkspaceOverviewMembership:
    """The overview endpoint should enforce workspace membership."""

    @pytest.mark.asyncio
    async def test_non_member_gets_403(self):
        """A user who is not a workspace member should get 403."""
        from app.api.v1.workspace_activity import get_workspace_overview

        user = _make_user(99)
        db = AsyncMock()

        # Membership query returns None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await get_workspace_overview("ws-1", user, db)

        assert exc_info.value.status_code == 403
        assert "Not a member" in exc_info.value.detail



class TestWorkspaceOverviewData:
    """The overview endpoint should aggregate workspace data correctly."""

    @pytest.mark.asyncio
    async def test_returns_correct_counts(self):
        """Overview returns correct mission, agent, member, and inbox counts."""
        from app.api.v1.workspace_activity import get_workspace_overview

        user = _make_user(1)
        db = AsyncMock()

        call_count = 0

        async def side_effect(stmt):
            nonlocal call_count
            call_count += 1
            # 1: membership check
            if call_count == 1:
                return MagicMock(scalar_one_or_none=lambda: _make_membership())
            # 2: active missions count
            if call_count == 2:
                return _make_scalar_result(3)
            # 3: total missions count
            if call_count == 3:
                return _make_scalar_result(12)
            # 4: total agents count
            if call_count == 4:
                return _make_scalar_result(5)
            # 5: pending inbox count
            if call_count == 5:
                return _make_scalar_result(2)
            # 6: total members count
            if call_count == 6:
                return _make_scalar_result(8)
            # 7: activity query
            if call_count == 7:
                return _make_scalars_result([
                    _make_activity_event(1, "mission_started", description="started Build API"),
                    _make_activity_event(2, "member_joined", description="Bob joined"),
                ])
            return _make_scalar_result(0)

        db.execute = AsyncMock(side_effect=side_effect)

        # Patch CostAttributionService
        with patch("app.services.cost_attribution_service.CostAttributionService") as MockCost:
            MockCost.return_value.get_aggregates = AsyncMock(return_value={
                "totals": {"total_cost_usd": 4.56},
            })

            result = await get_workspace_overview("ws-1", user, db)

        assert result["active_missions"] == 3
        assert result["total_missions"] == 12
        assert result["total_agents"] == 5
        assert result["total_members"] == 8
        assert result["pending_inbox"] == 2
        assert result["monthly_cost_usd"] == 4.56
        assert len(result["recent_activity"]) == 2

    @pytest.mark.asyncio
    async def test_empty_workspace_returns_zeros(self):
        """A workspace with no missions, agents, or activity returns all zeros."""
        from app.api.v1.workspace_activity import get_workspace_overview

        user = _make_user(1)
        db = AsyncMock()

        call_count = 0

        async def side_effect(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(scalar_one_or_none=lambda: _make_membership())
            if call_count == 7:
                return _make_scalars_result([])
            return _make_scalar_result(0)

        db.execute = AsyncMock(side_effect=side_effect)

        with patch("app.services.cost_attribution_service.CostAttributionService") as MockCost:
            MockCost.return_value.get_aggregates = AsyncMock(return_value={
                "totals": {"total_cost_usd": 0},
            })

            result = await get_workspace_overview("ws-empty", user, db)

        assert result["active_missions"] == 0
        assert result["total_missions"] == 0
        assert result["total_agents"] == 0
        assert result["total_members"] == 0
        assert result["pending_inbox"] == 0
        assert result["monthly_cost_usd"] == 0
        assert result["recent_activity"] == []

    @pytest.mark.asyncio
    async def test_recent_activity_contains_event_fields(self):
        """Activity items should include id, event_type, user_id, actor_name, description, created_at."""
        from app.api.v1.workspace_activity import get_workspace_overview

        user = _make_user(1)
        db = AsyncMock()

        call_count = 0

        async def side_effect(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(scalar_one_or_none=lambda: _make_membership())
            if call_count == 7:
                return _make_scalars_result([
                    _make_activity_event(42, "mission_completed", description="Deploy done"),
                ])
            return _make_scalar_result(0)

        db.execute = AsyncMock(side_effect=side_effect)

        with patch("app.services.cost_attribution_service.CostAttributionService") as MockCost:
            MockCost.return_value.get_aggregates = AsyncMock(return_value={
                "totals": {"total_cost_usd": 0},
            })

            result = await get_workspace_overview("ws-1", user, db)

        activity = result["recent_activity"]
        assert len(activity) == 1
        assert activity[0]["id"] == 42
        assert activity[0]["event_type"] == "mission_completed"
        assert activity[0]["actor_name"] == "Alice"
        assert activity[0]["description"] == "Deploy done"
        assert "created_at" in activity[0]

    @pytest.mark.asyncio
    async def test_cost_service_failure_returns_zero(self):
        """If CostAttributionService raises, monthly_cost_usd should be 0."""
        from app.api.v1.workspace_activity import get_workspace_overview

        user = _make_user(1)
        db = AsyncMock()

        call_count = 0

        async def side_effect(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(scalar_one_or_none=lambda: _make_membership())
            if call_count == 7:
                return _make_scalars_result([])
            return _make_scalar_result(0)

        db.execute = AsyncMock(side_effect=side_effect)

        with patch("app.services.cost_attribution_service.CostAttributionService") as MockCost:
            MockCost.return_value.get_aggregates = AsyncMock(
                side_effect=RuntimeError("DB connection lost")
            )

            result = await get_workspace_overview("ws-1", user, db)

        assert result["monthly_cost_usd"] == 0

    @pytest.mark.asyncio
    async def test_cost_rounded_to_4_decimals(self):
        """Monthly cost should be rounded to 4 decimal places."""
        from app.api.v1.workspace_activity import get_workspace_overview

        user = _make_user(1)
        db = AsyncMock()

        call_count = 0

        async def side_effect(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(scalar_one_or_none=lambda: _make_membership())
            if call_count == 7:
                return _make_scalars_result([])
            return _make_scalar_result(0)

        db.execute = AsyncMock(side_effect=side_effect)

        with patch("app.services.cost_attribution_service.CostAttributionService") as MockCost:
            MockCost.return_value.get_aggregates = AsyncMock(return_value={
                "totals": {"total_cost_usd": 12.3456789},
            })

            result = await get_workspace_overview("ws-1", user, db)

        assert result["monthly_cost_usd"] == 12.3457

    @pytest.mark.asyncio
    async def test_none_counts_default_to_zero(self):
        """If DB returns None for counts (no rows), they should default to 0."""
        from app.api.v1.workspace_activity import get_workspace_overview

        user = _make_user(1)
        db = AsyncMock()

        call_count = 0

        async def side_effect(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(scalar_one_or_none=lambda: _make_membership())
            if call_count == 7:
                return _make_scalars_result([])
            # Return None for scalar queries
            return _make_scalar_result(None)

        db.execute = AsyncMock(side_effect=side_effect)

        with patch("app.services.cost_attribution_service.CostAttributionService") as MockCost:
            MockCost.return_value.get_aggregates = AsyncMock(return_value={
                "totals": {},
            })

            result = await get_workspace_overview("ws-1", user, db)

        assert result["active_missions"] == 0
        assert result["total_missions"] == 0
        assert result["total_agents"] == 0
        assert result["total_members"] == 0
        assert result["pending_inbox"] == 0

    @pytest.mark.asyncio
    async def test_activity_with_no_properties(self):
        """Activity events with None properties should not crash."""
        from app.api.v1.workspace_activity import get_workspace_overview

        user = _make_user(1)
        db = AsyncMock()

        event = MagicMock()
        event.id = 1
        event.event_type = "member_online"
        event.user_id = "1"
        event.properties = None
        event.timestamp = datetime.now(timezone.utc)

        call_count = 0

        async def side_effect(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(scalar_one_or_none=lambda: _make_membership())
            if call_count == 7:
                return _make_scalars_result([event])
            return _make_scalar_result(0)

        db.execute = AsyncMock(side_effect=side_effect)

        with patch("app.services.cost_attribution_service.CostAttributionService") as MockCost:
            MockCost.return_value.get_aggregates = AsyncMock(return_value={
                "totals": {"total_cost_usd": 0},
            })

            result = await get_workspace_overview("ws-1", user, db)

        assert len(result["recent_activity"]) == 1
        assert result["recent_activity"][0]["actor_name"] is None
        assert result["recent_activity"][0]["description"] is None

    @pytest.mark.asyncio
    async def test_activity_with_no_timestamp(self):
        """Activity events with None timestamp should return empty string."""
        from app.api.v1.workspace_activity import get_workspace_overview

        user = _make_user(1)
        db = AsyncMock()

        event = MagicMock()
        event.id = 1
        event.event_type = "role_changed"
        event.user_id = "1"
        event.properties = {"workspace_id": "ws-1"}
        event.timestamp = None

        call_count = 0

        async def side_effect(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(scalar_one_or_none=lambda: _make_membership())
            if call_count == 7:
                return _make_scalars_result([event])
            return _make_scalar_result(0)

        db.execute = AsyncMock(side_effect=side_effect)

        with patch("app.services.cost_attribution_service.CostAttributionService") as MockCost:
            MockCost.return_value.get_aggregates = AsyncMock(return_value={
                "totals": {"total_cost_usd": 0},
            })

            result = await get_workspace_overview("ws-1", user, db)

        assert result["recent_activity"][0]["created_at"] == ""

    @pytest.mark.asyncio
    async def test_cost_totals_missing_cost_key(self):
        """If cost totals dict is missing total_cost_usd, should default to 0."""
        from app.api.v1.workspace_activity import get_workspace_overview

        user = _make_user(1)
        db = AsyncMock()

        call_count = 0

        async def side_effect(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(scalar_one_or_none=lambda: _make_membership())
            if call_count == 7:
                return _make_scalars_result([])
            return _make_scalar_result(0)

        db.execute = AsyncMock(side_effect=side_effect)

        with patch("app.services.cost_attribution_service.CostAttributionService") as MockCost:
            MockCost.return_value.get_aggregates = AsyncMock(return_value={
                "totals": {},  # missing total_cost_usd
            })

            result = await get_workspace_overview("ws-1", user, db)

        assert result["monthly_cost_usd"] == 0
