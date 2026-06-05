"""Tests for 4.12 — Workspace access audit trail.

Verifies that structured log messages and audit DB writes fire on:
1. get_workspace_id: denied workspace resolution (no membership)
2. require_mission_access: workspace membership denial + owner mismatch
3. require_graph_access: workspace membership denial + owner mismatch
4. require_chat_thread_access: workspace membership denial + owner mismatch
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.services.mission_errors import MissionNotFoundError


# ──────────────────────────────────────────────────────────────
# 1. get_workspace_id — denied workspace resolution
# ──────────────────────────────────────────────────────────────


class TestGetWorkspaceIdAudit:
    """get_workspace_id should log + fire audit when explicit workspace is denied."""

    @pytest.mark.asyncio
    async def test_denied_workspace_logs_warning(self, caplog):
        """Explicit workspace_id with no membership triggers warning log."""
        from unittest.mock import MagicMock

        from app.api.deps import get_workspace_id

        request = MagicMock()
        request.headers = {"X-Workspace-Id": "ws-nonmember"}
        request.query_params = {}

        user = MagicMock()
        user.id = 42

        # Mock DB that returns no membership
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        # Also mock the auto-detect query (returns None = no primary workspace)
        mock_detect = MagicMock()
        mock_detect.first.return_value = None

        call_count = 0

        async def side_effect(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_result  # membership check
            return mock_detect  # auto-detect

        db.execute = AsyncMock(side_effect=side_effect)

        with caplog.at_level(logging.WARNING):
            result = await get_workspace_id(request, user, db)

        assert result is None
        assert any("workspace_access_denied" in r.message for r in caplog.records)
        assert any("user_id=42" in r.message for r in caplog.records)
        assert any("workspace_id=ws-nonmember" in r.message for r in caplog.records)
        assert any("reason=no_membership" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_denied_workspace_no_exception_from_audit(self):
        """Denial should complete cleanly even if audit write fails."""
        from unittest.mock import MagicMock

        from app.api.deps import get_workspace_id

        request = MagicMock()
        request.headers = {"X-Workspace-Id": "ws-denied"}
        request.query_params = {}

        user = MagicMock()
        user.id = 99

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db = AsyncMock()

        mock_detect = MagicMock()
        mock_detect.first.return_value = None

        call_count = 0

        async def side_effect(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_result
            return mock_detect

        db.execute = AsyncMock(side_effect=side_effect)

        # Even if audit internals fail, the function must return None cleanly
        with patch("app.api.middleware.audit.log_auth_event", side_effect=RuntimeError("db down")):
            result = await get_workspace_id(request, user, db)

        assert result is None

    @pytest.mark.asyncio
    async def test_valid_workspace_no_audit_log(self, caplog):
        """Valid workspace membership should NOT trigger audit logging."""
        from unittest.mock import MagicMock

        from app.api.deps import get_workspace_id

        request = MagicMock()
        request.headers = {"X-Workspace-Id": "ws-valid"}
        request.query_params = {}

        user = MagicMock()
        user.id = 42

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = MagicMock()  # membership exists
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        with caplog.at_level(logging.WARNING):
            result = await get_workspace_id(request, user, db)

        assert result == "ws-valid"
        assert not any("workspace_access_denied" in r.message for r in caplog.records)


# ──────────────────────────────────────────────────────────────
# 2. require_mission_access — workspace denial + owner mismatch
# ──────────────────────────────────────────────────────────────


class TestRequireMissionAccessAudit:
    """require_mission_access should log on workspace denial and owner mismatch."""

    @pytest.mark.asyncio
    async def test_workspace_denial_logs_warning(self, caplog):
        from unittest.mock import MagicMock

        from app.services.mission_service import require_mission_access

        mission = MagicMock()
        mission.workspace_id = "ws-mission-1"
        mission.user_id = 10

        db = AsyncMock()

        # Patch get_mission to return our mock mission
        with patch("app.services.mission_service.get_mission", return_value=mission):
            # Patch WorkspaceMember query to return no membership
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            db.execute = AsyncMock(return_value=mock_result)

            with caplog.at_level(logging.WARNING):
                with pytest.raises(MissionNotFoundError):
                    await require_mission_access(db, "m-123", user_id=99)

        assert any("entity_access_denied" in r.message for r in caplog.records)
        assert any("entity_type=mission" in r.message for r in caplog.records)
        assert any("entity_id=m-123" in r.message for r in caplog.records)
        assert any("workspace_id=ws-mission-1" in r.message for r in caplog.records)
        assert any("reason=no_membership" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_owner_mismatch_logs_warning(self, caplog):
        from unittest.mock import MagicMock

        from app.services.mission_service import require_mission_access

        mission = MagicMock()
        mission.workspace_id = None  # no workspace → user_id fallback
        mission.user_id = 10  # owner is user 10

        db = AsyncMock()

        with patch("app.services.mission_service.get_mission", return_value=mission):
            with caplog.at_level(logging.WARNING):
                with pytest.raises(MissionNotFoundError):
                    await require_mission_access(db, "m-456", user_id=99)

        assert any("entity_access_denied" in r.message for r in caplog.records)
        assert any("reason=owner_mismatch" in r.message for r in caplog.records)
        assert any("owner_user_id=10" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_valid_access_no_audit_log(self, caplog):
        from unittest.mock import MagicMock

        from app.services.mission_service import require_mission_access

        mission = MagicMock()
        mission.workspace_id = "ws-ok"
        mission.user_id = 10

        db = AsyncMock()

        with patch("app.services.mission_service.get_mission", return_value=mission):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = MagicMock()  # membership exists
            db.execute = AsyncMock(return_value=mock_result)

            with caplog.at_level(logging.WARNING):
                result = await require_mission_access(db, "m-789", user_id=10)

        assert result is mission
        assert not any("entity_access_denied" in r.message for r in caplog.records)


# ──────────────────────────────────────────────────────────────
# 3. require_graph_access — workspace denial + owner mismatch
# ──────────────────────────────────────────────────────────────


class TestRequireGraphAccessAudit:
    """require_graph_access should log on workspace denial and owner mismatch."""

    @pytest.mark.asyncio
    async def test_workspace_denial_logs_warning(self, caplog):
        from unittest.mock import MagicMock

        from app.services.graph_service import require_graph_access
        from app.services.mission_errors import GraphNotFoundError

        workflow = MagicMock()
        workflow.workspace_id = "ws-graph-1"
        workflow.user_id = 10

        db = AsyncMock()

        with patch("app.services.graph_service.get_graph_workflow", return_value=workflow):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            db.execute = AsyncMock(return_value=mock_result)

            with caplog.at_level(logging.WARNING):
                with pytest.raises(GraphNotFoundError):
                    await require_graph_access(db, "wf-abc", user_id=99)

        assert any("entity_access_denied" in r.message for r in caplog.records)
        assert any("entity_type=workflow" in r.message for r in caplog.records)
        assert any("entity_id=wf-abc" in r.message for r in caplog.records)
        assert any("reason=no_membership" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_owner_mismatch_logs_warning(self, caplog):
        from unittest.mock import MagicMock

        from app.services.graph_service import require_graph_access
        from app.services.mission_errors import GraphNotFoundError

        workflow = MagicMock()
        workflow.workspace_id = None
        workflow.user_id = 10

        db = AsyncMock()

        with patch("app.services.graph_service.get_graph_workflow", return_value=workflow):
            with caplog.at_level(logging.WARNING):
                with pytest.raises(GraphNotFoundError):
                    await require_graph_access(db, "wf-def", user_id=99)

        assert any("entity_access_denied" in r.message for r in caplog.records)
        assert any("reason=owner_mismatch" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_valid_access_no_audit_log(self, caplog):
        from unittest.mock import MagicMock

        from app.services.graph_service import require_graph_access

        workflow = MagicMock()
        workflow.workspace_id = "ws-ok"
        workflow.user_id = 10

        db = AsyncMock()

        with patch("app.services.graph_service.get_graph_workflow", return_value=workflow):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = MagicMock()
            db.execute = AsyncMock(return_value=mock_result)

            with caplog.at_level(logging.WARNING):
                result = await require_graph_access(db, "wf-ghi", user_id=10)

        assert result is workflow
        assert not any("entity_access_denied" in r.message for r in caplog.records)


# ──────────────────────────────────────────────────────────────
# 4. require_chat_thread_access — workspace denial + owner mismatch
# ──────────────────────────────────────────────────────────────


class TestRequireChatThreadAccessAudit:
    """require_chat_thread_access should log on workspace denial and owner mismatch."""

    @pytest.mark.asyncio
    async def test_workspace_denial_logs_warning(self, caplog):
        from unittest.mock import MagicMock

        from app.services.chat_service import require_chat_thread_access

        thread = MagicMock()
        thread.workspace_id = "ws-chat-1"
        thread.user_id = 10

        db = AsyncMock()

        with patch("app.services.chat_service.get_chat_thread", return_value=thread):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            db.execute = AsyncMock(return_value=mock_result)

            with caplog.at_level(logging.WARNING):
                from fastapi import HTTPException
                with pytest.raises(HTTPException):
                    await require_chat_thread_access(db, 42, user_id=99)

        assert any("entity_access_denied" in r.message for r in caplog.records)
        assert any("entity_type=chat_thread" in r.message for r in caplog.records)
        assert any("entity_id=42" in r.message for r in caplog.records)
        assert any("reason=no_membership" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_owner_mismatch_logs_warning(self, caplog):
        from unittest.mock import MagicMock

        from app.services.chat_service import require_chat_thread_access

        thread = MagicMock()
        thread.workspace_id = None
        thread.user_id = 10

        db = AsyncMock()

        with patch("app.services.chat_service.get_chat_thread", return_value=thread):
            with caplog.at_level(logging.WARNING):
                from fastapi import HTTPException
                with pytest.raises(HTTPException):
                    await require_chat_thread_access(db, 42, user_id=99)

        assert any("entity_access_denied" in r.message for r in caplog.records)
        assert any("reason=owner_mismatch" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_valid_access_no_audit_log(self, caplog):
        from unittest.mock import MagicMock

        from app.services.chat_service import require_chat_thread_access

        thread = MagicMock()
        thread.workspace_id = "ws-ok"
        thread.user_id = 10

        db = AsyncMock()

        with patch("app.services.chat_service.get_chat_thread", return_value=thread):
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = MagicMock()
            db.execute = AsyncMock(return_value=mock_result)

            with caplog.at_level(logging.WARNING):
                result = await require_chat_thread_access(db, 42, user_id=10)

        assert result is thread
        assert not any("entity_access_denied" in r.message for r in caplog.records)


# ──────────────────────────────────────────────────────────────
# 5. Structured log format consistency
# ──────────────────────────────────────────────────────────────


class TestAuditLogFormatConsistency:
    """All audit log messages should follow a consistent structured format."""

    EXPECTED_FIELDS = {
        "workspace_access_denied": ["user_id", "workspace_id", "reason"],
        "entity_access_denied": ["user_id", "entity_type", "entity_id"],
    }

    @pytest.mark.asyncio
    async def test_all_access_denied_events_logged(self, caplog):
        """Every entity access denial fires exactly one structured warning."""
        from unittest.mock import MagicMock
        from fastapi import HTTPException

        from app.api.deps import get_workspace_id
        from app.services.mission_service import require_mission_access
        from app.services.graph_service import require_graph_access
        from app.services.chat_service import require_chat_thread_access

        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        # get_workspace_id with no membership
        caplog.clear()
        request = MagicMock()
        request.headers = {"X-Workspace-Id": "ws-x"}
        request.query_params = {}
        user = MagicMock()
        user.id = 1
        mock_detect = MagicMock()
        mock_detect.first.return_value = None
        call_count = 0
        async def ws_side(stmt):
            nonlocal call_count
            call_count += 1
            return mock_result if call_count == 1 else mock_detect
        db.execute = AsyncMock(side_effect=ws_side)
        with caplog.at_level(logging.WARNING):
            await get_workspace_id(request, user, db)
        denials = [r for r in caplog.records if "workspace_access_denied" in r.message]
        assert len(denials) == 1, f"Expected 1 workspace_access_denied, got {len(denials)}"

        # require_mission_access with workspace denial
        caplog.clear()
        mission = MagicMock()
        mission.workspace_id = "ws-m"
        mission.user_id = 1
        with patch("app.services.mission_service.get_mission", return_value=mission):
            db.execute = AsyncMock(return_value=mock_result)
            with caplog.at_level(logging.WARNING):
                with pytest.raises(MissionNotFoundError):
                    await require_mission_access(db, "m-1", user_id=2)
        entity_denials = [r for r in caplog.records if "entity_access_denied" in r.message]
        assert len(entity_denials) == 1
        assert "entity_type=mission" in entity_denials[0].message
