"""Regression test — RunService.get() resolves short UUID prefixes.

Bug #2 (2026-07-19): GET /api/v2/runs/{id} returned HTTP 500 when the
caller passed an 8-char UUID prefix (e.g. ``d0a940a3``) instead of the
full 36-char UUID.  The ``Run.id`` column is ``UUID(as_uuid=True)`` so
SQLAlchemy tried to cast the short string to a UUID and PostgreSQL
rejected it with ``DataError``.

This test verifies that ``RunService.get()`` normalises short prefixes
to the canonical full UUID before querying.

Additionally tests the non-owneraccess bug: RunNotFoundError (which inherits
from BlueprintError → AppError with http_status=404) is raised when a user
does not own the run and is not an active workspace member, ensuring the
v2 endpoint returns 404 instead of 500.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from app.api._blueprint_cqrs.errors import RunNotFoundError
from app.models.blueprint_models import Run
from app.services.run_service import RunService


def _make_run(run_id: str) -> Run:
    """Create a minimal Run ORM instance with the given id."""
    run = Run()
    object.__setattr__(run, "id", UUID(run_id))
    object.__setattr__(run, "user_id", 1)
    object.__setattr__(run, "status", "completed")
    object.__setattr__(run, "snapshot", {})
    return run


@pytest.mark.asyncio
async def test_get_resolves_short_uuid_prefix() -> None:
    """Short 8-char prefix should resolve to the full UUID."""
    full_id = "d0a940a3-59b4-4744-be14-c98a376a3306"
    short_id = "d0a940a3"
    run = _make_run(full_id)

    load_result = MagicMock()
    load_result.scalar_one_or_none.return_value = run

    db = MagicMock()
    db.execute = AsyncMock(return_value=load_result)

    service = RunService(db=db)
    result = await service.get(short_id, user_id=1)

    assert result.id == run.id
    assert str(result.id) == full_id


@pytest.mark.asyncio
async def test_get_full_uuid_works_as_before() -> None:
    """Full UUID string should resolve via the normal UUID path."""
    full_id = "d0a940a3-59b4-4744-be14-c98a376a3306"
    run = _make_run(full_id)

    load_result = MagicMock()
    load_result.scalar_one_or_none.return_value = run

    db = MagicMock()
    db.execute = AsyncMock(return_value=load_result)

    service = RunService(db=db)
    result = await service.get(full_id, user_id=1)

    assert result.id == run.id


@pytest.mark.asyncio
async def test_get_short_prefix_not_found() -> None:
    """Short prefix that matches nothing should raise RunNotFoundError."""
    db = MagicMock()
    db.execute = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result

    service = RunService(db=db)
    with pytest.raises(RunNotFoundError):
        await service.get("deadbeef", user_id=1)


@pytest.mark.asyncio
async def test_get_non_owner_raises_run_not_found() -> None:
    """Non-owner user should get RunNotFoundError (maps to 404, not 500)."""
    full_id = "d0a940a3-59b4-4744-be14-c98a376a3306"
    owner_id = 33
    other_user_id = 1

    run = Run()
    object.__setattr__(run, "id", UUID(full_id))
    object.__setattr__(run, "user_id", owner_id)
    object.__setattr__(run, "workspace_id", "ws-1")
    object.__setattr__(run, "status", "completed")
    object.__setattr__(run, "snapshot", {})

    run_load_result = MagicMock()
    run_load_result.scalar_one_or_none.return_value = run

    # Second query: no workspace membership found (user is not a member)
    member_load_result = MagicMock()
    member_load_result.scalar_one_or_none.return_value = None

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[run_load_result, member_load_result])

    service = RunService(db=db)
    with pytest.raises(RunNotFoundError):
        await service.get(full_id, user_id=other_user_id)


@pytest.mark.asyncio
async def test_run_not_found_is_app_error_subclass() -> None:
    """RunNotFoundError should be an AppError subclass for proper HTTP status."""
    from app.core.exceptions import AppError

    assert issubclass(RunNotFoundError, AppError)
    assert RunNotFoundError.http_status == 404
    assert RunNotFoundError.code == "RUN_NOT_FOUND"
