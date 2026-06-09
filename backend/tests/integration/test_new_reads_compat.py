"""Integration tests: USE_NEW_READS=1 — Mission reads from Blueprint/Run tables.

When USE_NEW_READS=1, the MissionQueryHandlers delegate list_missions and
get_mission_response to the compat layer which reads from Blueprint + Run
tables instead of the legacy missions table.

Test strategy:
  - Feature flag, status mapping, and converter tests exercise the compat layer
    directly (no mocks).
  - Handler-level tests mock the compat functions to verify the CQRS handler
    correctly delegates to them.
  - API-level tests use TestClient with the compat functions mocked for full
    HTTP request → handler → compat path coverage.

Usage:
    pytest tests/integration/test_new_reads_compat.py -v
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test"
)


pytestmark = pytest.mark.integration


# ── Helpers ─────────────────────────────────────────────────────────────────


def _mission_response(
    *,
    mission_id: str | None = None,
    user_id: int = 42,
    title: str = "Test Mission",
    description: str = "A test mission",
    mission_type: str = "solo",
    status: str = "pending",
    tokens_used: int | None = None,
    actual_cost: float | None = None,
    results: dict | None = None,
    error_message: str | None = None,
):
    """Build a MissionResponse for use as a mock return value."""
    from app.schemas.mission import MissionResponse

    return MissionResponse(
        id=mission_id or uuid4(),
        user_id=user_id,
        title=title,
        description=description,
        mission_type=mission_type,
        status=status,
        priority="medium",
        tokens_used=tokens_used,
        actual_cost=actual_cost,
        results=results,
        error_message=error_message,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _enable_new_reads():
    """Enable USE_NEW_READS for all tests in this module."""
    with patch.dict(os.environ, {"USE_NEW_READS": "1"}):
        yield


@pytest.fixture
def mock_user():
    return MagicMock(
        id=42,
        email="test@example.com",
        username="testuser",
        full_name="Test User",
        is_active=True,
        role="admin",
    )


# ═══════════════════════════════════════════════════════════════════════════
# compat.use_new_reads()
# ═══════════════════════════════════════════════════════════════════════════


class TestFeatureFlag:
    """Verify use_new_reads() respects environment variable."""

    def test_enabled_with_1(self):
        with patch.dict(os.environ, {"USE_NEW_READS": "1"}):
            from app.api._mission_cqrs.compat import use_new_reads

            assert use_new_reads() is True

    def test_enabled_with_true(self):
        with patch.dict(os.environ, {"USE_NEW_READS": "true"}):
            from app.api._mission_cqrs.compat import use_new_reads

            assert use_new_reads() is True

    def test_enabled_with_yes(self):
        with patch.dict(os.environ, {"USE_NEW_READS": "yes"}):
            from app.api._mission_cqrs.compat import use_new_reads

            assert use_new_reads() is True

    def test_disabled_when_empty(self):
        with patch.dict(os.environ, {"USE_NEW_READS": ""}):
            from app.api._mission_cqrs.compat import use_new_reads

            assert use_new_reads() is False

    def test_disabled_when_unset(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("USE_NEW_READS", None)
            from app.api._mission_cqrs.compat import use_new_reads

            assert use_new_reads() is False

    def test_disabled_with_random_value(self):
        with patch.dict(os.environ, {"USE_NEW_READS": "nope"}):
            from app.api._mission_cqrs.compat import use_new_reads

            assert use_new_reads() is False


# ═══════════════════════════════════════════════════════════════════════════
# Status mapping
# ═══════════════════════════════════════════════════════════════════════════


class TestStatusMapping:
    """Verify Run and Blueprint statuses map correctly to MissionStatus."""

    def test_run_status_completed(self):
        from app.api._mission_cqrs.compat import _map_run_status
        from app.models.mission_models import MissionStatus

        assert _map_run_status("completed") == MissionStatus.COMPLETED

    def test_run_status_executing(self):
        from app.api._mission_cqrs.compat import _map_run_status
        from app.models.mission_models import MissionStatus

        assert _map_run_status("executing") == MissionStatus.EXECUTING

    def test_run_status_failed(self):
        from app.api._mission_cqrs.compat import _map_run_status
        from app.models.mission_models import MissionStatus

        assert _map_run_status("failed") == MissionStatus.FAILED

    def test_run_status_aborted(self):
        from app.api._mission_cqrs.compat import _map_run_status
        from app.models.mission_models import MissionStatus

        assert _map_run_status("aborted") == MissionStatus.ABORTED

    def test_run_status_queued(self):
        from app.api._mission_cqrs.compat import _map_run_status
        from app.models.mission_models import MissionStatus

        assert _map_run_status("queued") == MissionStatus.QUEUED

    def test_run_status_paused(self):
        from app.api._mission_cqrs.compat import _map_run_status
        from app.models.mission_models import MissionStatus

        assert _map_run_status("paused") == MissionStatus.PAUSED

    def test_run_status_unknown_defaults_to_pending(self):
        from app.api._mission_cqrs.compat import _map_run_status
        from app.models.mission_models import MissionStatus

        assert _map_run_status("unknown_status") == MissionStatus.PENDING

    def test_bp_status_draft(self):
        from app.api._mission_cqrs.compat import _map_bp_status
        from app.models.mission_models import MissionStatus

        assert _map_bp_status("draft") == MissionStatus.PENDING

    def test_bp_status_published(self):
        from app.api._mission_cqrs.compat import _map_bp_status
        from app.models.mission_models import MissionStatus

        assert _map_bp_status("published") == MissionStatus.PLANNED

    def test_bp_status_deprecated(self):
        from app.api._mission_cqrs.compat import _map_bp_status
        from app.models.mission_models import MissionStatus

        assert _map_bp_status("deprecated") == MissionStatus.FAILED


# ═══════════════════════════════════════════════════════════════════════════
# Converter: _blueprint_run_to_mission_response
# ═══════════════════════════════════════════════════════════════════════════


class TestBlueprintRunConverter:
    """Verify the Blueprint+Run → MissionResponse conversion."""

    @staticmethod
    def _bp(**kwargs):
        """Blueprint-like mock."""
        defaults = dict(
            id=str(uuid4()),
            user_id=42,
            workspace_id=None,
            title="Test BP",
            description="desc",
            blueprint_type="solo",
            definition={},
            status="draft",
            version=1,
            deleted_at=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        defaults.update(kwargs)
        return MagicMock(**defaults)

    @staticmethod
    def _run(blueprint_id: str, **kwargs):
        """Run-like mock."""
        now = datetime.now(UTC)
        defaults = dict(
            id=str(uuid4()),
            blueprint_id=blueprint_id,
            user_id=42,
            status="completed",
            total_tokens=100,
            total_cost_usd=0.002,
            error_message=None,
            output_data=None,
            started_at=now,
            completed_at=now,
            created_at=now,
            updated_at=now,
        )
        defaults.update(kwargs)
        return MagicMock(**defaults)

    def test_converter_with_no_run(self):
        from app.api._mission_cqrs.compat import _blueprint_run_to_mission_response
        from app.models.mission_models import MissionStatus

        bp = self._bp(title="No Run BP", blueprint_type="dag")
        result = _blueprint_run_to_mission_response(bp, None)

        assert result.title == "No Run BP"
        assert result.mission_type == "dag"
        assert result.status == MissionStatus.PENDING  # draft → pending
        assert result.tokens_used is None
        assert result.results is None
        assert result.priority == "medium"

    def test_converter_with_completed_run(self):
        from app.api._mission_cqrs.compat import _blueprint_run_to_mission_response
        from app.models.mission_models import MissionStatus

        bp = self._bp(title="With Run")
        run = self._run(
            blueprint_id=str(bp.id),
            status="completed",
            total_tokens=1000,
            total_cost_usd=0.1,
            output_data={"answer": 42},
        )
        result = _blueprint_run_to_mission_response(bp, run)

        assert result.title == "With Run"
        assert result.status == MissionStatus.COMPLETED
        assert result.tokens_used == 1000
        assert result.actual_cost == 0.1
        assert result.results == {"answer": 42}
        assert result.started_at is not None
        assert result.completed_at is not None

    def test_converter_preserves_definition_as_plan(self):
        from app.api._mission_cqrs.compat import _blueprint_run_to_mission_response

        definition = {"nodes": [{"id": "n1"}], "edges": []}
        bp = self._bp(definition=definition)
        result = _blueprint_run_to_mission_response(bp, None)

        assert result.plan == definition

    def test_converter_with_failed_run(self):
        from app.api._mission_cqrs.compat import _blueprint_run_to_mission_response
        from app.models.mission_models import MissionStatus

        bp = self._bp()
        run = self._run(
            blueprint_id=str(bp.id),
            status="failed",
            error_message="LLM timeout",
        )
        result = _blueprint_run_to_mission_response(bp, run)

        assert result.status == MissionStatus.FAILED
        assert result.error_message == "LLM timeout"

    def test_converter_run_status_overrides_bp_status(self):
        """Run status should always take precedence over Blueprint status."""
        from app.api._mission_cqrs.compat import _blueprint_run_to_mission_response
        from app.models.mission_models import MissionStatus

        bp = self._bp(status="published")  # Would map to PLANNED
        run = self._run(blueprint_id=str(bp.id), status="completed")
        result = _blueprint_run_to_mission_response(bp, run)

        # Run status wins → COMPLETED, not PLANNED
        assert result.status == MissionStatus.COMPLETED


# ═══════════════════════════════════════════════════════════════════════════
# MissionShim
# ═══════════════════════════════════════════════════════════════════════════


class TestMissionShim:
    """Verify MissionShim provides Mission-compatible attributes."""

    def test_shim_from_blueprint_run(self):
        from app.api._mission_cqrs.compat import MissionShim
        from app.models.mission_models import MissionStatus

        bp = MagicMock(
            id=str(uuid4()),
            user_id=42,
            workspace_id=None,
            title="Shim Test",
            description="desc",
            blueprint_type="solo",
            definition={"key": "val"},
            status="published",
            version=1,
            deleted_at=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        run = MagicMock(
            status="completed",
            output_data={"r": 1},
            error_message=None,
            total_tokens=200,
            total_cost_usd=0.02,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )

        shim = MissionShim.from_blueprint_run(bp, run)

        assert shim.id == str(bp.id)
        assert shim.title == "Shim Test"
        assert shim.status == MissionStatus.COMPLETED
        assert shim.tokens_used == 200
        assert shim.plan == {"key": "val"}
        assert shim.workspace_id is None
        assert shim.deleted_at is None

    def test_shim_without_run(self):
        from app.api._mission_cqrs.compat import MissionShim
        from app.models.mission_models import MissionStatus

        bp = MagicMock(
            id=str(uuid4()),
            user_id=42,
            workspace_id="ws-1",
            title="No Run",
            description="",
            blueprint_type="dag",
            definition=None,
            status="draft",
            version=1,
            deleted_at=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        shim = MissionShim.from_blueprint_run(bp, None)

        assert shim.status == MissionStatus.PENDING  # draft → pending
        assert shim.results is None
        assert shim.error_message is None
        assert shim.workspace_id == "ws-1"

    def test_shim_has_all_downstream_attributes(self):
        """MissionShim exposes all attributes accessed by downstream callers."""
        from app.api._mission_cqrs.compat import MissionShim

        bp = MagicMock(
            id=str(uuid4()),
            user_id=42,
            workspace_id=None,
            title="T",
            description="",
            blueprint_type="solo",
            definition=None,
            status="draft",
            version=1,
            deleted_at=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        shim = MissionShim.from_blueprint_run(bp, None)

        # Attributes used by _make_execution_status, stream_status, etc.
        for attr in (
            "id",
            "status",
            "started_at",
            "completed_at",
            "workspace_id",
            "deleted_at",
            "version",
            "user_id",
            "title",
            "description",
        ):
            assert hasattr(shim, attr), f"Missing attribute: {attr}"


# ═══════════════════════════════════════════════════════════════════════════
# Handler: list_missions with USE_NEW_READS=1
# ═══════════════════════════════════════════════════════════════════════════


class TestListMissionsNewReads:
    """list_missions() delegates to list_missions_from_blueprints when enabled."""

    @pytest.mark.asyncio
    async def test_list_empty(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mock_list = AsyncMock(return_value=([], 0))
        db = AsyncMock()

        with (
            patch(
                "app.api._mission_cqrs.queries.cache_list",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api._mission_cqrs.queries.list_missions_from_blueprints",
                new=mock_list,
            ),
        ):
            handler = MissionQueryHandlers(db)
            result = await handler.list_missions(user_id=42, page=1, per_page=20)

        assert result.items == []
        assert result.total == 0
        mock_list.assert_awaited_once_with(
            db, 42, offset=0, limit=20, workspace_id=None
        )

    @pytest.mark.asyncio
    async def test_list_returns_missions(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        m1 = _mission_response(title="Mission A", status="completed")
        m2 = _mission_response(title="Mission B", status="running")
        mock_list = AsyncMock(return_value=([m1, m2], 2))

        with (
            patch(
                "app.api._mission_cqrs.queries.cache_list",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api._mission_cqrs.queries.list_missions_from_blueprints",
                new=mock_list,
            ),
            patch("app.api._mission_cqrs.queries.cache_set_list", new=AsyncMock()),
        ):
            handler = MissionQueryHandlers(AsyncMock())
            result = await handler.list_missions(user_id=42, page=1, per_page=20)

        assert result.total == 2
        assert len(result.items) == 2
        titles = {item.title for item in result.items}
        assert titles == {"Mission A", "Mission B"}

    @pytest.mark.asyncio
    async def test_list_passes_workspace_id(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mock_list = AsyncMock(return_value=([], 0))
        db = AsyncMock()

        with (
            patch(
                "app.api._mission_cqrs.queries.cache_list",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api._mission_cqrs.queries.list_missions_from_blueprints",
                new=mock_list,
            ),
        ):
            handler = MissionQueryHandlers(db)
            await handler.list_missions(
                user_id=42, page=1, per_page=20, workspace_id="ws-abc"
            )

        mock_list.assert_awaited_once_with(
            db, 42, offset=0, limit=20, workspace_id="ws-abc"
        )

    @pytest.mark.asyncio
    async def test_list_uses_cache_on_hit(self):
        """When cache returns data, compat function is NOT called."""
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        cached = {
            "items": [
                {
                    "id": str(uuid4()),
                    "user_id": 42,
                    "title": "Cached",
                    "description": "",
                    "mission_type": "solo",
                    "status": "completed",
                    "priority": "medium",
                    "created_at": "2026-01-01T00:00:00",
                }
            ],
            "total": 1,
            "page": 1,
            "per_page": 20,
        }
        mock_list = AsyncMock()

        with (
            patch(
                "app.api._mission_cqrs.queries.cache_list",
                new=AsyncMock(return_value=cached),
            ),
            patch(
                "app.api._mission_cqrs.queries.list_missions_from_blueprints",
                new=mock_list,
            ),
        ):
            handler = MissionQueryHandlers(AsyncMock())
            result = await handler.list_missions(user_id=42, page=1, per_page=20)

        assert result.total == 1
        assert result.items[0].title == "Cached"
        mock_list.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_pagination_offset(self):
        """page=3, per_page=10 → offset=20."""
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mock_list = AsyncMock(return_value=([], 0))
        db = AsyncMock()

        with (
            patch(
                "app.api._mission_cqrs.queries.cache_list",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api._mission_cqrs.queries.list_missions_from_blueprints",
                new=mock_list,
            ),
        ):
            handler = MissionQueryHandlers(db)
            result = await handler.list_missions(user_id=42, page=3, per_page=10)

        mock_list.assert_awaited_once_with(
            db, 42, offset=20, limit=10, workspace_id=None
        )
        assert result.page == 3
        assert result.per_page == 10

    @pytest.mark.asyncio
    async def test_list_populates_cache(self):
        """After DB fetch, cache_set_list is called."""
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        m = _mission_response(title="Cached Soon")
        mock_list = AsyncMock(return_value=([m], 1))
        mock_cache_set = AsyncMock()
        db = AsyncMock()

        with (
            patch(
                "app.api._mission_cqrs.queries.cache_list",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api._mission_cqrs.queries.list_missions_from_blueprints",
                new=mock_list,
            ),
            patch("app.api._mission_cqrs.queries.cache_set_list", new=mock_cache_set),
        ):
            handler = MissionQueryHandlers(db)
            await handler.list_missions(user_id=42, page=1, per_page=20)

        mock_list.assert_awaited_once_with(
            db, 42, offset=0, limit=20, workspace_id=None
        )
        # cache_set_list is called via asyncio.create_task (fire-and-forget),
        # so the coroutine is invoked but not directly awaited by the caller.
        mock_cache_set.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# Handler: get_mission_response with USE_NEW_READS=1
# ═══════════════════════════════════════════════════════════════════════════


class TestGetMissionResponseNewReads:
    """get_mission_response() delegates to get_mission_from_blueprint when enabled."""

    @pytest.mark.asyncio
    async def test_get_returns_mission(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        bp_id = str(uuid4())
        mr = _mission_response(mission_id=bp_id, title="Found Me", tokens_used=200)
        mock_get = AsyncMock(return_value=mr)
        db = AsyncMock()

        with (
            patch(
                "app.api._mission_cqrs.queries.cache_get",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api._mission_cqrs.queries.get_mission_from_blueprint", new=mock_get
            ),
            patch("app.api._mission_cqrs.queries.cache_set", new=AsyncMock()),
        ):
            handler = MissionQueryHandlers(db)
            result = await handler.get_mission_response(user_id=42, mission_id=bp_id)

        assert str(result.id) == bp_id
        assert result.title == "Found Me"
        assert result.tokens_used == 200
        mock_get.assert_awaited_once_with(db, bp_id, 42)

    @pytest.mark.asyncio
    async def test_get_raises_not_found(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers
        from app.services.mission_errors import MissionNotFoundError

        mock_get = AsyncMock(side_effect=MissionNotFoundError("not found"))

        with (
            patch(
                "app.api._mission_cqrs.queries.cache_get",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api._mission_cqrs.queries.get_mission_from_blueprint", new=mock_get
            ),
        ):
            handler = MissionQueryHandlers(AsyncMock())
            with pytest.raises(MissionNotFoundError):
                await handler.get_mission_response(user_id=42, mission_id=str(uuid4()))

    @pytest.mark.asyncio
    async def test_get_returns_cached(self):
        """Cache hit → returns without calling compat function."""
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        bp_id = str(uuid4())
        cached = {
            "id": bp_id,
            "user_id": 42,
            "title": "Cached Mission",
            "description": "",
            "mission_type": "solo",
            "status": "completed",
            "priority": "medium",
            "created_at": "2026-01-01T00:00:00",
        }
        mock_get = AsyncMock()

        with (
            patch(
                "app.api._mission_cqrs.queries.cache_get",
                new=AsyncMock(return_value=cached),
            ),
            patch(
                "app.api._mission_cqrs.queries.get_mission_from_blueprint", new=mock_get
            ),
        ):
            handler = MissionQueryHandlers(AsyncMock())
            result = await handler.get_mission_response(user_id=42, mission_id=bp_id)

        assert result.title == "Cached Mission"
        mock_get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_rejects_cache_wrong_owner(self):
        """Cache hit with wrong user_id → MissionNotFoundError."""
        from app.api._mission_cqrs.queries import MissionQueryHandlers
        from app.services.mission_errors import MissionNotFoundError

        cached = {"id": str(uuid4()), "user_id": 999, "title": "Not Yours"}

        with patch(
            "app.api._mission_cqrs.queries.cache_get",
            new=AsyncMock(return_value=cached),
        ):
            handler = MissionQueryHandlers(AsyncMock())
            with pytest.raises(MissionNotFoundError):
                await handler.get_mission_response(user_id=42, mission_id=str(uuid4()))

    @pytest.mark.asyncio
    async def test_get_populates_cache(self):
        """After DB fetch, cache_set is called."""
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mr = _mission_response(title="To Cache")
        mock_cache_set = AsyncMock()

        with (
            patch(
                "app.api._mission_cqrs.queries.cache_get",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api._mission_cqrs.queries.get_mission_from_blueprint",
                new=AsyncMock(return_value=mr),
            ),
            patch("app.api._mission_cqrs.queries.cache_set", new=mock_cache_set),
        ):
            handler = MissionQueryHandlers(AsyncMock())
            await handler.get_mission_response(user_id=42, mission_id=str(uuid4()))

        # cache_set is called via asyncio.create_task (fire-and-forget),
        # so the coroutine is invoked but not directly awaited by the caller.
        mock_cache_set.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# Handler: get_mission (ORM path) with USE_NEW_READS=1
# ═══════════════════════════════════════════════════════════════════════════


class TestGetMissionShimNewReads:
    """get_mission() returns MissionShim when USE_NEW_READS=1."""

    @pytest.mark.asyncio
    async def test_returns_mission_shim(self):
        from app.api._mission_cqrs.compat import MissionShim
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        bp_id = str(uuid4())
        shim = MissionShim(
            id=bp_id,
            user_id=42,
            title="Shim Test",
            description="",
            mission_type="solo",
            status="running",
            priority="medium",
            plan=None,
            results=None,
            error_message=None,
            tokens_used=None,
            estimated_cost=None,
            actual_cost=None,
            started_at=None,
            completed_at=None,
            created_at=None,
            updated_at=None,
            workspace_id=None,
        )
        mock_shim = AsyncMock(return_value=shim)
        db = AsyncMock()

        with (
            patch("app.api._mission_cqrs.queries.get_mission_as_shim", new=mock_shim),
            patch("app.api._mission_cqrs.queries.cache_set", new=AsyncMock()),
        ):
            handler = MissionQueryHandlers(db)
            result = await handler.get_mission(user_id=42, mission_id=bp_id)

        assert isinstance(result, MissionShim)
        assert result.id == bp_id
        assert result.title == "Shim Test"
        mock_shim.assert_awaited_once_with(db, bp_id, 42)

    @pytest.mark.asyncio
    async def test_shim_populates_cache(self):
        from app.api._mission_cqrs.compat import MissionShim
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        shim = MissionShim(
            id=str(uuid4()),
            user_id=42,
            title="T",
            description="",
            mission_type="solo",
            status="pending",
            priority="medium",
            plan=None,
            results=None,
            error_message=None,
            tokens_used=None,
            estimated_cost=None,
            actual_cost=None,
            started_at=None,
            completed_at=None,
            created_at=None,
            updated_at=None,
            workspace_id=None,
        )
        mock_cache_set = AsyncMock()
        mock_shim = AsyncMock(return_value=shim)
        db = AsyncMock()

        with (
            patch("app.api._mission_cqrs.queries.get_mission_as_shim", new=mock_shim),
            patch("app.api._mission_cqrs.queries.cache_set", new=mock_cache_set),
        ):
            handler = MissionQueryHandlers(db)
            await handler.get_mission(user_id=42, mission_id=str(uuid4()))

        mock_shim.assert_awaited_once()
        # cache_set is called via asyncio.create_task (fire-and-forget),
        # so the coroutine is invoked but not directly awaited by the caller.
        mock_cache_set.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# Full API path: v1 mission endpoints with USE_NEW_READS=1
# ═══════════════════════════════════════════════════════════════════════════


class TestMissionApiNewReads:
    """Full HTTP request → CQRS handler → compat → response path."""

    @pytest.fixture
    def app_with_mission_router(self, mock_user):
        """Minimal FastAPI app with v1 mission router."""
        from fastapi import FastAPI
        from fastapi.responses import JSONResponse

        from app.api.deps import get_current_user, get_workspace_id
        from app.api.v1.mission import router as mission_router
        from app.database import get_db_session
        from app.services.mission_errors import MissionNotFoundError

        _app = FastAPI()

        @_app.exception_handler(MissionNotFoundError)
        async def _not_found(request, exc):
            return JSONResponse(status_code=404, content={"detail": str(exc)})

        _app.include_router(mission_router, prefix="/api/v1")

        async def _override_user():
            return mock_user

        async def _override_workspace():
            return None

        _app.dependency_overrides[get_current_user] = _override_user
        _app.dependency_overrides[get_workspace_id] = _override_workspace

        return _app

    def test_list_missions_via_api(self, app_with_mission_router):
        """GET /api/v1/missions returns missions from compat layer."""
        from fastapi.testclient import TestClient

        from app.database import get_db_session

        m = _mission_response(title="API Mission")
        mock_list = AsyncMock(return_value=([m], 1))

        async def _override_db():
            yield AsyncMock()

        app_with_mission_router.dependency_overrides[get_db_session] = _override_db

        with (
            patch(
                "app.api._mission_cqrs.queries.cache_list",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api._mission_cqrs.queries.list_missions_from_blueprints",
                new=mock_list,
            ),
            patch("app.api._mission_cqrs.queries.cache_set_list", new=AsyncMock()),
            TestClient(app_with_mission_router) as client,
        ):
            resp = client.get("/api/v1/missions?page=1&per_page=20")

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["title"] == "API Mission"

    def test_get_mission_via_api(self, app_with_mission_router):
        """GET /api/v1/missions/{id} returns mission from compat layer."""
        from fastapi.testclient import TestClient

        from app.api._mission_cqrs.compat import MissionShim
        from app.database import get_db_session

        bp_id = str(uuid4())
        # Build a MissionShim to return from the mocked get_mission_as_shim.
        # The v1 endpoint calls get_mission() → queries.get_mission_as_shim()
        # when USE_NEW_READS=1. Must patch in the queries module where it's
        # imported, not in the compat module where it's defined.
        shim = MissionShim(
            id=bp_id,
            user_id=42,
            title="API Single",
            description="",
            mission_type="solo",
            status="completed",
            priority="medium",
            plan=None,
            results=None,
            error_message=None,
            tokens_used=None,
            estimated_cost=None,
            actual_cost=None,
            started_at=None,
            completed_at=None,
            created_at=None,
            updated_at=None,
            workspace_id=None,
        )
        mock_shim = AsyncMock(return_value=shim)

        async def _override_db():
            yield AsyncMock()

        app_with_mission_router.dependency_overrides[get_db_session] = _override_db

        with (
            patch("app.api._mission_cqrs.queries.get_mission_as_shim", new=mock_shim),
            patch("app.api._mission_cqrs.queries.cache_set", new=AsyncMock()),
        ):
            with TestClient(app_with_mission_router) as client:
                resp = client.get(f"/api/v1/missions/{bp_id}")

        assert resp.status_code == 200
        assert resp.json()["title"] == "API Single"
        mock_shim.assert_called_once()

    def test_get_mission_not_found_via_api(self, app_with_mission_router):
        """GET /api/v1/missions/{id} with missing ID returns 404."""
        from fastapi.testclient import TestClient

        from app.database import get_db_session
        from app.services.mission_errors import MissionNotFoundError

        mock_shim = AsyncMock(side_effect=MissionNotFoundError("not found"))

        async def _override_db():
            yield AsyncMock()

        app_with_mission_router.dependency_overrides[get_db_session] = _override_db

        # Must patch in the queries module where get_mission_as_shim is imported.
        with (
            patch("app.api._mission_cqrs.queries.get_mission_as_shim", new=mock_shim),
            patch("app.api._mission_cqrs.queries.cache_set", new=AsyncMock()),
        ):
            with TestClient(app_with_mission_router) as client:
                resp = client.get(f"/api/v1/missions/{uuid4()}")

        assert resp.status_code == 404
        mock_shim.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# Handler: list_active with USE_NEW_READS=1
# ═══════════════════════════════════════════════════════════════════════════


class TestListActiveNewReads:
    """list_active() delegates to list_active_from_blueprints when enabled."""

    @pytest.mark.asyncio
    async def test_list_active_delegates_to_blueprints(self):
        from app.api._mission_cqrs.compat import MissionShim
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        shim = MissionShim(
            id=str(uuid4()),
            user_id=42,
            title="Active BP",
            description="",
            mission_type="solo",
            status="running",
            priority="medium",
            plan=None,
            results=None,
            error_message=None,
            tokens_used=None,
            estimated_cost=None,
            actual_cost=None,
            started_at=None,
            completed_at=None,
            created_at=None,
            updated_at=None,
            workspace_id=None,
        )
        mock_active = AsyncMock(return_value=[shim])
        db = AsyncMock()

        with (
            patch(
                "app.api._mission_cqrs.queries.cache_active",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api._mission_cqrs.queries.list_active_from_blueprints",
                new=mock_active,
            ),
            patch("app.api._mission_cqrs.queries.cache_set_active", new=AsyncMock()),
        ):
            handler = MissionQueryHandlers(db)
            result = await handler.list_active(user_id=42)

        assert len(result) == 1
        assert isinstance(result[0], MissionShim)
        assert result[0].title == "Active BP"
        mock_active.assert_awaited_once_with(db, 42, workspace_id=None)

    @pytest.mark.asyncio
    async def test_list_active_passes_workspace_id(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mock_active = AsyncMock(return_value=[])
        db = AsyncMock()

        with (
            patch(
                "app.api._mission_cqrs.queries.cache_active",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api._mission_cqrs.queries.list_active_from_blueprints",
                new=mock_active,
            ),
            patch("app.api._mission_cqrs.queries.cache_set_active", new=AsyncMock()),
        ):
            handler = MissionQueryHandlers(db)
            result = await handler.list_active(user_id=42, workspace_id="ws-1")

        assert result == []
        mock_active.assert_awaited_once_with(db, 42, workspace_id="ws-1")

    @pytest.mark.asyncio
    async def test_list_active_returns_cache_hit(self):
        """When cache has data, compat function is NOT called."""
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mock_active = AsyncMock()

        with (
            patch(
                "app.api._mission_cqrs.queries.cache_active",
                new=AsyncMock(return_value={"active_ids": []}),
            ),
            patch(
                "app.api._mission_cqrs.queries.list_active_from_blueprints",
                new=mock_active,
            ),
        ):
            handler = MissionQueryHandlers(AsyncMock())
            # Empty active_ids → returns [] without touching compat layer
            result = await handler.list_active(user_id=42)

        assert result == []
        mock_active.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_active_populates_cache(self):
        """After DB fetch, cache_set_active is called with mission IDs."""
        from app.api._mission_cqrs.compat import MissionShim
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        shim = MissionShim(
            id=str(uuid4()),
            user_id=42,
            title="T",
            description="",
            mission_type="solo",
            status="queued",
            priority="medium",
            plan=None,
            results=None,
            error_message=None,
            tokens_used=None,
            estimated_cost=None,
            actual_cost=None,
            started_at=None,
            completed_at=None,
            created_at=None,
            updated_at=None,
            workspace_id=None,
        )
        mock_cache_set = AsyncMock()
        db = AsyncMock()

        with (
            patch(
                "app.api._mission_cqrs.queries.cache_active",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api._mission_cqrs.queries.list_active_from_blueprints",
                new=AsyncMock(return_value=[shim]),
            ),
            patch("app.api._mission_cqrs.queries.cache_set_active", new=mock_cache_set),
        ):
            handler = MissionQueryHandlers(db)
            await handler.list_active(user_id=42)

        mock_cache_set.assert_called_once()
        # Verify the cached IDs contain our shim ID
        call_args = mock_cache_set.call_args
        assert shim.id in call_args[0][1]["active_ids"]


# ═══════════════════════════════════════════════════════════════════════════
# Handler: active_missions with USE_NEW_READS=1
# ═══════════════════════════════════════════════════════════════════════════


class TestActiveMissionsNewReads:
    """active_missions() delegates to active_missions_from_blueprints when enabled."""

    @pytest.mark.asyncio
    async def test_active_missions_delegates_to_blueprints(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mr = _mission_response(title="Active Mission", status="running")
        mock_active = AsyncMock(return_value=([mr], 1))
        db = AsyncMock()

        with (
            patch(
                "app.api._mission_cqrs.queries.cache_active",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api._mission_cqrs.queries.active_missions_from_blueprints",
                new=mock_active,
            ),
            patch("app.api._mission_cqrs.queries.cache_set_active", new=AsyncMock()),
        ):
            handler = MissionQueryHandlers(db)
            result = await handler.active_missions(
                user_id=42, user_role="pro", is_pro=True
            )

        assert result.total == 1
        assert len(result.missions) == 1
        assert result.missions[0].title == "Active Mission"
        mock_active.assert_awaited_once_with(db, 42, workspace_id=None)

    @pytest.mark.asyncio
    async def test_active_missions_passes_workspace_id(self):
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mock_active = AsyncMock(return_value=([], 0))
        db = AsyncMock()

        with (
            patch(
                "app.api._mission_cqrs.queries.cache_active",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api._mission_cqrs.queries.active_missions_from_blueprints",
                new=mock_active,
            ),
            patch("app.api._mission_cqrs.queries.cache_set_active", new=AsyncMock()),
        ):
            handler = MissionQueryHandlers(db)
            result = await handler.active_missions(
                user_id=42,
                user_role="pro",
                is_pro=True,
                workspace_id="ws-xyz",
            )

        assert result.total == 0
        mock_active.assert_awaited_once_with(db, 42, workspace_id="ws-xyz")

    @pytest.mark.asyncio
    async def test_active_missions_requires_pro(self):
        """Non-pro users are rejected before reaching the compat layer."""
        from app.api._mission_cqrs.queries import MissionQueryHandlers
        from app.services.mission_errors import MissionForbiddenError

        mock_active = AsyncMock()

        with patch(
            "app.api._mission_cqrs.queries.active_missions_from_blueprints",
            new=mock_active,
        ):
            handler = MissionQueryHandlers(AsyncMock())
            with pytest.raises(MissionForbiddenError):
                await handler.active_missions(
                    user_id=42, user_role="member", is_pro=False
                )

        mock_active.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_active_missions_returns_cache_hit(self):
        """When cache has data, compat function is NOT called."""
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mr = _mission_response(title="Cached Active")
        cached = {"missions": [mr.model_dump()], "total": 1}
        mock_active = AsyncMock()

        with (
            patch(
                "app.api._mission_cqrs.queries.cache_active",
                new=AsyncMock(return_value=cached),
            ),
            patch(
                "app.api._mission_cqrs.queries.active_missions_from_blueprints",
                new=mock_active,
            ),
        ):
            handler = MissionQueryHandlers(AsyncMock())
            result = await handler.active_missions(
                user_id=42, user_role="pro", is_pro=True
            )

        assert result.total == 1
        mock_active.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_active_missions_populates_cache(self):
        """After DB fetch, cache_set_active is called."""
        from app.api._mission_cqrs.queries import MissionQueryHandlers

        mr = _mission_response(title="To Cache")
        mock_cache_set = AsyncMock()

        with (
            patch(
                "app.api._mission_cqrs.queries.cache_active",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.api._mission_cqrs.queries.active_missions_from_blueprints",
                new=AsyncMock(return_value=([mr], 1)),
            ),
            patch("app.api._mission_cqrs.queries.cache_set_active", new=mock_cache_set),
        ):
            handler = MissionQueryHandlers(AsyncMock())
            await handler.active_missions(user_id=42, user_role="pro", is_pro=True)

        mock_cache_set.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# Status mapping: MissionStatus → RunStatus
# ═══════════════════════════════════════════════════════════════════════════


class TestMissionToRunStatusMapping:
    """Verify _mission_status_to_run_status maps divergent statuses correctly."""

    def test_running_maps_to_executing(self):
        from app.api._mission_cqrs.compat import _mission_status_to_run_status

        assert _mission_status_to_run_status("running") == "executing"

    def test_planning_maps_to_pending(self):
        from app.api._mission_cqrs.compat import _mission_status_to_run_status

        assert _mission_status_to_run_status("planning") == "pending"

    def test_planned_maps_to_pending(self):
        from app.api._mission_cqrs.compat import _mission_status_to_run_status

        assert _mission_status_to_run_status("planned") == "pending"

    def test_approved_maps_to_completed(self):
        from app.api._mission_cqrs.compat import _mission_status_to_run_status

        assert _mission_status_to_run_status("approved") == "completed"

    def test_passthrough_statuses(self):
        """Statuses that exist in both MissionStatus and RunStatus pass through."""
        from app.api._mission_cqrs.compat import _mission_status_to_run_status

        for status in (
            "pending",
            "queued",
            "executing",
            "paused",
            "completed",
            "failed",
            "aborted",
        ):
            assert (
                _mission_status_to_run_status(status) == status
            ), f"{status} should pass through"


# ═══════════════════════════════════════════════════════════════════════════
# Dual-write helpers
# ═══════════════════════════════════════════════════════════════════════════


class TestDualWriteSyncRunStatus:
    """Verify dual_write_sync_run_status updates the latest Run."""

    @pytest.mark.asyncio
    async def test_sync_run_status_updates_run(self):
        from app.api._mission_cqrs.compat import dual_write_sync_run_status

        mission_id = str(uuid4())
        mock_run = MagicMock()
        mock_run.status = "pending"
        mock_run.error_message = None
        mock_run.completed_at = None

        mock_bp = MagicMock()
        mock_bp.id = str(uuid4())
        mock_bp.deleted_at = None

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=mock_bp)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=mock_run)),
            ]
        )
        mock_db.commit = AsyncMock()

        with patch(
            "app.database.AsyncSessionLocal",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_db),
                __aexit__=AsyncMock(return_value=False),
            ),
        ):
            await dual_write_sync_run_status(
                mission_id,
                42,
                "aborted",
                error_message="User aborted",
                completed_at=datetime.now(UTC),
            )

        assert mock_run.status == "aborted"
        assert mock_run.error_message == "User aborted"
        assert mock_run.completed_at is not None
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sync_run_status_maps_running_to_executing(self):
        from app.api._mission_cqrs.compat import dual_write_sync_run_status

        mock_run = MagicMock()
        mock_run.status = "pending"
        mock_run.error_message = None
        mock_run.completed_at = None

        mock_bp = MagicMock()
        mock_bp.id = str(uuid4())

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            side_effect=[
                MagicMock(scalar_one_or_none=MagicMock(return_value=mock_bp)),
                MagicMock(scalar_one_or_none=MagicMock(return_value=mock_run)),
            ]
        )
        mock_db.commit = AsyncMock()

        with patch(
            "app.database.AsyncSessionLocal",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_db),
                __aexit__=AsyncMock(return_value=False),
            ),
        ):
            await dual_write_sync_run_status(str(uuid4()), 42, "running")

        assert mock_run.status == "executing"

    @pytest.mark.asyncio
    async def test_sync_run_status_no_blueprint_is_noop(self):
        """When no linked Blueprint exists, function returns silently."""
        from app.api._mission_cqrs.compat import dual_write_sync_run_status

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=None),
                scalars=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=None))
                ),
            )
        )

        with patch(
            "app.database.AsyncSessionLocal",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_db),
                __aexit__=AsyncMock(return_value=False),
            ),
        ):
            await dual_write_sync_run_status(str(uuid4()), 42, "completed")

    @pytest.mark.asyncio
    async def test_sync_run_status_no_run_is_noop(self):
        """When Blueprint exists but no Run, function returns silently."""
        from app.api._mission_cqrs.compat import dual_write_sync_run_status

        mock_bp = MagicMock()
        mock_bp.id = str(uuid4())

        mock_db = AsyncMock()
        call_count = 0

        async def _execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MagicMock(scalar_one_or_none=MagicMock(return_value=mock_bp))
            return MagicMock(scalar_one_or_none=MagicMock(return_value=None))

        mock_db.execute = _execute

        with patch(
            "app.database.AsyncSessionLocal",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_db),
                __aexit__=AsyncMock(return_value=False),
            ),
        ):
            await dual_write_sync_run_status(str(uuid4()), 42, "completed")

    @pytest.mark.asyncio
    async def test_sync_run_status_exception_is_swallowed(self):
        """Exceptions are caught and logged (fire-and-forget)."""
        from app.api._mission_cqrs.compat import dual_write_sync_run_status

        with patch(
            "app.database.AsyncSessionLocal", side_effect=RuntimeError("db down")
        ):
            await dual_write_sync_run_status(str(uuid4()), 42, "completed")


class TestDualWriteSyncBlueprint:
    """Verify dual_write_sync_blueprint updates Blueprint fields."""

    @pytest.mark.asyncio
    async def test_sync_blueprint_updates_title(self):
        from app.api._mission_cqrs.compat import dual_write_sync_blueprint

        mock_bp = MagicMock()
        mock_bp.title = "Old Title"
        mock_bp.updated_at = None

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=mock_bp),
                scalars=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=mock_bp))
                ),
            )
        )
        mock_db.commit = AsyncMock()

        with patch(
            "app.database.AsyncSessionLocal",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_db),
                __aexit__=AsyncMock(return_value=False),
            ),
        ):
            await dual_write_sync_blueprint(str(uuid4()), 42, title="New Title")

        assert mock_bp.title == "New Title"
        assert mock_bp.updated_at is not None
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sync_blueprint_no_blueprint_is_noop(self):
        from app.api._mission_cqrs.compat import dual_write_sync_blueprint

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=None),
                scalars=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=None))
                ),
            )
        )

        with patch(
            "app.database.AsyncSessionLocal",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_db),
                __aexit__=AsyncMock(return_value=False),
            ),
        ):
            await dual_write_sync_blueprint(str(uuid4()), 42, title="Ignored")

    @pytest.mark.asyncio
    async def test_sync_blueprint_exception_is_swallowed(self):
        from app.api._mission_cqrs.compat import dual_write_sync_blueprint

        with patch(
            "app.database.AsyncSessionLocal", side_effect=RuntimeError("db down")
        ):
            await dual_write_sync_blueprint(str(uuid4()), 42, title="Nope")


class TestDualWriteSoftDeleteBlueprint:
    """Verify dual_write_soft_delete_blueprint soft-deletes the Blueprint."""

    @pytest.mark.asyncio
    async def test_soft_delete_sets_deleted_at(self):
        from app.api._mission_cqrs.compat import dual_write_soft_delete_blueprint

        mock_bp = MagicMock()
        mock_bp.deleted_at = None
        mock_bp.deleted_by = None

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=mock_bp),
                scalars=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=mock_bp))
                ),
            )
        )
        mock_db.commit = AsyncMock()

        with patch(
            "app.database.AsyncSessionLocal",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_db),
                __aexit__=AsyncMock(return_value=False),
            ),
        ):
            await dual_write_soft_delete_blueprint(str(uuid4()), 42)

        assert mock_bp.deleted_at is not None
        assert mock_bp.deleted_by == 42
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_soft_delete_no_blueprint_is_noop(self):
        from app.api._mission_cqrs.compat import dual_write_soft_delete_blueprint

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(
            return_value=MagicMock(
                scalar_one_or_none=MagicMock(return_value=None),
                scalars=MagicMock(
                    return_value=MagicMock(first=MagicMock(return_value=None))
                ),
            )
        )

        with patch(
            "app.database.AsyncSessionLocal",
            return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_db),
                __aexit__=AsyncMock(return_value=False),
            ),
        ):
            await dual_write_soft_delete_blueprint(str(uuid4()), 42)

    @pytest.mark.asyncio
    async def test_soft_delete_exception_is_swallowed(self):
        from app.api._mission_cqrs.compat import dual_write_soft_delete_blueprint

        with patch(
            "app.database.AsyncSessionLocal", side_effect=RuntimeError("db down")
        ):
            await dual_write_soft_delete_blueprint(str(uuid4()), 42)
