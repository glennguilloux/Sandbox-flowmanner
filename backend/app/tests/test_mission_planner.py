"""Unit tests for app/services/mission_planner.py — MissionPlanner."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")


# ── _build_plan_prompt ────────────────────────────────────────────────────────


class TestBuildPlanPrompt:
    """MissionPlanner._build_plan_prompt: prompt structure."""

    def test_includes_mission_fields(self):
        from app.services.mission_planner import MissionPlanner

        planner = MissionPlanner()
        mock_mission = MagicMock()
        mock_mission.title = "Build a website"
        mock_mission.description = "Create a landing page"
        mock_mission.mission_type = "development"
        mock_mission.constraints = {"max_tasks": 5}

        prompt = planner._build_plan_prompt(mock_mission)
        assert "Build a website" in prompt
        assert "Create a landing page" in prompt
        assert "development" in prompt
        assert "JSON array" in prompt

    def test_handles_missing_description(self):
        from app.services.mission_planner import MissionPlanner

        planner = MissionPlanner()
        mock_mission = MagicMock()
        mock_mission.title = "No desc mission"
        mock_mission.description = None
        mock_mission.mission_type = "general"
        mock_mission.constraints = {}

        prompt = planner._build_plan_prompt(mock_mission)
        assert "No desc mission" in prompt
        assert "No description provided" in prompt

    def test_handles_missing_title(self):
        from app.services.mission_planner import MissionPlanner

        planner = MissionPlanner()
        mock_mission = MagicMock()
        mock_mission.title = None
        mock_mission.description = "desc only"
        mock_mission.mission_type = "general"
        mock_mission.constraints = {}

        prompt = planner._build_plan_prompt(mock_mission)
        assert "Untitled Mission" in prompt

    def test_includes_task_type_instructions(self):
        from app.services.mission_planner import MissionPlanner

        planner = MissionPlanner()
        mock_mission = MagicMock()
        mock_mission.title = "Test"
        mock_mission.description = "Test"
        mock_mission.mission_type = "general"
        mock_mission.constraints = {}

        prompt = planner._build_plan_prompt(mock_mission)
        assert "llm" in prompt
        assert "tool" in prompt
        assert "rag" in prompt
        assert "code" in prompt
        assert "dependencies" in prompt

    def test_includes_constraints_json(self):
        from app.services.mission_planner import MissionPlanner

        planner = MissionPlanner()
        mock_mission = MagicMock()
        mock_mission.title = "Test"
        mock_mission.description = "Test"
        mock_mission.mission_type = "general"
        mock_mission.constraints = {"max_tasks": 3, "allowed_models": ["deepseek-chat"]}

        prompt = planner._build_plan_prompt(mock_mission)
        assert '"max_tasks": 3' in prompt
        assert '"allowed_models": ["deepseek-chat"]' in prompt


# ── plan_mission ──────────────────────────────────────────────────────────────


class TestPlanMission:
    """MissionPlanner.plan_mission: end-to-end planning."""

    @pytest.mark.asyncio
    async def test_generates_tasks_from_llm(self):
        from app.services.mission_planner import MissionPlanner

        planner = MissionPlanner(
            log_callback=AsyncMock(),
            transition_callback=AsyncMock(),
        )
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        mock_mission = MagicMock()
        mock_mission.id = "mission-1"
        mock_mission.title = "Test Plan"
        mock_mission.description = "Plan me"
        mock_mission.mission_type = "general"
        mock_mission.user_id = 1
        mock_mission.constraints = {}
        mock_mission.status = "pending"

        # First query returns mission, second returns no existing tasks
        mock_mission_result = MagicMock()
        mock_mission_result.scalars().first.return_value = mock_mission

        mock_existing_result = MagicMock()
        mock_existing_result.scalars().first.return_value = None

        mock_db.execute = AsyncMock(
            side_effect=[
                mock_mission_result,  # SELECT Mission
                mock_existing_result,  # SELECT MissionTask (existing)
            ]
        )

        with patch("app.services.mission_planner.AsyncSessionLocal") as mock_session:
            mock_session.return_value.__aenter__.return_value = mock_db
            mock_session.return_value.__aexit__.return_value = None

            with patch.object(
                planner,
                "_generate_plan",
                AsyncMock(
                    return_value=[
                        {
                            "title": "Task 1",
                            "description": "Do thing",
                            "task_type": "llm",
                            "dependencies": [],
                        },
                        {
                            "title": "Task 2",
                            "description": "Do another",
                            "task_type": "tool",
                            "dependencies": [0],
                        },
                    ]
                ),
            ):
                result = await planner.plan_mission("mission-1")

        assert result["success"] is True
        assert result["status"] == "planned"
        assert result["task_count"] == 2
        assert mock_db.add.call_count == 2  # 2 tasks added

    @pytest.mark.asyncio
    async def test_skips_planning_when_tasks_exist(self):
        from app.services.mission_planner import MissionPlanner

        planner = MissionPlanner(
            log_callback=AsyncMock(),
            transition_callback=AsyncMock(),
        )
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_mission = MagicMock()
        mock_mission.id = "mission-1"
        mock_mission.title = "Test"
        mock_mission.description = "Test"
        mock_mission.mission_type = "general"
        mock_mission.constraints = {}

        mock_mission_result = MagicMock()
        mock_mission_result.scalars().first.return_value = mock_mission

        mock_existing = MagicMock()
        mock_existing.scalars().first.return_value = MagicMock()  # existing task

        mock_db.execute = AsyncMock(
            side_effect=[
                mock_mission_result,
                mock_existing,
            ]
        )

        with patch("app.services.mission_planner.AsyncSessionLocal") as mock_session:
            mock_session.return_value.__aenter__.return_value = mock_db
            mock_db.execute.side_effect = [mock_mission_result, mock_existing]
            result = await planner.plan_mission("mission-1")

        assert result["success"] is True
        assert result["status"] == "planned"

    @pytest.mark.asyncio
    async def test_fallback_to_default_task_on_empty_llm(self):
        from app.services.mission_planner import MissionPlanner

        planner = MissionPlanner(
            log_callback=AsyncMock(),
            transition_callback=AsyncMock(),
        )
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        mock_mission = MagicMock()
        mock_mission.id = "mission-1"
        mock_mission.title = "Fallback Test"
        mock_mission.description = "test"
        mock_mission.mission_type = "general"
        mock_mission.user_id = 1
        mock_mission.constraints = {}

        mock_mission_result = MagicMock()
        mock_mission_result.scalars().first.return_value = mock_mission

        mock_existing = MagicMock()
        mock_existing.scalars().first.return_value = None

        mock_db.execute = AsyncMock(
            side_effect=[
                mock_mission_result,
                mock_existing,
            ]
        )

        with patch("app.services.mission_planner.AsyncSessionLocal") as mock_session:
            mock_session.return_value.__aenter__.return_value = mock_db
            with patch.object(planner, "_generate_plan", AsyncMock(return_value=[])):
                result = await planner.plan_mission("mission-1")

        assert result["success"] is True
        assert result["task_count"] == 1
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_failure_when_mission_not_found(self):
        from app.services.mission_planner import MissionPlanner

        planner = MissionPlanner()
        mock_db = AsyncMock()

        mock_result = MagicMock()
        mock_result.scalars().first.return_value = None

        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.mission_planner.AsyncSessionLocal") as mock_session:
            mock_session.return_value.__aenter__.return_value = mock_db
            result = await planner.plan_mission("nonexistent")

        assert result["success"] is False
        assert "not found" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_handles_permanent_error_in_planning(self):
        from app.services.mission_errors import PermanentMissionError
        from app.services.mission_planner import MissionPlanner

        planner = MissionPlanner(
            log_callback=AsyncMock(),
            transition_callback=AsyncMock(),
        )
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_mission = MagicMock()
        mock_mission.id = "mission-1"
        mock_mission.title = "Test"
        mock_mission.description = "Test"
        mock_mission.mission_type = "general"
        mock_mission.constraints = {}

        mock_mission_result = MagicMock()
        mock_mission_result.scalars().first.return_value = mock_mission

        mock_existing = MagicMock()
        mock_existing.scalars().first.return_value = None

        mock_db.execute = AsyncMock(
            side_effect=[
                mock_mission_result,
                mock_existing,
            ]
        )

        with patch("app.services.mission_planner.AsyncSessionLocal") as mock_session:
            mock_session.return_value.__aenter__.return_value = mock_db
            with patch.object(
                planner,
                "_generate_plan",
                AsyncMock(side_effect=PermanentMissionError("forbidden")),
            ):
                result = await planner.plan_mission("mission-1")

        assert result["success"] is False
        assert result.get("permanent") is True

    @pytest.mark.asyncio
    async def test_handles_unexpected_error_in_planning(self):
        from app.services.mission_planner import MissionPlanner

        planner = MissionPlanner(
            log_callback=AsyncMock(),
            transition_callback=AsyncMock(),
        )
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()

        mock_mission = MagicMock()
        mock_mission.id = "mission-1"
        mock_mission.title = "Test"
        mock_mission.description = "Test"
        mock_mission.mission_type = "general"
        mock_mission.constraints = {}

        mock_mission_result = MagicMock()
        mock_mission_result.scalars().first.return_value = mock_mission

        mock_existing = MagicMock()
        mock_existing.scalars().first.return_value = None

        mock_db.execute = AsyncMock(
            side_effect=[
                mock_mission_result,
                mock_existing,
            ]
        )

        with patch("app.services.mission_planner.AsyncSessionLocal") as mock_session:
            mock_session.return_value.__aenter__.return_value = mock_db
            with patch.object(
                planner,
                "_generate_plan",
                AsyncMock(side_effect=RuntimeError("unexpected")),
            ):
                result = await planner.plan_mission("mission-1")

        assert result["success"] is False


# ── _generate_plan ────────────────────────────────────────────────────────────


class TestGeneratePlan:
    """MissionPlanner._generate_plan: LLM-based plan generation."""

    @pytest.mark.asyncio
    async def test_parses_json_array_from_response(self):
        from app.services.mission_planner import MissionPlanner

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "content": '[{"title":"T1","description":"D1","task_type":"llm","dependencies":[]}]',
                "model": "deepseek-chat",
                "provider": "deepseek",
                "cost": {"input_tokens": 10, "output_tokens": 5},
            }
        )

        planner = MissionPlanner(get_model_router=lambda: mock_router)
        tasks = await planner._generate_plan("Plan this")
        assert len(tasks) == 1
        assert tasks[0]["title"] == "T1"

    @pytest.mark.asyncio
    async def test_extracts_json_from_markdown_wrapper(self):
        from app.services.mission_planner import MissionPlanner

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "content": '```json\n[{"title":"T1","description":"D1","task_type":"llm","dependencies":[]}]\n```',
                "model": "deepseek-chat",
                "provider": "deepseek",
                "cost": {"input_tokens": 10, "output_tokens": 5},
            }
        )

        planner = MissionPlanner(get_model_router=lambda: mock_router)
        tasks = await planner._generate_plan("Plan this")
        assert len(tasks) == 1
        assert tasks[0]["title"] == "T1"

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_json_in_response(self):
        from app.services.mission_planner import MissionPlanner

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "content": "Sorry, I cannot plan this right now.",
                "model": "deepseek-chat",
                "provider": "deepseek",
                "cost": {"input_tokens": 5, "output_tokens": 10},
            }
        )

        planner = MissionPlanner(get_model_router=lambda: mock_router)
        tasks = await planner._generate_plan("Plan this")
        assert tasks == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_empty_json_array(self):
        from app.services.mission_planner import MissionPlanner

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "content": "[]",
                "model": "deepseek-chat",
                "provider": "deepseek",
                "cost": {"input_tokens": 5, "output_tokens": 2},
            }
        )

        planner = MissionPlanner(get_model_router=lambda: mock_router)
        tasks = await planner._generate_plan("Plan this")
        assert tasks == []

    @pytest.mark.asyncio
    async def test_falls_back_to_httpx_when_no_router(self):
        from app.services.mission_planner import MissionPlanner

        planner = MissionPlanner(get_model_router=lambda: None)

        mock_response = MagicMock()
        mock_response.json = MagicMock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "content": '[{"title":"Via HTTP","description":"d","task_type":"llm","dependencies":[]}]'
                        }
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 10},
            }
        )
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            tasks = await planner._generate_plan("Plan via HTTP")

        assert len(tasks) == 1
        assert tasks[0]["title"] == "Via HTTP"

    @pytest.mark.asyncio
    async def test_handles_router_failure(self):
        from app.services.mission_planner import MissionPlanner

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": False,
                "error": "Router is down",
            }
        )

        planner = MissionPlanner(get_model_router=lambda: mock_router)
        tasks = await planner._generate_plan("Plan this")
        assert tasks == []

    @pytest.mark.asyncio
    async def test_reraises_retryable_error(self):
        from app.services.mission_errors import RetryableMissionError
        from app.services.mission_planner import MissionPlanner

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(side_effect=RetryableMissionError("overloaded"))

        planner = MissionPlanner(get_model_router=lambda: mock_router)
        with pytest.raises(RetryableMissionError):
            await planner._generate_plan("Plan this")

    @pytest.mark.asyncio
    async def test_returns_empty_on_permanent_error(self):
        from app.services.mission_errors import PermanentMissionError
        from app.services.mission_planner import MissionPlanner

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(side_effect=PermanentMissionError("forbidden"))

        planner = MissionPlanner(get_model_router=lambda: mock_router)
        tasks = await planner._generate_plan("Plan this")
        assert tasks == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_httpx_fallback_failure(self):
        from app.services.mission_planner import MissionPlanner

        planner = MissionPlanner(get_model_router=lambda: None)

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(side_effect=Exception("Connection error"))
            tasks = await planner._generate_plan("Plan this")
        assert tasks == []

    @pytest.mark.asyncio
    async def test_records_cost_in_finally_block(self):
        from app.services.mission_planner import MissionPlanner

        mock_cost_tracker = MagicMock()
        mock_cost_tracker.record_llm_call = AsyncMock()
        mock_cost_tracker.estimate_cost = MagicMock(return_value=0.001)

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "content": '[{"title":"T1","description":"D1","task_type":"llm","dependencies":[]}]',
                "model": "deepseek-chat",
                "provider": "deepseek",
                "cost": {"input_tokens": 10, "output_tokens": 5},
            }
        )

        planner = MissionPlanner(
            cost_tracker=mock_cost_tracker,
            get_model_router=lambda: mock_router,
        )
        await planner._generate_plan("Plan", mission_id="mission-1")

        mock_cost_tracker.record_llm_call.assert_called_once()
        call_kwargs = mock_cost_tracker.record_llm_call.call_args[1]
        assert call_kwargs["mission_id"] == "mission-1"
        assert call_kwargs["task_id"] is None
        assert call_kwargs["success"] is True

    @pytest.mark.asyncio
    async def test_records_cost_on_failure_too(self):
        from app.services.mission_planner import MissionPlanner

        mock_cost_tracker = MagicMock()
        mock_cost_tracker.record_llm_call = AsyncMock()
        mock_cost_tracker.estimate_cost = MagicMock(return_value=0.0)

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "content": "No JSON here",
                "model": "deepseek-chat",
                "provider": "deepseek",
                "cost": {"input_tokens": 5, "output_tokens": 3},
            }
        )

        planner = MissionPlanner(
            cost_tracker=mock_cost_tracker,
            get_model_router=lambda: mock_router,
        )
        await planner._generate_plan("Plan", mission_id="mission-2")

        mock_cost_tracker.record_llm_call.assert_called_once()
        call_kwargs = mock_cost_tracker.record_llm_call.call_args[1]
        assert call_kwargs["success"] is False
        assert call_kwargs["error_message"] is not None


# ── Constructor ───────────────────────────────────────────────────────────────


class TestMissionPlannerConstructor:
    """MissionPlanner.__init__: wiring and defaults."""

    def test_default_constructor(self):
        from app.services.mission_planner import MissionPlanner

        planner = MissionPlanner()
        assert planner.cost_tracker is None
        assert callable(planner._get_model_router)
        assert callable(planner._log)
        assert callable(planner._transition_status)

    def test_injects_dependencies(self):
        from app.services.mission_planner import MissionPlanner

        mock_cost = MagicMock()
        mock_router = lambda: "fake-router"
        mock_log = AsyncMock()
        mock_trans = AsyncMock()

        planner = MissionPlanner(
            cost_tracker=mock_cost,
            get_model_router=mock_router,
            log_callback=mock_log,
            transition_callback=mock_trans,
        )

        assert planner.cost_tracker is mock_cost
        assert planner._get_model_router() == "fake-router"
        assert planner._log is mock_log
        assert planner._transition_status is mock_trans
