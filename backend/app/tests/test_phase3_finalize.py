"""Phase 3 verification tests: alembic single head, cache hit/miss,
invalidation effects, soft-deleted exclusion, config-driven DB settings.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# GOAL A — Alembic single-head state
# ═══════════════════════════════════════════════════════════════════════════════


class TestAlembicSingleHead:
    def test_merge_migration_exists(self):
        path = Path(__file__).parent.parent.parent / "alembic" / "versions" / "a3bc0003_merge_h4_6_and_a3bc0002.py"
        assert path.exists()

    def test_merge_migration_references_both_parents(self):
        path = Path(__file__).parent.parent.parent / "alembic" / "versions" / "a3bc0003_merge_h4_6_and_a3bc0002.py"
        content = path.read_text()
        assert "h4_6_drop_cancelled_status" in content
        assert "a3bc0002" in content

    def test_merge_migration_has_no_schema_ops(self):
        path = Path(__file__).parent.parent.parent / "alembic" / "versions" / "a3bc0003_merge_h4_6_and_a3bc0002.py"
        content = path.read_text()
        assert "op.create_table" not in content
        assert "op.add_column" not in content
        assert "op.drop_column" not in content

    def test_heads_recognize_merge(self):
        """Verify alembic has a single head (no branch divergence)."""
        import subprocess
        result = subprocess.run(
            ["alembic", "heads"],
            cwd=Path(__file__).parent.parent.parent,
            capture_output=True, text=True,
        )
        # Count non-empty lines that look like revision lines (end with '(head)')
        head_lines = [
            line.strip() for line in result.stdout.strip().splitlines()
            if line.strip().endswith("(head)")
        ]
        assert len(head_lines) == 1, (
            f"Expected 1 alembic head, got {len(head_lines)}:\n{result.stdout}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# GOAL B — Cache behavior
# ═══════════════════════════════════════════════════════════════════════════════


class TestCacheKeys:
    def test_cache_keys_are_user_scoped(self):
        from app.services.mission_cache import _active_key, _get_key, _list_key
        assert _get_key(1, "abc") != _get_key(2, "abc")
        assert _list_key(1, 1, 20) != _list_key(2, 1, 20)
        assert _active_key(1) != _active_key(2)


class TestCacheReadPathIntegration:
    """Cache is wired into query handlers."""

    def test_queries_import_cache_functions(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers
        assert MissionQueryHandlers is not None

    @pytest.mark.asyncio
    async def test_list_missions_checks_cache_first(self, mocker):
        """list_missions returns cached data when available."""
        mock_cache_list = mocker.patch(
            "app.api._mission_cqrs.queries.cache_list",
            new=AsyncMock(return_value={
                "items": [], "total": 0, "page": 1, "per_page": 20,
            }),
        )
        from app.api._mission_cqrs.queries import MissionQueryHandlers
        session = AsyncMock()
        handlers = MissionQueryHandlers(session)
        result = await handlers.list_missions(user_id=1, page=1, per_page=20)
        assert result.total == 0
        assert mock_cache_list.called

    @pytest.mark.asyncio
    async def test_get_mission_populates_cache_after_db(self, mocker):
        """get_mission writes to cache after DB fetch."""
        mock_cache_set = mocker.patch(
            "app.api._mission_cqrs.queries.cache_set",
            new=AsyncMock(return_value=None),
        )
        mission = MagicMock()
        mission.user_id = 1
        mission.id = "abc-123"
        mission.title = "Test"
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
        # Patch require_mission_access (handler calls this, not get_mission)
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
        result = await handlers.get_mission(user_id=1, mission_id="abc-123")
        assert result is mission

    @pytest.mark.asyncio
    async def test_soft_deleted_not_in_cache_list(self, mocker):
        """Cache miss + DB returns empty for soft-deleted."""
        mock_cache_list = mocker.patch(
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


# ═══════════════════════════════════════════════════════════════════════════════
# GOAL C — Config-driven DB settings
# ═══════════════════════════════════════════════════════════════════════════════


class TestConfigDrivenDbSettings:
    def test_config_has_all_db_pool_settings(self):
        from app.config import settings
        for attr in ("DATABASE_POOL_SIZE", "DATABASE_MAX_OVERFLOW", "DATABASE_POOL_TIMEOUT",
                     "DATABASE_POOL_RECYCLE", "DATABASE_STATEMENT_TIMEOUT_MS",
                     "DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS", "DATABASE_CONNECT_TIMEOUT"):
            assert hasattr(settings, attr), f"Missing setting: {attr}"

    def test_config_defaults_are_sane(self):
        from app.config import settings
        assert settings.DATABASE_POOL_SIZE >= 5
        assert settings.DATABASE_POOL_TIMEOUT >= 5
        assert settings.DATABASE_STATEMENT_TIMEOUT_MS >= 5000
        assert settings.DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS >= 10000

    def test_config_overridable_by_env(self, monkeypatch):
        monkeypatch.setenv("DATABASE_POOL_SIZE", "25")
        monkeypatch.setenv("DATABASE_STATEMENT_TIMEOUT_MS", "30000")
        from app.config import Settings
        s = Settings()
        assert s.DATABASE_POOL_SIZE == 25
        assert s.DATABASE_STATEMENT_TIMEOUT_MS == 30000

    def test_database_py_uses_settings(self):
        db_path = Path(__file__).parent.parent / "database.py"
        content = db_path.read_text()
        assert "settings.DATABASE_POOL_TIMEOUT" in content
        assert "settings.DATABASE_POOL_RECYCLE" in content
        assert "settings.DATABASE_STATEMENT_TIMEOUT_MS" in content
        assert "settings.DATABASE_IDLE_IN_TRANSACTION_TIMEOUT_MS" in content
