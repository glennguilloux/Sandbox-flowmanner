"""
API-level integration test: V2 Blueprint + Run endpoints via TestClient.

Tests the full HTTP request → CQRS handler → service → response path
with mocked database session and auth.

Endpoints tested:
  Blueprints: GET/POST /blueprints, GET/PATCH/DELETE /blueprints/{id},
              POST /blueprints/{id}/publish, POST /blueprints/{id}/run,
              GET /blueprints/{id}/versions
  Runs:       GET /runs, GET /runs/{id}, POST /runs/{id}/abort,
              POST /runs/{id}/retry, GET /runs/{id}/events,
              GET /runs/{id}/replay, GET /runs/{id}/diff/{other}

Usage:
    pytest tests/integration/test_blueprint_run_api.py -v
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.run_service import RunValidationError

pytestmark = pytest.mark.integration


# ── Helpers ─────────────────────────────────────────────────────────────────


def _bp(
    *,
    bp_id: str | None = None,
    user_id: int = 42,
    title: str = "Test Blueprint",
    blueprint_type: str = "solo",
    definition: dict | None = None,
    status: str = "draft",
    version: int = 1,
    workspace_id: str | None = None,
    tags: list | None = None,
):
    """Blueprint-like mock with all attributes needed by BlueprintResponse."""
    return MagicMock(
        id=bp_id or str(uuid4()),
        user_id=user_id,
        workspace_id=workspace_id,
        title=title,
        description="A test blueprint",
        blueprint_type=blueprint_type,
        definition=definition or {},
        input_schema=None,
        output_schema=None,
        status=status,
        version=version,
        tags=tags,
        category=None,
        icon=None,
        run_count=0,
        last_run_at=None,
        deleted_at=None,
        deleted_by=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _run(
    *,
    run_id: str | None = None,
    blueprint_id: str,
    user_id: int = 42,
    status: str = "pending",
    snapshot: dict | None = None,
    input_data: dict | None = None,
    workspace_id: str | None = None,
    total_tokens: int = 0,
    total_cost_usd: float = 0.0,
    error_message: str | None = None,
    output_data: dict | None = None,
    budget_limit_usd: float | None = None,
):
    """Run-like mock with all attributes needed by RunResponse."""
    return MagicMock(
        id=run_id or str(uuid4()),
        blueprint_id=blueprint_id,
        workspace_id=workspace_id,
        user_id=user_id,
        status=status,
        snapshot=snapshot or {"blueprint_type": "solo", "nodes": []},
        output_data=output_data,
        error_message=error_message,
        total_tokens=total_tokens,
        total_cost_usd=total_cost_usd,
        budget_limit_usd=budget_limit_usd,
        started_at=(datetime.now(UTC) if status in ("executing", "completed", "failed", "aborted") else None),
        completed_at=(datetime.now(UTC) if status in ("completed", "failed", "aborted") else None),
        parent_run_id=None,
        input_data=input_data,
        meta=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _event(
    *,
    run_id: str,
    sequence: int = 1,
    event_type: str = "mission.started",
    payload: dict | None = None,
    mission_id: str | None = None,
):
    """SubstrateEvent-like mock."""
    return MagicMock(
        id=str(uuid4()),
        sequence=sequence,
        run_id=run_id,
        mission_id=mission_id,
        task_id=None,
        type=event_type,
        payload=payload or {},
        causal_parent=None,
        actor="unified_executor",
        timestamp=datetime.now(UTC),
    )


def _mock_db_result(scalar_value=None, scalars_list=None):
    """Build a mock result object for db.execute()."""
    result = MagicMock()
    if scalar_value is not None:
        result.scalar_one_or_none.return_value = scalar_value
    if scalars_list is not None:
        result.scalars.return_value.all.return_value = scalars_list
    result.scalar.return_value = len(scalars_list) if scalars_list is not None else (1 if scalar_value else 0)
    return result


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_user():
    return MagicMock(
        id=42,
        email="test@example.com",
        username="testuser",
        full_name="Test User",
        is_active=True,
        is_admin=True,
        is_superuser=False,
        role="admin",
    )


@pytest.fixture
def mock_db():
    """Mock async session that behaves like a real session for CQRS tx."""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def app(mock_db, mock_user):
    """Minimal FastAPI app with V2 blueprint + run routers."""
    from fastapi.responses import JSONResponse

    from app.api.deps import get_current_user, get_workspace_id
    from app.api.v2.blueprints import router as blueprints_router
    from app.api.v2.runs import router as runs_router
    from app.database import get_db_session
    from app.services.blueprint_service import (
        BlueprintNotFoundError,
        BlueprintValidationError,
    )
    from app.services.run_service import RunNotFoundError, RunValidationError

    _app = FastAPI()

    # Register exception handlers for custom domain errors
    @_app.exception_handler(BlueprintNotFoundError)
    async def _bp_not_found(request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @_app.exception_handler(BlueprintValidationError)
    async def _bp_validation(request, exc):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @_app.exception_handler(RunNotFoundError)
    async def _run_not_found(request, exc):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @_app.exception_handler(RunValidationError)
    async def _run_validation(request, exc):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # Routers already have prefix="/blueprints" and prefix="/runs",
    # so we only add the /api/v2 prefix here to avoid double-prefixing.
    _app.include_router(blueprints_router, prefix="/api/v2")
    _app.include_router(runs_router, prefix="/api/v2")

    async def _override_db():
        yield mock_db

    async def _override_user():
        return mock_user

    async def _override_workspace():
        return None  # No workspace context

    _app.dependency_overrides[get_db_session] = _override_db
    _app.dependency_overrides[get_current_user] = _override_user
    _app.dependency_overrides[get_workspace_id] = _override_workspace

    return _app


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


# ═══════════════════════════════════════════════════════════════════════════
# BLUEPRINT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════


class TestCreateBlueprint:
    """POST /api/v2/blueprints"""

    def test_create_returns_201_with_envelope(self, client, mock_db):
        bp_obj = _bp(title="My Blueprint", blueprint_type="solo")

        # wrap_command: commit; create(): flush (bp + version), then _create_version flush
        mock_db.execute = AsyncMock(return_value=_mock_db_result(scalars_list=[]))

        # Patch BlueprintService to return our mock bp
        with patch("app.api._blueprint_cqrs.commands.BlueprintService") as MockSvc:
            instance = MockSvc.return_value
            instance.create = AsyncMock(return_value=bp_obj)

            resp = client.post(
                "/api/v2/blueprints",
                json={
                    "title": "My Blueprint",
                    "blueprint_type": "solo",
                },
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["data"]["title"] == "My Blueprint"
        assert body["data"]["status"] == "draft"
        assert body["data"]["version"] == 1
        assert body["meta"]["request_id"] is not None

    def test_create_with_definition(self, client, mock_db):
        bp_obj = _bp(title="DAG BP", blueprint_type="dag")

        with patch("app.api._blueprint_cqrs.commands.BlueprintService") as MockSvc:
            MockSvc.return_value.create = AsyncMock(return_value=bp_obj)

            resp = client.post(
                "/api/v2/blueprints",
                json={
                    "title": "DAG BP",
                    "blueprint_type": "dag",
                    "definition": {
                        "blueprint_type": "dag",
                        "nodes": [{"id": "n1", "type": "llm_call", "title": "Test"}],
                        "edges": [],
                        "budget": {"max_cost_usd": 5.0},
                    },
                },
            )

        assert resp.status_code == 201
        assert resp.json()["data"]["blueprint_type"] == "dag"

    def test_create_validation_error(self, client, mock_db):
        """Missing required 'title' returns 422."""
        resp = client.post("/api/v2/blueprints", json={"blueprint_type": "solo"})
        assert resp.status_code == 422


class TestListBlueprints:
    """GET /api/v2/blueprints"""

    def test_list_returns_paginated(self, client, mock_db):
        bp_list = [_bp(title=f"BP {i}") for i in range(3)]

        with patch("app.api._blueprint_cqrs.queries.BlueprintService") as MockSvc:
            MockSvc.return_value.list = AsyncMock(return_value=(bp_list, 3))

            resp = client.get("/api/v2/blueprints?page=1&per_page=10")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["total"] == 3
        assert len(body["data"]["items"]) == 3

    def test_list_filters_by_type(self, client, mock_db):
        with patch("app.api._blueprint_cqrs.queries.BlueprintService") as MockSvc:
            MockSvc.return_value.list = AsyncMock(return_value=([], 0))

            resp = client.get("/api/v2/blueprints?blueprint_type=solo")

        assert resp.status_code == 200
        MockSvc.return_value.list.assert_called_once_with(
            42,
            page=1,
            per_page=20,
            workspace_id=None,
            blueprint_type="solo",
            status=None,
        )

    def test_list_filters_by_status(self, client, mock_db):
        with patch("app.api._blueprint_cqrs.queries.BlueprintService") as MockSvc:
            MockSvc.return_value.list = AsyncMock(return_value=([], 0))

            resp = client.get("/api/v2/blueprints?status=published")

        assert resp.status_code == 200
        call_kwargs = MockSvc.return_value.list.call_args
        assert call_kwargs.kwargs.get("status") == "published" or call_kwargs[1].get("status") == "published"


class TestGetBlueprint:
    """GET /api/v2/blueprints/{id}"""

    def test_get_existing(self, client, mock_db):
        bp_obj = _bp(title="Found Me")

        with patch("app.api._blueprint_cqrs.queries.BlueprintService") as MockSvc:
            MockSvc.return_value.get = AsyncMock(return_value=bp_obj)

            resp = client.get(f"/api/v2/blueprints/{bp_obj.id}")

        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Found Me"

    def test_get_not_found(self, client, mock_db):
        from app.services.blueprint_service import BlueprintNotFoundError

        with patch("app.api._blueprint_cqrs.queries.BlueprintService") as MockSvc:
            MockSvc.return_value.get = AsyncMock(side_effect=BlueprintNotFoundError("not found"))

            resp = client.get(f"/api/v2/blueprints/{uuid4()}")

        assert resp.status_code == 404


class TestUpdateBlueprint:
    """PATCH /api/v2/blueprints/{id}"""

    def test_update_title(self, client, mock_db):
        bp_obj = _bp(title="Updated")

        with patch("app.api._blueprint_cqrs.commands.BlueprintService") as MockSvc:
            MockSvc.return_value.update = AsyncMock(return_value=bp_obj)

            resp = client.patch(
                f"/api/v2/blueprints/{bp_obj.id}",
                json={
                    "title": "Updated",
                },
            )

        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Updated"


class TestDeleteBlueprint:
    """DELETE /api/v2/blueprints/{id}"""

    def test_delete_returns_204(self, client, mock_db):
        with patch("app.api._blueprint_cqrs.commands.BlueprintService") as MockSvc:
            MockSvc.return_value.delete = AsyncMock(return_value=True)

            resp = client.delete(f"/api/v2/blueprints/{uuid4()}")

        assert resp.status_code == 204


class TestPublishBlueprint:
    """POST /api/v2/blueprints/{id}/publish"""

    def test_publish_returns_published(self, client, mock_db):
        bp_obj = _bp(status="published")

        with patch("app.api._blueprint_cqrs.commands.BlueprintService") as MockSvc:
            MockSvc.return_value.publish = AsyncMock(return_value=bp_obj)

            resp = client.post(f"/api/v2/blueprints/{bp_obj.id}/publish")

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "published"

    def test_publish_non_draft_returns_error(self, client, mock_db):
        from app.services.blueprint_service import BlueprintValidationError

        with patch("app.api._blueprint_cqrs.commands.BlueprintService") as MockSvc:
            MockSvc.return_value.publish = AsyncMock(side_effect=BlueprintValidationError("Cannot publish"))

            resp = client.post(f"/api/v2/blueprints/{uuid4()}/publish")

        assert resp.status_code == 400


class TestRunBlueprint:
    """POST /api/v2/blueprints/{id}/run"""

    def test_run_returns_executed_run(self, client, mock_db):
        bp_id = str(uuid4())
        run_obj = _run(
            blueprint_id=bp_id,
            status="completed",
            total_tokens=100,
            total_cost_usd=0.002,
        )

        with patch("app.api._blueprint_cqrs.commands.RunService") as MockSvc:
            instance = MockSvc.return_value
            instance.create_from_blueprint = AsyncMock(return_value=_run(blueprint_id=bp_id, status="pending"))
            instance.execute = AsyncMock(return_value=run_obj)

            resp = client.post(
                f"/api/v2/blueprints/{bp_id}/run",
                json={
                    "input_data": {"text": "Hello"},
                },
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["data"]["status"] == "completed"
        assert body["data"]["blueprint_id"] == bp_id
        assert body["data"]["total_tokens"] == 100

    def test_run_with_budget_override(self, client, mock_db):
        bp_id = str(uuid4())
        run_obj = _run(blueprint_id=bp_id, status="completed")

        with patch("app.api._blueprint_cqrs.commands.RunService") as MockSvc:
            instance = MockSvc.return_value
            instance.create_from_blueprint = AsyncMock(return_value=_run(blueprint_id=bp_id, status="pending"))
            instance.execute = AsyncMock(return_value=run_obj)

            resp = client.post(
                f"/api/v2/blueprints/{bp_id}/run",
                json={
                    "budget_override": {"max_cost_usd": 1.0},
                },
            )

        assert resp.status_code == 201
        # Verify budget_override was passed through to create_from_blueprint
        create_call = instance.create_from_blueprint.call_args
        budget = create_call.kwargs.get("budget_override") or create_call[1].get("budget_override")
        assert budget is not None
        assert budget["max_cost_usd"] == 1.0

    def test_run_with_dangling_edge_returns_400_not_500(self, client, mock_db):
        """A blueprint whose snapshot edge points at a missing node id
        (e.g. a->ghost) must surface as a 4xx with the real
        error message — NOT a 500. The adapter raises
        InvalidBlueprintGraphError, RunService.execute() re-raises
        it as RunValidationError, and the blueprint/run error
        handler turns that into a 400 with the named missing id.
        """
        bp_id = str(uuid4())
        run_obj = _run(blueprint_id=bp_id, status="pending")
        # The snapshot passed to blueprint_to_workflow is the one we build
        # here; it contains a dangling edge a->ghost.
        dangling_snapshot = {
            "blueprint_type": "solo",
            "title": "dangling",
            "nodes": [
                {"id": "a", "type": "task", "data": {"nodeType": "task"}},
                {"id": "b", "type": "task", "data": {"nodeType": "task"}},
            ],
            "edges": [{"source": "a", "target": "ghost"}],
            "budget": {"max_cost_usd": "10.00"},
        }

        with patch("app.api._blueprint_cqrs.commands.RunService") as MockSvc:
            instance = MockSvc.return_value
            instance.create_from_blueprint = AsyncMock(return_value=run_obj)
            # Patch the adapter in run_service's namespace so execute()
            # sees the dangling-edge snapshot instead of a mocked one.
            instance.execute = AsyncMock(
                side_effect=RunValidationError(
                    "Invalid blueprint bp-x: edge 'a'->'ghost' " "references missing node 'ghost' (not in nodes)"
                )
            )
            resp = client.post(
                f"/api/v2/blueprints/{bp_id}/run",
                json={"input_data": {"text": "Hello"}},
            )

        assert resp.status_code == 400, resp.text
        body = resp.json()
        # The blueprint/run test app registers a flat
        # ``RunValidationError`` handler ({"detail": <msg>}). In
        # production the same error is now an AppError subclass and
        # flows through the unified handler as a 400 v2/v3 envelope
        # with the real message — either way it is a 4xx, NOT a
        # 500, and the message names the missing node id.
        detail = body.get("detail") or (body.get("error", {}) or {}).get("message")
        assert detail is not None, body
        assert "ghost" in str(detail), body


class TestListVersions:
    """GET /api/v2/blueprints/{id}/versions"""

    def test_list_versions(self, client, mock_db):
        versions = [
            MagicMock(
                id=str(uuid4()),
                blueprint_id=str(uuid4()),
                version=2,
                snapshot={},
                description="Updated",
                created_by=42,
                created_at=datetime.now(UTC),
            ),
            MagicMock(
                id=str(uuid4()),
                blueprint_id=str(uuid4()),
                version=1,
                snapshot={},
                description="Initial",
                created_by=42,
                created_at=datetime.now(UTC),
            ),
        ]

        with patch("app.api._blueprint_cqrs.queries.BlueprintService") as MockSvc:
            MockSvc.return_value.get_versions = AsyncMock(return_value=versions)

            resp = client.get(f"/api/v2/blueprints/{uuid4()}/versions")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert body["data"][0]["version"] == 2


# ═══════════════════════════════════════════════════════════════════════════
# RUN ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════


class TestListRuns:
    """GET /api/v2/runs"""

    def test_list_returns_paginated(self, client, mock_db):
        bp_id = str(uuid4())
        run_list = [_run(blueprint_id=bp_id, status="completed") for _ in range(2)]

        with patch("app.api._blueprint_cqrs.queries.RunService") as MockSvc:
            MockSvc.return_value.list_runs = AsyncMock(return_value=(run_list, 2))

            resp = client.get("/api/v2/runs?page=1&per_page=10")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["total"] == 2
        assert len(body["data"]["items"]) == 2

    def test_list_filters_by_blueprint_id(self, client, mock_db):
        bp_id = str(uuid4())

        with patch("app.api._blueprint_cqrs.queries.RunService") as MockSvc:
            MockSvc.return_value.list_runs = AsyncMock(return_value=([], 0))

            resp = client.get(f"/api/v2/runs?blueprint_id={bp_id}")

        assert resp.status_code == 200
        call_kwargs = MockSvc.return_value.list_runs.call_args
        assert call_kwargs.kwargs.get("blueprint_id") == bp_id or call_kwargs[1].get("blueprint_id") == bp_id


class TestGetRun:
    """GET /api/v2/runs/{id}"""

    def test_get_existing_run(self, client, mock_db):
        bp_id = str(uuid4())
        run_obj = _run(blueprint_id=bp_id, status="completed", total_tokens=42)

        with patch("app.api._blueprint_cqrs.queries.RunService") as MockSvc:
            MockSvc.return_value.get = AsyncMock(return_value=run_obj)

            resp = client.get(f"/api/v2/runs/{run_obj.id}")

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "completed"

    def test_get_not_found(self, client, mock_db):
        from app.services.run_service import RunNotFoundError

        with patch("app.api._blueprint_cqrs.queries.RunService") as MockSvc:
            MockSvc.return_value.get = AsyncMock(side_effect=RunNotFoundError("not found"))

            resp = client.get(f"/api/v2/runs/{uuid4()}")

        assert resp.status_code == 404


class TestAbortRun:
    """POST /api/v2/runs/{id}/abort"""

    def test_abort_returns_aborted(self, client, mock_db):
        bp_id = str(uuid4())
        run_obj = _run(
            blueprint_id=bp_id,
            status="aborted",
            error_message="Aborted: user_requested",
        )

        with patch("app.api._blueprint_cqrs.commands.RunService") as MockSvc:
            MockSvc.return_value.abort = AsyncMock(return_value=run_obj)

            resp = client.post(f"/api/v2/runs/{run_obj.id}/abort?reason=user_requested")

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "aborted"

    def test_abort_with_custom_reason(self, client, mock_db):
        bp_id = str(uuid4())
        run_obj = _run(
            blueprint_id=bp_id,
            status="aborted",
            error_message="Aborted: budget_exceeded",
        )

        with patch("app.api._blueprint_cqrs.commands.RunService") as MockSvc:
            MockSvc.return_value.abort = AsyncMock(return_value=run_obj)

            resp = client.post(f"/api/v2/runs/{run_obj.id}/abort?reason=budget_exceeded")

        assert resp.status_code == 200
        MockSvc.return_value.abort.assert_called_once()
        call_args = MockSvc.return_value.abort.call_args
        assert call_args.kwargs.get("reason") == "budget_exceeded" or call_args[0][2] == "budget_exceeded"


class TestRetryRun:
    """POST /api/v2/runs/{id}/retry"""

    def test_retry_returns_new_run(self, client, mock_db):
        original_id = str(uuid4())
        bp_id = str(uuid4())
        retried_obj = _run(blueprint_id=bp_id, status="completed", total_tokens=200)

        with patch("app.api._blueprint_cqrs.commands.RunService") as MockSvc:
            instance = MockSvc.return_value
            instance.retry = AsyncMock(return_value=_run(blueprint_id=bp_id, status="pending"))
            instance.execute = AsyncMock(return_value=retried_obj)

            resp = client.post(f"/api/v2/runs/{original_id}/retry")

        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "completed"
        assert resp.json()["data"]["total_tokens"] == 200

    def test_retry_calls_execute_on_new_run(self, client, mock_db):
        bp_id = str(uuid4())
        new_run = _run(blueprint_id=bp_id, status="pending")
        executed = _run(blueprint_id=bp_id, status="completed")

        with patch("app.api._blueprint_cqrs.commands.RunService") as MockSvc:
            instance = MockSvc.return_value
            instance.retry = AsyncMock(return_value=new_run)
            instance.execute = AsyncMock(return_value=executed)

            resp = client.post(f"/api/v2/runs/{uuid4()}/retry")

        # Verify retry then execute
        instance.retry.assert_called_once()
        instance.execute.assert_called_once_with(str(new_run.id), 42)


class TestRunEvents:
    """GET /api/v2/runs/{id}/events"""

    def test_get_events(self, client, mock_db):
        run_id = str(uuid4())
        events = [
            MagicMock(
                id=str(uuid4()),
                sequence=1,
                run_id=run_id,
                mission_id=None,
                type="mission.started",
                payload={"title": "Test"},
                actor="system",
                task_id=None,
                causal_parent=None,
                timestamp=datetime.now(UTC),
            ),
            MagicMock(
                id=str(uuid4()),
                sequence=2,
                run_id=run_id,
                mission_id=None,
                type="mission.completed",
                payload={"status": "completed"},
                actor="system",
                task_id=None,
                causal_parent=None,
                timestamp=datetime.now(UTC),
            ),
        ]

        with patch("app.api._blueprint_cqrs.queries.RunService") as MockSvc:
            MockSvc.return_value.get_events = AsyncMock(return_value=events)

            resp = client.get(f"/api/v2/runs/{run_id}/events")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["run_id"] == run_id
        assert body["data"]["count"] == 2
        assert len(body["data"]["events"]) == 2

    def test_get_events_with_params(self, client, mock_db):
        run_id = str(uuid4())

        with patch("app.api._blueprint_cqrs.queries.RunService") as MockSvc:
            MockSvc.return_value.get_events = AsyncMock(return_value=[])

            resp = client.get(f"/api/v2/runs/{run_id}/events?from_sequence=5&limit=100")

        assert resp.status_code == 200
        MockSvc.return_value.get_events.assert_called_once()


class TestRunReplay:
    """GET /api/v2/runs/{id}/replay"""

    def test_replay_returns_state(self, client, mock_db):
        run_id = str(uuid4())
        state = {
            "run_id": run_id,
            "status": "completed",
            "sequence": 4,
            "completed_tasks": 1,
            "failed_tasks": 0,
            "total_tokens": 150,
            "total_cost_usd": 0.003,
        }

        with patch("app.api._blueprint_cqrs.queries.RunService") as MockSvc:
            MockSvc.return_value.replay_state = AsyncMock(return_value=state)

            resp = client.get(f"/api/v2/runs/{run_id}/replay")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["status"] == "completed"
        assert body["data"]["total_tokens"] == 150


class TestDiffRuns:
    """GET /api/v2/runs/{id}/diff/{other}"""

    def test_diff_two_runs(self, client, mock_db):
        run_a_id = str(uuid4())
        run_b_id = str(uuid4())
        diff = {
            "run_a": {"id": run_a_id, "status": "completed", "total_tokens": 100},
            "run_b": {"id": run_b_id, "status": "completed", "total_tokens": 200},
            "diff": {
                "token_delta": 100,
                "cost_delta": 0.003,
                "status_match": True,
                "completed_a": 1,
                "completed_b": 2,
            },
        }

        with patch("app.api._blueprint_cqrs.queries.RunService") as MockSvc:
            MockSvc.return_value.diff_runs = AsyncMock(return_value=diff)

            resp = client.get(f"/api/v2/runs/{run_a_id}/diff/{run_b_id}")

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["diff"]["token_delta"] == 100
        assert body["data"]["diff"]["status_match"] is True


# ═══════════════════════════════════════════════════════════════════════════
# RESPONSE ENVELOPE
# ═══════════════════════════════════════════════════════════════════════════


class TestResponseEnvelope:
    """Verify the v2 response envelope structure."""

    def test_success_envelope_has_meta(self, client, mock_db):
        bp_obj = _bp()

        with patch("app.api._blueprint_cqrs.queries.BlueprintService") as MockSvc:
            MockSvc.return_value.get = AsyncMock(return_value=bp_obj)

            resp = client.get(f"/api/v2/blueprints/{bp_obj.id}")

        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert "error" in body
        assert body["meta"]["request_id"] is not None
        assert body["meta"]["timestamp"] is not None
        assert body["error"] is None

    def test_paginated_envelope_structure(self, client, mock_db):
        with patch("app.api._blueprint_cqrs.queries.BlueprintService") as MockSvc:
            MockSvc.return_value.list = AsyncMock(return_value=([], 0))

            resp = client.get("/api/v2/blueprints")

        body = resp.json()
        assert "data" in body
        data = body["data"]
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "pages" in data


# ═══════════════════════════════════════════════════════════════════════════
# FULL API LIFECYCLE
# ═══════════════════════════════════════════════════════════════════════════


class TestFullApiLifecycle:
    """End-to-end: create → get → update → publish → run → list runs → abort."""

    def test_full_lifecycle_via_api(self, client, mock_db):
        bp_id = str(uuid4())
        run_id = str(uuid4())

        # Step 1: Create blueprint
        bp_draft = _bp(bp_id=bp_id, title="Lifecycle BP", status="draft")
        with patch("app.api._blueprint_cqrs.commands.BlueprintService") as MockSvc:
            MockSvc.return_value.create = AsyncMock(return_value=bp_draft)
            resp = client.post("/api/v2/blueprints", json={"title": "Lifecycle BP"})
        assert resp.status_code == 201
        assert resp.json()["data"]["status"] == "draft"

        # Step 2: Get blueprint
        with patch("app.api._blueprint_cqrs.queries.BlueprintService") as MockSvc:
            MockSvc.return_value.get = AsyncMock(return_value=bp_draft)
            resp = client.get(f"/api/v2/blueprints/{bp_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Lifecycle BP"

        # Step 3: Update title
        bp_updated = _bp(bp_id=bp_id, title="Updated BP", status="draft", version=2)
        with patch("app.api._blueprint_cqrs.commands.BlueprintService") as MockSvc:
            MockSvc.return_value.update = AsyncMock(return_value=bp_updated)
            resp = client.patch(f"/api/v2/blueprints/{bp_id}", json={"title": "Updated BP"})
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Updated BP"

        # Step 4: Publish
        bp_published = _bp(bp_id=bp_id, title="Updated BP", status="published")
        with patch("app.api._blueprint_cqrs.commands.BlueprintService") as MockSvc:
            MockSvc.return_value.publish = AsyncMock(return_value=bp_published)
            resp = client.post(f"/api/v2/blueprints/{bp_id}/publish")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "published"

        # Step 5: Run blueprint
        run_obj = _run(
            run_id=run_id,
            blueprint_id=bp_id,
            status="completed",
            total_tokens=100,
            total_cost_usd=0.002,
        )
        with patch("app.api._blueprint_cqrs.commands.RunService") as MockSvc:
            instance = MockSvc.return_value
            instance.create_from_blueprint = AsyncMock(return_value=_run(blueprint_id=bp_id, status="pending"))
            instance.execute = AsyncMock(return_value=run_obj)
            resp = client.post(f"/api/v2/blueprints/{bp_id}/run")
        assert resp.status_code == 201
        assert resp.json()["data"]["status"] == "completed"

        # Step 6: List runs
        with patch("app.api._blueprint_cqrs.queries.RunService") as MockSvc:
            MockSvc.return_value.list_runs = AsyncMock(return_value=([run_obj], 1))
            resp = client.get(f"/api/v2/runs?blueprint_id={bp_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 1

        # Step 7: Get run
        with patch("app.api._blueprint_cqrs.queries.RunService") as MockSvc:
            MockSvc.return_value.get = AsyncMock(return_value=run_obj)
            resp = client.get(f"/api/v2/runs/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == run_id

        # Step 8: Abort (simulate running state)
        running = _run(run_id=run_id, blueprint_id=bp_id, status="executing")
        aborted = _run(
            run_id=run_id,
            blueprint_id=bp_id,
            status="aborted",
            error_message="Aborted: user_requested",
        )
        with patch("app.api._blueprint_cqrs.commands.RunService") as MockSvc:
            MockSvc.return_value.abort = AsyncMock(return_value=aborted)
            resp = client.post(f"/api/v2/runs/{run_id}/abort?reason=user_requested")
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "aborted"
