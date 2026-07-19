"""Regression: query handlers always serve the legacy ``Mission`` table.

The ``USE_NEW_READS`` kill-switch (``compat.use_new_reads()``) is pinned False.
Its read-route branches in ``queries.py`` were removed, so the handlers must
route to the legacy ``app.services.mission_service`` reads and never to the
dormant Blueprint/Run compat reads. This test locks that in.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.api._mission_cqrs import queries
from app.api._mission_cqrs.queries import MissionQueryHandlers


@pytest.fixture
def handler(monkeypatch):
    """A handler with a mock session and a forced cache miss."""
    session = AsyncMock()
    h = MissionQueryHandlers(session)

    # Force cache miss so the handler falls through to the DB read path.
    monkeypatch.setattr(queries, "cache_list", AsyncMock(return_value=None))
    # Prevent the fire-and-forget cache write from touching anything real.
    monkeypatch.setattr(queries, "_schedule_fire_and_forget", AsyncMock())
    return h


async def test_list_missions_routes_to_legacy_service(handler, monkeypatch):
    legacy = AsyncMock(return_value=([], 0))
    monkeypatch.setattr(queries, "list_missions", legacy)

    await handler.list_missions(1, 1, 20)

    legacy.assert_awaited_once()


async def test_compat_blueprint_reads_are_not_referenced(handler):
    # The dead branches were deleted: compat Blueprint/Run read functions must
    # no longer be reachable from the queries module.
    assert not hasattr(queries, "list_missions_from_blueprints")
    assert not hasattr(queries, "list_active_from_blueprints")
    assert not hasattr(queries, "active_missions_from_blueprints")
    assert not hasattr(queries, "get_mission_as_shim")
    assert not hasattr(queries, "get_mission_from_blueprint")


async def test_get_mission_routes_to_legacy_service(handler, monkeypatch):
    legacy = AsyncMock()
    monkeypatch.setattr(queries, "require_mission_access", legacy)

    await handler.get_mission(1, __import__("uuid").uuid4())

    legacy.assert_awaited_once()
