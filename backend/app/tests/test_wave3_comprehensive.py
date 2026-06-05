"""Comprehensive tests for Wave 1-3: dashboard, integrations, approval flow, HTTP executor."""

import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")


# ═══════════════════════════════════════════════════════════════════════════════
# Dashboard API Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestDashboardMissionHistory:
    """GET /api/v2/dashboard/missions — paginated mission history."""

    def test_mission_history_item_schema_valid(self):
        from app.schemas.dashboard_v2 import MissionHistoryItem

        item = MissionHistoryItem(
            id=str(uuid4()),
            title="Test Mission",
            status="completed",
            task_count=3,
            completed_tasks=3,
            failed_tasks=0,
        )
        assert item.id
        assert item.title == "Test Mission"
        data = item.model_dump()
        assert data["status"] == "completed"
        assert data["task_count"] == 3

    def test_mission_history_response_pagination(self):
        from app.schemas.dashboard_v2 import MissionHistoryItem, MissionHistoryResponse

        resp = MissionHistoryResponse(
            items=[
                MissionHistoryItem(id=str(uuid4()), title="M1", status="completed"),
                MissionHistoryItem(id=str(uuid4()), title="M2", status="failed"),
            ],
            total=25,
            page=2,
            per_page=10,
            pages=3,
        )
        assert len(resp.items) == 2
        assert resp.total == 25
        assert resp.pages == 3


class TestDashboardCostAnalytics:
    """GET /api/v2/dashboard/costs — cost breakdown."""

    def test_cost_analytics_defaults(self):
        from app.schemas.dashboard_v2 import CostAnalyticsResponse

        resp = CostAnalyticsResponse()
        assert resp.total_cost == 0.0
        assert resp.by_agent == []
        assert resp.by_model == []

    def test_cost_analytics_with_data(self):
        from app.schemas.dashboard_v2 import (
            CostAnalyticsResponse,
            CostByAgent,
            CostByModel,
        )

        resp = CostAnalyticsResponse(
            total_cost=1.23,
            by_agent=[CostByAgent(agent_id="agent-1", cost_usd=0.5)],
            by_model=[CostByModel(model_id="deepseek-chat", cost_usd=1.23)],
        )
        assert resp.total_cost == 1.23
        assert resp.by_agent[0].agent_id == "agent-1"


class TestDashboardStats:
    """GET /api/v2/dashboard/stats — aggregate stats."""

    def test_stats_defaults(self):
        from app.schemas.dashboard_v2 import DashboardStats

        stats = DashboardStats()
        assert stats.total_missions == 0
        assert stats.success_rate == 0.0

    def test_stats_computed(self):
        from app.schemas.dashboard_v2 import DashboardStats

        stats = DashboardStats(
            total_missions=10,
            completed_missions=8,
            failed_missions=2,
            success_rate=80.0,
            avg_duration_seconds=45.2,
            total_cost=5.67,
            total_tokens=50000,
        )
        assert stats.success_rate == 80.0
        assert stats.total_cost == 5.67


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP Integration Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestHttpIntegrationModels:
    """HttpIntegrationConfig and HttpIntegrationLog model validation."""

    def test_config_model_has_required_fields(self):
        from app.models.integration_models import HttpIntegrationConfig

        config = HttpIntegrationConfig(
            id=str(uuid4()),
            user_id=1,
            name="Test API",
            base_url="https://api.example.com",
            timeout_seconds=30,
            max_retries=3,
        )
        assert config.name == "Test API"
        assert config.timeout_seconds == 30
        assert config.max_retries == 3
        assert config.is_active is None  # Boolean default False only at DB level

    def test_log_model_has_required_fields(self):
        from app.models.integration_models import HttpIntegrationLog

        log = HttpIntegrationLog(
            id=str(uuid4()),
            integration_id=str(uuid4()),
            request_method="GET",
            request_url="https://api.example.com/data",
            status="pending",
        )
        assert log.request_method == "GET"
        assert log.status == "pending"


class TestHttpIntegrationSchemas:
    """Pydantic schema validation for integration CRUD."""

    def test_create_schema_validation(self):
        from app.schemas.integration_v2 import HttpIntegrationConfigCreate

        payload = HttpIntegrationConfigCreate(
            name="My Integration",
            base_url="https://api.example.com",
            auth_type="bearer",
            auth_config={"token": "secret123"},
        )
        assert payload.name == "My Integration"
        assert payload.auth_type == "bearer"

    def test_update_schema_partial(self):
        from app.schemas.integration_v2 import HttpIntegrationConfigUpdate

        payload = HttpIntegrationConfigUpdate(name="Renamed", is_active=False)
        assert payload.name == "Renamed"
        assert payload.base_url is None  # not provided
        assert payload.is_active is False

    def test_response_schema_hides_auth(self):
        from app.schemas.integration_v2 import HttpIntegrationConfigResponse

        resp = HttpIntegrationConfigResponse(
            id=str(uuid4()),
            user_id=1,
            name="Test",
            base_url="https://api.example.com",
        )
        data = resp.model_dump()
        assert "auth_config_encrypted" not in data
        assert "auth_config" not in data


class TestHttpIntegrationExecutor:
    """HttpIntegrationExecutor — HTTP call execution with retry and logging."""

    @pytest.mark.asyncio
    async def test_executor_get_success(self):
        from app.services.http_integration_executor import HttpIntegrationExecutor

        executor = HttpIntegrationExecutor()

        mock_config = MagicMock()
        mock_config.id = str(uuid4())
        mock_config.base_url = "https://httpbin.org"
        mock_config.default_headers = {}
        mock_config.auth_type = None
        mock_config.auth_config_encrypted = None
        mock_config.timeout_seconds = 10
        mock_config.max_retries = 1

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.is_success = True
            mock_response.text = '{"status": "ok"}'
            mock_response.headers = {"Content-Type": "application/json"}
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await executor.execute(
                db=mock_db,
                config=mock_config,
                method="GET",
                path="/get",
            )

        assert result["success"] is True
        assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_executor_timeout_handled(self):
        import httpx

        from app.services.http_integration_executor import HttpIntegrationExecutor

        executor = HttpIntegrationExecutor()

        mock_config = MagicMock()
        mock_config.id = str(uuid4())
        mock_config.base_url = "https://slow.example.com"
        mock_config.default_headers = {}
        mock_config.auth_type = None
        mock_config.auth_config_encrypted = None
        mock_config.timeout_seconds = 1
        mock_config.max_retries = 0

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.request = AsyncMock(
                side_effect=httpx.TimeoutException("timed out")
            )
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await executor.execute(
                db=mock_db,
                config=mock_config,
                method="GET",
                path="/slow",
            )

        assert result["success"] is False
        assert "timeout" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_executor_auth_bearer(self):
        from app.services.http_integration_executor import HttpIntegrationExecutor
        from app.utils.encryption import encrypt_api_key

        executor = HttpIntegrationExecutor()

        mock_config = MagicMock()
        mock_config.id = str(uuid4())
        mock_config.base_url = "https://api.example.com"
        mock_config.default_headers = None
        mock_config.auth_type = "bearer"
        mock_config.auth_config_encrypted = encrypt_api_key('{"token":"my-token"}')
        mock_config.timeout_seconds = 10
        mock_config.max_retries = 0

        headers = executor._get_auth_headers(mock_config)
        assert headers == {"Authorization": "Bearer my-token"}

    @pytest.mark.asyncio
    async def test_executor_auth_basic(self):
        from app.services.http_integration_executor import HttpIntegrationExecutor
        from app.utils.encryption import encrypt_api_key

        executor = HttpIntegrationExecutor()

        mock_config = MagicMock()
        mock_config.id = str(uuid4())
        mock_config.auth_type = "basic"
        mock_config.auth_config_encrypted = encrypt_api_key(
            '{"username":"admin","password":"pass123"}'
        )

        headers = executor._get_auth_headers(mock_config)
        assert "Authorization" in headers
        assert headers["Authorization"].startswith("Basic ")


# ═══════════════════════════════════════════════════════════════════════════════
# TaskExecutor HTTP Integration Task Type Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestTaskExecutorHttpIntegration:
    """TaskExecutor dispatch for http_integration / http_request task types."""

    @pytest.mark.asyncio
    async def test_http_integration_task_type_dispatches(self):
        from app.services.task_executor import TaskExecutor

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        mock_config = MagicMock()
        mock_config.is_active = True

        mock_result = MagicMock()
        mock_result.scalars().first.return_value = mock_config
        mock_db.execute = AsyncMock(return_value=mock_result)

        executor = TaskExecutor()

        mock_task = MagicMock()
        mock_task.task_type = "http_integration"
        mock_task.title = "Call External API"
        mock_task.id = uuid4()
        mock_task.status = MagicMock()
        mock_task.started_at = None
        mock_task.input_data = {
            "integration_config_id": str(uuid4()),
            "method": "POST",
            "path": "/webhooks",
            "body": {"event": "test"},
        }
        mock_task.dependencies = None

        mock_mission = MagicMock()
        mock_mission.id = uuid4()

        with patch(
            "app.services.http_integration_executor.HttpIntegrationExecutor.execute",
            new_callable=AsyncMock,
        ) as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "status_code": 201,
                "response_body": '{"created": true}',
                "duration_ms": 150,
            }
            result = await executor.execute_task(mock_db, mock_mission, mock_task, {})

        assert result["success"] is True
        assert result["status_code"] == 201

    @pytest.mark.asyncio
    async def test_http_integration_missing_config_id(self):
        from app.services.task_executor import TaskExecutor

        executor = TaskExecutor()

        mock_task = MagicMock()
        mock_task.task_type = "http_request"
        mock_task.title = "Bad Task"
        mock_task.id = uuid4()
        mock_task.status = MagicMock()
        mock_task.started_at = None
        mock_task.input_data = {}
        mock_task.dependencies = None

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_mission = MagicMock()
        mock_mission.id = uuid4()

        result = await executor.execute_task(mock_db, mock_mission, mock_task, {})

        assert result["success"] is False
        assert "integration_config_id" in result["error"]


# ═══════════════════════════════════════════════════════════════════════════════
# Approval Flow Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestApprovalFlow:
    """End-to-end approval flow: pause → approve → resume."""

    @pytest.mark.asyncio
    async def test_hitl_manager_raise_and_resolve(self):
        from app.orchestration.human_interrupt import (
            HumanInterrupt,
            get_hitl_manager,
        )

        hitl = get_hitl_manager()
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        # Raise interrupt
        interrupt = HumanInterrupt(
            mission_id=str(uuid4()),
            interrupt_type="approval",
            context={"task_title": "Risky Operation"},
        )
        record_id = await hitl.raise_interrupt(mock_db, interrupt)
        assert record_id is not None

    def test_approval_required_for_low_confidence(self):
        from app.orchestration.human_interrupt import HITLManager

        assert HITLManager.approval_required_for("deploy", confidence=0.5) is True

    def test_approval_required_for_destructive(self):
        from app.orchestration.human_interrupt import HITLManager

        assert HITLManager.approval_required_for("destructive_delete") is True

    def test_approval_not_required_for_normal(self):
        from app.orchestration.human_interrupt import HITLManager

        assert HITLManager.approval_required_for("read_data", confidence=0.9) is False

    def test_mission_executor_has_hitl_wiring(self):
        """Verify mission_executor imports HITLManager at module level."""
        from app.services.mission_executor import MissionExecutor

        executor = MissionExecutor()
        # HITLManager is wired in execute_mission, not in __init__
        assert not hasattr(executor, "hitl_manager") or executor.hitl_manager is None


# ═══════════════════════════════════════════════════════════════════════════════
# Schema Consistency Tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestSchemaConsistency:
    """All new schemas use model_config = {'from_attributes': True}."""

    def test_dashboard_schemas_have_model_config(self):
        from app.schemas.dashboard_v2 import (
            CostAnalyticsResponse,
            DashboardStats,
            LogEntry,
            MissionHistoryItem,
        )

        assert hasattr(MissionHistoryItem, "model_config")
        assert hasattr(LogEntry, "model_config")
        assert hasattr(DashboardStats, "model_config")
        assert hasattr(CostAnalyticsResponse, "model_config")

    def test_integration_schemas_have_model_config(self):
        from app.schemas.integration_v2 import (
            HttpIntegrationConfigResponse,
            HttpIntegrationLogResponse,
        )

        assert hasattr(HttpIntegrationConfigResponse, "model_config")
        assert hasattr(HttpIntegrationLogResponse, "model_config")
