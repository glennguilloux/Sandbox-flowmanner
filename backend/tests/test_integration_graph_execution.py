"""
Integration test: create a linear workflow, execute it end-to-end,
and verify subgraph execution via start_node_id.

Tests:
1. Create a workflow with start -> task -> log -> end
2. Full execution: all 4 nodes run to completion
3. Subgraph execution from "task": only task, log, end run (start skipped)
4. Verify execution results include per-node outputs

Requirements:
- PostgreSQL must be running (Docker: workflow-postgres container)
- Tests override DATABASE_URL to use localhost

Usage:
    pytest tests/test_integration_graph_execution.py -v
"""

import asyncio
import uuid
import time

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.main_fastapi import app
from app.models.user import User

pytestmark = pytest.mark.integration

# ── Override DATABASE_URL to use localhost ─────────────────────────────────

_TEST_DATABASE_URL = settings.DATABASE_URL.replace("workflow-postgres", "localhost")

_test_engine = create_async_engine(_TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestSessionLocal = sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)


# ── Engine lifecycle ───────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session", autouse=True)
async def _manage_engine():
    yield
    await _test_engine.dispose()


# ── Patch settings.DATABASE_URL for background tasks ────────────────────
# The background task _execute_graph_async creates its own session via
# AsyncSessionLocal, which uses settings.DATABASE_URL. We must override
# it to use localhost, otherwise the background task tries to connect to
# the Docker hostname "workflow-postgres" and fails.

@pytest.fixture(autouse=True)
def _patch_database(monkeypatch):
    """Patch both settings.DATABASE_URL and app.database.AsyncSessionLocal.

    The background task _execute_graph_async imports AsyncSessionLocal from
    app.database, which binds to an engine created at import time with the
    original settings.DATABASE_URL. Monkeypatching settings alone doesn't
    change the already-created engine, so we also replace AsyncSessionLocal
    with our localhost-based TestSessionLocal.
    """
    monkeypatch.setattr(settings, "DATABASE_URL", _TEST_DATABASE_URL)
    import app.database
    monkeypatch.setattr(app.database, "AsyncSessionLocal", TestSessionLocal)


# ── Skip if database isn't reachable ───────────────────────────────────────

@pytest.fixture(scope="session")
def _check_database():
    loop = asyncio.new_event_loop()
    try:
        async def _ping():
            async with TestSessionLocal() as s:
                await s.execute(text("SELECT 1"))
        loop.run_until_complete(_ping())
    except Exception as e:
        pytest.skip(f"Database not reachable: {e}")
    finally:
        loop.close()


# ── Unique test user ID ────────────────────────────────────────────────────

def _unique_test_id() -> int:
    return uuid.uuid4().int % 900_000 + 100_000


# ── Test user + session fixture ────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_user_and_session():
    user_id = _unique_test_id()
    email = f"test-{user_id}@test-graph-exec.flowmanner.example"

    async with TestSessionLocal() as session:
        user = User(
            id=user_id,
            email=email,
            username=f"test_graph_{user_id}",
            full_name=f"Test Graph User {user_id}",
            hashed_password="test-hash-not-real",
            is_active=True,
            is_admin=False,
            role="free",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        yield user, session

    # Cleanup
    async with TestSessionLocal() as cleanup_session:
        await cleanup_session.execute(
            text("DELETE FROM graph_states WHERE execution_id IN (SELECT id FROM graph_executions WHERE workflow_id IN (SELECT id FROM graph_workflows WHERE user_id = :uid))"),
            {"uid": user_id},
        )
        await cleanup_session.execute(
            text("DELETE FROM graph_executions WHERE workflow_id IN (SELECT id FROM graph_workflows WHERE user_id = :uid)"),
            {"uid": user_id},
        )
        await cleanup_session.execute(
            text("DELETE FROM graph_workflows WHERE user_id = :uid"),
            {"uid": user_id},
        )
        await cleanup_session.execute(
            text("DELETE FROM users WHERE id = :uid"),
            {"uid": user_id},
        )
        await cleanup_session.commit()


# ── TestClient with real DB, mocked auth ──────────────────────────────────

@pytest.fixture
def real_db_client(test_user_and_session):
    test_user, _ = test_user_and_session

    async def override_get_db():
        async with TestSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_current_user, None)


# ── Helpers ────────────────────────────────────────────────────────────────

def _linear_workflow_payload(name: str = "Integration Test — Linear") -> dict:
    """Return a graph_definition for: start → task → log → end."""
    return {
        "name": name,
        "description": "Linear workflow for integration testing",
        "graph_definition": {
            "nodes": [
                {
                    "id": "start-1",
                    "type": "custom",
                    "position": {"x": 250, "y": 0},
                    "data": {
                        "label": "Start",
                        "nodeType": "start",
                        "input": {"message": "hello from integration test"},
                    },
                },
                {
                    "id": "transform-1",
                    "type": "custom",
                    "position": {"x": 250, "y": 100},
                    "data": {
                        "label": "Transform",
                        "nodeType": "transform",
                        "template": "{{start-1.output.message}}",
                        "outputSchema": {"text": "string"},
                    },
                },
                {
                    "id": "log-1",
                    "type": "custom",
                    "position": {"x": 250, "y": 200},
                    "data": {
                        "label": "Log Result",
                        "nodeType": "log",
                        "message": "Transformed: {{transform-1.output.text}}",
                    },
                },
                {
                    "id": "end-1",
                    "type": "custom",
                    "position": {"x": 250, "y": 300},
                    "data": {
                        "label": "End",
                        "nodeType": "end",
                    },
                },
            ],
            "edges": [
                {"id": "e-start-task", "source": "start-1", "target": "transform-1"},
                {"id": "e-task-log", "source": "transform-1", "target": "log-1"},
                {"id": "e-log-end", "source": "log-1", "target": "end-1"},
            ],
        },
    }


def _wait_for_execution(client, workflow_id: str, execution_id: str, timeout: float = 30.0) -> dict:
    """Poll GET /api/graphs/{wid}/executions/{eid} until terminal status."""
    deadline = time.monotonic() + timeout
    terminal = {"completed", "failed", "paused"}

    while time.monotonic() < deadline:
        resp = client.get(f"/api/graphs/{workflow_id}/executions/{execution_id}")
        assert resp.status_code == 200, f"Failed to fetch execution: {resp.text}"
        data = resp.json()
        if data["status"] in terminal:
            return data
        time.sleep(0.5)

    # Timeout — fetch one last time to report current state, then fail
    try:
        resp = client.get(f"/api/graphs/{workflow_id}/executions/{execution_id}")
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status", "unknown")
            error = data.get("error_message", "")
            pytest.fail(f"Execution did not reach terminal state within {timeout}s. "
                        f"Current status: {status}. Error: {error}")
    except Exception:
        pass
    pytest.fail(f"Execution did not reach terminal state within {timeout}s. "
                f"Could not determine current status.")


# ── Tests ──────────────────────────────────────────────────────────────────

class TestFullGraphExecution:
    """End-to-end: start → task → log → end, all nodes complete."""

    def test_create_and_execute_full_workflow(self, real_db_client):
        client = real_db_client

        # 1. Create workflow
        payload = _linear_workflow_payload()
        create_resp = client.post("/api/graphs/", json=payload)
        assert create_resp.status_code == 201, f"Create failed: {create_resp.text}"
        workflow = create_resp.json()
        workflow_id = workflow["id"]
        assert workflow["name"] == payload["name"]
        assert workflow["status"] in ("draft", None)

        # 2. Execute full workflow
        exec_resp = client.post(
            f"/api/graphs/{workflow_id}/execute",
            json={"input_data": {"message": "test"}},
        )
        assert exec_resp.status_code == 201, f"Execute failed: {exec_resp.text}"
        execution = exec_resp.json()
        execution_id = execution["id"]
        assert execution["status"] in ("pending", "running")

        # 3. Poll until complete
        result = _wait_for_execution(client, workflow_id, execution_id, timeout=30)
        assert result["status"] == "completed", (
            f"Expected completed, got {result['status']}. "
            f"Error: {result.get('error_message', 'none')}. "
            f"Output: {result.get('output_data')}"
        )

        # 4. Verify node outputs exist
        output_data = result.get("output_data") or {}
        outputs = output_data.get("outputs", {})
        for nid in ("start-1", "transform-1", "log-1", "end-1"):
            assert nid in outputs, f"Missing output for node {nid}. Got: {list(outputs.keys())}"
            node_output = outputs[nid]
            assert node_output.get("success") is not False, (
                f"Node {nid} failed: {node_output.get('error')}"
            )

    def test_execution_detail_has_node_states(self, real_db_client):
        """Verify GET /executions/{eid} returns per-node states."""
        client = real_db_client

        payload = _linear_workflow_payload("Node States Test")
        create_resp = client.post("/api/graphs/", json=payload)
        workflow_id = create_resp.json()["id"]

        exec_resp = client.post(
            f"/api/graphs/{workflow_id}/execute",
            json={"input_data": {}},
        )
        execution_id = exec_resp.json()["id"]

        result = _wait_for_execution(client, workflow_id, execution_id)
        assert result["status"] == "completed"

        detail = client.get(f"/api/graphs/{workflow_id}/executions/{execution_id}")
        assert detail.status_code == 200
        detail_data = detail.json()
        node_states = detail_data.get("node_states", [])
        assert len(node_states) >= 4, f"Expected >=4 node states, got {len(node_states)}"

        node_ids = {ns.get("node_id") for ns in node_states}
        assert "start-1" in node_ids
        assert "transform-1" in node_ids
        assert "log-1" in node_ids
        assert "end-1" in node_ids


class TestSubGraphExecution:
    """Subgraph: start_node_id=task-1 — only task, log, end execute."""

    def test_subgraph_from_task_skips_start(self, real_db_client):
        client = real_db_client

        payload = _linear_workflow_payload("Subgraph Test — From Task")
        create_resp = client.post("/api/graphs/", json=payload)
        workflow_id = create_resp.json()["id"]

        # Execute with start_node_id in input_data
        exec_resp = client.post(
            f"/api/graphs/{workflow_id}/execute",
            json={"input_data": {"start_node_id": "transform-1"}},
        )
        assert exec_resp.status_code == 201, f"Execute failed: {exec_resp.text}"
        execution_id = exec_resp.json()["id"]

        result = _wait_for_execution(client, workflow_id, execution_id)
        assert result["status"] == "completed", (
            f"Expected completed, got {result['status']}. "
            f"Error: {result.get('error_message', 'none')}"
        )

        # Verify: task-1, log-1, end-1 should have outputs
        output_data = result.get("output_data") or {}
        outputs = output_data.get("outputs", {})
        for nid in ("transform-1", "log-1", "end-1"):
            assert nid in outputs, (
                f"Missing output for downstream node {nid}. "
                f"Got: {list(outputs.keys())}"
            )
            assert outputs[nid].get("success") is not False, (
                f"Node {nid} failed: {outputs[nid].get('error')}"
            )

        # start-1 should NOT be in outputs
        assert "start-1" not in outputs, (
            f"start-1 should not have executed in subgraph mode, "
            f"but it appears in outputs: {list(outputs.keys())}"
        )

    def test_subgraph_from_log_only_log_and_end_execute(self, real_db_client):
        """Subgraph from log-1: only log and end execute."""
        client = real_db_client

        payload = _linear_workflow_payload("Subgraph Test — From Log")
        create_resp = client.post("/api/graphs/", json=payload)
        workflow_id = create_resp.json()["id"]

        exec_resp = client.post(
            f"/api/graphs/{workflow_id}/execute",
            json={"input_data": {"start_node_id": "log-1"}},
        )
        execution_id = exec_resp.json()["id"]

        result = _wait_for_execution(client, workflow_id, execution_id)
        assert result["status"] == "completed"

        outputs = (result.get("output_data") or {}).get("outputs", {})

        assert "log-1" in outputs
        assert "end-1" in outputs
        assert "start-1" not in outputs
        assert "transform-1" not in outputs

    def test_subgraph_from_end_executes_only_end(self, real_db_client):
        """Subgraph from end-1: only end executes."""
        client = real_db_client

        payload = _linear_workflow_payload("Subgraph Test — From End")
        create_resp = client.post("/api/graphs/", json=payload)
        workflow_id = create_resp.json()["id"]

        exec_resp = client.post(
            f"/api/graphs/{workflow_id}/execute",
            json={"input_data": {"start_node_id": "end-1"}},
        )
        execution_id = exec_resp.json()["id"]

        result = _wait_for_execution(client, workflow_id, execution_id)
        assert result["status"] == "completed"

        outputs = (result.get("output_data") or {}).get("outputs", {})
        assert "end-1" in outputs
        assert "start-1" not in outputs
        assert "transform-1" not in outputs
        assert "log-1" not in outputs


class TestEdgeCases:
    """Error and edge case scenarios."""

    def test_execute_nonexistent_workflow(self, real_db_client):
        client = real_db_client
        fake_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/graphs/{fake_id}/execute",
            json={"input_data": {}},
        )
        assert resp.status_code in (404, 422)

    def test_subgraph_nonexistent_node(self, real_db_client):
        """start_node_id that doesn't exist in the graph."""
        client = real_db_client

        payload = _linear_workflow_payload("Subgraph — Bad Node")
        create_resp = client.post("/api/graphs/", json=payload)
        workflow_id = create_resp.json()["id"]

        exec_resp = client.post(
            f"/api/graphs/{workflow_id}/execute",
            json={"input_data": {"start_node_id": "nonexistent-node"}},
        )
        execution_id = exec_resp.json()["id"]

        result = _wait_for_execution(client, workflow_id, execution_id)
        # The execution completes but the nonexistent node produces an error output
        outputs = (result.get("output_data") or {}).get("outputs", {})
        assert len(outputs) == 1, (
            f"Expected 1 output with error for nonexistent start node, got {len(outputs)}"
        )
        node_output = list(outputs.values())[0]
        assert node_output.get("success") is False, (
            f"Expected node failure, got: {node_output}"
        )
        assert "not found" in node_output.get("error", "").lower(), (
            f"Expected 'not found' error, got: {node_output.get('error')}"
        )

    def test_create_workflow_without_nodes(self, real_db_client):
        """Workflow with empty graph_definition should still be creatable."""
        client = real_db_client
        resp = client.post("/api/graphs/", json={
            "name": "Empty Workflow",
            "graph_definition": {"nodes": [], "edges": []},
        })
        assert resp.status_code == 201
        wf = resp.json()
        assert wf["name"] == "Empty Workflow"

        # Executing an empty workflow should complete instantly
        exec_resp = client.post(
            f"/api/graphs/{wf['id']}/execute",
            json={"input_data": {}},
        )
        execution_id = exec_resp.json()["id"]
        result = _wait_for_execution(client, wf["id"], execution_id)
        assert result["status"] == "completed"
