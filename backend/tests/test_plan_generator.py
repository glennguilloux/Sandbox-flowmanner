"""Unit tests for app/services/plan_selection/plan_generator.py."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from app.services.plan_selection.plan_generator import (
    _build_heuristic_plan,
    generate_plan_candidates,
)
from app.services.plan_selection.plan_scorer import score_plan


class TestBuildHeuristicPlan:
    """_build_heuristic_plan: rule-based plan construction."""

    def test_basic_mission(self):
        tasks = _build_heuristic_plan("Test", "Do something", "general")
        # Always: analyze + review = 2 minimum
        assert len(tasks) >= 2
        assert tasks[0]["title"] == "Analyze requirements"
        assert tasks[-1]["title"] == "Review and summarize"

    def test_code_mission_gets_implementation_step(self):
        tasks = _build_heuristic_plan("Build API", "Create a REST API with FastAPI", "development")
        titles = [t["title"] for t in tasks]
        assert "Implement solution" in titles

    def test_research_mission_gets_tool_step(self):
        tasks = _build_heuristic_plan("Research", "Find and compare database options", "research")
        titles = [t["title"] for t in tasks]
        assert "Research and gather information" in titles

    def test_simple_mission_minimal_tasks(self):
        tasks = _build_heuristic_plan("Summarize", "Summarize this text", "general")
        # analyze + review (no code or research keywords)
        assert len(tasks) == 2

    def test_tasks_have_dependencies(self):
        tasks = _build_heuristic_plan("Build", "Implement a web scraper", "development")
        # Last task depends on the previous one
        last_deps = tasks[-1].get("dependencies", [])
        assert len(last_deps) > 0

    def test_empty_description(self):
        tasks = _build_heuristic_plan("Title", "", None)
        assert len(tasks) >= 2


class TestGeneratePlanCandidates:
    """generate_plan_candidates: K candidate generation."""

    @pytest.mark.asyncio
    async def test_returns_k_candidates(self):
        mock_mission = MagicMock()
        mock_mission.title = "Test Mission"
        mock_mission.description = "Build something useful"
        mock_mission.mission_type = "development"
        mock_mission.constraints = {}
        mock_mission.user_id = 1
        mock_mission.id = "mission-1"

        # Mock the LLM to return valid plans
        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "content": '[{"title":"LLM Task","description":"Do it","task_type":"llm","dependencies":[]}]',
                "model": "deepseek-chat",
                "provider": "local",
                "cost": {"input_tokens": 100, "output_tokens": 50},
            }
        )

        with patch("app.services.mission_planner.MissionPlanner") as MockPlanner:
            MockPlanner.return_value._build_plan_prompt = MagicMock(return_value="Plan this mission")
            candidates = await generate_plan_candidates(
                mock_mission,
                k=3,
                get_model_router=lambda: mock_router,
            )

        assert len(candidates) == 3
        ids = [c.plan_id for c in candidates]
        assert "heuristic_v1" in ids
        assert "llm_persona_a" in ids
        assert "llm_persona_b" in ids

    @pytest.mark.asyncio
    async def test_heuristic_always_first(self):
        mock_mission = MagicMock()
        mock_mission.title = "Test"
        mock_mission.description = "Test"
        mock_mission.mission_type = "general"
        mock_mission.constraints = {}
        mock_mission.user_id = 1
        mock_mission.id = "m1"

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "content": '[{"title":"T","description":"D","task_type":"llm","dependencies":[]}]',
                "model": "m",
                "provider": "p",
                "cost": {"input_tokens": 10, "output_tokens": 5},
            }
        )

        with patch("app.services.mission_planner.MissionPlanner") as MockPlanner:
            MockPlanner.return_value._build_plan_prompt = MagicMock(return_value="prompt")
            candidates = await generate_plan_candidates(mock_mission, k=3, get_model_router=lambda: mock_router)

        assert candidates[0].plan_id == "heuristic_v1"
        assert candidates[0].generation_strategy == "heuristic"

    @pytest.mark.asyncio
    async def test_candidates_have_scores(self):
        mock_mission = MagicMock()
        mock_mission.title = "Test"
        mock_mission.description = "Do code work"
        mock_mission.mission_type = "development"
        mock_mission.constraints = {}
        mock_mission.user_id = 1
        mock_mission.id = "m1"

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "content": '[{"title":"T","description":"D","task_type":"llm","dependencies":[]}]',
                "model": "m",
                "provider": "p",
                "cost": {"input_tokens": 10, "output_tokens": 5},
            }
        )

        with patch("app.services.mission_planner.MissionPlanner") as MockPlanner:
            MockPlanner.return_value._build_plan_prompt = MagicMock(return_value="prompt")
            candidates = await generate_plan_candidates(mock_mission, k=3, get_model_router=lambda: mock_router)

        for cand in candidates:
            assert 0.0 <= cand.quality_score <= 1.0
            assert cand.estimated_tokens >= 0
            assert cand.estimated_latency_ms >= 0

    @pytest.mark.asyncio
    async def test_llm_failure_falls_back_to_heuristic(self):
        mock_mission = MagicMock()
        mock_mission.title = "Test"
        mock_mission.description = "Test"
        mock_mission.mission_type = "general"
        mock_mission.constraints = {}
        mock_mission.user_id = 1
        mock_mission.id = "m1"

        # Router returns failure
        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(return_value={"success": False, "error": "LLM down"})

        with patch("app.services.mission_planner.MissionPlanner") as MockPlanner:
            MockPlanner.return_value._build_plan_prompt = MagicMock(return_value="prompt")
            candidates = await generate_plan_candidates(mock_mission, k=3, get_model_router=lambda: mock_router)

        # All 3 candidates should exist (LLM ones fallback to heuristic tasks)
        assert len(candidates) == 3
        # Heuristic should still be the first
        assert candidates[0].plan_id == "heuristic_v1"

    @pytest.mark.asyncio
    async def test_k2_skips_third_persona(self):
        mock_mission = MagicMock()
        mock_mission.title = "Test"
        mock_mission.description = "Test"
        mock_mission.mission_type = "general"
        mock_mission.constraints = {}
        mock_mission.user_id = 1
        mock_mission.id = "m1"

        mock_router = MagicMock()
        mock_router.route_request = AsyncMock(
            return_value={
                "success": True,
                "content": '[{"title":"T","description":"D","task_type":"llm","dependencies":[]}]',
                "model": "m",
                "provider": "p",
                "cost": {"input_tokens": 10, "output_tokens": 5},
            }
        )

        with patch("app.services.mission_planner.MissionPlanner") as MockPlanner:
            MockPlanner.return_value._build_plan_prompt = MagicMock(return_value="prompt")
            candidates = await generate_plan_candidates(mock_mission, k=2, get_model_router=lambda: mock_router)

        assert len(candidates) == 2
        ids = [c.plan_id for c in candidates]
        assert "heuristic_v1" in ids
        assert "llm_persona_a" in ids
        assert "llm_persona_b" not in ids
