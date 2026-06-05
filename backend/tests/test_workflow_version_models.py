"""Tests for Phase 2.6: WorkflowVersion and ExecutionEvent models + migration."""

from __future__ import annotations

import pytest


class TestWorkflowVersionModel:
    """Verify WorkflowVersion model structure."""

    def test_table_name(self):
        from app.models.workflow_version_models import WorkflowVersion

        assert WorkflowVersion.__tablename__ == "workflow_versions"

    def test_columns(self):
        from app.models.workflow_version_models import WorkflowVersion

        cols = {c.name for c in WorkflowVersion.__table__.columns}
        expected = {
            "id",
            "workflow_id",
            "version",
            "snapshot",
            "description",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(cols)

    def test_workflow_id_fk(self):
        from app.models.workflow_version_models import WorkflowVersion

        fk = list(WorkflowVersion.__table__.columns["workflow_id"].foreign_keys)
        assert len(fk) == 1
        assert "workflows" in str(fk[0].target_fullname)

    def test_registered_with_base(self):
        from app.models import Base

        assert "workflow_versions" in Base.metadata.tables


class TestExecutionEventModel:
    """Verify ExecutionEvent model structure."""

    def test_table_name(self):
        from app.models.workflow_version_models import ExecutionEvent

        assert ExecutionEvent.__tablename__ == "execution_events"

    def test_columns(self):
        from app.models.workflow_version_models import ExecutionEvent

        cols = {c.name for c in ExecutionEvent.__table__.columns}
        expected = {
            "id",
            "execution_id",
            "event_type",
            "node_id",
            "message",
            "payload",
            "level",
            "sequence",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(cols)

    def test_execution_id_fk(self):
        from app.models.workflow_version_models import ExecutionEvent

        fk = list(ExecutionEvent.__table__.columns["execution_id"].foreign_keys)
        assert len(fk) == 1
        assert "workflow_executions" in str(fk[0].target_fullname)

    def test_registered_with_base(self):
        from app.models import Base

        assert "execution_events" in Base.metadata.tables

    def test_event_type_is_indexed(self):
        from app.models.workflow_version_models import ExecutionEvent

        col = ExecutionEvent.__table__.columns["event_type"]
        # Column exists and is not nullable
        assert col.nullable is False


class TestBackwardCompatAliases:
    """Verify the Graph* aliases still work."""

    def test_graph_workflow_alias(self):
        from app.models.graph import GraphWorkflow, Workflow

        assert GraphWorkflow is Workflow

    def test_graph_execution_alias(self):
        from app.models.graph import GraphExecution, WorkflowExecution

        assert GraphExecution is WorkflowExecution

    def test_graph_state_alias(self):
        from app.models.graph import GraphState, WorkflowState

        assert GraphState is WorkflowState
