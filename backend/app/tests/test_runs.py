"""Phase A — Run→Mission link regression tests.

Covers the two focused acceptance criteria for t_da8eba14:
  (a) ``RunService.create_from_blueprint`` attaches a non-null ``mission_id``
      to the created ``Run`` (inline mission creation via A2a).
  (b) ``RunResponse`` serializes ``mission_id`` (coerced to str when the
      model carries a UUID).

These tests are hermetic: the AsyncSession is a MagicMock, so no real
Postgres is required and the suite runs on the host.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.blueprint_models import Blueprint, Run, RunStatus
from app.schemas.blueprint import RunResponse
from app.services.run_service import RunService


def _make_blueprint() -> Blueprint:
    bp = Blueprint()
    object.__setattr__(bp, "id", "bp-1")
    object.__setattr__(bp, "workspace_id", "ws-1")
    object.__setattr__(bp, "title", "Test blueprint")
    object.__setattr__(bp, "description", "A blueprint for testing")
    object.__setattr__(bp, "blueprint_type", "workflow")
    object.__setattr__(bp, "definition", {"nodes": [], "edges": []})
    object.__setattr__(bp, "deleted_at", None)
    return bp


async def test_create_from_blueprint_links_mission_id():
    """(a) The created Run carries a non-null mission_id (A2a inline create)."""

    bp = _make_blueprint()

    # Fake the SELECT(Blueprint) load.
    load_result = MagicMock()
    load_result.scalar_one_or_none.return_value = bp

    # ``_create_mission`` is patched to return a lightweight fake mission.
    fake_mission = MagicMock()
    object.__setattr__(fake_mission, "id", "mission-1234")

    db = MagicMock()
    db.execute = AsyncMock(return_value=load_result)
    db.add = MagicMock()
    db.flush = AsyncMock()

    service = RunService(db=db)
    with patch(
        "app.services.run_service._create_mission",
        new=AsyncMock(return_value=fake_mission),
    ) as fake_create:
        run = await service.create_from_blueprint(
            blueprint_id="bp-1",
            user_id=1,
            input_data={"x": 1},
        )
        # Inline-create path was taken (no caller-supplied mission_id).
        fake_create.assert_awaited_once()
        assert fake_create.call_args.kwargs["user_id"] == 1
        assert fake_create.call_args.kwargs["workspace_id"] == "ws-1"

    # The Run was constructed with the mission link.
    assert isinstance(run, Run)
    assert run.mission_id == "mission-1234"
    assert run.status == RunStatus.PENDING.value


async def test_create_from_blueprint_uses_caller_supplied_mission_id():
    """A caller-supplied mission_id is honored and no mission is created."""

    bp = _make_blueprint()
    load_result = MagicMock()
    load_result.scalar_one_or_none.return_value = bp

    db = MagicMock()
    db.execute = AsyncMock(return_value=load_result)
    db.add = MagicMock()
    db.flush = AsyncMock()

    service = RunService(db=db)
    with patch(
        "app.services.run_service._create_mission",
        new=AsyncMock(),
    ) as fake_create:
        run = await service.create_from_blueprint(
            blueprint_id="bp-1",
            user_id=1,
            mission_id="caller-mission-9",
        )
        # Inline-create path skipped.
        fake_create.assert_not_awaited()

    assert run.mission_id == "caller-mission-9"


def test_run_response_serializes_mission_id():
    """(b) RunResponse coerces a UUID mission_id to str and includes it."""

    from uuid import UUID

    run = Run()
    object.__setattr__(run, "id", "run-1")
    object.__setattr__(run, "mission_id", UUID("aaaaaaaa-0000-0000-0000-000000000000"))
    object.__setattr__(run, "parent_run_id", None)
    object.__setattr__(run, "blueprint_id", "bp-1")
    object.__setattr__(run, "workspace_id", "ws-1")
    object.__setattr__(run, "status", "pending")
    object.__setattr__(run, "snapshot", {})
    object.__setattr__(run, "total_tokens", 0)
    object.__setattr__(run, "total_cost_usd", 0.0)

    payload = RunResponse.model_validate(run).model_dump()
    assert payload["mission_id"] == "aaaaaaaa-0000-0000-0000-000000000000"
    assert isinstance(payload["mission_id"], str)


def test_run_response_mission_id_none_is_allowed():
    """Backwards-compat: legacy runs with no mission link serialize fine."""

    run = Run()
    object.__setattr__(run, "id", "run-2")
    object.__setattr__(run, "mission_id", None)
    object.__setattr__(run, "parent_run_id", None)
    object.__setattr__(run, "blueprint_id", "bp-2")
    object.__setattr__(run, "workspace_id", "ws-2")
    object.__setattr__(run, "status", "pending")
    object.__setattr__(run, "snapshot", {})
    object.__setattr__(run, "total_tokens", 0)
    object.__setattr__(run, "total_cost_usd", 0.0)

    payload = RunResponse.model_validate(run).model_dump()
    assert payload["mission_id"] is None
