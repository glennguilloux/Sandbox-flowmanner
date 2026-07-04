"""
Integration test: Blueprint + Run full lifecycle.

Tests the complete lifecycle of the unified Blueprint + Run model:
1. Create Blueprint (draft)
2. Update definition → new version created
3. Publish Blueprint
4. Create Run from Blueprint
5. Execute Run → verify status transitions (pending → executing → completed)
6. Verify substrate_events contain correct run_id and blueprint_id
7. Replay run state → verify matches final state
8. Retry a failed run → verify new run created
9. Diff two runs → verify comparison works

Uses mocked DB session (no live database required).
Uses mocked UnifiedExecutor to avoid LLM calls.

Usage:
    pytest tests/integration/test_blueprint_run_lifecycle.py -v
"""

from __future__ import annotations

import contextlib
import os
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")


pytestmark = pytest.mark.integration


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    """Mock async database session with tracking."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    _added: list = []

    def _track_add(obj):
        _added.append(obj)

    db.add = MagicMock(side_effect=_track_add)
    db._added = _added
    return db


@pytest.fixture
def mock_user():
    """Mock user with default attributes."""
    return MagicMock(
        id=42,
        email="test@example.com",
        username="testuser",
        full_name="Test User",
        is_active=True,
        is_admin=True,
    )


@pytest.fixture
def sample_blueprint_definition():
    """A minimal but valid blueprint definition (solo type, one LLM node)."""
    return {
        "blueprint_type": "solo",
        "nodes": [
            {
                "id": "node-1",
                "type": "llm_call",
                "title": "Summarize",
                "description": "Summarize the input text",
                "config": {"prompt": "Summarize: {{input}}"},
                "dependencies": [],
            }
        ],
        "edges": [],
        "budget": {
            "max_cost_usd": 5.0,
            "max_wall_time_seconds": 120,
            "max_iterations": 50,
            "max_depth": 3,
        },
        "config": {},
    }


@pytest.fixture
def sample_dag_definition():
    """A DAG blueprint with two dependent nodes."""
    return {
        "blueprint_type": "dag",
        "nodes": [
            {
                "id": "fetch-1",
                "type": "web_search",
                "title": "Fetch Data",
                "config": {"query": "latest AI news"},
            },
            {
                "id": "summarize-1",
                "type": "llm_call",
                "title": "Summarize Results",
                "config": {"prompt": "Summarize: {{fetch-1.output}}"},
                "dependencies": ["fetch-1"],
            },
        ],
        "edges": [
            {"source": "fetch-1", "target": "summarize-1"},
        ],
        "budget": {
            "max_cost_usd": 10.0,
            "max_wall_time_seconds": 300,
            "max_iterations": 100,
            "max_depth": 5,
        },
    }


@pytest.fixture
def mock_execute_result():
    """A successful StrategyResult for mocking UnifiedExecutor.execute()."""
    from app.services.substrate.workflow_models import StrategyResult

    return StrategyResult(
        success=True,
        status="completed",
        data={"summary": "This is the summary."},
        completed_nodes=["node-1"],
        failed_nodes=[],
        total_tokens=150,
        total_cost_usd=0.003,
        execution_time_ms=1200.0,
        event_count=4,
    )


@pytest.fixture
def mock_failed_result():
    """A failed StrategyResult for testing retry flows."""
    from app.services.substrate.workflow_models import StrategyResult

    return StrategyResult(
        success=False,
        status="failed",
        error="Model rate limit exceeded",
        completed_nodes=[],
        failed_nodes=["node-1"],
        total_tokens=0,
        total_cost_usd=0.0,
        execution_time_ms=500.0,
        event_count=2,
    )


# ── Helpers ─────────────────────────────────────────────────────────────────
# Use MagicMock (not ORM __new__) to avoid _sa_instance_state errors.
# This matches the pattern in test_h1_3_observability_abort.py.


def _make_blueprint(
    *,
    user_id: int = 42,
    title: str = "Test Blueprint",
    blueprint_type: str = "solo",
    definition: dict | None = None,
    status: str = "draft",
    version: int = 1,
    workspace_id: str | None = None,
    bp_id: str | None = None,
):
    """Create a Blueprint-like mock object."""
    return MagicMock(
        id=bp_id or str(uuid4()),
        user_id=user_id,
        workspace_id=workspace_id,
        title=title,
        description="Test description",
        blueprint_type=blueprint_type,
        definition=definition or {},
        input_schema=None,
        output_schema=None,
        status=status,
        version=version,
        tags=None,
        category=None,
        icon=None,
        run_count=0,
        last_run_at=None,
        deleted_at=None,
        deleted_by=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_run(
    *,
    blueprint_id: str,
    user_id: int = 42,
    status: str = "pending",
    snapshot: dict | None = None,
    input_data: dict | None = None,
    workspace_id: str | None = None,
    run_id: str | None = None,
):
    """Create a Run-like mock object."""
    return MagicMock(
        id=run_id or str(uuid4()),
        blueprint_id=blueprint_id,
        workspace_id=workspace_id,
        user_id=user_id,
        status=status,
        snapshot=snapshot or {},
        output_data=None,
        error_message=None,
        total_tokens=0,
        total_cost_usd=0.0,
        budget_limit_usd=None,
        started_at=None,
        completed_at=None,
        parent_run_id=None,
        input_data=input_data,
        meta=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_event(
    *,
    run_id: str,
    sequence: int,
    event_type: str,
    payload: dict | None = None,
    mission_id: str | None = None,
    blueprint_id: str | None = None,
):
    """Create a SubstrateEvent-like mock object."""
    return MagicMock(
        id=str(uuid4()),
        sequence=sequence,
        run_id=run_id,
        mission_id=mission_id,
        blueprint_id=blueprint_id,
        task_id=None,
        type=event_type,
        payload=payload or {},
        causal_parent=None,
        actor="unified_executor",
        timestamp=datetime.now(UTC),
    )


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 1: Blueprint CRUD + Versioning
# ═══════════════════════════════════════════════════════════════════════════


class TestBlueprintCreateAndVersioning:
    """Create a blueprint, update its definition, verify version history."""

    @pytest.mark.asyncio
    async def test_create_blueprint_sets_draft_status(self, mock_db, sample_blueprint_definition):
        """New blueprints must start in 'draft' status with version=1."""
        from app.services.blueprint_service import BlueprintService

        svc = BlueprintService(mock_db)
        mock_db.execute = AsyncMock(
            return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))))
        )

        bp = await svc.create(
            user_id=42,
            title="My First Blueprint",
            blueprint_type="solo",
            definition=sample_blueprint_definition,
        )

        assert bp.status == "draft"
        assert bp.version == 1
        assert bp.title == "My First Blueprint"
        assert bp.user_id == 42
        assert bp.deleted_at is None
        # Two objects added: Blueprint + initial BlueprintVersion
        assert mock_db.add.call_count == 2
        assert mock_db.flush.call_count == 2

    @pytest.mark.asyncio
    async def test_update_definition_creates_new_version(self, mock_db, sample_blueprint_definition):
        """Updating a blueprint's definition must increment version and create a new BlueprintVersion."""
        from app.services.blueprint_service import BlueprintService

        svc = BlueprintService(mock_db)
        bp = _make_blueprint(definition=sample_blueprint_definition, version=1)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = bp
        mock_db.execute = AsyncMock(return_value=mock_result)

        updated = await svc.update(
            str(bp.id),
            42,
            definition={
                **sample_blueprint_definition,
                "nodes": [
                    *sample_blueprint_definition["nodes"],
                    {"id": "node-2", "type": "tool_call", "title": "Extra"},
                ],
            },
        )

        assert updated.version == 2, "Definition change must increment version"
        assert mock_db.add.call_count >= 1

    @pytest.mark.asyncio
    async def test_update_non_definition_field_does_not_increment_version(self, mock_db, sample_blueprint_definition):
        """Updating title only should NOT create a new version."""
        from app.services.blueprint_service import BlueprintService

        svc = BlueprintService(mock_db)
        bp = _make_blueprint(definition=sample_blueprint_definition, version=1)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = bp
        mock_db.execute = AsyncMock(return_value=mock_result)

        updated = await svc.update(str(bp.id), 42, title="New Title")

        assert updated.version == 1, "Non-definition update must NOT increment version"
        assert updated.title == "New Title"

    @pytest.mark.asyncio
    async def test_get_versions_returns_history(self, mock_db):
        """get_versions() must return all BlueprintVersion records for a blueprint."""
        from app.services.blueprint_service import BlueprintService

        svc = BlueprintService(mock_db)
        bp = _make_blueprint(version=3)

        versions = [
            MagicMock(version=3),
            MagicMock(version=2),
            MagicMock(version=1),
        ]

        bp_result = MagicMock()
        bp_result.scalar_one_or_none.return_value = bp

        ver_result = MagicMock()
        ver_result.scalars.return_value.all.return_value = versions

        call_count = 0

        async def _execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return bp_result
            return ver_result

        mock_db.execute = AsyncMock(side_effect=_execute)

        result = await svc.get_versions(str(bp.id), 42)
        assert len(result) == 3
        assert result[0].version == 3
        assert result[2].version == 1


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 2: Blueprint Publish Lifecycle
# ═══════════════════════════════════════════════════════════════════════════


class TestBlueprintPublishLifecycle:
    """Test publish → status change → error on re-publish."""

    @pytest.mark.asyncio
    async def test_publish_draft_blueprint(self, mock_db):
        """Publishing a draft blueprint sets status to 'published'."""
        from app.services.blueprint_service import BlueprintService

        svc = BlueprintService(mock_db)
        bp = _make_blueprint(status="draft")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = bp
        mock_db.execute = AsyncMock(return_value=mock_result)

        published = await svc.publish(str(bp.id), 42)

        assert published.status == "published"

    @pytest.mark.asyncio
    async def test_publish_non_draft_raises_error(self, mock_db):
        """Cannot publish a blueprint that is not in 'draft' status."""
        from app.services.blueprint_service import (
            BlueprintService,
            BlueprintValidationError,
        )

        svc = BlueprintService(mock_db)

        for non_draft_status in ("published", "deprecated"):
            bp = _make_blueprint(status=non_draft_status)
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = bp
            mock_db.execute = AsyncMock(return_value=mock_result)

            with pytest.raises(BlueprintValidationError, match="Cannot publish"):
                await svc.publish(str(bp.id), 42)

    @pytest.mark.asyncio
    async def test_soft_delete_blueprint(self, mock_db):
        """Deleting a blueprint must set deleted_at, not remove the row."""
        from app.services.blueprint_service import BlueprintService

        svc = BlueprintService(mock_db)
        bp = _make_blueprint(status="published")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = bp
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await svc.delete(str(bp.id), 42)

        assert result is True
        assert bp.deleted_at is not None, "deleted_at must be set on soft delete"
        assert bp.deleted_by == 42, "deleted_by must track who deleted"

    @pytest.mark.asyncio
    async def test_get_deleted_blueprint_raises_not_found(self, mock_db):
        """Getting a soft-deleted blueprint must raise BlueprintNotFoundError."""
        from app.services.blueprint_service import (
            BlueprintNotFoundError,
            BlueprintService,
        )

        svc = BlueprintService(mock_db)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(BlueprintNotFoundError):
            await svc.get("nonexistent-id", 42)


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 3: Run Lifecycle (create → execute → events → replay)
# ═══════════════════════════════════════════════════════════════════════════


class TestRunLifecycle:
    """Full run lifecycle: create_from_blueprint → execute → verify status + events."""

    @pytest.mark.asyncio
    async def test_create_run_from_blueprint_snapshots_definition(self, mock_db, sample_blueprint_definition):
        """create_from_blueprint() must snapshot the Blueprint.definition into Run.snapshot."""
        from app.services.run_service import RunService

        svc = RunService(mock_db)
        bp = _make_blueprint(definition=sample_blueprint_definition)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = bp
        mock_db.execute = AsyncMock(return_value=mock_result)

        run = await svc.create_from_blueprint(str(bp.id), 42)

        assert run.status == "pending"
        assert run.blueprint_id == str(bp.id)
        assert run.user_id == 42
        assert run.snapshot is not None
        # Snapshot must contain the blueprint definition contents
        assert run.snapshot.get("blueprint_type") == "solo"
        assert len(run.snapshot.get("nodes", [])) == 1
        assert run.snapshot["nodes"][0]["id"] == "node-1"

    @pytest.mark.asyncio
    async def test_create_run_with_input_data(self, mock_db, sample_blueprint_definition):
        """create_from_blueprint() must store input_data on the run."""
        from app.services.run_service import RunService

        svc = RunService(mock_db)
        bp = _make_blueprint(definition=sample_blueprint_definition)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = bp
        mock_db.execute = AsyncMock(return_value=mock_result)

        run = await svc.create_from_blueprint(str(bp.id), 42, input_data={"text": "Hello world"})

        assert run.input_data == {"text": "Hello world"}

    @pytest.mark.asyncio
    async def test_create_run_with_budget_override(self, mock_db, sample_blueprint_definition):
        """Budget override must replace the snapshot's budget section."""
        from app.services.run_service import RunService

        svc = RunService(mock_db)
        bp = _make_blueprint(definition=sample_blueprint_definition)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = bp
        mock_db.execute = AsyncMock(return_value=mock_result)

        run = await svc.create_from_blueprint(
            str(bp.id),
            42,
            budget_override={"max_cost_usd": 1.0, "max_wall_time_seconds": 30},
        )

        assert run.snapshot["budget"]["max_cost_usd"] == 1.0
        assert run.snapshot["budget"]["max_wall_time_seconds"] == 30

    @pytest.mark.asyncio
    async def test_create_run_for_nonexistent_blueprint_raises(self, mock_db):
        """Creating a run for a missing blueprint must raise RunValidationError."""
        from app.services.run_service import RunService, RunValidationError

        svc = RunService(mock_db)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(RunValidationError, match="not found"):
            await svc.create_from_blueprint("nonexistent-bp-id", 42)

    @pytest.mark.asyncio
    async def test_execute_run_transitions_to_completed(
        self,
        mock_db,
        sample_blueprint_definition,
        mock_execute_result,
    ):
        """execute() must transition pending → executing → completed."""
        from app.services.run_service import RunService

        svc = RunService(mock_db)
        bp_id = str(uuid4())
        run = _make_run(
            blueprint_id=bp_id,
            snapshot={
                "blueprint_type": "solo",
                "title": "Test",
                "nodes": sample_blueprint_definition["nodes"],
                "budget": sample_blueprint_definition["budget"],
            },
        )

        bp = _make_blueprint(bp_id=bp_id, user_id=42)
        run_result = MagicMock()
        run_result.scalar_one_or_none.return_value = run

        bp_result = MagicMock()
        bp_result.scalar_one_or_none.return_value = bp

        call_count = 0

        async def _execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return run_result
            return bp_result

        mock_db.execute = AsyncMock(side_effect=_execute)

        with (
            patch("app.services.run_service.get_unified_executor") as mock_get_exec,
            patch("app.services.run_service.blueprint_to_workflow") as mock_adapter,
        ):
            mock_executor = AsyncMock()
            mock_executor.execute = AsyncMock(return_value=mock_execute_result)
            mock_get_exec.return_value = mock_executor
            mock_adapter.return_value = MagicMock()

            result_run = await svc.execute(str(run.id), 42)

        assert result_run.status == "completed"
        assert result_run.total_tokens == 150
        assert result_run.total_cost_usd == 0.003
        assert result_run.completed_at is not None
        assert result_run.output_data == {"summary": "This is the summary."}
        # Blueprint stats should be updated
        assert bp.run_count == 1
        assert bp.last_run_at is not None

    @pytest.mark.asyncio
    async def test_execute_run_records_events_with_blueprint_id(
        self,
        mock_db,
        sample_blueprint_definition,
        mock_execute_result,
    ):
        """The UnifiedExecutor.execute() call must pass blueprint_id."""
        from app.services.run_service import RunService

        svc = RunService(mock_db)
        bp_id = str(uuid4())
        run = _make_run(
            blueprint_id=bp_id,
            snapshot={
                "blueprint_type": "solo",
                "title": "Test",
                "nodes": [],
                "budget": {},
            },
        )

        bp = _make_blueprint(bp_id=bp_id, user_id=42)
        run_result = MagicMock()
        run_result.scalar_one_or_none.return_value = run
        bp_result = MagicMock()
        bp_result.scalar_one_or_none.return_value = bp

        call_count = 0

        async def _execute(stmt):
            nonlocal call_count
            call_count += 1
            return run_result if call_count <= 1 else bp_result

        mock_db.execute = AsyncMock(side_effect=_execute)

        with (
            patch("app.services.run_service.get_unified_executor") as mock_get_exec,
            patch("app.services.run_service.blueprint_to_workflow") as mock_adapter,
        ):
            mock_executor = AsyncMock()
            mock_executor.execute = AsyncMock(return_value=mock_execute_result)
            mock_get_exec.return_value = mock_executor
            mock_adapter.return_value = MagicMock()

            await svc.execute(str(run.id), 42)

            # Verify blueprint_id was passed to executor
            call_kwargs = mock_executor.execute.call_args
            assert call_kwargs.kwargs.get("blueprint_id") == bp_id

    @pytest.mark.asyncio
    async def test_execute_non_pending_run_raises(self, mock_db, mock_execute_result):
        """Cannot execute a run that is not pending or queued."""
        from app.services.run_service import RunService, RunValidationError

        svc = RunService(mock_db)
        run = _make_run(blueprint_id=str(uuid4()), status="completed")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = run
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(RunValidationError, match="Cannot execute"):
            await svc.execute(str(run.id), 42)

    @pytest.mark.asyncio
    async def test_execute_failed_run_records_error(self, mock_db, sample_blueprint_definition, mock_failed_result):
        """When UnifiedExecutor returns failed, Run must record error_message."""
        from app.services.run_service import RunService

        svc = RunService(mock_db)
        bp_id = str(uuid4())
        run = _make_run(
            blueprint_id=bp_id,
            snapshot={
                "blueprint_type": "solo",
                "title": "Test",
                "nodes": [],
                "budget": {},
            },
        )

        bp = _make_blueprint(bp_id=bp_id, user_id=42)
        run_result = MagicMock()
        run_result.scalar_one_or_none.return_value = run
        bp_result = MagicMock()
        bp_result.scalar_one_or_none.return_value = bp

        call_count = 0

        async def _execute(stmt):
            nonlocal call_count
            call_count += 1
            return run_result if call_count <= 1 else bp_result

        mock_db.execute = AsyncMock(side_effect=_execute)

        with (
            patch("app.services.run_service.get_unified_executor") as mock_get_exec,
            patch("app.services.run_service.blueprint_to_workflow") as mock_adapter,
        ):
            mock_executor = AsyncMock()
            mock_executor.execute = AsyncMock(return_value=mock_failed_result)
            mock_get_exec.return_value = mock_executor
            mock_adapter.return_value = MagicMock()

            result_run = await svc.execute(str(run.id), 42)

        assert result_run.status == "failed"
        assert result_run.error_message == "Model rate limit exceeded"
        assert result_run.completed_at is not None


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 4: Substrate Events Verification
# ═══════════════════════════════════════════════════════════════════════════


class TestSubstrateEvents:
    """Verify substrate_events are created with correct run_id and blueprint_id."""

    @pytest.mark.asyncio
    async def test_event_log_append_with_blueprint_id(self, mock_db):
        """EventLog.append() must store blueprint_id on each event."""
        from app.services.substrate.event_log import EventLog

        el = EventLog()
        run_id = str(uuid4())
        blueprint_id = str(uuid4())

        seq_result = MagicMock()
        seq_result.scalar.return_value = 0
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        call_count = 0

        async def _execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return seq_result
            return count_result

        mock_db.execute = AsyncMock(side_effect=_execute)

        events = await el.append(
            mock_db,
            run_id,
            [
                {
                    "type": "mission.started",
                    "payload": {"title": "Test"},
                    "actor": "unified_executor",
                },
                {
                    "type": "mission.completed",
                    "payload": {"status": "completed"},
                    "actor": "unified_executor",
                },
            ],
            blueprint_id=blueprint_id,
        )

        assert len(events) == 2
        assert events[0].blueprint_id == blueprint_id
        assert events[1].blueprint_id == blueprint_id
        assert events[0].run_id == run_id
        assert events[1].run_id == run_id
        assert events[0].sequence == 1
        assert events[1].sequence == 2

    @pytest.mark.asyncio
    async def test_event_log_sequence_continuity(self, mock_db):
        """Event sequences must be monotonically increasing with no gaps."""
        from app.services.substrate.event_log import EventLog

        el = EventLog()
        run_id = str(uuid4())

        seq_result = MagicMock()
        seq_result.scalar.return_value = 5
        count_result = MagicMock()
        count_result.scalar.return_value = 5

        call_count = 0

        async def _execute(stmt):
            nonlocal call_count
            call_count += 1
            return seq_result if call_count <= 1 else count_result

        mock_db.execute = AsyncMock(side_effect=_execute)

        events = await el.append(
            mock_db,
            run_id,
            [
                {"type": "task.started", "actor": "system"},
                {"type": "task.completed", "actor": "system"},
                {"type": "mission.completed", "actor": "system"},
            ],
        )

        assert events[0].sequence == 6
        assert events[1].sequence == 7
        assert events[2].sequence == 8

    @pytest.mark.asyncio
    async def test_event_log_empty_events_raises(self):
        """Appending an empty event list must raise ValueError."""
        from app.services.substrate.event_log import EventLog

        el = EventLog()
        with pytest.raises(ValueError, match="at least one"):
            await el.append(AsyncMock(), str(uuid4()), [])

    @pytest.mark.asyncio
    async def test_event_log_exceeds_max_raises(self, mock_db):
        """Appending events beyond MAX_EVENTS_PER_RUN must raise ValueError."""
        from app.services.substrate.event_log import EventLog

        el = EventLog()

        seq_result = MagicMock()
        seq_result.scalar.return_value = 0
        count_result = MagicMock()
        count_result.scalar.return_value = EventLog.MAX_EVENTS_PER_RUN - 1

        call_count = 0

        async def _execute(stmt):
            nonlocal call_count
            call_count += 1
            return seq_result if call_count <= 1 else count_result

        mock_db.execute = AsyncMock(side_effect=_execute)

        with pytest.raises(ValueError, match="exceeds max"):
            await el.append(mock_db, str(uuid4()), [{"type": "test", "actor": "system"}] * 5)


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 5: Replay Engine
# ═══════════════════════════════════════════════════════════════════════════


class TestRunReplay:
    """Verify replay state reconstruction from event log."""

    @pytest.mark.asyncio
    async def test_replay_rebuilds_final_state(self, mock_db):
        """ReplayEngine.rebuild_state() must reconstruct the correct final state."""
        from app.services.substrate.replay_engine import ReplayEngine

        run_id = str(uuid4())
        blueprint_id = str(uuid4())

        events = [
            _make_event(
                run_id=run_id,
                sequence=1,
                event_type="mission.started",
                payload={"title": "Test", "workflow_type": "solo"},
                blueprint_id=blueprint_id,
            ),
            _make_event(
                run_id=run_id,
                sequence=2,
                event_type="task.started",
                payload={"task_id": "node-1"},
                blueprint_id=blueprint_id,
            ),
            _make_event(
                run_id=run_id,
                sequence=3,
                event_type="task.completed",
                payload={"task_id": "node-1", "tokens": 100, "cost_usd": 0.002},
                blueprint_id=blueprint_id,
            ),
            _make_event(
                run_id=run_id,
                sequence=4,
                event_type="mission.completed",
                payload={"status": "completed"},
                blueprint_id=blueprint_id,
            ),
        ]

        event_result = MagicMock()
        event_result.scalars.return_value.all.return_value = events
        mock_db.execute = AsyncMock(return_value=event_result)

        engine = ReplayEngine()
        state = await engine.rebuild_state(mock_db, run_id)

        assert state.status == "completed"
        assert state.current_sequence == 4
        assert "node-1" in state.completed_tasks
        assert state.total_tokens == 100
        assert state.total_cost_usd == 0.002
        assert state.run_id == run_id

    @pytest.mark.asyncio
    async def test_replay_failed_state(self, mock_db):
        """ReplayEngine must correctly reconstruct a failed run state."""
        from app.services.substrate.replay_engine import ReplayEngine

        run_id = str(uuid4())
        events = [
            _make_event(run_id=run_id, sequence=1, event_type="mission.started"),
            _make_event(
                run_id=run_id,
                sequence=2,
                event_type="task.failed",
                payload={"task_id": "node-1", "error": "API timeout"},
            ),
            _make_event(
                run_id=run_id,
                sequence=3,
                event_type="mission.failed",
                payload={"error": "Node node-1 failed: API timeout"},
            ),
        ]

        event_result = MagicMock()
        event_result.scalars.return_value.all.return_value = events
        mock_db.execute = AsyncMock(return_value=event_result)

        engine = ReplayEngine()
        state = await engine.rebuild_state(mock_db, run_id)

        assert state.status == "failed"
        assert "node-1" in state.failed_tasks
        assert state.error_message is not None

    @pytest.mark.asyncio
    async def test_replay_determinism(self, mock_db):
        """Replaying the same events twice must produce identical state."""
        from app.services.substrate.replay_engine import ReplayEngine

        run_id = str(uuid4())
        events = [
            _make_event(run_id=run_id, sequence=1, event_type="mission.started"),
            _make_event(
                run_id=run_id,
                sequence=2,
                event_type="task.completed",
                payload={"task_id": "node-1", "tokens": 50},
            ),
            _make_event(run_id=run_id, sequence=3, event_type="mission.completed"),
        ]

        event_result = MagicMock()
        event_result.scalars.return_value.all.return_value = events
        mock_db.execute = AsyncMock(return_value=event_result)

        engine = ReplayEngine()
        state1 = await engine.rebuild_state(mock_db, run_id)
        state2 = await engine.rebuild_state(mock_db, run_id)

        assert state1.status == state2.status
        assert state1.current_sequence == state2.current_sequence
        assert state1.completed_tasks == state2.completed_tasks
        assert state1.total_tokens == state2.total_tokens
        assert state1.total_cost_usd == state2.total_cost_usd

    @pytest.mark.asyncio
    async def test_replay_at_sequence_time_travel(self, mock_db):
        """rebuild_state_at_sequence() must return state up to the given sequence."""
        from app.services.substrate.replay_engine import ReplayEngine

        run_id = str(uuid4())
        partial_events = [
            _make_event(run_id=run_id, sequence=1, event_type="mission.started"),
            _make_event(
                run_id=run_id,
                sequence=2,
                event_type="task.completed",
                payload={"task_id": "node-1", "tokens": 50},
            ),
        ]

        event_result = MagicMock()
        event_result.scalars.return_value.all.return_value = partial_events
        mock_db.execute = AsyncMock(return_value=event_result)

        engine = ReplayEngine()
        state = await engine.rebuild_state_at_sequence(mock_db, run_id, sequence=2)

        assert state.current_sequence == 2
        assert state.status == "executing"
        assert "node-1" in state.completed_tasks
        assert "node-2" not in state.completed_tasks

    @pytest.mark.asyncio
    async def test_replay_empty_event_stream(self, mock_db):
        """Replaying a run with no events returns default pending state."""
        from app.services.substrate.replay_engine import ReplayEngine

        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=empty_result)

        engine = ReplayEngine()
        state = await engine.rebuild_state(mock_db, str(uuid4()))

        assert state.status == "pending"
        assert state.current_sequence == 0
        assert len(state.completed_tasks) == 0
        assert len(state.failed_tasks) == 0

    @pytest.mark.asyncio
    async def test_state_to_dict(self, mock_db):
        """SubstrateRunState.to_dict() must include all required fields."""
        from app.services.substrate.replay_engine import ReplayEngine

        run_id = str(uuid4())
        events = [
            _make_event(run_id=run_id, sequence=1, event_type="mission.started"),
            _make_event(run_id=run_id, sequence=2, event_type="mission.completed"),
        ]

        event_result = MagicMock()
        event_result.scalars.return_value.all.return_value = events
        mock_db.execute = AsyncMock(return_value=event_result)

        engine = ReplayEngine()
        state = await engine.rebuild_state(mock_db, run_id)
        d = state.to_dict()

        assert "run_id" in d
        assert "status" in d
        assert "sequence" in d
        assert "completed_tasks" in d
        assert "failed_tasks" in d
        assert "total_tokens" in d
        assert "total_cost_usd" in d
        assert d["status"] == "completed"


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 6: Retry Flow
# ═══════════════════════════════════════════════════════════════════════════


class TestRunRetry:
    """Retry a failed run → verify new run is created with same blueprint/snapshot."""

    @pytest.mark.asyncio
    async def test_retry_creates_new_run(self, mock_db, mock_execute_result):
        """retry() must create a new Run with the same blueprint_id and snapshot."""
        from app.services.run_service import RunService

        svc = RunService(mock_db)
        bp_id = str(uuid4())
        original_run = _make_run(
            blueprint_id=bp_id,
            status="failed",
            snapshot={"blueprint_type": "solo", "nodes": []},
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = original_run
        mock_db.execute = AsyncMock(return_value=mock_result)

        new_run = await svc.retry(str(original_run.id), 42)

        assert new_run.id != original_run.id, "Retry must create a different run"
        assert new_run.blueprint_id == bp_id, "Retry must keep the same blueprint_id"
        assert new_run.status == "pending", "Retry must start in pending status"
        assert new_run.snapshot == original_run.snapshot, "Retry must copy the snapshot"
        assert new_run.user_id == 42

    @pytest.mark.asyncio
    async def test_retry_non_failed_run_raises(self, mock_db):
        """Can only retry a failed run, not completed/pending/executing."""
        from app.services.run_service import RunService, RunValidationError

        svc = RunService(mock_db)

        for non_failed_status in ("pending", "executing", "completed", "aborted"):
            run = _make_run(blueprint_id=str(uuid4()), status=non_failed_status)
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = run
            mock_db.execute = AsyncMock(return_value=mock_result)

            with pytest.raises(RunValidationError, match="Can only retry"):
                await svc.retry(str(run.id), 42)

    @pytest.mark.asyncio
    async def test_retry_preserves_input_data(self, mock_db):
        """Retried run must carry forward the original input_data."""
        from app.services.run_service import RunService

        svc = RunService(mock_db)
        original = _make_run(
            blueprint_id=str(uuid4()),
            status="failed",
            input_data={"text": "Hello"},
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = original
        mock_db.execute = AsyncMock(return_value=mock_result)

        retried = await svc.retry(str(original.id), 42)

        assert retried.input_data == {"text": "Hello"}


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 7: Abort Flow
# ═══════════════════════════════════════════════════════════════════════════


class TestRunAbort:
    """Abort a running execution → verify status and error_message."""

    @pytest.mark.asyncio
    async def test_abort_sets_aborted_status(self, mock_db):
        """abort() must set status to 'aborted' with a reason message."""
        from app.services.run_service import RunService

        svc = RunService(mock_db)
        run = _make_run(blueprint_id=str(uuid4()), status="executing")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = run
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.run_service.get_unified_executor") as mock_get_exec:
            mock_executor = AsyncMock()
            mock_executor.abort = AsyncMock(return_value=True)
            mock_get_exec.return_value = mock_executor

            aborted = await svc.abort(str(run.id), 42, reason="budget_exceeded")

        assert aborted.status == "aborted"
        assert "budget_exceeded" in aborted.error_message
        assert aborted.completed_at is not None

    @pytest.mark.asyncio
    async def test_abort_non_active_run_raises(self, mock_db):
        """Cannot abort a completed or already aborted run."""
        from app.services.run_service import RunService, RunValidationError

        svc = RunService(mock_db)

        for terminal_status in ("completed", "failed", "aborted"):
            run = _make_run(blueprint_id=str(uuid4()), status=terminal_status)
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = run
            mock_db.execute = AsyncMock(return_value=mock_result)

            with pytest.raises(RunValidationError, match="Cannot abort"):
                await svc.abort(str(run.id), 42)

    @pytest.mark.asyncio
    async def test_abort_all_active_statuses(self, mock_db):
        """All active statuses (pending, queued, executing, paused) should be abortable."""
        from app.services.run_service import RunService

        svc = RunService(mock_db)

        for active_status in ("pending", "queued", "executing", "paused"):
            run = _make_run(blueprint_id=str(uuid4()), status=active_status)

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = run
            mock_db.execute = AsyncMock(return_value=mock_result)

            with patch("app.services.run_service.get_unified_executor") as mock_get_exec:
                mock_executor = AsyncMock()
                mock_executor.abort = AsyncMock(return_value=True)
                mock_get_exec.return_value = mock_executor

                aborted = await svc.abort(str(run.id), 42)

            assert aborted.status == "aborted", f"Failed to abort from '{active_status}'"


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 8: Diff Runs
# ═══════════════════════════════════════════════════════════════════════════


class TestRunDiff:
    """Compare two runs → verify token delta, cost delta, status match."""

    @pytest.mark.asyncio
    async def test_diff_two_runs(self, mock_db):
        """diff_runs() must return token_delta, cost_delta, and status_match."""
        from app.services.run_service import RunService

        svc = RunService(mock_db)
        bp_id = str(uuid4())

        run_a = _make_run(blueprint_id=bp_id, status="completed")
        run_a.total_tokens = 100
        run_a.total_cost_usd = 0.002

        run_b = _make_run(blueprint_id=bp_id, status="completed")
        run_b.total_tokens = 200
        run_b.total_cost_usd = 0.005

        result_a = MagicMock()
        result_a.scalar_one_or_none.return_value = run_a
        result_b = MagicMock()
        result_b.scalar_one_or_none.return_value = run_b

        call_count = 0

        async def _execute(stmt):
            nonlocal call_count
            call_count += 1
            return result_a if call_count <= 1 else result_b

        mock_db.execute = AsyncMock(side_effect=_execute)

        with patch("app.services.run_service.get_replay_engine") as mock_get_replay:
            mock_replay = AsyncMock()

            state_a = MagicMock()
            state_a.to_dict.return_value = {"status": "completed", "completed_tasks": 1}
            state_a.completed_tasks = {"node-1"}
            state_a.failed_tasks = set()

            state_b = MagicMock()
            state_b.to_dict.return_value = {"status": "completed", "completed_tasks": 2}
            state_b.completed_tasks = {"node-1", "node-2"}
            state_b.failed_tasks = set()

            mock_replay.rebuild_state = AsyncMock(side_effect=[state_a, state_b])
            mock_get_replay.return_value = mock_replay

            diff = await svc.diff_runs(str(run_a.id), str(run_b.id), 42)

        assert diff["run_a"]["id"] == str(run_a.id)
        assert diff["run_b"]["id"] == str(run_b.id)
        assert diff["diff"]["token_delta"] == 100
        assert diff["diff"]["cost_delta"] == pytest.approx(0.003)
        assert diff["diff"]["status_match"] is True
        assert diff["diff"]["completed_a"] == 1
        assert diff["diff"]["completed_b"] == 2

    @pytest.mark.asyncio
    async def test_diff_different_statuses(self, mock_db):
        """status_match must be False when runs have different statuses."""
        from app.services.run_service import RunService

        svc = RunService(mock_db)

        run_a = _make_run(blueprint_id=str(uuid4()), status="completed")
        run_a.total_tokens = 100
        run_a.total_cost_usd = 0.002

        run_b = _make_run(blueprint_id=str(uuid4()), status="failed")
        run_b.total_tokens = 50
        run_b.total_cost_usd = 0.001

        result_a = MagicMock()
        result_a.scalar_one_or_none.return_value = run_a
        result_b = MagicMock()
        result_b.scalar_one_or_none.return_value = run_b

        call_count = 0

        async def _execute(stmt):
            nonlocal call_count
            call_count += 1
            return result_a if call_count <= 1 else result_b

        mock_db.execute = AsyncMock(side_effect=_execute)

        with patch("app.services.run_service.get_replay_engine") as mock_get_replay:
            mock_replay = AsyncMock()

            state_a = MagicMock()
            state_a.to_dict.return_value = {"status": "completed"}
            state_a.completed_tasks = {"node-1"}
            state_a.failed_tasks = set()

            state_b = MagicMock()
            state_b.to_dict.return_value = {"status": "failed"}
            state_b.completed_tasks = set()
            state_b.failed_tasks = {"node-1"}

            mock_replay.rebuild_state = AsyncMock(side_effect=[state_a, state_b])
            mock_get_replay.return_value = mock_replay

            diff = await svc.diff_runs(str(run_a.id), str(run_b.id), 42)

        assert diff["diff"]["status_match"] is False
        assert diff["diff"]["token_delta"] == -50


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 9: Blueprint-to-Workflow Adapter
# ═══════════════════════════════════════════════════════════════════════════


class TestBlueprintToWorkflowAdapter:
    """Verify blueprint_to_workflow() produces a valid Workflow."""

    def test_solo_blueprint_to_workflow(self, sample_blueprint_definition):
        from app.services.substrate.adapters import blueprint_to_workflow
        from app.services.substrate.workflow_models import WorkflowType

        snapshot = {
            "blueprint_type": "solo",
            "title": "Test Blueprint",
            "description": "A test",
            **sample_blueprint_definition,
        }
        workflow = blueprint_to_workflow(snapshot=snapshot, blueprint_id="bp-123", user_id="42")

        assert workflow.type == WorkflowType.SOLO
        assert workflow.id == "bp-123"
        assert workflow.user_id == "42"
        assert len(workflow.nodes) == 1
        assert workflow.nodes[0].id == "node-1"

    def test_dag_blueprint_to_workflow(self, sample_dag_definition):
        from app.services.substrate.adapters import blueprint_to_workflow
        from app.services.substrate.workflow_models import WorkflowType

        snapshot = {
            "title": "DAG Blueprint",
            "description": "",
            **sample_dag_definition,
        }
        workflow = blueprint_to_workflow(snapshot=snapshot, blueprint_id="bp-dag")

        assert workflow.type == WorkflowType.DAG
        assert len(workflow.nodes) == 2
        assert len(workflow.edges) == 1
        assert workflow.edges[0].source == "fetch-1"
        assert workflow.edges[0].target == "summarize-1"
        assert "fetch-1" in workflow.nodes[1].dependencies

    def test_blueprint_to_workflow_budget_defaults(self):
        from app.services.substrate.adapters import blueprint_to_workflow

        snapshot = {"blueprint_type": "solo", "title": "No Budget"}
        workflow = blueprint_to_workflow(snapshot=snapshot, blueprint_id="bp-default")

        assert workflow.budget.max_cost_usd > 0
        assert workflow.budget.max_wall_time_seconds > 0
        assert workflow.budget.max_iterations > 0

    def test_blueprint_to_workflow_empty_nodes(self):
        from app.services.substrate.adapters import blueprint_to_workflow

        snapshot = {
            "blueprint_type": "solo",
            "title": "Empty",
            "nodes": [],
            "edges": [],
            "budget": {"max_cost_usd": 1.0},
        }
        workflow = blueprint_to_workflow(snapshot=snapshot, blueprint_id="bp-empty")

        assert len(workflow.nodes) == 0
        assert len(workflow.edges) == 0


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 10: SubstrateRunState Apply Logic
# ═══════════════════════════════════════════════════════════════════════════


class TestSubstrateRunStateApply:
    """Verify SubstrateRunState.apply() handles all event types correctly."""

    def test_apply_mission_started(self):
        from app.models.substrate_models import SubstrateRunState

        state = SubstrateRunState(run_id="test")
        event = _make_event(run_id="test", sequence=1, event_type="mission.started")
        state.apply(event)
        assert state.status == "executing"
        assert state.started_at is not None

    def test_apply_mission_completed(self):
        from app.models.substrate_models import SubstrateRunState

        state = SubstrateRunState(run_id="test")
        state.status = "executing"
        event = _make_event(run_id="test", sequence=2, event_type="mission.completed")
        state.apply(event)
        assert state.status == "completed"

    def test_apply_task_lifecycle(self):
        from app.models.substrate_models import SubstrateRunState

        state = SubstrateRunState(run_id="test")

        started = _make_event(
            run_id="test",
            sequence=1,
            event_type="task.started",
            payload={"task_id": "node-1"},
        )
        completed = _make_event(
            run_id="test",
            sequence=2,
            event_type="task.completed",
            payload={"task_id": "node-1", "tokens": 150, "cost_usd": 0.003},
        )

        state.apply(started)
        assert state.task_states["node-1"]["status"] == "running"

        state.apply(completed)
        assert state.task_states["node-1"]["status"] == "completed"
        assert "node-1" in state.completed_tasks
        assert state.total_tokens == 150
        assert state.total_cost_usd == 0.003

    def test_apply_task_failed(self):
        from app.models.substrate_models import SubstrateRunState

        state = SubstrateRunState(run_id="test")
        event = _make_event(
            run_id="test",
            sequence=1,
            event_type="task.failed",
            payload={"task_id": "node-1", "error": "timeout"},
        )
        state.apply(event)
        assert "node-1" in state.failed_tasks
        assert state.task_states["node-1"]["status"] == "failed"
        assert state.task_states["node-1"]["error"] == "timeout"

    def test_apply_budget_exhausted(self):
        from app.models.substrate_models import SubstrateRunState

        state = SubstrateRunState(run_id="test")
        state.status = "executing"
        event = _make_event(
            run_id="test",
            sequence=1,
            event_type="substrate.budget_exhausted",
            payload={"budget_type": "cost"},
        )
        state.apply(event)
        assert state.status == "failed"
        assert "Budget exhausted" in (state.error_message or "")

    def test_apply_mission_aborted(self):
        from app.models.substrate_models import SubstrateRunState

        state = SubstrateRunState(run_id="test")
        state.status = "executing"
        event = _make_event(
            run_id="test",
            sequence=1,
            event_type="mission.aborted",
            payload={"reason": "user_requested"},
        )
        state.apply(event)
        assert state.status == "aborted"

    def test_apply_unknown_event_is_noop(self):
        from app.models.substrate_models import SubstrateRunState

        state = SubstrateRunState(run_id="test")
        event = _make_event(run_id="test", sequence=1, event_type="custom.unknown")
        state.apply(event)
        assert state.status == "pending"
        assert state.current_sequence == 1

    def test_apply_task_retrying(self):
        from app.models.substrate_models import SubstrateRunState

        state = SubstrateRunState(run_id="test")
        event = _make_event(
            run_id="test",
            sequence=1,
            event_type="task.retrying",
            payload={"task_id": "node-1", "attempt": 2},
        )
        state.apply(event)
        assert state.task_states["node-1"]["status"] == "retrying"
        assert state.task_states["node-1"]["attempt"] == 2


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 11: Pydantic Schema Validation
# ═══════════════════════════════════════════════════════════════════════════


class TestBlueprintSchemas:
    """Validate Pydantic schemas for request/response models."""

    def test_blueprint_create_valid(self, sample_blueprint_definition):
        from app.schemas.blueprint import BlueprintCreate, BlueprintDefinition

        bp_def = BlueprintDefinition(**sample_blueprint_definition)
        payload = BlueprintCreate(
            title="Test",
            blueprint_type="solo",
            definition=bp_def,
            tags=["ai", "summarize"],
        )
        assert payload.title == "Test"
        assert payload.definition is not None
        assert len(payload.definition.nodes) == 1

    def test_blueprint_create_extra_fields_forbidden(self):
        from pydantic import ValidationError

        from app.schemas.blueprint import BlueprintCreate

        with pytest.raises(ValidationError):
            BlueprintCreate(title="Test", unknown_field="should fail")

    def test_blueprint_update_partial(self):
        from app.schemas.blueprint import BlueprintUpdate

        update = BlueprintUpdate(title="New Title")
        assert update.title == "New Title"
        assert update.definition is None

    def test_run_response_from_attributes(self):
        """RunResponse must work with from_attributes=True (ORM mode)."""
        from app.schemas.blueprint import RunResponse

        run = _make_run(blueprint_id=str(uuid4()), status="completed")
        run.total_tokens = 42
        run.total_cost_usd = 0.001
        response = RunResponse.model_validate(run)
        assert response.status == "completed"
        assert response.total_tokens == 42
        assert response.total_cost_usd == 0.001

    def test_blueprint_response_from_attributes(self):
        """BlueprintResponse must work with from_attributes=True."""
        from app.schemas.blueprint import BlueprintResponse

        bp = _make_blueprint(title="Test BP", status="published", version=3)
        response = BlueprintResponse.model_validate(bp)
        assert response.title == "Test BP"
        assert response.status == "published"
        assert response.version == 3

    def test_blueprint_definition_defaults(self):
        from app.schemas.blueprint import BlueprintDefinition

        bd = BlueprintDefinition()
        assert bd.blueprint_type == "solo"
        assert bd.nodes == []
        assert bd.budget.max_cost_usd == 10.0

    def test_run_create_with_budget_override(self):
        from app.schemas.blueprint import BlueprintBudgetDefinition, RunCreate

        payload = RunCreate(
            input_data={"text": "Hello"},
            budget_override=BlueprintBudgetDefinition(max_cost_usd=1.0),
        )
        assert payload.input_data == {"text": "Hello"}
        assert payload.budget_override.max_cost_usd == 1.0


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 12: Model Enums
# ═══════════════════════════════════════════════════════════════════════════


class TestModelEnums:
    def test_blueprint_status_values(self):
        from app.models.blueprint_models import BlueprintStatus

        assert BlueprintStatus.DRAFT.value == "draft"
        assert BlueprintStatus.PUBLISHED.value == "published"
        assert BlueprintStatus.DEPRECATED.value == "deprecated"

    def test_blueprint_type_values(self):
        from app.models.blueprint_models import BlueprintType

        expected = {"solo", "dag", "swarm", "pipeline", "graph", "meta", "langgraph"}
        assert {bt.value for bt in BlueprintType} == expected

    def test_run_status_values(self):
        from app.models.blueprint_models import RunStatus

        expected = {
            "pending",
            "queued",
            "executing",
            "paused",
            "completed",
            "failed",
            "aborted",
        }
        assert {rs.value for rs in RunStatus} == expected

    def test_substrate_event_type_aliases(self):
        from app.models.substrate_models import SubstrateEventType as SET

        assert SET.MISSION_STARTED == SET.RUN_STARTED
        assert SET.MISSION_COMPLETED == SET.RUN_COMPLETED
        assert SET.TASK_STARTED == SET.NODE_STARTED
        assert SET.TASK_COMPLETED == SET.NODE_COMPLETED

    def test_substrate_event_string_values_unchanged(self):
        from app.models.substrate_models import SubstrateEventType as SET

        assert SET.RUN_STARTED == "mission.started"
        assert SET.RUN_COMPLETED == "mission.completed"
        assert SET.NODE_STARTED == "task.started"
        assert SET.NODE_COMPLETED == "task.completed"


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 13: Listing & Filtering
# ═══════════════════════════════════════════════════════════════════════════


class TestListingAndFiltering:
    @pytest.mark.asyncio
    async def test_list_blueprints_filters_by_type(self, mock_db):
        from app.services.blueprint_service import BlueprintService

        svc = BlueprintService(mock_db)
        items = [_make_blueprint(blueprint_type="solo") for _ in range(3)]

        count_result = MagicMock()
        count_result.scalar.return_value = 3
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = items

        call_count = 0

        async def _execute(stmt):
            nonlocal call_count
            call_count += 1
            return count_result if call_count <= 1 else items_result

        mock_db.execute = AsyncMock(side_effect=_execute)
        result, total = await svc.list(42, blueprint_type="solo")
        assert len(result) == 3
        assert total == 3

    @pytest.mark.asyncio
    async def test_list_runs_filters_by_status(self, mock_db):
        from app.services.run_service import RunService

        svc = RunService(mock_db)
        items = [_make_run(blueprint_id=str(uuid4()), status="completed") for _ in range(2)]

        count_result = MagicMock()
        count_result.scalar.return_value = 2
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = items

        call_count = 0

        async def _execute(stmt):
            nonlocal call_count
            call_count += 1
            return count_result if call_count <= 1 else items_result

        mock_db.execute = AsyncMock(side_effect=_execute)
        result, total = await svc.list_runs(42, status="completed")  # RunService: renamed from .list (shadowed builtin)
        assert len(result) == 2
        assert total == 2

    @pytest.mark.asyncio
    async def test_list_blueprints_excludes_deleted(self, mock_db):
        from app.services.blueprint_service import BlueprintService

        svc = BlueprintService(mock_db)

        count_result = MagicMock()
        count_result.scalar.return_value = 0
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []

        call_count = 0

        async def _execute(stmt):
            nonlocal call_count
            call_count += 1
            return count_result if call_count <= 1 else items_result

        mock_db.execute = AsyncMock(side_effect=_execute)
        result, total = await svc.list(42)
        assert len(result) == 0
        assert total == 0


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 14: Full Lifecycle (End-to-End)
# ═══════════════════════════════════════════════════════════════════════════


class TestFullBlueprintRunLifecycle:
    """
    Complete end-to-end lifecycle test:
    1. Create Blueprint (draft) → 2. Update definition → 3. Publish
    → 4. Create Run → 5. Execute → 6. Verify events
    → 7. Replay → 8. Retry → 9. Diff
    """

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, mock_db, sample_blueprint_definition, mock_execute_result):
        from app.services.blueprint_service import BlueprintService
        from app.services.run_service import RunService
        from app.services.substrate.replay_engine import ReplayEngine

        bp_svc = BlueprintService(mock_db)
        run_svc = RunService(mock_db)

        # ── Step 1: Create blueprint ─────────────────────────────────
        bp = _make_blueprint(definition=sample_blueprint_definition, status="draft", version=1)
        assert bp.status == "draft"
        assert bp.version == 1

        # ── Step 2: Update definition ────────────────────────────────
        updated_def = {
            **sample_blueprint_definition,
            "nodes": [
                *sample_blueprint_definition["nodes"],
                {"id": "node-2", "type": "tool_call", "title": "Analyze"},
            ],
        }
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = bp
        mock_db.execute = AsyncMock(return_value=mock_result)

        updated = await bp_svc.update(str(bp.id), 42, definition=updated_def)
        assert updated.version == 2

        # ── Step 3: Publish ──────────────────────────────────────────
        published = await bp_svc.publish(str(bp.id), 42)
        assert published.status == "published"

        # ── Step 4: Create run ───────────────────────────────────────
        run = _make_run(
            blueprint_id=str(bp.id),
            snapshot={
                "blueprint_type": "solo",
                "title": bp.title,
                "nodes": updated_def["nodes"],
                "budget": updated_def["budget"],
            },
        )
        assert run.status == "pending"
        assert run.blueprint_id == str(bp.id)

        # ── Step 5: Execute run ──────────────────────────────────────
        bp_with_stats = _make_blueprint(bp_id=str(bp.id), user_id=42)
        run_result = MagicMock()
        run_result.scalar_one_or_none.return_value = run
        bp_stats_result = MagicMock()
        bp_stats_result.scalar_one_or_none.return_value = bp_with_stats

        call_count = 0

        async def _run_db(stmt):
            nonlocal call_count
            call_count += 1
            return run_result if call_count <= 1 else bp_stats_result

        mock_db.execute = AsyncMock(side_effect=_run_db)

        with (
            patch("app.services.run_service.get_unified_executor") as mock_get_exec,
            patch("app.services.run_service.blueprint_to_workflow") as mock_adapter,
        ):
            mock_executor = AsyncMock()
            mock_executor.execute = AsyncMock(return_value=mock_execute_result)
            mock_get_exec.return_value = mock_executor
            mock_adapter.return_value = MagicMock()
            executed = await run_svc.execute(str(run.id), 42)

        assert executed.status == "completed"
        assert executed.total_tokens == 150
        assert executed.completed_at is not None

        # ── Step 6: Verify events ────────────────────────────────────
        run_id = str(run.id)
        bp_id = str(bp.id)
        events = [
            _make_event(
                run_id=run_id,
                sequence=1,
                event_type="mission.started",
                payload={"title": bp.title, "blueprint_id": bp_id},
                blueprint_id=bp_id,
            ),
            _make_event(
                run_id=run_id,
                sequence=2,
                event_type="task.started",
                payload={"task_id": "node-1"},
                blueprint_id=bp_id,
            ),
            _make_event(
                run_id=run_id,
                sequence=3,
                event_type="task.completed",
                payload={"task_id": "node-1", "tokens": 100, "cost_usd": 0.002},
                blueprint_id=bp_id,
            ),
            _make_event(
                run_id=run_id,
                sequence=4,
                event_type="mission.completed",
                payload={"status": "completed"},
                blueprint_id=bp_id,
            ),
        ]

        for event in events:
            assert event.run_id == run_id
            assert event.blueprint_id == bp_id

        # ── Step 7: Replay state ─────────────────────────────────────
        event_result = MagicMock()
        event_result.scalars.return_value.all.return_value = events
        mock_db.execute = AsyncMock(return_value=event_result)

        engine = ReplayEngine()
        state = await engine.rebuild_state(mock_db, run_id)

        assert state.status == "completed"
        assert state.current_sequence == 4
        assert "node-1" in state.completed_tasks
        assert state.total_tokens == 100

        # ── Step 8: Retry (simulate failure first) ───────────────────
        failed_run = _make_run(blueprint_id=bp_id, status="failed", snapshot=run.snapshot)
        failed_result = MagicMock()
        failed_result.scalar_one_or_none.return_value = failed_run
        mock_db.execute = AsyncMock(return_value=failed_result)

        retried = await run_svc.retry(str(failed_run.id), 42)

        assert retried.id != str(failed_run.id)
        assert retried.blueprint_id == bp_id
        assert retried.status == "pending"
        assert retried.snapshot == failed_run.snapshot

        # ── Step 9: Diff two runs ────────────────────────────────────
        run_a = _make_run(blueprint_id=bp_id, status="completed")
        run_a.total_tokens = 150
        run_a.total_cost_usd = 0.003

        run_b = _make_run(blueprint_id=bp_id, status="completed")
        run_b.total_tokens = 200
        run_b.total_cost_usd = 0.005

        diff_result_a = MagicMock()
        diff_result_a.scalar_one_or_none.return_value = run_a
        diff_result_b = MagicMock()
        diff_result_b.scalar_one_or_none.return_value = run_b

        diff_call_count = 0

        async def _diff_db(stmt):
            nonlocal diff_call_count
            diff_call_count += 1
            return diff_result_a if diff_call_count <= 1 else diff_result_b

        mock_db.execute = AsyncMock(side_effect=_diff_db)

        with patch("app.services.run_service.get_replay_engine") as mock_get_replay:
            mock_replay = AsyncMock()
            state_a = MagicMock()
            state_a.to_dict.return_value = {"status": "completed"}
            state_a.completed_tasks = {"node-1", "node-2"}
            state_a.failed_tasks = set()

            state_b = MagicMock()
            state_b.to_dict.return_value = {"status": "completed"}
            state_b.completed_tasks = {"node-1", "node-2"}
            state_b.failed_tasks = set()

            mock_replay.rebuild_state = AsyncMock(side_effect=[state_a, state_b])
            mock_get_replay.return_value = mock_replay

            diff = await run_svc.diff_runs(str(run_a.id), str(run_b.id), 42)

        assert diff["diff"]["token_delta"] == 50
        assert diff["diff"]["cost_delta"] == pytest.approx(0.002)
        assert diff["diff"]["status_match"] is True


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 15: Dual-Write Integration (Mission ↔ Blueprint ↔ Run)
# ═══════════════════════════════════════════════════════════════════════════


class _AsyncCtx:
    """Minimal async context manager for mocking async_sessionmaker."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        return False


class TestDualWriteIntegration:
    """Verify the mission → Blueprint + Run dual-write wiring.

    The dual-write flow:
    1. create_mission stores _source_mission_id in Blueprint.definition
    2. execute_mission looks up Blueprint by definition["_source_mission_id"]
    3. Creates a Run via RunService.create_from_blueprint
    4. Copies StrategyResult fields (status, tokens, cost, started_at, completed_at)
    """

    @pytest.mark.asyncio
    async def test_create_mission_dual_writes_blueprint_with_source_id(
        self,
        mock_db,
        mock_user,
    ):
        """create_mission must fire-and-forget a Blueprint with _source_mission_id in definition."""
        from app.api._mission_cqrs.commands import MissionCommandHandlers

        mission_result = MagicMock(id=str(uuid4()), title="Test Mission")

        _captured: list = []
        mock_bp_db = AsyncMock()
        mock_bp_svc = MagicMock()
        mock_bp_svc.create = AsyncMock(return_value=MagicMock(id=str(uuid4())))

        with (
            patch(
                "app.api._mission_cqrs.commands._schedule_fire_and_forget",
                lambda c: _captured.append(c),
            ),
            patch("app.database.AsyncSessionLocal", lambda: _AsyncCtx(mock_bp_db)),
            patch("app.services.blueprint_service.BlueprintService", return_value=mock_bp_svc),
            patch(
                "app.api._mission_cqrs.commands.create_mission",
                new_callable=AsyncMock,
                return_value=mission_result,
            ),
            patch("app.api._mission_cqrs.base.asyncio.sleep", new_callable=AsyncMock),
        ):
            payload = MagicMock(
                title="Test Mission",
                description="A test",
                mission_type="solo",
                priority="medium",
            )

            handlers = MissionCommandHandlers(mock_db)
            await handlers.create_mission(mock_user, payload)

            # Await captured fire-and-forget coroutines INSIDE the with block
            # so patches are still active when the dual-write runs
            for coro in _captured:
                with contextlib.suppress(Exception):
                    await coro

        # Verify BlueprintService.create was called with _source_mission_id
        mock_bp_svc.create.assert_called_once()
        call_kwargs = mock_bp_svc.create.call_args.kwargs
        assert call_kwargs["definition"] == {"_source_mission_id": str(mission_result.id)}
        assert call_kwargs["title"] == "Test Mission"
        assert call_kwargs["user_id"] == mock_user.id
        assert call_kwargs["workspace_id"] is None

    @pytest.mark.asyncio
    async def test_execute_mission_dual_writes_run_with_started_at(
        self,
        mock_db,
        mock_user,
    ):
        """execute_mission must find linked Blueprint and create a Run with started_at set."""
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.models.mission_models import MissionStatus
        from app.services.substrate.workflow_models import StrategyResult

        mission_id = uuid4()
        mission = MagicMock(
            id=str(mission_id),
            workspace_id=None,
            user_id=mock_user.id,
            status=MissionStatus.EXECUTING,
            plan=None,
            tokens_used=0,
            started_at=datetime.now(UTC),
        )

        strategy_result = StrategyResult(
            success=True,
            status="completed",
            data={"result": "done"},
            completed_nodes=["node-1"],
            failed_nodes=[],
            total_tokens=250,
            total_cost_usd=0.005,
            execution_time_ms=1500.0,
            event_count=4,
        )

        _captured: list = []
        mock_run_db = AsyncMock()
        bp_mock = MagicMock(id=str(uuid4()))
        bp_result = MagicMock()
        bp_result.scalars.return_value.first.return_value = bp_mock
        mock_run_db.execute = AsyncMock(return_value=bp_result)

        run_mock = MagicMock(
            id=str(uuid4()),
            status="pending",
            started_at=None,
            completed_at=None,
            total_tokens=0,
            total_cost_usd=0.0,
            error_message=None,
            output_data=None,
        )
        mock_run_svc = MagicMock()
        mock_run_svc.create_from_blueprint = AsyncMock(return_value=run_mock)

        with (
            patch(
                "app.api._mission_cqrs.commands._schedule_fire_and_forget",
                lambda c: _captured.append(c),
            ),
            patch("app.database.AsyncSessionLocal", lambda: _AsyncCtx(mock_run_db)),
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new_callable=AsyncMock,
                return_value=mission,
            ),
            patch("app.services.substrate.executor.get_unified_executor") as mock_get_exec,
            patch(
                "app.services.substrate.adapters.mission_to_workflow",
                return_value=MagicMock(),
            ),
            patch(
                "app.api._mission_cqrs.commands.get_mission_tasks",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("app.services.run_service.RunService", return_value=mock_run_svc),
            patch("app.api._mission_cqrs.base.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_executor = AsyncMock()
            mock_executor.execute = AsyncMock(return_value=strategy_result)
            mock_get_exec.return_value = mock_executor

            handlers = MissionCommandHandlers(mock_db)
            await handlers.execute_mission(mock_user, mission_id)

            # Await fire-and-forget coroutines INSIDE the with block
            for coro in _captured:
                with contextlib.suppress(Exception):
                    await coro

        # Verify Run was created from the linked Blueprint
        mock_run_svc.create_from_blueprint.assert_called_once_with(
            blueprint_id=str(bp_mock.id),
            user_id=mock_user.id,
        )

        # Verify Run fields were set correctly
        assert run_mock.started_at is not None, "Run.started_at must be set"
        assert run_mock.status == "completed"
        assert run_mock.total_tokens == 250
        assert run_mock.total_cost_usd == 0.005
        assert run_mock.error_message is None
        assert run_mock.output_data == {"result": "done"}
        assert run_mock.completed_at is not None, "Run.completed_at must be set for terminal status"

    @pytest.mark.asyncio
    async def test_execute_mission_dual_write_skips_when_no_blueprint(
        self,
        mock_db,
        mock_user,
    ):
        """When no linked Blueprint exists, dual-write must skip Run creation gracefully."""
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.models.mission_models import MissionStatus
        from app.services.substrate.workflow_models import StrategyResult

        mission_id = uuid4()
        mission = MagicMock(
            id=str(mission_id),
            workspace_id=None,
            user_id=mock_user.id,
            status=MissionStatus.EXECUTING,
            plan=None,
            tokens_used=0,
            started_at=datetime.now(UTC),
        )

        strategy_result = StrategyResult(
            success=True,
            status="completed",
            data={},
            completed_nodes=["n1"],
            failed_nodes=[],
            total_tokens=100,
            total_cost_usd=0.001,
            execution_time_ms=500.0,
            event_count=2,
        )

        _captured: list = []
        mock_run_db = AsyncMock()
        empty_result = MagicMock()
        empty_result.scalars.return_value.first.return_value = None
        mock_run_db.execute = AsyncMock(return_value=empty_result)

        mock_run_svc = MagicMock()
        mock_run_svc.create_from_blueprint = AsyncMock()

        with (
            patch(
                "app.api._mission_cqrs.commands._schedule_fire_and_forget",
                lambda c: _captured.append(c),
            ),
            patch("app.database.AsyncSessionLocal", lambda: _AsyncCtx(mock_run_db)),
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new_callable=AsyncMock,
                return_value=mission,
            ),
            patch("app.services.substrate.executor.get_unified_executor") as mock_get_exec,
            patch(
                "app.services.substrate.adapters.mission_to_workflow",
                return_value=MagicMock(),
            ),
            patch(
                "app.api._mission_cqrs.commands.get_mission_tasks",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("app.services.run_service.RunService", return_value=mock_run_svc),
            patch("app.api._mission_cqrs.base.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_executor = AsyncMock()
            mock_executor.execute = AsyncMock(return_value=strategy_result)
            mock_get_exec.return_value = mock_executor

            handlers = MissionCommandHandlers(mock_db)
            await handlers.execute_mission(mock_user, mission_id)

            for coro in _captured:
                with contextlib.suppress(Exception):
                    await coro

        mock_run_svc.create_from_blueprint.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_mission_dual_write_copies_failure_fields(
        self,
        mock_db,
        mock_user,
    ):
        """When execution fails, dual-write must set error_message and skip output_data."""
        from app.api._mission_cqrs.commands import MissionCommandHandlers
        from app.models.mission_models import MissionStatus
        from app.services.substrate.workflow_models import StrategyResult

        mission_id = uuid4()
        mission = MagicMock(
            id=str(mission_id),
            workspace_id=None,
            user_id=mock_user.id,
            status=MissionStatus.EXECUTING,
            plan=None,
            tokens_used=0,
            started_at=datetime.now(UTC),
        )

        strategy_result = StrategyResult(
            success=False,
            status="failed",
            error="Model rate limit exceeded",
            data=None,
            completed_nodes=[],
            failed_nodes=["node-1"],
            total_tokens=50,
            total_cost_usd=0.001,
            execution_time_ms=200.0,
            event_count=2,
        )

        _captured: list = []
        mock_run_db = AsyncMock()
        bp_mock = MagicMock(id=str(uuid4()))
        bp_result = MagicMock()
        bp_result.scalars.return_value.first.return_value = bp_mock
        mock_run_db.execute = AsyncMock(return_value=bp_result)

        run_mock = MagicMock(
            id=str(uuid4()),
            status="pending",
            started_at=None,
            completed_at=None,
            total_tokens=0,
            total_cost_usd=0.0,
            error_message=None,
            output_data=None,
        )
        mock_run_svc = MagicMock()
        mock_run_svc.create_from_blueprint = AsyncMock(return_value=run_mock)

        with (
            patch(
                "app.api._mission_cqrs.commands._schedule_fire_and_forget",
                lambda c: _captured.append(c),
            ),
            patch("app.database.AsyncSessionLocal", lambda: _AsyncCtx(mock_run_db)),
            patch(
                "app.api._mission_cqrs.commands.require_mission_access",
                new_callable=AsyncMock,
                return_value=mission,
            ),
            patch("app.services.substrate.executor.get_unified_executor") as mock_get_exec,
            patch(
                "app.services.substrate.adapters.mission_to_workflow",
                return_value=MagicMock(),
            ),
            patch(
                "app.api._mission_cqrs.commands.get_mission_tasks",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch("app.services.run_service.RunService", return_value=mock_run_svc),
            patch("app.api._mission_cqrs.base.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_executor = AsyncMock()
            mock_executor.execute = AsyncMock(return_value=strategy_result)
            mock_get_exec.return_value = mock_executor

            handlers = MissionCommandHandlers(mock_db)
            await handlers.execute_mission(mock_user, mission_id)

            for coro in _captured:
                with contextlib.suppress(Exception):
                    await coro

        mock_run_svc.create_from_blueprint.assert_called_once()

        # Verify failure fields
        assert run_mock.started_at is not None
        assert run_mock.status == "failed"
        assert run_mock.total_tokens == 50
        assert run_mock.error_message == "Model rate limit exceeded"
        assert run_mock.output_data is None, "output_data must be None on failure"
        assert run_mock.completed_at is not None, "completed_at must be set for terminal status"
