"""Tests for Phase 3.3: Workspace-native substrate.

Verifies that workspace_id columns exist on all expected tables and
that the migration was applied correctly.

Usage (inside container):
    pytest /app/tests/test_workspace_native.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


class TestWorkspaceIdColumns:
    """Verify all models have workspace_id column."""

    def test_mission_has_workspace_id(self):
        from app.models.mission_models import Mission

        cols = {c.name for c in Mission.__table__.columns}
        assert "workspace_id" in cols

    def test_workflow_has_workspace_id(self):
        from app.models.graph import Workflow

        cols = {c.name for c in Workflow.__table__.columns}
        assert "workspace_id" in cols

    def test_workflow_execution_has_workspace_id(self):
        from app.models.graph import WorkflowExecution

        cols = {c.name for c in WorkflowExecution.__table__.columns}
        assert "workspace_id" in cols

    def test_agent_has_workspace_id(self):
        from app.models.agent import Agent

        cols = {c.name for c in Agent.__table__.columns}
        assert "workspace_id" in cols

    def test_agent_template_has_workspace_id(self):
        from app.models.agent import AgentTemplate

        cols = {c.name for c in AgentTemplate.__table__.columns}
        assert "workspace_id" in cols

    def test_tool_catalog_has_workspace_id(self):
        from app.models.tool_catalog_models import Tool

        cols = {c.name for c in Tool.__table__.columns}
        assert "workspace_id" in cols

    def test_capability_catalog_has_workspace_id(self):
        from app.models.capability_catalog_models import Capability

        cols = {c.name for c in Capability.__table__.columns}
        assert "workspace_id" in cols

    def test_chat_thread_has_workspace_id(self):
        from app.models.chat import ChatThread

        cols = {c.name for c in ChatThread.__table__.columns}
        assert "workspace_id" in cols


class TestWorkspaceIdNullability:
    """Verify workspace_id is nullable (backward compat with existing data)."""

    def test_mission_workspace_id_nullable(self):
        from app.models.mission_models import Mission

        col = Mission.__table__.columns["workspace_id"]
        assert col.nullable is True

    def test_agent_workspace_id_nullable(self):
        from app.models.agent import Agent

        col = Agent.__table__.columns["workspace_id"]
        assert col.nullable is True

    def test_workflow_workspace_id_nullable(self):
        from app.models.graph import Workflow

        col = Workflow.__table__.columns["workspace_id"]
        assert col.nullable is True

    def test_tool_catalog_workspace_id_nullable(self):
        from app.models.tool_catalog_models import Tool

        col = Tool.__table__.columns["workspace_id"]
        assert col.nullable is True


class TestWorkspaceIdForeignKey:
    """Verify FK constraints point to workspaces.id for operational tables."""

    def test_mission_workspace_fk(self):
        from app.models.mission_models import Mission

        col = Mission.__table__.columns["workspace_id"]
        fk = next(iter(col.foreign_keys))
        assert "workspaces" in str(fk)

    def test_agent_workspace_fk(self):
        from app.models.agent import Agent

        col = Agent.__table__.columns["workspace_id"]
        fk = next(iter(col.foreign_keys))
        assert "workspaces" in str(fk)

    def test_workflow_workspace_fk(self):
        from app.models.graph import Workflow

        col = Workflow.__table__.columns["workspace_id"]
        fk = next(iter(col.foreign_keys))
        assert "workspaces" in str(fk)

    def test_workflow_execution_workspace_fk(self):
        from app.models.graph import WorkflowExecution

        col = WorkflowExecution.__table__.columns["workspace_id"]
        fk = next(iter(col.foreign_keys))
        assert "workspaces" in str(fk)

    def test_agent_template_workspace_fk(self):
        from app.models.agent import AgentTemplate

        col = AgentTemplate.__table__.columns["workspace_id"]
        fk = next(iter(col.foreign_keys))
        assert "workspaces" in str(fk)

    def test_tool_catalog_no_fk(self):
        """Catalog tables use workspace_id without FK (NULL = global)."""
        from app.models.tool_catalog_models import Tool

        col = Tool.__table__.columns["workspace_id"]
        fks = list(col.foreign_keys)
        assert len(fks) == 0, "tools_catalog.workspace_id should NOT have FK"


class TestPlaygroundWorkspaceIdType:
    """Issue #25: playground_sandboxes.workspace_id must be String(36), not UUID.

    The reconciliation migration inadvertently changed it to UUID, creating a
    type mismatch with workspaces.id (VARCHAR 36).  These tests guard against
    regression.
    """

    def test_playground_workspace_id_is_string(self):
        from sqlalchemy import String

        from app.models.playground_models import PlaygroundSandbox

        col = PlaygroundSandbox.__table__.columns["workspace_id"]
        assert isinstance(col.type, String), f"Expected String, got {type(col.type).__name__}"

    def test_playground_workspace_id_length(self):
        from app.models.playground_models import PlaygroundSandbox

        col = PlaygroundSandbox.__table__.columns["workspace_id"]
        assert col.type.length == 36

    def test_playground_workspace_id_fk_to_workspaces(self):
        from app.models.playground_models import PlaygroundSandbox

        col = PlaygroundSandbox.__table__.columns["workspace_id"]
        fk = next(iter(col.foreign_keys))
        assert "workspaces" in str(fk)

    def test_playground_workspace_id_nullable(self):
        from app.models.playground_models import PlaygroundSandbox

        col = PlaygroundSandbox.__table__.columns["workspace_id"]
        assert col.nullable is True

    def test_playground_workspace_id_matches_workspaces_pk(self):
        from sqlalchemy import String

        from app.models.playground_models import PlaygroundSandbox
        from app.models.workspace_models import Workspace

        pk_type = Workspace.__table__.columns["id"].type
        fk_type = PlaygroundSandbox.__table__.columns["workspace_id"].type
        assert isinstance(pk_type, String)
        assert isinstance(fk_type, String)
        assert type(pk_type) == type(fk_type)


class TestMigrationStructure:
    """Verify migration file is importable and correct."""

    def test_migration_importable(self):
        import importlib.util
        from pathlib import Path

        migration_path = Path(__file__).parent.parent / "alembic" / "versions" / "20260606_workspace_native.py"
        spec = importlib.util.spec_from_file_location(
            "20260606_workspace_native",
            str(migration_path),
        )
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert module.revision == "20260606_workspace_native"
        assert module.down_revision == "20260605_entity_versioning"
        assert callable(module.upgrade)
        assert callable(module.downgrade)
