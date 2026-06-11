"""Tests for 4.11 — Cross-workspace permission grants.

Verifies:
1. CrossWorkspaceService: grant, revoke, check, list operations
2. Access check integration: require_mission_access, require_graph_access,
   require_chat_thread_access fall back to cross-workspace grants
3. Edge cases: self-share prevention, invalid entity types, permission levels
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

# ──────────────────────────────────────────────────────────────
# 1. CrossWorkspaceService — grant/revoke/check
# ──────────────────────────────────────────────────────────────


class TestCrossWorkspaceService:
    """Unit tests for the cross_workspace_service module."""

    @pytest.mark.asyncio
    async def test_grant_share_creates_new(self):
        from app.services.cross_workspace_service import grant_share

        db = AsyncMock()
        added = []
        db.add = lambda obj: added.append(obj)
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        # No existing share
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        share = await grant_share(
            db,
            source_workspace_id="ws-a",
            target_workspace_id="ws-b",
            entity_type="mission",
            entity_id="m-123",
            permission="read",
            granted_by=1,
        )

        assert len(added) == 1
        assert added[0].source_workspace_id == "ws-a"
        assert added[0].target_workspace_id == "ws-b"
        assert added[0].entity_type == "mission"
        assert added[0].entity_id == "m-123"
        assert added[0].permission == "read"

    @pytest.mark.asyncio
    async def test_grant_share_updates_existing(self):
        from app.services.cross_workspace_service import grant_share

        existing = MagicMock()
        existing.permission = "read"

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing
        db.execute = AsyncMock(return_value=mock_result)
        db.flush = AsyncMock()
        db.refresh = AsyncMock()

        share = await grant_share(
            db,
            source_workspace_id="ws-a",
            target_workspace_id="ws-b",
            entity_type="mission",
            entity_id="m-123",
            permission="write",
            granted_by=1,
        )

        assert existing.permission == "write"
        assert existing.is_active is True

    @pytest.mark.asyncio
    async def test_grant_share_rejects_self_share(self):
        from app.services.cross_workspace_service import (
            CrossWorkspaceError,
            grant_share,
        )

        db = AsyncMock()
        with pytest.raises(CrossWorkspaceError, match="Cannot share"):
            await grant_share(
                db,
                source_workspace_id="ws-a",
                target_workspace_id="ws-a",
                entity_type="mission",
                entity_id="m-1",
            )

    @pytest.mark.asyncio
    async def test_grant_share_rejects_invalid_entity_type(self):
        from app.services.cross_workspace_service import (
            CrossWorkspaceError,
            grant_share,
        )

        db = AsyncMock()
        with pytest.raises(CrossWorkspaceError, match="Invalid entity_type"):
            await grant_share(
                db,
                source_workspace_id="ws-a",
                target_workspace_id="ws-b",
                entity_type="invalid_type",
                entity_id="x",
            )

    @pytest.mark.asyncio
    async def test_grant_share_rejects_invalid_permission(self):
        from app.services.cross_workspace_service import (
            CrossWorkspaceError,
            grant_share,
        )

        db = AsyncMock()
        with pytest.raises(CrossWorkspaceError, match="Invalid permission"):
            await grant_share(
                db,
                source_workspace_id="ws-a",
                target_workspace_id="ws-b",
                entity_type="mission",
                entity_id="x",
                permission="admin",
            )

    @pytest.mark.asyncio
    async def test_revoke_share_deactivates(self):
        from app.services.cross_workspace_service import revoke_share

        share = MagicMock()
        share.is_active = True

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = share
        db.execute = AsyncMock(return_value=mock_result)
        db.flush = AsyncMock()

        result = await revoke_share(db, "share-1", revoked_by=1)
        assert result is True
        assert share.is_active is False

    @pytest.mark.asyncio
    async def test_revoke_share_not_found(self):
        from app.services.cross_workspace_service import (
            ShareNotFoundError,
            revoke_share,
        )

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ShareNotFoundError):
            await revoke_share(db, "nonexistent")

    @pytest.mark.asyncio
    async def test_check_entity_access_read_granted(self):
        from app.services.cross_workspace_service import check_entity_access

        share = MagicMock()
        share.permission = "read"

        member = MagicMock()

        db = AsyncMock()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(scalar_one_or_none=MagicMock(return_value=member))
            return MagicMock(scalar_one_or_none=MagicMock(return_value=share))

        db.execute = AsyncMock(side_effect=mock_execute)

        result = await check_entity_access(
            db,
            user_id=1,
            target_workspace_id="ws-b",
            entity_type="mission",
            entity_id="m-1",
            required_permission="read",
        )
        assert result is share

    @pytest.mark.asyncio
    async def test_check_entity_access_write_denied_for_read_share(self):
        from app.services.cross_workspace_service import check_entity_access

        share = MagicMock()
        share.permission = "read"

        member = MagicMock()

        db = AsyncMock()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(scalar_one_or_none=MagicMock(return_value=member))
            return MagicMock(scalar_one_or_none=MagicMock(return_value=share))

        db.execute = AsyncMock(side_effect=mock_execute)

        result = await check_entity_access(
            db,
            user_id=1,
            target_workspace_id="ws-b",
            entity_type="mission",
            entity_id="m-1",
            required_permission="write",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_check_entity_access_no_membership(self):
        from app.services.cross_workspace_service import check_entity_access

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await check_entity_access(
            db,
            user_id=1,
            target_workspace_id="ws-b",
            entity_type="mission",
            entity_id="m-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_check_entity_access_no_share(self):
        from app.services.cross_workspace_service import check_entity_access

        member = MagicMock()

        db = AsyncMock()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(scalar_one_or_none=MagicMock(return_value=member))
            return MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        db.execute = AsyncMock(side_effect=mock_execute)

        result = await check_entity_access(
            db,
            user_id=1,
            target_workspace_id="ws-b",
            entity_type="mission",
            entity_id="m-1",
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_find_user_workspaces(self):
        from app.services.cross_workspace_service import find_user_workspaces

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.all.return_value = [("ws-1",), ("ws-2",)]
        db.execute = AsyncMock(return_value=mock_result)

        result = await find_user_workspaces(db, user_id=1)
        assert result == ["ws-1", "ws-2"]


# ──────────────────────────────────────────────────────────────
# 2. Access check integration — cross-workspace fallback
# ──────────────────────────────────────────────────────────────


class TestAccessCheckCrossWorkspaceIntegration:
    """Verify that require_*_access falls back to cross-workspace grants."""

    @pytest.mark.asyncio
    async def test_mission_access_cross_workspace_granted(self, caplog):
        from app.services.mission_service import require_mission_access

        mission = MagicMock()
        mission.workspace_id = "ws-owner"
        mission.user_id = 10

        db = AsyncMock()

        with patch("app.services.mission_service.get_mission", return_value=mission):
            # First call: workspace membership check → no membership
            # Then cross-workspace check → finds grant
            call_count = 0

            async def mock_execute(stmt):
                nonlocal call_count
                call_count += 1
                stmt_str = str(stmt)
                # WorkspaceMember check for the mission's workspace → no membership
                if call_count == 1:
                    return MagicMock(scalar_one_or_none=MagicMock(return_value=None))
                # find_user_workspaces → user is in ws-other
                if "workspace_members" in stmt_str and call_count == 2:
                    mock_r = MagicMock()
                    mock_r.all.return_value = [("ws-other",)]
                    return mock_r
                # check_entity_access: member check in ws-other → member exists
                if call_count == 3:
                    return MagicMock(scalar_one_or_none=MagicMock(return_value=MagicMock()))
                # check_entity_access: share lookup → found
                if call_count == 4:
                    grant = MagicMock()
                    grant.permission = "read"
                    return MagicMock(scalar_one_or_none=MagicMock(return_value=grant))
                return MagicMock(scalar_one_or_none=MagicMock(return_value=None))

            db.execute = AsyncMock(side_effect=mock_execute)

            with caplog.at_level(logging.WARNING):
                result = await require_mission_access(db, "m-1", user_id=99)

            assert result is mission
            assert not any("entity_access_denied" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_mission_access_cross_workspace_denied(self, caplog):
        from app.services.mission_errors import MissionNotFoundError
        from app.services.mission_service import require_mission_access

        mission = MagicMock()
        mission.workspace_id = "ws-owner"
        mission.user_id = 10

        db = AsyncMock()

        with patch("app.services.mission_service.get_mission", return_value=mission):
            call_count = 0

            async def mock_execute(stmt):
                nonlocal call_count
                call_count += 1
                # All membership checks fail, all cross-workspace checks fail
                return MagicMock(scalar_one_or_none=MagicMock(return_value=None))

            db.execute = AsyncMock(side_effect=mock_execute)

            with caplog.at_level(logging.WARNING), pytest.raises(MissionNotFoundError):
                await require_mission_access(db, "m-1", user_id=99)

            assert any("entity_access_denied" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_graph_access_cross_workspace_granted(self):
        from app.services.graph_service import require_graph_access

        workflow = MagicMock()
        workflow.workspace_id = "ws-owner"
        workflow.user_id = 10

        db = AsyncMock()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(scalar_one_or_none=MagicMock(return_value=None))
            if call_count == 2:
                mock_r = MagicMock()
                mock_r.all.return_value = [("ws-other",)]
                return mock_r
            if call_count == 3:
                return MagicMock(scalar_one_or_none=MagicMock(return_value=MagicMock()))
            if call_count == 4:
                grant = MagicMock()
                grant.permission = "read"
                return MagicMock(scalar_one_or_none=MagicMock(return_value=grant))
            return MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        db.execute = AsyncMock(side_effect=mock_execute)

        with patch("app.services.graph_service.get_graph_workflow", return_value=workflow):
            result = await require_graph_access(db, "wf-1", user_id=99)
            assert result is workflow

    @pytest.mark.asyncio
    async def test_chat_access_cross_workspace_granted(self):
        from app.services.chat_service import require_chat_thread_access

        thread = MagicMock()
        thread.workspace_id = "ws-owner"
        thread.user_id = 10

        db = AsyncMock()
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(scalar_one_or_none=MagicMock(return_value=None))
            if call_count == 2:
                mock_r = MagicMock()
                mock_r.all.return_value = [("ws-other",)]
                return mock_r
            if call_count == 3:
                return MagicMock(scalar_one_or_none=MagicMock(return_value=MagicMock()))
            if call_count == 4:
                grant = MagicMock()
                grant.permission = "read"
                return MagicMock(scalar_one_or_none=MagicMock(return_value=grant))
            return MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        db.execute = AsyncMock(side_effect=mock_execute)

        with patch("app.services.chat_service.get_chat_thread", return_value=thread):
            result = await require_chat_thread_access(db, 42, user_id=99)
            assert result is thread


# ──────────────────────────────────────────────────────────────
# 3. API schemas
# ──────────────────────────────────────────────────────────────


class TestWorkspaceShareAPI:
    """Verify API endpoint schemas and validation."""

    def test_share_create_request_validation(self):
        from app.api.v1.workspace_shares import ShareCreateRequest

        req = ShareCreateRequest(
            target_workspace_id="ws-b",
            entity_type="mission",
            entity_id="m-1",
            permission="read",
        )
        assert req.target_workspace_id == "ws-b"
        assert req.permission == "read"

    def test_share_create_request_default_permission(self):
        from app.api.v1.workspace_shares import ShareCreateRequest

        req = ShareCreateRequest(
            target_workspace_id="ws-b",
            entity_type="workflow",
            entity_id="wf-1",
        )
        assert req.permission == "read"

    def test_share_response_from_attributes(self):
        from app.api.v1.workspace_shares import ShareResponse

        resp = ShareResponse(
            id="share-1",
            source_workspace_id="ws-a",
            target_workspace_id="ws-b",
            entity_type="mission",
            entity_id="m-1",
            permission="read",
            granted_by=1,
            is_active=True,
        )
        assert resp.id == "share-1"
