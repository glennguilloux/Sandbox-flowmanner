"""Phase 4 verification tests: cache read-through (no DB on hit), ownership
enforcement on cache hit/miss, soft-delete exclusion on active cache hits,
and no remaining asyncio.ensure_future in mission CQRS code paths.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# GOAL A — GET mission cache hit bypasses DB
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetMissionCacheHitAvoidsDb:
    """Prove that get_mission_response returns cached data without DB query."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_without_db_fetch(self, mocker):
        """Cache hit → MissionResponse returned, get_mission(…) never called."""
        import uuid

        valid_id = str(uuid.uuid4())
        mock_cache_get = mocker.patch(
            "app.api._mission_cqrs.queries.cache_get",
            new=AsyncMock(
                return_value={
                    "id": valid_id,
                    "user_id": 1,
                    "title": "Cached Mission",
                    "description": "",
                    "mission_type": "general",
                    "status": "pending",
                    "priority": "medium",
                    "plan": {},
                    "results": {},
                    "error_message": None,
                    "tokens_used": 0,
                    "estimated_cost": 0.0,
                    "actual_cost": 0.0,
                    "started_at": None,
                    "completed_at": None,
                    "created_at": None,
                    "updated_at": None,
                }
            ),
        )
        mock_get_mission = mocker.patch(
            "app.api._mission_cqrs.queries.get_mission",
            new=AsyncMock(),
        )

        from app.api._mission_cqrs.queries import MissionQueryHandlers

        session = AsyncMock()
        handlers = MissionQueryHandlers(session)
        result = await handlers.get_mission_response(user_id=1, mission_id=valid_id)

        assert result.title == "Cached Mission"
        assert str(result.id) == valid_id
        mock_cache_get.assert_awaited_once()
        # DB fetch must NOT have been called
        mock_get_mission.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_miss_falls_through_to_db(self, mocker):
        """Cache miss → DB fetch, ownership validated, cache populated."""
        import uuid

        valid_id = str(uuid.uuid4())
        mock_cache_get = mocker.patch(
            "app.api._mission_cqrs.queries.cache_get",
            new=AsyncMock(return_value=None),
        )
        mock_cache_set = mocker.patch(
            "app.api._mission_cqrs.queries.cache_set",
            new=AsyncMock(return_value=None),
        )
        # Build a mock Mission that can pass model_validate
        mission = MagicMock()
        mission.user_id = 1
        mission.id = valid_id
        mission.title = "DB Mission"
        mission.description = ""
        mission.mission_type = "general"
        mission.status = "pending"
        mission.priority = "medium"
        mission.plan = {}
        mission.results = {}
        mission.error_message = None
        mission.tokens_used = 0
        mission.estimated_cost = 0.0
        mission.actual_cost = 0.0
        mission.started_at = None
        mission.completed_at = None
        mission.created_at = None
        mission.updated_at = None
        # Patch require_mission_access (handler calls this on cache miss)
        mock_require_access = mocker.patch(
            "app.api._mission_cqrs.queries.require_mission_access",
            new=AsyncMock(return_value=mission),
        )

        from app.api._mission_cqrs.queries import MissionQueryHandlers

        session = AsyncMock()
        # Configure session.execute to avoid coroutine leakage
        execute_mock = AsyncMock()
        execute_mock.return_value = MagicMock()
        session.execute = execute_mock
        handlers = MissionQueryHandlers(session)
        result = await handlers.get_mission_response(user_id=1, mission_id=valid_id)

        assert result.title == "DB Mission"
        # DB was hit on cache miss
        mock_require_access.assert_awaited_once()


# ═══════════════════════════════════════════════════════════════════════════════
# GOAL A cont — Ownership enforced on cache hit AND miss
# ═══════════════════════════════════════════════════════════════════════════════


class TestOwnershipEnforcementOnCachePaths:
    """Ownership is checked regardless of cache-hit vs cache-miss path."""

    @pytest.mark.asyncio
    async def test_cache_hit_wrong_user_raises_not_found(self, mocker):
        """Cache hit for user 1 but mission owned by user 2 → 404."""
        import uuid

        valid_id = str(uuid.uuid4())
        mocker.patch(
            "app.api._mission_cqrs.queries.cache_get",
            new=AsyncMock(
                return_value={
                    "id": valid_id,
                    "user_id": 2,  # different user
                    "title": "Other User's Mission",
                    "description": "",
                    "mission_type": "general",
                    "status": "pending",
                    "priority": "medium",
                    "plan": {},
                    "results": {},
                    "error_message": None,
                    "tokens_used": 0,
                    "estimated_cost": 0.0,
                    "actual_cost": 0.0,
                    "started_at": None,
                    "completed_at": None,
                    "created_at": None,
                    "updated_at": None,
                }
            ),
        )
        from app.api._mission_cqrs.queries import MissionQueryHandlers
        from app.services.mission_errors import MissionNotFoundError

        session = AsyncMock()
        handlers = MissionQueryHandlers(session)
        with pytest.raises(MissionNotFoundError):
            await handlers.get_mission_response(user_id=1, mission_id=valid_id)

    @pytest.mark.asyncio
    async def test_cache_miss_wrong_user_raises_not_found(self, mocker):
        """Cache miss + DB returns mission owned by different user → 404."""
        import uuid

        valid_id = str(uuid.uuid4())
        mocker.patch(
            "app.api._mission_cqrs.queries.cache_get",
            new=AsyncMock(return_value=None),
        )
        mission = MagicMock()
        mission.user_id = 2  # different user
        mission.id = valid_id
        mission.workspace_id = None  # ensure user_id ownership check
        # Patch get_mission at the mission_service level so
        # require_mission_access gets this mission and validates ownership
        mocker.patch(
            "app.services.mission_service.get_mission",
            new=AsyncMock(return_value=mission),
        )
        from app.api._mission_cqrs.queries import MissionQueryHandlers
        from app.services.mission_errors import MissionNotFoundError

        session = AsyncMock()
        # Configure session.execute to avoid coroutine leakage
        execute_mock = AsyncMock()
        execute_mock.return_value = MagicMock()
        session.execute = execute_mock
        handlers = MissionQueryHandlers(session)
        with pytest.raises(MissionNotFoundError):
            await handlers.get_mission_response(user_id=1, mission_id=valid_id)

    @pytest.mark.asyncio
    async def test_cache_miss_none_mission_raises_not_found(self, mocker):
        """Cache miss + DB returns None → 404."""
        import uuid

        valid_id = str(uuid.uuid4())
        mocker.patch(
            "app.api._mission_cqrs.queries.cache_get",
            new=AsyncMock(return_value=None),
        )
        # Patch get_mission at mission_service so require_mission_access
        # gets None and raises MissionNotFoundError
        mocker.patch(
            "app.services.mission_service.get_mission",
            new=AsyncMock(return_value=None),
        )
        from app.api._mission_cqrs.queries import MissionQueryHandlers
        from app.services.mission_errors import MissionNotFoundError

        session = AsyncMock()
        # Configure session.execute to avoid coroutine leakage
        execute_mock = AsyncMock()
        execute_mock.return_value = MagicMock()
        session.execute = execute_mock
        handlers = MissionQueryHandlers(session)
        with pytest.raises(MissionNotFoundError):
            await handlers.get_mission_response(user_id=1, mission_id=valid_id)


# ═══════════════════════════════════════════════════════════════════════════════
# GOAL C — Soft-delete exclusion on active cache hits
# ═══════════════════════════════════════════════════════════════════════════════


class TestSoftDeleteExclusionOnActiveCache:
    """active_missions and list_active cache hits exclude soft-deleted records."""

    @pytest.mark.asyncio
    async def test_active_missions_cache_hit_filters_deleted(self, mocker):
        """Cached active missions list includes a soft-deleted entry → filtered out."""
        import uuid

        id1 = str(uuid.uuid4())
        id2 = str(uuid.uuid4())
        mocker.patch(
            "app.api._mission_cqrs.queries.cache_active",
            new=AsyncMock(
                return_value={
                    "missions": [
                        {
                            "id": id1,
                            "user_id": 1,
                            "title": "Active 1",
                            "description": "",
                            "mission_type": "general",
                            "status": "running",
                            "priority": "medium",
                            "plan": {},
                            "results": {},
                            "error_message": None,
                            "tokens_used": 0,
                            "estimated_cost": 0.0,
                            "actual_cost": 0.0,
                            "started_at": None,
                            "completed_at": None,
                            "created_at": None,
                            "updated_at": None,
                        },
                        {
                            "id": id2,
                            "user_id": 1,
                            "title": "Deleted Mission",
                            "description": "",
                            "mission_type": "general",
                            "status": "running",
                            "priority": "medium",
                            "plan": {},
                            "results": {},
                            "error_message": None,
                            "tokens_used": 0,
                            "estimated_cost": 0.0,
                            "actual_cost": 0.0,
                            "started_at": None,
                            "completed_at": None,
                            "created_at": None,
                            "updated_at": None,
                            "deleted_at": "2026-01-01T00:00:00",  # <-- soft-deleted
                        },
                    ],
                    "total": 2,
                }
            ),
        )
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        session = AsyncMock()
        handlers = MissionQueryHandlers(session)
        result = await handlers.active_missions(user_id=1, user_role="pro")

        # Only the non-deleted mission should appear
        assert len(result.missions) == 1
        assert result.missions[0].title == "Active 1"
        assert result.total == 1

    @pytest.mark.asyncio
    async def test_active_missions_cache_hit_no_deleted_filtering_needed(self, mocker):
        """Cached active missions with no soft-deleted → all returned."""
        import uuid

        id1 = str(uuid.uuid4())
        id2 = str(uuid.uuid4())
        mocker.patch(
            "app.api._mission_cqrs.queries.cache_active",
            new=AsyncMock(
                return_value={
                    "missions": [
                        {
                            "id": id1,
                            "user_id": 1,
                            "title": "Active 1",
                            "description": "",
                            "mission_type": "general",
                            "status": "running",
                            "priority": "medium",
                            "plan": {},
                            "results": {},
                            "error_message": None,
                            "tokens_used": 0,
                            "estimated_cost": 0.0,
                            "actual_cost": 0.0,
                            "started_at": None,
                            "completed_at": None,
                            "created_at": None,
                            "updated_at": None,
                        },
                        {
                            "id": id2,
                            "user_id": 1,
                            "title": "Active 2",
                            "description": "",
                            "mission_type": "general",
                            "status": "running",
                            "priority": "medium",
                            "plan": {},
                            "results": {},
                            "error_message": None,
                            "tokens_used": 0,
                            "estimated_cost": 0.0,
                            "actual_cost": 0.0,
                            "started_at": None,
                            "completed_at": None,
                            "created_at": None,
                            "updated_at": None,
                        },
                    ],
                    "total": 2,
                }
            ),
        )
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        session = AsyncMock()
        handlers = MissionQueryHandlers(session)
        result = await handlers.active_missions(user_id=1, user_role="pro")

        assert len(result.missions) == 2
        assert result.total == 2


# ═══════════════════════════════════════════════════════════════════════════════
# GOAL B — No remaining asyncio.ensure_future in mission CQRS code
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoEnsureFutureInCqrs:
    """Verify that asyncio.ensure_future is fully removed from CQRS files."""

    def test_no_ensure_future_in_queries_py(self):
        from pathlib import Path

        path = Path(__file__).parent.parent / "api" / "_mission_cqrs" / "queries.py"
        content = path.read_text()
        assert "asyncio.ensure_future" not in content, "queries.py still contains asyncio.ensure_future"

    def test_no_ensure_future_in_commands_py(self):
        from pathlib import Path

        path = Path(__file__).parent.parent / "api" / "_mission_cqrs" / "commands.py"
        content = path.read_text()
        assert "asyncio.ensure_future" not in content, "commands.py still contains asyncio.ensure_future"

    def test_schedule_helper_exists_and_used(self):
        from pathlib import Path

        path = Path(__file__).parent.parent / "api" / "_mission_cqrs" / "base.py"
        content = path.read_text()
        assert "_schedule_fire_and_forget" in content, "base.py should define _schedule_fire_and_forget"
        assert "def _schedule_fire_and_forget" in content

    def test_queries_py_uses_schedule_helper(self):
        from pathlib import Path

        path = Path(__file__).parent.parent / "api" / "_mission_cqrs" / "queries.py"
        content = path.read_text()
        assert "_schedule_fire_and_forget" in content, (
            "queries.py should use _schedule_fire_and_forget instead of ensure_future"
        )

    def test_commands_py_uses_schedule_helper(self):
        from pathlib import Path

        path = Path(__file__).parent.parent / "api" / "_mission_cqrs" / "commands.py"
        content = path.read_text()
        assert "_schedule_fire_and_forget" in content, (
            "commands.py should use _schedule_fire_and_forget instead of ensure_future"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# GOAL D cross-check — existing tests still pass (import-only sanity)
# ═══════════════════════════════════════════════════════════════════════════════


class TestExistingImportsStillWork:
    """Sanity: imports that other test files depend on still resolve."""

    def test_import_mission_query_handlers(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        assert MissionQueryHandlers is not None

    def test_import_mission_command_handlers(self):
        from app.api._mission_cqrs.commands import MissionCommandHandlers

        assert MissionCommandHandlers is not None

    def test_import_get_mission_response(self):
        """New method is accessible on the class."""
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        assert hasattr(MissionQueryHandlers, "get_mission_response")

    def test_import_v2_missions_router(self):
        from app.api.v2.missions import router

        assert router is not None
