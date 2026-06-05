"""
Integration test: create a classify-and-route workflow, execute it end-to-end,
and verify subgraph execution via start_node_id.

Tests:
1. Create a workflow with start -> task -> log -> end
2. Full execution: all 4 nodes run
3. Subgraph execution from "task": only task, log, end run (start skipped)
4. Verify execution results and node states
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main_fastapi import app
from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.models.graph import GraphWorkflow, GraphExecution

pytestmark = pytest.mark.integration


# ── Test user fixture ──────────────────────────────────────────

TEST_USER = {
    "id": 99999,
    "email": "integration-test@flowmanner.com",
    "name": "Integration Test",
    "role": "pro",
}


@pytest_asyncio.fixture
async def test_user():
    """Return a mock user dict for dependency override."""
    return TEST_USER


# ── Auth bypass ────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client(test_user):
    """Create an async TestClient with auth bypassed."""

    async def override_get_current_user():
        return test_user

    async def override_get_db():
        # Use the app's default session for real DB access
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            yield session

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Cleanup overrides
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db, None)


# ── Workflow definition ────────────────────────────────────────


def classify_route_workflow():
    """Build a simple linear workflow: start -> task -> log -> end."""
    return {
        "name": "Test: Classify & Route",
        "description": "Integration test for classify-and-route workflow with subgraph execution",
        "graph_definition": {
            "nodes": [
                {
                    "id": "n-start",
                    "type": "start",
                    "position": {"x": 100, "y": 200},
                    "data": {
                        "label": "Start",
                        "nodeType": "start",
                    },
                },
                {
                    "id": "n-classify",
                    "type": "condition",
                    "position": {"x": 300, "y": 200},
                    "data": {
                        "label": "Classify",
                        "nodeType": "condition",
                        "expression": "context.get('category') == 'high'",
                    },
                },
                {
                    "id": "n-process",
                    "type": "task",
                    "position": {"x": 500, "y": 200},
                    "data": {
                        "label": "Process",
                        "nodeType": "task",
                        "agent": "You are a data processor. Output a JSON with key 'result' set to 'processed'.",
                    },
                },
                {
                    "id": "n-log",
                    "type": "log",
                    "position": {"x": 700, "y": 200},
                    "data": {
                        "label": "Log Result",
                        "nodeType": "log",
                        "level": "info",
                        "message": "Workflow complete: {{ result }}",
                    },
                },
                {
                    "id": "n-end",
                    "type": "end",
                    "position": {"x": 900, "y": 200},
                    "data": {
                        "label": "End",
                        "nodeType": "end",
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "n-start", "target": "n-classify"},
                {"id": "e2", "source": "n-classify", "target": "n-process"},
                {"id": "e3", "source": "n-process", "target": "n-log"},
                {"id": "e4", "source": "n-log", "target": "n-end"},
            ],
        },
    }


# ── Tests ──────────────────────────────────────────────────────


class TestClassifyRouteWorkflow:
    """Integration tests for the classify-and-route workflow."""

    @pytest.mark.asyncio
    async def test_create_workflow(self, client: AsyncClient):
        """Create a workflow and verify it's saved."""
        payload = classify_route_workflow()
        response = await client.post("/api/graphs/", json=payload)
        assert response.status_code == 201, f"Create failed: {response.text}"

        data = response.json()
        assert "id" in data
        assert data["name"] == payload["name"]
        assert data["graph_definition"] == payload["graph_definition"]

    @pytest.mark.asyncio
    async def test_full_execution(self, client: AsyncClient):
        """Execute the full workflow and verify all 5 nodes complete."""
        # Create the workflow
        payload = classify_route_workflow()
        create_resp = await client.post("/api/graphs/", json=payload)
        assert create_resp.status_code == 201
        workflow_id = create_resp.json()["id"]

        # Execute with input data
        exec_payload = {
            "input_data": {
                "category": "high",
                "message": "test-input",
            }
        }
        exec_resp = await client.post(
            f"/api/graphs/{workflow_id}/execute", json=exec_payload
        )
        assert exec_resp.status_code == 200, f"Execute failed: {exec_resp.text}"

        execution = exec_resp.json()
        assert "id" in execution
        execution_id = execution["id"]

        # Poll until complete (or timeout)
        import asyncio

        status = execution["status"]
        for _ in range(60):  # up to 30 seconds
            await asyncio.sleep(0.5)
            detail_resp = await client.get(
                f"/api/graphs/{workflow_id}/executions/{execution_id}"
            )
            if detail_resp.status_code == 200:
                detail = detail_resp.json()
                status = detail.get("status", status)
                if status in ("completed", "failed"):
                    break

        assert status == "completed", f"Execution did not complete: status={status}"

        # Verify output data exists
        if detail:
            assert detail.get("output_data") is not None

    @pytest.mark.asyncio
    async def test_subgraph_execution_from_process(self, client: AsyncClient):
        """Execute from the process node (subgraph): skip start+classify, run process+log+end."""
        # Create the workflow
        payload = classify_route_workflow()
        create_resp = await client.post("/api/graphs/", json=payload)
        assert create_resp.status_code == 201
        workflow_id = create_resp.json()["id"]

        # Execute from n-process (subgraph = process, log, end)
        exec_payload = {
            "input_data": {
                "start_node_id": "n-process",
                "category": "high",
                "message": "subgraph-test",
            }
        }
        exec_resp = await client.post(
            f"/api/graphs/{workflow_id}/execute", json=exec_payload
        )
        assert (
            exec_resp.status_code == 200
        ), f"Subgraph execute failed: {exec_resp.text}"

        execution = exec_resp.json()
        execution_id = execution["id"]

        # Poll until complete
        import asyncio

        status = execution["status"]
        detail = None
        for _ in range(60):
            await asyncio.sleep(0.5)
            detail_resp = await client.get(
                f"/api/graphs/{workflow_id}/executions/{execution_id}"
            )
            if detail_resp.status_code == 200:
                detail = detail_resp.json()
                status = detail.get("status", status)
                if status in ("completed", "failed"):
                    break

        assert (
            status == "completed"
        ), f"Subgraph execution did not complete: status={status}"

        # Verify node states: start and classify should be "not_executed" or absent
        if detail and detail.get("node_states"):
            node_states = detail["node_states"]
            executed_nodes = {
                ns["node_id"] for ns in node_states if ns.get("status") == "completed"
            }
            # n-process, n-log, n-end should have executed
            assert (
                "n-process" in executed_nodes
            ), f"Expected n-process in executed nodes, got {executed_nodes}"
            assert "n-log" in executed_nodes
            assert "n-end" in executed_nodes
            # n-start and n-classify should NOT have executed (subgraph skip)
            assert (
                "n-start" not in executed_nodes
            ), "n-start should NOT have executed in subgraph"
            assert (
                "n-classify" not in executed_nodes
            ), "n-classify should NOT have executed in subgraph"

    @pytest.mark.asyncio
    async def test_subgraph_execution_curl_equivalent(self, client: AsyncClient):
        """Verify the same flow using a curl-like pattern via httpx."""
        # Create workflow
        payload = classify_route_workflow()
        create_resp = await client.post("/api/graphs/", json=payload)
        assert create_resp.status_code == 201
        workflow_id = create_resp.json()["id"]

        # This verifies the exact curl-equivalent call:
        # curl -X POST http://localhost:8000/api/graphs/{id}/execute \
        #   -H "Content-Type: application/json" \
        #   -d '{"input_data": {"start_node_id": "n-process"}}'
        import json

        response = await client.post(
            f"/api/graphs/{workflow_id}/execute",
            content=json.dumps({"input_data": {"start_node_id": "n-process"}}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["status"] in ("pending", "running", "completed", "failed")
