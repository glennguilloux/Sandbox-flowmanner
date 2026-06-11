"""Tests for GET/PATCH /workspaces/{id}/settings endpoints.

Verifies:
1. Membership enforcement (non-member gets 404)
2. GET returns defaults when no stored settings
3. GET merges stored settings with defaults
4. PATCH owner/admin can update
5. PATCH member/guest get 403
6. PATCH partial updates (only CB or only approval)
7. PATCH merges with existing stored settings
8. Workspace not found after membership passes
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

# ── Helpers ──────────────────────────────────────────────────────────


def _make_user(user_id: int = 1) -> MagicMock:
    return MagicMock(id=user_id, email="test@example.com")


def _make_membership(role: str = "member") -> MagicMock:
    m = MagicMock()
    m.is_active = True
    m.role = role
    return m


def _make_workspace(ws_id: str = "ws-1", settings: dict | None = None) -> MagicMock:
    ws = MagicMock()
    ws.id = ws_id
    ws.name = "Test Workspace"
    ws.slug = "test"
    ws.settings = settings
    return ws


def _mock_db_queries(*results):
    """Create an AsyncMock db that returns results in order for successive execute calls."""
    db = AsyncMock()
    call_count = 0

    async def side_effect(stmt):
        nonlocal call_count
        idx = call_count
        call_count += 1
        if idx < len(results):
            r = results[idx]
            if isinstance(r, Exception):
                raise r
            return r
        return MagicMock(scalar_one_or_none=lambda: None)

    db.execute = AsyncMock(side_effect=side_effect)
    return db


def _membership_result(member):
    """Mock result for membership check (scalar_one_or_none)."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = member
    return r


def _workspace_result(ws):
    """Mock result for workspace query (scalar_one_or_none)."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = ws
    return r


# ── GET Settings Tests ───────────────────────────────────────────────


class TestGetWorkspaceSettings:
    @pytest.mark.asyncio
    async def test_non_member_gets_404(self):
        """Non-member should get 404 from _verify_membership."""
        from app.api.v1.workspace import get_workspace_settings

        db = _mock_db_queries(_membership_result(None))

        with pytest.raises(HTTPException) as exc_info:
            await get_workspace_settings("ws-1", _make_user(99), db)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_defaults_when_no_stored_settings(self):
        """When ws.settings is None, returns full defaults."""
        from app.api.v1.workspace import get_workspace_settings

        ws = _make_workspace(settings=None)
        db = _mock_db_queries(
            _membership_result(_make_membership()),
            _workspace_result(ws),
        )

        result = await get_workspace_settings("ws-1", _make_user(1), db)

        cb = result["circuit_breaker_defaults"]
        assert cb["max_llm_calls"] == 100
        assert cb["max_cost_usd"] == 10.0
        assert cb["max_duration_seconds"] == 3600
        assert cb["max_tool_calls"] == 200
        assert cb["destructive_actions_require_approval"] is True

        ap = result["approval_policies"]
        assert ap["require_approval_for_deployments"] is False
        assert ap["require_approval_for_destructive_actions"] is True
        assert ap["require_approval_above_cost_usd"] == 5.0
        assert ap["auto_approve_low_risk"] is True

    @pytest.mark.asyncio
    async def test_returns_defaults_when_empty_settings_dict(self):
        """When ws.settings is {}, returns full defaults."""
        from app.api.v1.workspace import get_workspace_settings

        ws = _make_workspace(settings={})
        db = _mock_db_queries(
            _membership_result(_make_membership()),
            _workspace_result(ws),
        )

        result = await get_workspace_settings("ws-1", _make_user(1), db)

        assert result["circuit_breaker_defaults"]["max_llm_calls"] == 100
        assert result["approval_policies"]["auto_approve_low_risk"] is True

    @pytest.mark.asyncio
    async def test_merges_stored_settings_with_defaults(self):
        """Stored values take precedence; missing keys fall back to defaults."""
        from app.api.v1.workspace import get_workspace_settings

        stored = {
            "circuit_breaker_defaults": {
                "max_llm_calls": 50,  # overridden
                "max_cost_usd": 25.0,  # overridden
                # max_duration_seconds, max_tool_calls, destructive... from defaults
            },
            # approval_policies entirely from defaults
        }
        ws = _make_workspace(settings=stored)
        db = _mock_db_queries(
            _membership_result(_make_membership()),
            _workspace_result(ws),
        )

        result = await get_workspace_settings("ws-1", _make_user(1), db)

        cb = result["circuit_breaker_defaults"]
        assert cb["max_llm_calls"] == 50  # stored
        assert cb["max_cost_usd"] == 25.0  # stored
        assert cb["max_duration_seconds"] == 3600  # default
        assert cb["max_tool_calls"] == 200  # default

        ap = result["approval_policies"]
        assert ap["require_approval_for_deployments"] is False  # default
        assert ap["auto_approve_low_risk"] is True  # default

    @pytest.mark.asyncio
    async def test_stored_approval_policies_override_defaults(self):
        """Stored approval policies override defaults."""
        from app.api.v1.workspace import get_workspace_settings

        stored = {
            "approval_policies": {
                "require_approval_for_deployments": True,
                "auto_approve_low_risk": False,
            },
        }
        ws = _make_workspace(settings=stored)
        db = _mock_db_queries(
            _membership_result(_make_membership()),
            _workspace_result(ws),
        )

        result = await get_workspace_settings("ws-1", _make_user(1), db)

        ap = result["approval_policies"]
        assert ap["require_approval_for_deployments"] is True  # stored
        assert ap["auto_approve_low_risk"] is False  # stored
        assert ap["require_approval_above_cost_usd"] == 5.0  # default

    @pytest.mark.asyncio
    async def test_workspace_not_found_after_membership(self):
        """If workspace is None after membership check, raises 404."""
        from app.api.v1.workspace import get_workspace_settings

        db = _mock_db_queries(
            _membership_result(_make_membership()),
            _workspace_result(None),
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_workspace_settings("ws-deleted", _make_user(1), db)

        assert exc_info.value.status_code == 404
        assert "Workspace not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_response_has_both_sections(self):
        """Response always contains both circuit_breaker_defaults and approval_policies."""
        from app.api.v1.workspace import get_workspace_settings

        ws = _make_workspace(settings=None)
        db = _mock_db_queries(
            _membership_result(_make_membership()),
            _workspace_result(ws),
        )

        result = await get_workspace_settings("ws-1", _make_user(1), db)

        assert "circuit_breaker_defaults" in result
        assert "approval_policies" in result
        assert isinstance(result["circuit_breaker_defaults"], dict)
        assert isinstance(result["approval_policies"], dict)


# ── PATCH Settings Tests ─────────────────────────────────────────────


class TestUpdateWorkspaceSettings:
    @pytest.mark.asyncio
    async def test_non_member_gets_404(self):
        """Non-member should get 404 from _verify_membership."""
        from app.api.v1.workspace import (
            WorkspaceSettingsUpdate,
            update_workspace_settings,
        )

        db = _mock_db_queries(_membership_result(None))
        payload = WorkspaceSettingsUpdate()

        with pytest.raises(HTTPException) as exc_info:
            await update_workspace_settings("ws-1", payload, _make_user(99), db)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_member_gets_403(self):
        """Regular member (not owner/admin) should get 403."""
        from app.api.v1.workspace import (
            WorkspaceSettingsUpdate,
            update_workspace_settings,
        )

        db = _mock_db_queries(_membership_result(_make_membership("member")))
        payload = WorkspaceSettingsUpdate()

        with pytest.raises(HTTPException) as exc_info:
            await update_workspace_settings("ws-1", payload, _make_user(1), db)

        assert exc_info.value.status_code == 403
        assert "owners and admins" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_guest_gets_403(self):
        """Guest should get 403."""
        from app.api.v1.workspace import (
            WorkspaceSettingsUpdate,
            update_workspace_settings,
        )

        db = _mock_db_queries(_membership_result(_make_membership("guest")))
        payload = WorkspaceSettingsUpdate()

        with pytest.raises(HTTPException) as exc_info:
            await update_workspace_settings("ws-1", payload, _make_user(1), db)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_owner_can_update(self):
        """Owner can update workspace settings."""
        from app.api.v1.workspace import (
            CircuitBreakerDefaults,
            WorkspaceSettingsUpdate,
            update_workspace_settings,
        )

        ws = _make_workspace(settings=None)
        db = _mock_db_queries(
            _membership_result(_make_membership("owner")),
            _workspace_result(ws),
        )

        payload = WorkspaceSettingsUpdate(
            circuit_breaker_defaults=CircuitBreakerDefaults(
                max_llm_calls=200,
                max_cost_usd=50.0,
            ),
        )

        result = await update_workspace_settings("ws-1", payload, _make_user(1), db)

        assert result["circuit_breaker_defaults"]["max_llm_calls"] == 200
        assert result["circuit_breaker_defaults"]["max_cost_usd"] == 50.0
        # Non-overwritten fields keep defaults
        assert result["circuit_breaker_defaults"]["max_duration_seconds"] == 3600

    @pytest.mark.asyncio
    async def test_admin_can_update(self):
        """Admin can update workspace settings."""
        from app.api.v1.workspace import (
            ApprovalPolicy,
            WorkspaceSettingsUpdate,
            update_workspace_settings,
        )

        ws = _make_workspace(settings=None)
        db = _mock_db_queries(
            _membership_result(_make_membership("admin")),
            _workspace_result(ws),
        )

        payload = WorkspaceSettingsUpdate(
            approval_policies=ApprovalPolicy(
                require_approval_for_deployments=True,
            ),
        )

        result = await update_workspace_settings("ws-1", payload, _make_user(2), db)

        assert result["approval_policies"]["require_approval_for_deployments"] is True

    @pytest.mark.asyncio
    async def test_partial_update_only_cb(self):
        """Updating only circuit_breaker_defaults leaves approval_policies untouched."""
        from app.api.v1.workspace import (
            CircuitBreakerDefaults,
            WorkspaceSettingsUpdate,
            update_workspace_settings,
        )

        existing_settings = {
            "approval_policies": {
                "require_approval_for_deployments": True,
                "auto_approve_low_risk": False,
            },
        }
        ws = _make_workspace(settings=existing_settings)
        db = _mock_db_queries(
            _membership_result(_make_membership("owner")),
            _workspace_result(ws),
        )

        payload = WorkspaceSettingsUpdate(
            circuit_breaker_defaults=CircuitBreakerDefaults(max_llm_calls=50),
        )

        result = await update_workspace_settings("ws-1", payload, _make_user(1), db)

        # CB updated
        assert result["circuit_breaker_defaults"]["max_llm_calls"] == 50
        # Approval policies preserved from existing settings
        assert result["approval_policies"]["require_approval_for_deployments"] is True
        assert result["approval_policies"]["auto_approve_low_risk"] is False

    @pytest.mark.asyncio
    async def test_partial_update_only_approval(self):
        """Updating only approval_policies leaves circuit_breaker_defaults untouched."""
        from app.api.v1.workspace import (
            ApprovalPolicy,
            WorkspaceSettingsUpdate,
            update_workspace_settings,
        )

        existing_settings = {
            "circuit_breaker_defaults": {
                "max_llm_calls": 75,
                "max_cost_usd": 20.0,
            },
        }
        ws = _make_workspace(settings=existing_settings)
        db = _mock_db_queries(
            _membership_result(_make_membership("owner")),
            _workspace_result(ws),
        )

        payload = WorkspaceSettingsUpdate(
            approval_policies=ApprovalPolicy(auto_approve_low_risk=False),
        )

        result = await update_workspace_settings("ws-1", payload, _make_user(1), db)

        # CB preserved from existing
        assert result["circuit_breaker_defaults"]["max_llm_calls"] == 75
        assert result["circuit_breaker_defaults"]["max_cost_usd"] == 20.0
        # Approval updated
        assert result["approval_policies"]["auto_approve_low_risk"] is False
        # Non-overwritten approval fields use defaults
        assert result["approval_policies"]["require_approval_for_deployments"] is False

    @pytest.mark.asyncio
    async def test_update_merges_with_existing_settings(self):
        """PATCH merges new values into existing stored settings."""
        from app.api.v1.workspace import (
            ApprovalPolicy,
            CircuitBreakerDefaults,
            WorkspaceSettingsUpdate,
            update_workspace_settings,
        )

        existing_settings = {
            "circuit_breaker_defaults": {
                "max_llm_calls": 75,
                "max_cost_usd": 20.0,
            },
            "approval_policies": {
                "require_approval_for_deployments": True,
            },
        }
        ws = _make_workspace(settings=existing_settings)
        db = _mock_db_queries(
            _membership_result(_make_membership("owner")),
            _workspace_result(ws),
        )

        payload = WorkspaceSettingsUpdate(
            circuit_breaker_defaults=CircuitBreakerDefaults(max_llm_calls=300),
            approval_policies=ApprovalPolicy(auto_approve_low_risk=False),
        )

        result = await update_workspace_settings("ws-1", payload, _make_user(1), db)

        # CB: max_llm_calls updated, rest from defaults (new full object replaces old)
        assert result["circuit_breaker_defaults"]["max_llm_calls"] == 300
        assert result["circuit_breaker_defaults"]["max_cost_usd"] == 10.0  # from defaults
        # Approval: auto_approve_low_risk updated, rest from defaults
        assert result["approval_policies"]["auto_approve_low_risk"] is False
        assert result["approval_policies"]["require_approval_for_deployments"] is False  # default

    @pytest.mark.asyncio
    async def test_workspace_not_found_after_membership(self):
        """If workspace is None after membership check, raises 404."""
        from app.api.v1.workspace import (
            WorkspaceSettingsUpdate,
            update_workspace_settings,
        )

        db = _mock_db_queries(
            _membership_result(_make_membership("owner")),
            _workspace_result(None),
        )

        payload = WorkspaceSettingsUpdate()

        with pytest.raises(HTTPException) as exc_info:
            await update_workspace_settings("ws-deleted", payload, _make_user(1), db)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_ws_settings_attribute_is_updated(self):
        """The workspace.settings attribute should be set on the model."""
        from app.api.v1.workspace import (
            CircuitBreakerDefaults,
            WorkspaceSettingsUpdate,
            update_workspace_settings,
        )

        ws = _make_workspace(settings=None)
        db = _mock_db_queries(
            _membership_result(_make_membership("owner")),
            _workspace_result(ws),
        )

        payload = WorkspaceSettingsUpdate(
            circuit_breaker_defaults=CircuitBreakerDefaults(max_llm_calls=999),
        )

        await update_workspace_settings("ws-1", payload, _make_user(1), db)

        # The workspace object should have settings set
        assert ws.settings is not None
        assert ws.settings["circuit_breaker_defaults"]["max_llm_calls"] == 999

    @pytest.mark.asyncio
    async def test_empty_payload_returns_defaults(self):
        """Empty payload (no CB, no approval) returns full defaults unchanged."""
        from app.api.v1.workspace import (
            WorkspaceSettingsUpdate,
            update_workspace_settings,
        )

        ws = _make_workspace(settings=None)
        db = _mock_db_queries(
            _membership_result(_make_membership("owner")),
            _workspace_result(ws),
        )

        payload = WorkspaceSettingsUpdate()

        result = await update_workspace_settings("ws-1", payload, _make_user(1), db)

        # Empty payload means nothing to update, so result has defaults
        assert result["circuit_breaker_defaults"]["max_llm_calls"] == 100
        assert result["approval_policies"]["auto_approve_low_risk"] is True

    @pytest.mark.asyncio
    async def test_commit_called_on_update(self):
        """db.commit() and db.refresh(ws) should be called after update."""
        from app.api.v1.workspace import (
            CircuitBreakerDefaults,
            WorkspaceSettingsUpdate,
            update_workspace_settings,
        )

        ws = _make_workspace(settings=None)
        db = _mock_db_queries(
            _membership_result(_make_membership("owner")),
            _workspace_result(ws),
        )

        payload = WorkspaceSettingsUpdate(
            circuit_breaker_defaults=CircuitBreakerDefaults(max_llm_calls=42),
        )

        await update_workspace_settings("ws-1", payload, _make_user(1), db)

        db.commit.assert_awaited_once()
        db.refresh.assert_awaited_once_with(ws)
