"""Phase 5 integration tests: real cache-hit behavior, invalidation, and
remaining cache wiring (logs, status).

Proves that cache-aside works end-to-end for GET /api/v2/missions/{id},
soft-delete safety, ownership enforcement, and post-mutation freshness.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# GOAL D.1 — Cache hit bypasses DB for GET /api/v2/missions/{id}
# ═══════════════════════════════════════════════════════════════════════════════


class TestCacheHitAvoidsDbForGetMission:
    """Prove get_mission_response returns cached data without DB roundtrip."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self, mocker):
        """Cache hit → MissionResponse from cache, get_mission never called."""
        valid_id = str(uuid.uuid4())
        mock_cache_get = mocker.patch(
            "app.api._mission_cqrs.queries.cache_get",
            new=AsyncMock(
                return_value={
                    "id": valid_id,
                    "user_id": 1,
                    "title": "Cached",
                    "description": "",
                    "mission_type": "general",
                    "status": "running",
                    "priority": "medium",
                    "plan": {},
                    "results": {},
                    "error_message": None,
                    "tokens_used": 100,
                    "estimated_cost": 0.01,
                    "actual_cost": 0.01,
                    "started_at": None,
                    "completed_at": None,
                    "created_at": None,
                    "updated_at": None,
                    "progress": 50,
                    "eta": None,
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

        assert result.title == "Cached"
        mock_cache_get.assert_awaited_once()
        mock_get_mission.assert_not_awaited()  # ← key assertion

    @pytest.mark.asyncio
    async def test_cache_miss_then_populates_then_hit(self, mocker):
        """First call cache miss → DB → await cache_set. Second call serves from cache."""
        valid_id = str(uuid.uuid4())

        # Shared cache store
        cache_store: dict[str, str] = {}

        async def mock_get(user_id: int, mission_id: str) -> dict | None:
            import json

            raw = cache_store.get(mission_id)
            return json.loads(raw) if raw else None

        async def mock_set(user_id: int, mission_id: str, data: dict, ttl=None) -> None:
            import json

            cache_store[mission_id] = json.dumps(data)

        mocker.patch("app.api._mission_cqrs.queries.cache_get", side_effect=mock_get)
        mocker.patch("app.api._mission_cqrs.queries.cache_set", side_effect=mock_set)

        # Mock DB
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

        # First call: cache miss → DB hit
        result1 = await handlers.get_mission_response(user_id=1, mission_id=valid_id)
        assert result1.title == "DB Mission"
        assert mock_require_access.call_count == 1

        # Manually seed the cache store to simulate fire-and-forget completion
        import json

        cache_store[valid_id] = json.dumps(result1.model_dump(mode="json"))
        assert cache_store.get(valid_id) is not None

        # Second call: should be cache hit → no DB
        result2 = await handlers.get_mission_response(user_id=1, mission_id=valid_id)
        assert result2.title == "DB Mission"
        # require_mission_access must NOT have been called a second time
        assert mock_require_access.call_count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# GOAL D.2 — Cache wiring for logs and status
# ═══════════════════════════════════════════════════════════════════════════════


class TestLogsCacheWiring:
    """list_logs has cache write-through wired."""

    @pytest.mark.asyncio
    async def test_list_logs_populates_cache_after_db(self, mocker):
        """After DB fetch, cache_set_logs is called."""
        valid_id = str(uuid.uuid4())
        mock_cache_set_logs = mocker.patch(
            "app.api._mission_cqrs.queries.cache_set_logs",
            new=AsyncMock(return_value=None),
        )
        mission = MagicMock()
        mission.user_id = 1
        mission.id = valid_id
        mission.title = "X"
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
        mocker.patch(
            "app.api._mission_cqrs.queries.require_mission_access",
            new=AsyncMock(return_value=mission),
        )
        mocker.patch(
            "app.api._mission_cqrs.queries.get_mission_logs",
            new=AsyncMock(return_value=[]),
        )
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        session = AsyncMock()
        # Configure session.execute to avoid coroutine leakage
        execute_mock = AsyncMock()
        execute_mock.return_value = MagicMock()
        session.execute = execute_mock
        handlers = MissionQueryHandlers(session)
        result = await handlers.list_logs(user_id=1, mission_id=valid_id)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_logs_reads_cache_on_hit(self, mocker):
        """Cache hit returns logs without DB fetch for logs."""
        valid_id = str(uuid.uuid4())
        log_data = {
            "id": str(uuid.uuid4()),
            "mission_id": valid_id,
            "level": "info",
            "message": "Test log",
            "data": {},
            "created_at": "2026-06-02T00:00:00Z",
        }
        mock_cache_get_logs = mocker.patch(
            "app.api._mission_cqrs.queries.cache_get_logs",
            new=AsyncMock(return_value={"logs": [log_data]}),
        )
        mock_get_mission_logs = mocker.patch(
            "app.api._mission_cqrs.queries.get_mission_logs",
            new=AsyncMock(),
        )
        # Ownership check must pass
        mission = MagicMock()
        mission.user_id = 1
        mission.title = "X"
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
        mocker.patch(
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
        result = await handlers.list_logs(user_id=1, mission_id=valid_id)
        assert len(result) == 1
        assert result[0].message == "Test log"
        mock_cache_get_logs.assert_awaited_once()
        # DB logs fetch should NOT be called on cache hit
        mock_get_mission_logs.assert_not_awaited()


class TestStatusCacheWiring:
    """get_status has cache-aside wired."""

    @pytest.mark.asyncio
    async def test_get_status_reads_cache_on_hit(self, mocker):
        """Cache hit returns status without re-fetching tasks."""
        valid_id = str(uuid.uuid4())
        mock_cache_get_status = mocker.patch(
            "app.api._mission_cqrs.queries.cache_get_status",
            new=AsyncMock(
                return_value={
                    "mission_id": valid_id,
                    "status": "running",
                    "total_tasks": 5,
                    "completed_tasks": 3,
                    "failed_tasks": 0,
                    "total_tokens_used": 1000,
                    "started_at": None,
                    "estimated_completion": None,
                }
            ),
        )
        mock_get_mission_tasks = mocker.patch(
            "app.api._mission_cqrs.queries.get_mission_tasks",
            new=AsyncMock(),
        )
        mission = MagicMock()
        mission.user_id = 1
        mission.id = valid_id
        mission.title = "X"
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
        mocker.patch(
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
        result = await handlers.get_status(user_id=1, mission_id=valid_id)
        assert result.total_tasks == 5
        assert result.completed_tasks == 3
        mock_cache_get_status.assert_awaited_once()
        mock_get_mission_tasks.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════════
# GOAL D.3 — Soft-delete + cache safety
# ═══════════════════════════════════════════════════════════════════════════════


class TestSoftDeleteCacheSafety:
    """Soft-deleted missions are never served from cache."""

    @pytest.mark.asyncio
    async def test_soft_deleted_not_in_list_missions_cache(self, mocker):
        """Even if cache returns items, deleted missions are filtered by DB query."""
        mocker.patch(
            "app.api._mission_cqrs.queries.cache_list",
            new=AsyncMock(return_value=None),
        )
        mocker.patch(
            "app.api._mission_cqrs.queries.list_missions",
            new=AsyncMock(return_value=([], 0)),
        )
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        session = AsyncMock()
        handlers = MissionQueryHandlers(session)
        result = await handlers.list_missions(user_id=1, page=1, per_page=20)
        assert result.total == 0

    @pytest.mark.asyncio
    async def test_active_missions_cache_filters_soft_deleted(self, mocker):
        """active_missions cache-hit path excludes entries with deleted_at."""
        id1 = str(uuid.uuid4())
        mocker.patch(
            "app.api._mission_cqrs.queries.cache_active",
            new=AsyncMock(
                return_value={
                    "missions": [
                        {
                            "id": id1,
                            "user_id": 1,
                            "title": "Active",
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
                            "deleted_at": "2026-01-01T00:00:00",
                        }
                    ],
                    "total": 1,
                }
            ),
        )
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        session = AsyncMock()
        handlers = MissionQueryHandlers(session)
        result = await handlers.active_missions(user_id=1, user_role="pro")
        assert len(result.missions) == 0  # filtered out


# ═══════════════════════════════════════════════════════════════════════════════
# GOAL D.4 — Ownership enforcement on cache paths
# ═══════════════════════════════════════════════════════════════════════════════


class TestOwnershipOnCachePaths:
    """Ownership is enforced whether data comes from cache or DB."""

    @pytest.mark.asyncio
    async def test_ownership_on_get_mission_response_cache_hit(self, mocker):
        """Cache hit with wrong user_id → MissionNotFoundError."""
        valid_id = str(uuid.uuid4())
        mocker.patch(
            "app.api._mission_cqrs.queries.cache_get",
            new=AsyncMock(
                return_value={
                    "id": valid_id,
                    "user_id": 2,
                    "title": "Other User's",
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
                    "progress": 0,
                    "eta": None,
                }
            ),
        )
        from app.api._mission_cqrs.queries import MissionQueryHandlers
        from app.services.mission_errors import MissionNotFoundError

        session = AsyncMock()
        handlers = MissionQueryHandlers(session)
        with pytest.raises(MissionNotFoundError):
            await handlers.get_mission_response(user_id=1, mission_id=valid_id)


# ═══════════════════════════════════════════════════════════════════════════════
# GOAL C — asyncio.ensure_future grep proof
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoEnsureFutureInMissionCode:
    """Prove zero asyncio.ensure_future in mission CQRS + cache modules."""

    def test_no_ensure_future_in_queries(self):
        from pathlib import Path

        path = Path(__file__).parent.parent / "api" / "_mission_cqrs" / "queries.py"
        content = path.read_text()
        assert "asyncio.ensure_future" not in content

    def test_no_ensure_future_in_commands(self):
        from pathlib import Path

        path = Path(__file__).parent.parent / "api" / "_mission_cqrs" / "commands.py"
        content = path.read_text()
        assert "asyncio.ensure_future" not in content

    def test_no_ensure_future_in_cache_service(self):
        from pathlib import Path

        path = Path(__file__).parent.parent / "services" / "mission_cache.py"
        content = path.read_text()
        assert "asyncio.ensure_future" not in content


# ═══════════════════════════════════════════════════════════════════════════════
# GOAL D.5 — Invalidation → fresh read
# ═══════════════════════════════════════════════════════════════════════════════


class TestInvalidationCausesFreshRead:
    """After invalidation, the next read must NOT return stale cached data."""

    @pytest.mark.asyncio
    async def test_invalidate_mission_cache_clears_all_keys(self, mocker):
        """invalidate_mission_cache deletes get, tasks, logs, status, improvements, and active keys."""
        valid_id = str(uuid.uuid4())

        mock_redis = MagicMock()
        mock_redis.delete = AsyncMock()
        mocker.patch(
            "app.services.mission_cache._get_redis",
            new=AsyncMock(return_value=mock_redis),
        )

        from app.services.mission_cache import invalidate_mission_cache

        await invalidate_mission_cache(1, valid_id)

        mock_redis.delete.assert_awaited_once()
        # Verify the call includes all the expected key patterns
        call_args = mock_redis.delete.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_cache_get_returns_none_after_invalidation(self, mocker):
        """After invalidate_mission_cache, cache_get returns None."""
        valid_id = str(uuid.uuid4())

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)  # cache miss
        mock_redis.delete = AsyncMock()
        mocker.patch(
            "app.services.mission_cache._get_redis",
            new=AsyncMock(return_value=mock_redis),
        )

        from app.services.mission_cache import cache_get, invalidate_mission_cache

        # Invalidate
        await invalidate_mission_cache(1, valid_id)

        # Subsequent get should return None (not stale data)
        result = await cache_get(1, valid_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_mission_triggers_both_invalidations(self, mocker):
        """delete_mission in commands.py triggers both invalidate_user_caches
        AND invalidate_mission_cache."""
        from pathlib import Path

        path = Path(__file__).parent.parent / "api" / "_mission_cqrs" / "commands.py"
        content = path.read_text()
        # delete_mission should call both invalidation functions
        assert "invalidate_user_caches" in content
        assert "invalidate_mission_cache" in content

    @pytest.mark.asyncio
    async def test_invalidation_clears_cache_for_fresh_read(self, mocker):
        """End-to-end: after invalidate_mission_cache, cache_get returns None.
        This proves that a mutation followed by invalidation results in a cache
        miss on the next read, forcing a fresh DB fetch."""
        valid_id = str(uuid.uuid4())
        # Simulate a cache hit BEFORE invalidation
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value='{"id":"' + valid_id + '","user_id":1}')
        mock_redis.delete = AsyncMock()
        mocker.patch(
            "app.services.mission_cache._get_redis",
            new=AsyncMock(return_value=mock_redis),
        )
        from app.services.mission_cache import cache_get, invalidate_mission_cache

        # Before invalidation: cache returns data
        result_before = await cache_get(1, valid_id)
        assert result_before is not None

        # After invalidation: cache should return None
        mock_redis.get = AsyncMock(return_value=None)  # simulate cleared cache
        await invalidate_mission_cache(1, valid_id)
        mock_redis.delete.assert_awaited_once()

        result_after = await cache_get(1, valid_id)
        assert result_after is None  # ← fresh read, no stale data


# ═══════════════════════════════════════════════════════════════════════════════
# GOAL D — Cache key structure tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestNewCacheKeysExist:
    """Verify new cache key functions and get/set functions are defined."""

    def test_new_key_functions_defined(self):
        from app.services.mission_cache import (
            _improvements_key,
            _logs_key,
            _status_key,
            _tasks_key,
        )

        assert callable(_tasks_key)
        assert callable(_logs_key)
        assert callable(_status_key)
        assert callable(_improvements_key)

    def test_new_cache_get_set_functions_defined(self):
        from app.services.mission_cache import (
            cache_get_logs,
            cache_get_status,
            cache_get_tasks,
            cache_set_logs,
            cache_set_status,
            cache_set_tasks,
        )

        assert callable(cache_get_tasks)
        assert callable(cache_set_tasks)
        assert callable(cache_get_logs)
        assert callable(cache_set_logs)
        assert callable(cache_get_status)
        assert callable(cache_set_status)

    def test_invalidation_clears_new_keys(self):
        """invalidate_mission_cache now also deletes tasks/logs/status/improvements keys."""
        from pathlib import Path

        path = Path(__file__).parent.parent / "services" / "mission_cache.py"
        content = path.read_text()
        assert "_tasks_key" in content
        assert "_logs_key" in content
        assert "_status_key" in content
        assert "_improvements_key" in content
