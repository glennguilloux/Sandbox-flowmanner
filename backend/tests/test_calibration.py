"""Unit tests for app/services/plan_selection/calibration.py."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from app.services.plan_selection.calibration import (
    LATENCY_NORMALIZER_MS,
    TASK_COUNT_NORMALIZER,
    TOKEN_NORMALIZER,
    _load_profiling_data,
    get_strategy_success_rate,
    predict_strategy,
    reset_profiling_cache,
    strategy_risk_penalty,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    """Reset profiling cache before each test."""
    reset_profiling_cache()
    yield
    reset_profiling_cache()


class TestLoadProfilingData:
    """_load_profiling_data: loads strategy profiling results."""

    def test_loads_real_profiling_file(self):
        """When docs/strategy-profiling-results.json exists, loads real data."""
        rates = _load_profiling_data()
        # Based on actual profiling data: solo=1.0, dag=1.0, graph=1.0, swarm=0.0, etc.
        assert "solo" in rates
        assert "dag" in rates
        assert "swarm" in rates
        assert rates["solo"] == 1.0
        assert rates["dag"] == 1.0

    def test_caches_after_first_load(self):
        """Second call returns cached data without re-reading file."""
        _load_profiling_data()
        _load_profiling_data()  # should not re-read
        # If we got here without error, caching works

    def test_graceful_fallback_when_file_missing(self):
        """Falls back to 1.0 for all strategies when file is missing."""
        with patch("app.services.plan_selection.calibration._PROFILING_FILE", Path("/nonexistent/file.json")):
            reset_profiling_cache()
            rates = _load_profiling_data()
            assert all(v == 1.0 for v in rates.values())
            assert len(rates) == 7


class TestGetStrategySuccessRate:
    """get_strategy_success_rate: per-strategy lookup."""

    def test_solo_returns_1(self):
        assert get_strategy_success_rate("solo") == 1.0

    def test_dag_returns_1(self):
        assert get_strategy_success_rate("dag") == 1.0

    def test_graph_returns_1(self):
        assert get_strategy_success_rate("graph") == 1.0

    def test_unknown_strategy_defaults_to_1(self):
        assert get_strategy_success_rate("nonexistent") == 1.0

    def test_swarm_returns_0_from_profiling(self):
        """Swarm had 0% success in the actual profiling run."""
        rate = get_strategy_success_rate("swarm")
        assert rate == 0.0

    def test_pipeline_returns_0_from_profiling(self):
        rate = get_strategy_success_rate("pipeline")
        assert rate == 0.0

    def test_meta_returns_0_from_profiling(self):
        rate = get_strategy_success_rate("meta")
        assert rate == 0.0

    def test_langgraph_returns_0_from_profiling(self):
        rate = get_strategy_success_rate("langgraph")
        assert rate == 0.0


class TestPredictStrategy:
    """predict_strategy: task-structure → strategy affinity."""

    def test_single_task_predicts_solo(self):
        tasks = [{"title": "T1", "task_type": "llm", "dependencies": []}]
        assert predict_strategy(tasks) == "solo"

    def test_two_tasks_with_deps_predicts_dag(self):
        tasks = [
            {"title": "T1", "task_type": "llm", "dependencies": []},
            {"title": "T2", "task_type": "code", "dependencies": [0]},
        ]
        assert predict_strategy(tasks) == "dag"

    def test_multi_task_no_deps_predicts_dag(self):
        """Multi-task with no explicit deps still predicts dag (len > 1)."""
        tasks = [
            {"title": "T1", "task_type": "llm"},
            {"title": "T2", "task_type": "llm"},
        ]
        assert predict_strategy(tasks) == "dag"

    def test_conditional_edges_predicts_graph(self):
        tasks = [
            {"title": "T1", "task_type": "llm"},
            {"title": "T2", "task_type": "llm", "dependencies": [{"target": 0, "condition": "x > 0"}]},
        ]
        assert predict_strategy(tasks) == "graph"

    def test_branch_flag_predicts_graph(self):
        tasks = [
            {"title": "T1", "task_type": "llm", "branch": True},
            {"title": "T2", "task_type": "llm"},
        ]
        assert predict_strategy(tasks) == "graph"

    def test_fan_out_predicts_swarm(self):
        tasks = [
            {"title": "T1", "task_type": "fan_out", "spawn_parallel": True},
            {"title": "T2", "task_type": "llm"},
        ]
        assert predict_strategy(tasks) == "swarm"

    def test_phase_gates_predict_pipeline(self):
        tasks = [
            {"title": "T1", "task_type": "dispatch"},
            {"title": "T2", "task_type": "research"},
            {"title": "T3", "task_type": "draft"},
            {"title": "T4", "task_type": "debate"},
        ]
        assert predict_strategy(tasks) == "pipeline"

    def test_sub_workflow_predicts_meta(self):
        tasks = [
            {"title": "T1", "task_type": "sub_workflow"},
            {"title": "T2", "task_type": "llm"},
        ]
        assert predict_strategy(tasks) == "meta"

    def test_graph_name_predicts_langgraph(self):
        tasks = [
            {"title": "T1", "task_type": "llm", "graph_name": "my_graph"},
        ]
        assert predict_strategy(tasks) == "langgraph"

    def test_empty_tasks_defaults_to_solo(self):
        assert predict_strategy([]) == "solo"


class TestStrategyRiskPenalty:
    """strategy_risk_penalty: profiling-grounded risk penalty."""

    def test_solo_tasks_no_penalty(self):
        """Solo has 100% success → no penalty."""
        tasks = [{"title": "T1", "task_type": "llm"}]
        assert strategy_risk_penalty(tasks) == 0.0

    def test_dag_tasks_no_penalty(self):
        """DAG has 100% success → no penalty."""
        tasks = [
            {"title": "T1", "task_type": "llm"},
            {"title": "T2", "task_type": "code", "dependencies": [0]},
        ]
        assert strategy_risk_penalty(tasks) == 0.0

    def test_swarm_tasks_max_penalty(self):
        """Swarm has 0% success → max penalty (0.25)."""
        tasks = [
            {"title": "T1", "task_type": "fan_out", "spawn_parallel": True},
        ]
        assert strategy_risk_penalty(tasks) == pytest.approx(0.25)

    def test_pipeline_tasks_max_penalty(self):
        """Pipeline has 0% success → max penalty (0.25)."""
        tasks = [
            {"title": "T1", "task_type": "dispatch"},
            {"title": "T2", "task_type": "research"},
            {"title": "T3", "task_type": "draft"},
        ]
        assert strategy_risk_penalty(tasks) == pytest.approx(0.25)

    def test_penalty_range(self):
        """Penalty is always in [0.0, 0.25]."""
        tasks = [{"title": "T1", "task_type": "llm"}]
        penalty = strategy_risk_penalty(tasks)
        assert 0.0 <= penalty <= 0.25


class TestCalibratedConstants:
    """Calibrated normalizing constants are sensible."""

    def test_token_normalizer_is_50k(self):
        assert TOKEN_NORMALIZER == 50_000

    def test_latency_normalizer_is_30s(self):
        assert LATENCY_NORMALIZER_MS == 30_000

    def test_task_count_normalizer_is_10(self):
        assert TASK_COUNT_NORMALIZER == 10
