"""Integration tests for close-missions features: graphs list, execution history, resume, trigger-to-graph."""

import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.graph_executor import ExecutionContext, GraphInterpreter
from app.services.graph_node_handlers import ApprovalNodeHandler


class TestGraphsListAPI:
    """Test graphs list endpoint returns 401 (auth required)."""

    def test_list_graphs_unauthenticated(self):
        import httpx
        resp = httpx.get("http://localhost:8000/api/graphs/")
        assert resp.status_code == 401


class TestExecutionHistoryAPI:
    """Test execution history endpoints return 401."""

    def test_list_executions_unauthenticated(self):
        import httpx
        resp = httpx.get(f"http://localhost:8000/api/graphs/{uuid.uuid4()}/executions")
        assert resp.status_code == 401

    def test_get_execution_detail_unauthenticated(self):
        import httpx
        resp = httpx.get(f"http://localhost:8000/api/graphs/{uuid.uuid4()}/executions/{uuid.uuid4()}")
        assert resp.status_code == 401


class TestResumeAPI:
    """Test resume endpoint returns 401."""

    def test_resume_unauthenticated(self):
        import httpx
        resp = httpx.post(f"http://localhost:8000/api/graphs/{uuid.uuid4()}/resume/{uuid.uuid4()}")
        assert resp.status_code == 401


class TestTriggerGraphAPI:
    """Test trigger-to-graph endpoint returns 401."""

    def test_fire_graph_unauthenticated(self):
        import httpx
        resp = httpx.post(f"http://localhost:8000/api/triggers/{uuid.uuid4()}/fire-graph")
        assert resp.status_code == 401


class TestApprovalPauseResume:
    """Test approval node pauses and resume works."""

    @pytest.mark.asyncio
    async def test_approval_pauses_interpreter(self):
        """Approval node should signal pause to interpreter."""
        nodes = [
            {"id": "s", "data": {"nodeType": "start"}},
            {"id": "a", "data": {"nodeType": "approval", "approverRole": "admin"}},
            {"id": "e", "data": {"nodeType": "end"}},
        ]
        edges = [{"source": "s", "target": "a"}, {"source": "a", "target": "e"}]

        workflow = MagicMock()
        workflow.id = "wf-1"
        workflow.graph_definition = {"nodes": nodes, "edges": edges}
        execution = MagicMock()
        execution.id = "exec-1"
        execution.input_data = {}
        db = AsyncMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        interp = GraphInterpreter(db, workflow, execution)

        with patch("app.services.graph_service.pause_execution", new_callable=AsyncMock):
            result = await interp.execute()
            assert result["status"] == "paused"
            assert result["paused_at"] == "a"
            # End node should NOT have executed
            assert "e" not in result["outputs"]

    @pytest.mark.asyncio
    async def test_approval_returns_pause_flag(self):
        """Approval handler returns pause=True."""
        handler = ApprovalNodeHandler()
        result = await handler.execute(
            {"data": {"nodeType": "approval", "approverRole": "manager"}},
            ExecutionContext(),
        )
        assert result["success"] is True
        assert result["pause"] is True
        assert result["output"]["status"] == "paused"


class TestTriggerEndpointRegistration:
    """Verify trigger fire-graph endpoint is registered."""

    def test_fire_graph_returns_401_not_404(self):
        import httpx
        resp = httpx.post(f"http://localhost:8000/api/triggers/{uuid.uuid4()}/fire-graph")
        assert resp.status_code == 401


class TestEndpointRegistration:
    """Verify all new endpoints are registered."""

    ENDPOINTS = [
        ("GET", "/graphs/"),
        ("GET", "/graphs/test/executions"),
        ("GET", "/graphs/test/executions/test-id"),
        ("POST", "/graphs/test/resume/test-id"),
        ("POST", "/triggers/test-id/fire-graph"),
    ]

    @pytest.mark.parametrize("method,path", ENDPOINTS)
    def test_endpoint_returns_401_not_404(self, method, path):
        import httpx
        resp = httpx.request(method, f"http://localhost:8000/api{path}")
        assert resp.status_code == 401, f"{method} {path} returned {resp.status_code}"
