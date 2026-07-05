"""Integration tests for main swarm API endpoints.

Tests all 3 endpoints: POST /execute, GET (list), GET /{id}.
Validates route registration, request validation, response shapes, and error handling.
Uses synchronous TestClient (project convention) with mocked SwarmOrchestrator.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Mock factories ──────────────────────────────────────────────────────────


def _make_mock_execution(**overrides):
    """Create a mock SwarmExecution with realistic defaults."""
    defaults = {
        "id": "exec-001",
        "goal": "Analyze sales data across all regions",
        "status": "completed",
        "strategy": "parallel",
        "synthesis": "Q3 sales increased 12% across all regions",
        "conflict_markers": None,
        "agent_count": 3,
        "completed_count": 3,
        "total_tokens": 15000,
        "total_cost_usd": 0.045,
        "error_message": None,
        "started_at": None,
        "completed_at": None,
        "created_at": None,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


def _make_mock_task(**overrides):
    """Create a mock SwarmTask with realistic defaults."""
    defaults = {
        "id": "task-001",
        "agent_id": "agent-a",
        "agent_name": "Data Analyst",
        "task_description": "Extract sales figures from database",
        "task_type": "extraction",
        "status": "completed",
        "output": "Sales data extracted: 15000 rows",
        "score": 0.95,
        "tokens_used": 5000,
        "error_message": None,
        "depends_on": None,
        "priority": 1,
    }
    defaults.update(overrides)
    return MagicMock(**defaults)


# ═══════════════════════════════════════════════════════════════════════════════
# POST /api/swarm/execute
# ═══════════════════════════════════════════════════════════════════════════════


class TestExecute:
    """POST /api/swarm/execute — start a multi-agent swarm execution."""

    def test_execute_success(self, test_client):
        """Execute returns full execution shape with tasks array."""
        mock_exec = _make_mock_execution()
        mock_task = _make_mock_task()
        mock_task2 = _make_mock_task(
            id="task-002",
            agent_name="Visualization Expert",
            task_type="visualization",
        )

        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.execute = AsyncMock(return_value=mock_exec)
            mock_orch.get_tasks = AsyncMock(return_value=[mock_task, mock_task2])

            payload = {
                "goal": "Analyze sales data across all regions",
                "strategy": "parallel",
                "max_agents": 3,
            }
            resp = test_client.post("/api/swarm/execute", json=payload)

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "exec-001"
        assert data["goal"] == "Analyze sales data across all regions"
        assert data["status"] == "completed"
        assert data["strategy"] == "parallel"
        assert data["agent_count"] == 3
        assert data["completed_count"] == 3
        assert data["total_tokens"] == 15000
        assert data["synthesis"] == "Q3 sales increased 12% across all regions"
        assert data["conflict_markers"] is None
        assert data["error_message"] is None
        assert data["started_at"] is None
        assert data["completed_at"] is None
        assert len(data["tasks"]) == 2

        t0 = data["tasks"][0]
        assert t0["id"] == "task-001"
        assert t0["agent_name"] == "Data Analyst"
        assert t0["task_description"] == "Extract sales figures from database"
        assert t0["task_type"] == "extraction"
        assert t0["status"] == "completed"
        assert t0["score"] == 0.95
        assert t0["tokens_used"] == 5000
        assert t0["depends_on"] is None
        # output truncated to 500 chars
        assert t0["output"] == "Sales data extracted: 15000 rows"

    @pytest.mark.parametrize("strategy", ["parallel", "sequential", "debate"])
    def test_execute_with_strategies(self, test_client, strategy):
        """All three valid strategies are accepted and passed through."""
        mock_exec = _make_mock_execution(strategy=strategy)

        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.execute = AsyncMock(return_value=mock_exec)
            mock_orch.get_tasks = AsyncMock(return_value=[])

            payload = {
                "goal": "Test",
                "strategy": strategy,
                "max_agents": 3,
            }
            resp = test_client.post("/api/swarm/execute", json=payload)

        assert resp.status_code == 200
        mock_orch.execute.assert_called_once()
        call_kwargs = mock_orch.execute.call_args.kwargs
        assert call_kwargs["strategy"] == strategy

    @pytest.mark.parametrize("max_agents", [1, 5, 10])
    def test_execute_with_max_agents(self, test_client, max_agents):
        """Boundary values for max_agents: 1 (min), 5 (default), 10 (max)."""
        mock_exec = _make_mock_execution(agent_count=max_agents)

        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.execute = AsyncMock(return_value=mock_exec)
            mock_orch.get_tasks = AsyncMock(return_value=[])

            payload = {
                "goal": "Test",
                "strategy": "parallel",
                "max_agents": max_agents,
            }
            resp = test_client.post("/api/swarm/execute", json=payload)

        assert resp.status_code == 200
        call_kwargs = mock_orch.execute.call_args.kwargs
        assert call_kwargs["max_agents"] == max_agents

    def test_execute_with_metadata(self, test_client):
        """Metadata dict is passed through to orchestrator."""
        mock_exec = _make_mock_execution()

        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.execute = AsyncMock(return_value=mock_exec)
            mock_orch.get_tasks = AsyncMock(return_value=[])

            payload = {
                "goal": "Test",
                "strategy": "parallel",
                "max_agents": 3,
                "metadata": {"priority": "high", "tags": ["urgent"]},
            }
            resp = test_client.post("/api/swarm/execute", json=payload)

        assert resp.status_code == 200
        call_kwargs = mock_orch.execute.call_args.kwargs
        assert call_kwargs["metadata"] == {"priority": "high", "tags": ["urgent"]}

    def test_execute_default_strategy(self, test_client):
        """When strategy is omitted, default 'parallel' is used."""
        mock_exec = _make_mock_execution()

        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.execute = AsyncMock(return_value=mock_exec)
            mock_orch.get_tasks = AsyncMock(return_value=[])

            payload = {
                "goal": "Test",
                "max_agents": 3,
            }
            resp = test_client.post("/api/swarm/execute", json=payload)

        assert resp.status_code == 200
        call_kwargs = mock_orch.execute.call_args.kwargs
        assert call_kwargs["strategy"] == "parallel"

    def test_execute_default_max_agents(self, test_client):
        """When max_agents is omitted, default 5 is used."""
        mock_exec = _make_mock_execution()

        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.execute = AsyncMock(return_value=mock_exec)
            mock_orch.get_tasks = AsyncMock(return_value=[])

            payload = {
                "goal": "Test",
            }
            resp = test_client.post("/api/swarm/execute", json=payload)

        assert resp.status_code == 200
        call_kwargs = mock_orch.execute.call_args.kwargs
        assert call_kwargs["max_agents"] == 5
        assert call_kwargs["strategy"] == "parallel"

    def test_execute_output_truncation(self, test_client):
        """Task output is truncated to 500 characters in the response."""
        long_output = "x" * 1000
        mock_exec = _make_mock_execution()
        mock_task = _make_mock_task(output=long_output)

        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.execute = AsyncMock(return_value=mock_exec)
            mock_orch.get_tasks = AsyncMock(return_value=[mock_task])

            resp = test_client.post(
                "/api/swarm/execute",
                json={"goal": "Test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["tasks"][0]["output"]) == 500
        assert data["tasks"][0]["output"] == long_output[:500]

    def test_execute_with_long_output_at_boundary(self, test_client):
        """Task output exactly 500 chars is returned in full (no truncation needed)."""
        exact_output = "x" * 500
        mock_exec = _make_mock_execution()
        mock_task = _make_mock_task(output=exact_output)

        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.execute = AsyncMock(return_value=mock_exec)
            mock_orch.get_tasks = AsyncMock(return_value=[mock_task])

            resp = test_client.post(
                "/api/swarm/execute",
                json={"goal": "Test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["tasks"][0]["output"]) == 500
        assert data["tasks"][0]["output"] == exact_output

    # ── Validation ──────────────────────────────────────────────────────

    def test_validation_goal_required(self, test_client):
        """Missing goal returns 422."""
        resp = test_client.post("/api/swarm/execute", json={"strategy": "parallel"})
        assert resp.status_code == 422

    def test_validation_goal_empty_string(self, test_client):
        """Empty goal returns 422 (min_length=1)."""
        resp = test_client.post(
            "/api/swarm/execute",
            json={"goal": "", "strategy": "parallel"},
        )
        assert resp.status_code == 422

    def test_validation_invalid_strategy(self, test_client):
        """Invalid strategy value returns 422."""
        resp = test_client.post(
            "/api/swarm/execute",
            json={"goal": "Test", "strategy": "invalid_strategy"},
        )
        assert resp.status_code == 422

    def test_validation_max_agents_below_min(self, test_client):
        """max_agents=0 returns 422 (min=1)."""
        resp = test_client.post(
            "/api/swarm/execute",
            json={"goal": "Test", "max_agents": 0},
        )
        assert resp.status_code == 422

    def test_validation_max_agents_above_max(self, test_client):
        """max_agents=11 returns 422 (max=10)."""
        resp = test_client.post(
            "/api/swarm/execute",
            json={"goal": "Test", "max_agents": 11},
        )
        assert resp.status_code == 422

    def test_validation_goal_too_long(self, test_client):
        """Goal exceeding max_length=10000 returns 422."""
        long_goal = "x" * 10001
        resp = test_client.post(
            "/api/swarm/execute",
            json={"goal": long_goal},
        )
        assert resp.status_code == 422

    def test_validation_goal_at_boundary(self, test_client):
        """Goal exactly 10000 chars is accepted."""
        boundary_goal = "x" * 10000
        mock_exec = _make_mock_execution()

        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.execute = AsyncMock(return_value=mock_exec)
            mock_orch.get_tasks = AsyncMock(return_value=[])

            resp = test_client.post(
                "/api/swarm/execute",
                json={"goal": boundary_goal},
            )

        assert resp.status_code == 200

    def test_validation_empty_body(self, test_client):
        """Empty body returns 422."""
        resp = test_client.post("/api/swarm/execute", json={})
        assert resp.status_code == 422

    # ── Error handling ──────────────────────────────────────────────────

    def test_execute_service_failure(self, test_client):
        """Generic orchestrator exception returns 500."""
        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.execute = AsyncMock(side_effect=RuntimeError("LLM API rate limit exceeded"))

            resp = test_client.post(
                "/api/swarm/execute",
                json={"goal": "Test"},
            )

        assert resp.status_code == 500
        assert "LLM API rate limit exceeded" in resp.json()["detail"]

    def test_execute_get_tasks_failure(self, test_client):
        """Orchestrator fails during get_tasks returns 500."""
        mock_exec = _make_mock_execution()

        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.execute = AsyncMock(return_value=mock_exec)
            mock_orch.get_tasks = AsyncMock(side_effect=RuntimeError("Database read timeout"))

            resp = test_client.post(
                "/api/swarm/execute",
                json={"goal": "Test"},
            )

        assert resp.status_code == 500
        assert "Database read timeout" in resp.json()["detail"]

    # ── Null field handling ─────────────────────────────────────────────

    def test_execute_null_datetime_fields(self, test_client):
        """None started_at/completed_at stays None in JSON."""
        mock_exec = _make_mock_execution(started_at=None, completed_at=None)
        mock_task = _make_mock_task()

        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.execute = AsyncMock(return_value=mock_exec)
            mock_orch.get_tasks = AsyncMock(return_value=[mock_task])

            resp = test_client.post(
                "/api/swarm/execute",
                json={"goal": "Test"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["started_at"] is None
        assert data["completed_at"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/swarm  (list executions)
# ═══════════════════════════════════════════════════════════════════════════════


class TestList:
    """GET /api/swarm — list recent swarm executions."""

    def test_list_executions_success(self, test_client):
        """List returns correct envelope with execution summaries."""
        mock_e1 = _make_mock_execution(id="exec-001")
        mock_e2 = _make_mock_execution(
            id="exec-002",
            goal="Generate quarterly report",
            status="running",
            strategy="sequential",
            agent_count=5,
            completed_count=2,
            total_tokens=8000,
        )

        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.list_executions = AsyncMock(return_value=[mock_e1, mock_e2])

            resp = test_client.get("/api/swarm")

        assert resp.status_code == 200
        data = resp.json()
        assert "executions" in data
        assert len(data["executions"]) == 2

        e0 = data["executions"][0]
        assert e0["id"] == "exec-001"
        assert e0["goal"] == "Analyze sales data across all regions"
        assert e0["status"] == "completed"
        assert e0["strategy"] == "parallel"
        assert e0["agent_count"] == 3
        assert e0["completed_count"] == 3
        assert e0["total_tokens"] == 15000
        assert e0["created_at"] is None

    def test_list_executions_with_limit(self, test_client):
        """Limit query param is passed to service."""
        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.list_executions = AsyncMock(return_value=[])

            resp = test_client.get("/api/swarm", params={"limit": 10})

        assert resp.status_code == 200
        mock_orch.list_executions.assert_called_once()
        call_kwargs = mock_orch.list_executions.call_args.kwargs
        assert call_kwargs["limit"] == 10

    def test_list_executions_default_limit(self, test_client):
        """Default limit=20 is used when not specified."""
        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.list_executions = AsyncMock(return_value=[])

            resp = test_client.get("/api/swarm")

        assert resp.status_code == 200
        call_kwargs = mock_orch.list_executions.call_args.kwargs
        assert call_kwargs["limit"] == 20

    @pytest.mark.parametrize("limit", [1, 100])
    def test_list_executions_boundary_limits(self, test_client, limit):
        """Boundary limits 1 (min) and 100 (max) are accepted."""
        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.list_executions = AsyncMock(return_value=[])

            resp = test_client.get("/api/swarm", params={"limit": limit})

        assert resp.status_code == 200, f"limit={limit} should be accepted"
        assert mock_orch.list_executions.call_args.kwargs["limit"] == limit

    def test_list_executions_empty(self, test_client):
        """Empty list returns empty executions array."""
        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.list_executions = AsyncMock(return_value=[])

            resp = test_client.get("/api/swarm")

        assert resp.status_code == 200
        assert resp.json() == {"executions": []}

    def test_list_executions_goal_truncation(self, test_client):
        """Goal > 200 chars is truncated to 200 in the list response."""
        long_goal = "y" * 500
        mock_e = _make_mock_execution(goal=long_goal)

        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.list_executions = AsyncMock(return_value=[mock_e])

            resp = test_client.get("/api/swarm")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["executions"][0]["goal"]) == 200
        assert data["executions"][0]["goal"] == long_goal[:200]

    def test_list_executions_goal_at_boundary(self, test_client):
        """Goal exactly 200 chars is returned in full."""
        boundary_goal = "z" * 200
        mock_e = _make_mock_execution(goal=boundary_goal)

        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.list_executions = AsyncMock(return_value=[mock_e])

            resp = test_client.get("/api/swarm")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["executions"][0]["goal"]) == 200
        assert data["executions"][0]["goal"] == boundary_goal

    @pytest.mark.parametrize("limit", [0, 101])
    def test_list_executions_limit_out_of_range(self, test_client, limit):
        """Limit outside 1-100 range returns 422."""
        resp = test_client.get("/api/swarm", params={"limit": limit})
        assert resp.status_code == 422, f"limit={limit} should return 422, got {resp.status_code}"

    def test_list_executions_service_failure(self, test_client):
        """Service exception returns 500."""
        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.list_executions = AsyncMock(side_effect=RuntimeError("Database unavailable"))

            resp = test_client.get("/api/swarm")

        assert resp.status_code == 500
        assert "Database unavailable" in resp.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════════════
# GET /api/swarm/{execution_id}
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetById:
    """GET /api/swarm/{id} — get a specific swarm execution with tasks."""

    def test_get_execution_success(self, test_client):
        """Get returns full execution shape with all task fields."""
        mock_exec = _make_mock_execution()
        mock_task = _make_mock_task()
        mock_task2 = _make_mock_task(
            id="task-002",
            agent_name="Report Generator",
            depends_on="task-001",
            priority=2,
            error_message=None,
            output="Generated PDF report: 42 pages",
        )

        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.get_execution = AsyncMock(return_value=mock_exec)
            mock_orch.get_tasks = AsyncMock(return_value=[mock_task, mock_task2])

            resp = test_client.get("/api/swarm/exec-001")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "exec-001"
        assert data["goal"] == "Analyze sales data across all regions"
        assert data["status"] == "completed"
        assert data["strategy"] == "parallel"
        assert data["synthesis"] == "Q3 sales increased 12% across all regions"
        assert data["conflict_markers"] is None
        assert data["agent_count"] == 3
        assert data["completed_count"] == 3
        assert data["total_tokens"] == 15000
        assert data["total_cost_usd"] == 0.045
        assert data["error_message"] is None
        assert data["started_at"] is None
        assert data["completed_at"] is None
        assert len(data["tasks"]) == 2

        t0 = data["tasks"][0]
        assert t0["id"] == "task-001"
        assert t0["agent_id"] == "agent-a"
        assert t0["agent_name"] == "Data Analyst"
        assert t0["task_description"] == "Extract sales figures from database"
        assert t0["task_type"] == "extraction"
        assert t0["status"] == "completed"
        assert t0["output"] == "Sales data extracted: 15000 rows"
        assert t0["score"] == 0.95
        assert t0["tokens_used"] == 5000
        assert t0["error_message"] is None
        assert t0["depends_on"] is None
        assert t0["priority"] == 1

        t1 = data["tasks"][1]
        assert t1["depends_on"] == "task-001"
        assert t1["priority"] == 2

    def test_get_execution_not_found(self, test_client):
        """Non-existent execution returns 404."""
        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.get_execution = AsyncMock(return_value=None)

            resp = test_client.get("/api/swarm/nonexistent-id")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Execution not found"

    def test_get_execution_service_failure(self, test_client):
        """Service exception during get returns 500."""
        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.get_execution = AsyncMock(side_effect=RuntimeError("Connection pool exhausted"))

            resp = test_client.get("/api/swarm/exec-001")

        assert resp.status_code == 500
        assert "Connection pool exhausted" in resp.json()["detail"]

    def test_get_execution_tasks_failure(self, test_client):
        """Orchestrator fails during get_tasks returns 500 after successful get_execution."""
        mock_exec = _make_mock_execution()

        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.get_execution = AsyncMock(return_value=mock_exec)
            mock_orch.get_tasks = AsyncMock(side_effect=RuntimeError("Task table locked"))

            resp = test_client.get("/api/swarm/exec-001")

        assert resp.status_code == 500
        assert "Task table locked" in resp.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════════════
# Cross-cutting: route registration
# ═══════════════════════════════════════════════════════════════════════════════


class TestRouteRegistration:
    """Verify all 3 swarm endpoints are registered at expected paths."""

    @pytest.mark.parametrize(
        "method, path, expected_status",
        [
            ("GET", "/api/swarm", 200),
            ("GET", "/api/swarm/test-id", 404),  # route exists, service returns None
            ("POST", "/api/swarm/execute", 422),  # route exists, missing body
        ],
    )
    def test_endpoints_registered(self, test_client, method, path, expected_status):
        """Endpoint returns expected status (not 404 for the route itself)."""
        # Patch orchestrator so endpoints don't error trying to use real DB
        with patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch_cls:
            mock_orch = mock_orch_cls.return_value
            mock_orch.list_executions = AsyncMock(return_value=[])
            mock_orch.get_execution = AsyncMock(return_value=None)
            mock_orch.execute = AsyncMock()
            mock_orch.get_tasks = AsyncMock(return_value=[])

            if method == "GET":
                resp = test_client.get(path)
            else:
                resp = test_client.post(path, json={})

            assert resp.status_code == expected_status, (
                f"Expected {expected_status} for {method} {path}, got {resp.status_code}"
            )

    def test_swarm_and_protocol_routes_do_not_conflict(self, test_client):
        """Verify both swarm and protocol routers coexist without route conflicts."""
        with (
            patch("app.api.v1.swarm.SwarmOrchestrator") as mock_orch,
            patch("app.api.v1.swarm_protocol.HandoffProtocol") as mock_hp,
        ):
            mock_orch.return_value.list_executions = AsyncMock(return_value=[])
            mock_hp.return_value.list_handoffs = AsyncMock(return_value=[])

            # Both should work without conflicts
            swarm_resp = test_client.get("/api/swarm")
            protocol_resp = test_client.get("/api/swarm/protocol/handoffs")

            assert swarm_resp.status_code == 200
            assert protocol_resp.status_code == 200
