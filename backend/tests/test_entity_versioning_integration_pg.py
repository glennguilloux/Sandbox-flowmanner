"""Real PostgreSQL integration tests for Phase 3.1 Entity Versioning.

Exercises the versioning service against a live database:
- Creates real entities (Agent, Workspace, Mission)
- Calls create_version_snapshot() and verifies DB rows
- Calls get_version_history() and get_version_snapshot() against real DB
- Verifies unique composite indexes enforce constraints
- Verifies cascade deletes propagate to version tables
- Tests multi-version lifecycle (create → version → update → version again)

Requires: live PostgreSQL with the 20260605_entity_versioning migration applied.

Usage (inside container):
    pytest /app/tests/test_entity_versioning_integration_pg.py -v
"""

from __future__ import annotations

import asyncio
from typing import Generator
from uuid import uuid4

import pytest
from sqlalchemy import text

try:
    from app.database import AsyncSessionLocal
    from app.models.agent import Agent, AgentVersion
    from app.models.workspace_models import Workspace, WorkspaceVersion
    from app.models.mission_models import Mission, MissionStatus
    from app.models.mission_advanced_models import MissionVersion
    from app.services.versioning import (
        create_version_snapshot,
        get_version_history,
        get_version_snapshot,
    )

    _DB_AVAILABLE = True
except Exception as e:
    _DB_AVAILABLE = False
    _DB_IMPORT_ERROR = str(e)


# ── Session-scoped event loop ──────────────────────────────────────
@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Skip condition ─────────────────────────────────────────────────
pytestmark = [
    pytest.mark.skipif(
        not _DB_AVAILABLE,
        reason=f"Database not available: {_DB_IMPORT_ERROR if not _DB_AVAILABLE else ''}",
    ),
    pytest.mark.integration,
]


# ═══════════════════════════════════════════════════════════════════
# Test: Agent versioning (real DB)
# ═══════════════════════════════════════════════════════════════════


class TestAgentVersioningIntegration:

    @pytest.mark.asyncio
    async def test_create_agent_and_version_it(self):
        """Create a real Agent, version it, verify DB rows."""
        agent_id = str(uuid4())
        owner_id = str(uuid4())

        async with AsyncSessionLocal() as db:
            try:
                # Create agent (note: agents table has no 'state' column in DB)
                agent = Agent(
                    id=agent_id,
                    name="Integration Test Agent",
                    owner_id=owner_id,
                    description="An agent for testing",
                    system_prompt="You are helpful",
                    model_preference="deepseek-chat",
                    version=1,
                )
                db.add(agent)
                await db.flush()

                # Version it
                new_ver = await create_version_snapshot(
                    db,
                    "agent",
                    agent,
                    change_summary="initial creation",
                )
                await db.commit()

                assert new_ver == 2
                assert agent.version == 2

                # Verify version row exists
                result = await db.execute(
                    text(
                        "SELECT version, change_summary FROM agent_versions WHERE agent_id = :aid"
                    ),
                    {"aid": agent_id},
                )
                row = result.first()
                assert row is not None
                assert row[0] == 2
                assert row[1] == "initial creation"

                # Verify snapshot JSONB
                result = await db.execute(
                    text(
                        "SELECT snapshot FROM agent_versions WHERE agent_id = :aid AND version = 2"
                    ),
                    {"aid": agent_id},
                )
                snap_row = result.first()
                assert snap_row is not None
                snap = snap_row[0]
                assert snap["name"] == "Integration Test Agent"
                assert snap["snapshot_version"] == 2

            finally:
                await db.execute(
                    text("DELETE FROM agent_versions WHERE agent_id = :aid"),
                    {"aid": agent_id},
                )
                await db.execute(
                    text("DELETE FROM agents WHERE id = :aid"), {"aid": agent_id}
                )
                await db.commit()

    @pytest.mark.asyncio
    async def test_agent_multi_version_lifecycle(self):
        """Create agent, version it 3 times, verify history."""
        agent_id = str(uuid4())
        owner_id = str(uuid4())

        async with AsyncSessionLocal() as db:
            try:
                agent = Agent(
                    id=agent_id,
                    name="Multi-Version Agent",
                    owner_id=owner_id,
                    version=1,
                )
                db.add(agent)
                await db.flush()

                # Version 2
                v2 = await create_version_snapshot(
                    db, "agent", agent, change_summary="v2"
                )
                assert v2 == 2

                # Version 3
                agent.name = "Updated Agent"
                v3 = await create_version_snapshot(
                    db, "agent", agent, change_summary="v3 renamed"
                )
                assert v3 == 3

                # Version 4
                agent.description = "Now with description"
                v4 = await create_version_snapshot(
                    db, "agent", agent, change_summary="v4 described"
                )
                assert v4 == 4

                await db.commit()

                # Query history via service
                history = await get_version_history(db, "agent", agent_id)
                assert (
                    len(history) == 3
                )  # versions 2, 3, 4 (version 1 is the entity itself)
                # Should be desc order
                assert history[0]["version"] == 4
                assert history[1]["version"] == 3
                assert history[2]["version"] == 2

                # Query specific snapshot
                snap = await get_version_snapshot(db, "agent", agent_id, 3)
                assert snap is not None
                assert snap["version"] == 3
                assert snap["snapshot"]["name"] == "Updated Agent"
                assert snap["change_summary"] == "v3 renamed"

            finally:
                await db.execute(
                    text("DELETE FROM agent_versions WHERE agent_id = :aid"),
                    {"aid": agent_id},
                )
                await db.execute(
                    text("DELETE FROM agents WHERE id = :aid"), {"aid": agent_id}
                )
                await db.commit()

    @pytest.mark.asyncio
    async def test_agent_cascade_delete(self):
        """Deleting an agent should cascade-delete its versions."""
        agent_id = str(uuid4())
        owner_id = str(uuid4())

        async with AsyncSessionLocal() as db:
            try:
                agent = Agent(
                    id=agent_id,
                    name="Cascade Test Agent",
                    owner_id=owner_id,
                    version=1,
                )
                db.add(agent)
                await db.flush()

                await create_version_snapshot(db, "agent", agent, change_summary="v2")
                await db.commit()

                # Verify version exists
                result = await db.execute(
                    text("SELECT count(*) FROM agent_versions WHERE agent_id = :aid"),
                    {"aid": agent_id},
                )
                assert result.scalar() == 1

                # Delete the agent (cascade should remove versions)
                await db.execute(
                    text("DELETE FROM agents WHERE id = :aid"), {"aid": agent_id}
                )
                await db.commit()

                # Verify versions are gone
                result = await db.execute(
                    text("SELECT count(*) FROM agent_versions WHERE agent_id = :aid"),
                    {"aid": agent_id},
                )
                assert result.scalar() == 0

            finally:
                # Cleanup in case cascade didn't work (test would have failed above)
                await db.execute(
                    text("DELETE FROM agent_versions WHERE agent_id = :aid"),
                    {"aid": agent_id},
                )
                await db.execute(
                    text("DELETE FROM agents WHERE id = :aid"), {"aid": agent_id}
                )
                await db.commit()


# ═══════════════════════════════════════════════════════════════════
# Test: Workspace versioning (real DB)
# ═══════════════════════════════════════════════════════════════════


class TestWorkspaceVersioningIntegration:

    @pytest.mark.asyncio
    async def test_create_workspace_and_version_it(self):
        """Create a real Workspace, version it, verify DB rows."""
        ws_id = str(uuid4())
        slug = f"test-ws-{uuid4().hex[:8]}"

        async with AsyncSessionLocal() as db:
            try:
                ws = Workspace(
                    id=ws_id,
                    name="Integration Test Workspace",
                    slug=slug,
                    owner_id=1,
                    plan="free",
                    is_active=True,
                    version=1,
                )
                db.add(ws)
                await db.flush()

                # Version it
                new_ver = await create_version_snapshot(
                    db,
                    "workspace",
                    ws,
                    change_summary="initial creation",
                )
                await db.commit()

                assert new_ver == 2
                assert ws.version == 2

                # Verify version row
                result = await db.execute(
                    text(
                        "SELECT version, snapshot FROM workspace_versions WHERE workspace_id = :wid"
                    ),
                    {"wid": ws_id},
                )
                row = result.first()
                assert row is not None
                assert row[0] == 2
                assert row[1]["name"] == "Integration Test Workspace"
                assert row[1]["plan"] == "free"
                assert row[1]["snapshot_version"] == 2

            finally:
                await db.execute(
                    text("DELETE FROM workspace_versions WHERE workspace_id = :wid"),
                    {"wid": ws_id},
                )
                await db.execute(
                    text("DELETE FROM workspaces WHERE id = :wid"), {"wid": ws_id}
                )
                await db.commit()

    @pytest.mark.asyncio
    async def test_workspace_version_history_and_snapshot(self):
        """Version a workspace twice, query history and specific snapshot."""
        ws_id = str(uuid4())
        slug = f"test-ws-{uuid4().hex[:8]}"

        async with AsyncSessionLocal() as db:
            try:
                ws = Workspace(
                    id=ws_id,
                    name="History Test WS",
                    slug=slug,
                    owner_id=1,
                    plan="free",
                    is_active=True,
                    version=1,
                )
                db.add(ws)
                await db.flush()

                await create_version_snapshot(db, "workspace", ws, change_summary="v2")
                ws.plan = "pro"
                await create_version_snapshot(
                    db, "workspace", ws, change_summary="upgraded to pro"
                )
                await db.commit()

                # History
                history = await get_version_history(db, "workspace", ws_id)
                assert len(history) == 2
                assert history[0]["version"] == 3
                assert history[0]["change_summary"] == "upgraded to pro"
                assert history[1]["version"] == 2

                # Specific snapshot
                snap = await get_version_snapshot(db, "workspace", ws_id, 3)
                assert snap is not None
                assert snap["snapshot"]["plan"] == "pro"

                # Non-existent version
                missing = await get_version_snapshot(db, "workspace", ws_id, 99)
                assert missing is None

            finally:
                await db.execute(
                    text("DELETE FROM workspace_versions WHERE workspace_id = :wid"),
                    {"wid": ws_id},
                )
                await db.execute(
                    text("DELETE FROM workspaces WHERE id = :wid"), {"wid": ws_id}
                )
                await db.commit()


# ═══════════════════════════════════════════════════════════════════
# Test: Mission versioning (real DB)
# ═══════════════════════════════════════════════════════════════════


class TestMissionVersioningIntegration:

    @pytest.mark.asyncio
    async def test_create_mission_and_version_it(self):
        """Create a real Mission, version it, verify the normalized column name."""
        mission_id = str(uuid4())

        async with AsyncSessionLocal() as db:
            try:
                mission = Mission(
                    id=mission_id,
                    user_id=1,
                    title="Integration Test Mission",
                    description="Testing mission versioning",
                    mission_type="solo",
                    status=MissionStatus.PENDING,
                    priority="medium",
                    version=1,
                )
                db.add(mission)
                await db.flush()

                # Version it
                new_ver = await create_version_snapshot(
                    db,
                    "mission",
                    mission,
                    change_summary="initial plan",
                )
                await db.commit()

                assert new_ver == 2
                assert mission.version == 2

                # Verify version row uses 'version' column (not 'version_number')
                result = await db.execute(
                    text(
                        "SELECT version, title, mission_type, priority FROM mission_versions WHERE mission_id = :mid"
                    ),
                    {"mid": mission_id},
                )
                row = result.first()
                assert row is not None
                assert row[0] == 2
                assert row[1] == "Integration Test Mission"
                assert row[2] == "solo"
                assert row[3] == "medium"

            finally:
                await db.execute(
                    text("DELETE FROM mission_versions WHERE mission_id = :mid"),
                    {"mid": mission_id},
                )
                await db.execute(
                    text("DELETE FROM missions WHERE id = :mid"), {"mid": mission_id}
                )
                await db.commit()

    @pytest.mark.asyncio
    async def test_mission_cascade_delete(self):
        """Deleting a mission should cascade-delete its versions."""
        mission_id = str(uuid4())

        async with AsyncSessionLocal() as db:
            try:
                mission = Mission(
                    id=mission_id,
                    user_id=1,
                    title="Cascade Mission",
                    status=MissionStatus.PENDING,
                    version=1,
                )
                db.add(mission)
                await db.flush()

                await create_version_snapshot(
                    db, "mission", mission, change_summary="v2"
                )
                await create_version_snapshot(
                    db, "mission", mission, change_summary="v3"
                )
                await db.commit()

                # Verify 2 versions exist
                result = await db.execute(
                    text(
                        "SELECT count(*) FROM mission_versions WHERE mission_id = :mid"
                    ),
                    {"mid": mission_id},
                )
                assert result.scalar() == 2

                # Delete mission (cascade)
                await db.execute(
                    text("DELETE FROM missions WHERE id = :mid"), {"mid": mission_id}
                )
                await db.commit()

                # Verify versions gone
                result = await db.execute(
                    text(
                        "SELECT count(*) FROM mission_versions WHERE mission_id = :mid"
                    ),
                    {"mid": mission_id},
                )
                assert result.scalar() == 0

            finally:
                await db.execute(
                    text("DELETE FROM mission_versions WHERE mission_id = :mid"),
                    {"mid": mission_id},
                )
                await db.execute(
                    text("DELETE FROM missions WHERE id = :mid"), {"mid": mission_id}
                )
                await db.commit()


# ═══════════════════════════════════════════════════════════════════
# Test: Unique composite index enforcement
# ═══════════════════════════════════════════════════════════════════


class TestUniqueIndexIntegration:

    @pytest.mark.asyncio
    async def test_agent_versions_unique_constraint(self):
        """Two agent_versions with same (agent_id, version) should fail."""
        agent_id = str(uuid4())
        owner_id = str(uuid4())

        async with AsyncSessionLocal() as db:
            try:
                agent = Agent(
                    id=agent_id,
                    name="Unique Test Agent",
                    owner_id=owner_id,
                    version=1,
                )
                db.add(agent)
                await db.flush()

                # Create version 2
                await create_version_snapshot(
                    db, "agent", agent, change_summary="first v2"
                )
                await db.commit()

                # Try to insert a duplicate (agent_id, version=2) directly
                duplicate = AgentVersion(
                    id=str(uuid4()),
                    agent_id=agent_id,
                    version=2,  # Same version!
                    snapshot={"duplicate": True},
                )
                db.add(duplicate)

                with pytest.raises(Exception) as exc_info:
                    await db.commit()

                error_msg = str(exc_info.value).lower()
                assert "unique" in error_msg or "duplicate" in error_msg

                await db.rollback()

            finally:
                await db.execute(
                    text("DELETE FROM agent_versions WHERE agent_id = :aid"),
                    {"aid": agent_id},
                )
                await db.execute(
                    text("DELETE FROM agents WHERE id = :aid"), {"aid": agent_id}
                )
                await db.commit()

    @pytest.mark.asyncio
    async def test_workspace_versions_unique_constraint(self):
        """Two workspace_versions with same (workspace_id, version) should fail."""
        ws_id = str(uuid4())
        slug = f"unique-test-{uuid4().hex[:8]}"

        async with AsyncSessionLocal() as db:
            try:
                ws = Workspace(
                    id=ws_id,
                    name="Unique Test WS",
                    slug=slug,
                    owner_id=1,
                    plan="free",
                    is_active=True,
                    version=1,
                )
                db.add(ws)
                await db.flush()

                await create_version_snapshot(db, "workspace", ws, change_summary="v2")
                await db.commit()

                # Try duplicate
                duplicate = WorkspaceVersion(
                    id=str(uuid4()),
                    workspace_id=ws_id,
                    version=2,
                    snapshot={"duplicate": True},
                )
                db.add(duplicate)

                with pytest.raises(Exception) as exc_info:
                    await db.commit()

                error_msg = str(exc_info.value).lower()
                assert "unique" in error_msg or "duplicate" in error_msg

                await db.rollback()

            finally:
                await db.execute(
                    text("DELETE FROM workspace_versions WHERE workspace_id = :wid"),
                    {"wid": ws_id},
                )
                await db.execute(
                    text("DELETE FROM workspaces WHERE id = :wid"), {"wid": ws_id}
                )
                await db.commit()


# ═══════════════════════════════════════════════════════════════════
# Test: Empty history for non-existent entity
# ═══════════════════════════════════════════════════════════════════


class TestEmptyHistoryIntegration:

    @pytest.mark.asyncio
    async def test_version_history_empty_for_unknown_entity(self):
        """Querying history for a non-existent entity returns empty list."""
        async with AsyncSessionLocal() as db:
            history = await get_version_history(db, "agent", "non-existent-id")
            assert history == []

    @pytest.mark.asyncio
    async def test_version_snapshot_none_for_unknown_entity(self):
        """Querying a specific version for a non-existent entity returns None."""
        async with AsyncSessionLocal() as db:
            snap = await get_version_snapshot(db, "agent", "non-existent-id", 1)
            assert snap is None

    @pytest.mark.asyncio
    async def test_version_history_pagination(self):
        """Test limit and offset parameters."""
        agent_id = str(uuid4())
        owner_id = str(uuid4())

        async with AsyncSessionLocal() as db:
            try:
                agent = Agent(
                    id=agent_id,
                    name="Pagination Test Agent",
                    owner_id=owner_id,
                    version=1,
                )
                db.add(agent)
                await db.flush()

                # Create 5 versions (v2 through v6)
                for i in range(2, 7):
                    agent.name = f"Version {i}"
                    await create_version_snapshot(
                        db, "agent", agent, change_summary=f"v{i}"
                    )
                await db.commit()

                # Get all
                all_versions = await get_version_history(db, "agent", agent_id)
                assert len(all_versions) == 5

                # Limit 2
                limited = await get_version_history(db, "agent", agent_id, limit=2)
                assert len(limited) == 2
                assert limited[0]["version"] == 6  # desc order

                # Offset + limit
                offset = await get_version_history(
                    db, "agent", agent_id, limit=2, offset=2
                )
                assert len(offset) == 2
                assert offset[0]["version"] == 4

            finally:
                await db.execute(
                    text("DELETE FROM agent_versions WHERE agent_id = :aid"),
                    {"aid": agent_id},
                )
                await db.execute(
                    text("DELETE FROM agents WHERE id = :aid"), {"aid": agent_id}
                )
                await db.commit()
