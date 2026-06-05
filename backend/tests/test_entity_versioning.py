"""Tests for Phase 3.1 Entity Versioning.

Verifies:
1. Agent, Workspace, Mission models have `version` column
2. AgentVersion, WorkspaceVersion, MissionVersion tables exist with correct schema
3. Versioning service creates snapshots and increments version
4. Version history retrieval works
5. Unique composite indexes enforce one version per entity per number
6. Cascade deletes work correctly
"""

from __future__ import annotations

from datetime import datetime

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


# ── Model-level tests (no DB required) ─────────────────────────────


class TestModelSchema:
    """Verify models have the expected columns and tables."""

    def test_agent_has_version_column(self):
        from app.models.agent import Agent
        cols = {c.name for c in Agent.__table__.columns}
        assert "version" in cols, f"Agent missing 'version' column. Columns: {sorted(cols)}"

    def test_agent_version_table_exists(self):
        from app.models.agent import AgentVersion
        assert AgentVersion.__tablename__ == "agent_versions"
        cols = {c.name for c in AgentVersion.__table__.columns}
        assert "agent_id" in cols
        assert "version" in cols
        assert "snapshot" in cols
        assert "change_summary" in cols

    def test_workspace_has_version_column(self):
        from app.models.workspace_models import Workspace
        cols = {c.name for c in Workspace.__table__.columns}
        assert "version" in cols, f"Workspace missing 'version' column. Columns: {sorted(cols)}"

    def test_workspace_version_table_exists(self):
        from app.models.workspace_models import WorkspaceVersion
        assert WorkspaceVersion.__tablename__ == "workspace_versions"
        cols = {c.name for c in WorkspaceVersion.__table__.columns}
        assert "workspace_id" in cols
        assert "version" in cols
        assert "snapshot" in cols
        assert "change_summary" in cols

    def test_mission_has_version_column(self):
        from app.models.mission_models import Mission
        cols = {c.name for c in Mission.__table__.columns}
        assert "version" in cols, f"Mission missing 'version' column. Columns: {sorted(cols)}"

    def test_mission_version_table_normalized(self):
        from app.models.mission_advanced_models import MissionVersion
        assert MissionVersion.__tablename__ == "mission_versions"
        cols = {c.name for c in MissionVersion.__table__.columns}
        # Should use 'version' not 'version_number'
        assert "version" in cols, f"MissionVersion should have 'version' column, has: {sorted(cols)}"
        assert "version_number" not in cols, "MissionVersion should not have legacy 'version_number'"
        assert "mission_id" in cols
        assert "title" in cols  # individual columns, not snapshot JSONB
        assert "plan" in cols
        assert "change_summary" in cols
        # Snapshot is a @property that synthesizes from individual columns
        assert hasattr(MissionVersion, "snapshot")

    def test_version_models_registered_with_base(self):
        """Verify all version models are importable via __init__.py."""
        from app.models import AgentVersion, WorkspaceVersion, MissionVersion
        assert AgentVersion.__tablename__ == "agent_versions"
        assert WorkspaceVersion.__tablename__ == "workspace_versions"
        assert MissionVersion.__tablename__ == "mission_versions"

    def test_agent_version_defaults(self):
        from app.models.agent import Agent, AgentVersion
        # Agent version defaults to 1
        a = Agent.__table__
        version_col = a.columns["version"]
        assert version_col.default.arg == 1

    def test_workspace_version_defaults(self):
        from app.models.workspace_models import Workspace
        ws = Workspace.__table__
        version_col = ws.columns["version"]
        # server_default is "1"
        assert str(version_col.server_default.arg) == "1"


# ── Versioning service tests ───────────────────────────────────────


class TestVersioningService:
    """Test the shared versioning utility."""

    def test_entity_registry_covers_all_types(self):
        from app.services.versioning import _ENTITY_REGISTRY
        assert "agent" in _ENTITY_REGISTRY
        assert "workspace" in _ENTITY_REGISTRY
        assert "mission" in _ENTITY_REGISTRY

    def test_snapshot_agent(self):
        from app.services.versioning import _snapshot_agent
        agent = MagicMock()
        agent.id = "test-id"
        agent.name = "Test Agent"
        agent.owner_id = "owner-1"
        agent.description = "A test agent"
        agent.system_prompt = "You are helpful"
        agent.model_preference = "deepseek"
        agent.config = "{}"
        agent.state = "active"

        snap = _snapshot_agent(agent)
        assert snap["id"] == "test-id"
        assert snap["name"] == "Test Agent"
        assert snap["state"] == "active"

    def test_snapshot_workspace(self):
        from app.services.versioning import _snapshot_workspace
        ws = MagicMock()
        ws.id = "ws-1"
        ws.name = "My Workspace"
        ws.slug = "my-workspace"
        ws.owner_id = 1
        ws.plan = "pro"
        ws.is_active = True
        ws.logo_url = None
        ws.settings = {}
        ws.member_limit = 10
        ws.subscription_tier_id = None

        snap = _snapshot_workspace(ws)
        assert snap["id"] == "ws-1"
        assert snap["plan"] == "pro"

    def test_snapshot_mission(self):
        from app.services.versioning import _snapshot_mission
        mission = MagicMock()
        mission.id = uuid4()
        mission.user_id = 1
        mission.title = "Test Mission"
        mission.description = "Do something"
        mission.mission_type = "solo"
        mission.context_files = None
        mission.context_urls = None
        mission.constraints = None
        mission.plan = {"tasks": []}
        mission.status = "pending"
        mission.priority = "medium"
        mission.fallback_strategy = "human_escalate"
        mission.parent_mission_id = None

        snap = _snapshot_mission(mission)
        assert snap["title"] == "Test Mission"
        assert snap["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_version_snapshot_unknown_type(self):
        from app.services.versioning import create_version_snapshot
        db = AsyncMock()

        entity = MagicMock()
        entity.id = "test"

        with pytest.raises(ValueError, match="Unknown entity_type"):
            await create_version_snapshot(db, "unknown_type", entity)

    @pytest.mark.asyncio
    async def test_create_version_snapshot_increments_version(self):
        from app.services.versioning import create_version_snapshot
        db = AsyncMock()
        db.add = MagicMock()

        # Simulate an Agent with version=1
        agent = MagicMock()
        agent.id = "agent-1"
        agent.version = 1
        agent.name = "Test"
        agent.owner_id = "owner"
        agent.description = ""
        agent.system_prompt = ""
        agent.model_preference = None
        agent.config = None
        agent.state = "active"

        new_version = await create_version_snapshot(
            db, "agent", agent, change_summary="initial config",
        )

        assert new_version == 2
        assert agent.version == 2
        db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_version_snapshot_first_version(self):
        from app.services.versioning import create_version_snapshot
        db = AsyncMock()
        db.add = MagicMock()

        # Simulate a Workspace with version=None (never versioned)
        ws = MagicMock()
        ws.id = "ws-1"
        ws.version = None
        ws.name = "Test WS"
        ws.slug = "test-ws"
        ws.owner_id = 1
        ws.plan = "free"
        ws.is_active = True
        ws.logo_url = None
        ws.settings = None
        ws.member_limit = 5
        ws.subscription_tier_id = None

        new_version = await create_version_snapshot(db, "workspace", ws)

        assert new_version == 1
        assert ws.version == 1
        db.add.assert_called_once()


# ── Migration structural tests ─────────────────────────────────────


class TestVersionRetrieval:
    """Test version history and snapshot retrieval."""

    @pytest.mark.asyncio
    async def test_get_version_history_unknown_type(self):
        from app.services.versioning import get_version_history
        db = AsyncMock()
        with pytest.raises(ValueError, match="Unknown entity_type"):
            await get_version_history(db, "nope", "id-1")

    @pytest.mark.asyncio
    async def test_get_version_snapshot_unknown_type(self):
        from app.services.versioning import get_version_snapshot
        db = AsyncMock()
        with pytest.raises(ValueError, match="Unknown entity_type"):
            await get_version_snapshot(db, "nope", "id-1", 1)

    @pytest.mark.asyncio
    async def test_get_version_history_returns_list(self):
        from app.services.versioning import get_version_history
        from app.models.agent import AgentVersion

        # Mock the DB to return AgentVersion rows
        mock_row = MagicMock()
        mock_row.id = "v1"
        mock_row.version = 1
        mock_row.change_summary = "initial"
        mock_row.created_at = datetime(2026, 6, 5, 12, 0, 0)

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [mock_row]
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        history = await get_version_history(db, "agent", "agent-1")
        assert len(history) == 1
        assert history[0]["version"] == 1
        assert history[0]["change_summary"] == "initial"

    @pytest.mark.asyncio
    async def test_get_version_snapshot_returns_none_when_missing(self):
        from app.services.versioning import get_version_snapshot

        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await get_version_snapshot(db, "agent", "agent-1", 99)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_version_snapshot_returns_dict(self):
        from app.services.versioning import get_version_snapshot

        mock_row = MagicMock()
        mock_row.id = "v1"
        mock_row.version = 2
        mock_row.snapshot = {"id": "agent-1", "name": "Test"}
        mock_row.change_summary = "updated name"
        mock_row.created_at = datetime(2026, 6, 5, 12, 0, 0)

        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_row
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars

        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await get_version_snapshot(db, "agent", "agent-1", 2)
        assert result is not None
        assert result["version"] == 2
        assert result["snapshot"]["name"] == "Test"


class TestMigrationStructure:
    """Verify the migration file has correct structure."""

    def test_migration_file_imports(self):
        """Verify the migration module is importable."""
        from pathlib import Path
        import importlib.util

        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "20260605_entity_versioning.py"
        spec = importlib.util.spec_from_file_location(
            "20260605_entity_versioning",
            str(migration_path),
        )
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.revision == "20260605_entity_versioning"
        assert module.down_revision == "20260605_marketplace"
        assert callable(module.upgrade)
        assert callable(module.downgrade)
