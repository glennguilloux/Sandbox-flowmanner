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


# Synthetic, deterministic stand-in for docs/strategy-profiling-results.json.
#
# PRODUCTION FALLBACK FINDING (current contract — do NOT change yet):
#   calibration._load_profiling_data() falls back to 1.0 for every strategy
#   when the profiling file is absent. In production the file is NEVER present:
#   (a) it is uncommitted (git log --all shows no such path), and (b) docs/ is
#   excluded from the Docker build by backend/.dockerignore (the line "docs/"),
#   and the Dockerfile's COPY list (app/, alembic/, alembic.ini, pyproject.toml,
#   mcp_gateway/, agent_definitions/, scripts/, tests/, integrations/, schemas/)
#   does not include docs/. The generator scripts/profile_strategies.py also
#   builds workflows that fail the strategies' own validation, so its 0.0 rates
#   are validation artifacts, not measured performance. Net effect: production
#   calibration currently applies NO risk penalty (all rates 1.0). This is
#   documented here as a finding and is asserted by TestProductionFallback; it
#   must not be changed without first generating/committing real profiling data.
#
# The values below are INTENTIONALLY synthetic and varied (not just 0.0/1.0)
# purely to exercise calibration.py's calculation behavior: rate lookup,
# get_strategy_success_rate defaults, and the risk-penalty formula
#   penalty = (1.0 - success_rate) * 0.25   (range [0.0, 0.25])
# across the full range. They are a test fixture, not a performance claim, and
# deliberately do NOT mirror the archived file's 0.0/1.0 assumptions.
_PROFILING_FIXTURE_RATES: dict[str, float] = {
    "solo": 1.0,  # → penalty 0.0
    "dag": 0.8,  # → penalty 0.05
    "graph": 0.5,  # → penalty 0.125
    "pipeline": 0.25,  # → penalty 0.1875
    "meta": 0.0,  # → penalty 0.25 (max)
    "swarm": 0.6,  # → penalty 0.1
    "langgraph": 0.4,  # → penalty 0.15
}


@pytest.fixture
def _deterministic_rates(monkeypatch):
    """Patch _load_profiling_data to return a deterministic fixture dict.

    Applied explicitly to the rate-dependent tests (TestGetStrategySuccessRate,
    TestStrategyRiskPenalty) so they get known rates without depending on the
    uncommitted, unreliable docs/strategy-profiling-results.json artifact. The
    file-load / fallback tests do NOT use this fixture, so they exercise the
    real _load_profiling_data path.
    """
    from app.services.plan_selection import calibration as _cal_mod

    monkeypatch.setattr(
        _cal_mod,
        "_load_profiling_data",
        lambda: dict(_PROFILING_FIXTURE_RATES),
    )
    return


class TestLoadProfilingData:
    """_load_profiling_data: loads strategy profiling results."""

    def test_loads_real_profiling_file(self, tmp_path):
        """_load_profiling_data reads a profiling JSON at _PROFILING_FILE."""
        payload = {
            "timestamp": 0,
            "model": "fixture",
            "attempts_per_strategy": 1,
            "results": {
                name: {
                    "success_rate": rate,
                    "successes": int(rate),
                    "attempts": 1,
                    "avg_latency_ms": 0,
                    "avg_tokens": 0,
                    "total_tokens": 0,
                    "errors": [],
                }
                for name, rate in _PROFILING_FIXTURE_RATES.items()
            },
        }
        path = tmp_path / "strategy-profiling-results.json"
        path.write_text(json.dumps(payload))
        with patch("app.services.plan_selection.calibration._PROFILING_FILE", path):
            reset_profiling_cache()
            rates = _load_profiling_data()
        assert "solo" in rates
        assert "dag" in rates
        assert "swarm" in rates
        assert rates == _PROFILING_FIXTURE_RATES

    def test_caches_after_first_load(self, tmp_path):
        """Second call returns cached data without re-reading file."""
        payload = {
            "timestamp": 0,
            "model": "fixture",
            "attempts_per_strategy": 1,
            "results": {
                name: {
                    "success_rate": rate,
                    "successes": int(rate),
                    "attempts": 1,
                    "avg_latency_ms": 0,
                    "avg_tokens": 0,
                    "total_tokens": 0,
                    "errors": [],
                }
                for name, rate in _PROFILING_FIXTURE_RATES.items()
            },
        }
        path = tmp_path / "strategy-profiling-results.json"
        path.write_text(json.dumps(payload))
        with patch("app.services.plan_selection.calibration._PROFILING_FILE", path):
            reset_profiling_cache()
            _load_profiling_data()
            rates = _load_profiling_data()  # cached, should not re-read
        assert rates == _PROFILING_FIXTURE_RATES

    def test_graceful_fallback_when_file_missing(self):
        """Falls back to 1.0 for all strategies when file is missing."""
        with patch(
            "app.services.plan_selection.calibration._PROFILING_FILE",
            Path("/nonexistent/file.json"),
        ):
            reset_profiling_cache()
            rates = _load_profiling_data()
            assert all(v == 1.0 for v in rates.values())
            assert len(rates) == 7


class TestGetStrategySuccessRate:
    """get_strategy_success_rate: per-strategy lookup."""

    @pytest.mark.usefixtures("_deterministic_rates")
    def test_solo_returns_1(self):
        assert get_strategy_success_rate("solo") == 1.0

    @pytest.mark.usefixtures("_deterministic_rates")
    def test_dag_returns_0_8(self):
        assert get_strategy_success_rate("dag") == 0.8

    @pytest.mark.usefixtures("_deterministic_rates")
    def test_graph_returns_0_5(self):
        assert get_strategy_success_rate("graph") == 0.5

    @pytest.mark.usefixtures("_deterministic_rates")
    def test_unknown_strategy_defaults_to_1(self):
        assert get_strategy_success_rate("nonexistent") == 1.0

    @pytest.mark.usefixtures("_deterministic_rates")
    def test_swarm_returns_0_6(self):
        rate = get_strategy_success_rate("swarm")
        assert rate == 0.6

    @pytest.mark.usefixtures("_deterministic_rates")
    def test_pipeline_returns_0_25(self):
        rate = get_strategy_success_rate("pipeline")
        assert rate == 0.25

    @pytest.mark.usefixtures("_deterministic_rates")
    def test_meta_returns_0(self):
        rate = get_strategy_success_rate("meta")
        assert rate == 0.0

    @pytest.mark.usefixtures("_deterministic_rates")
    def test_langgraph_returns_0_4(self):
        rate = get_strategy_success_rate("langgraph")
        assert rate == 0.4


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
    """strategy_risk_penalty: penalty = (1.0 - success_rate) * 0.25.

    Rates come from the synthetic _PROFILING_FIXTURE_RATES via the
    _deterministic_rates fixture, so expected penalties are DERIVED from those
    values (e.g. dag 0.8 -> 0.05, swarm 0.6 -> 0.1, pipeline 0.25 -> 0.1875,
    meta 0.0 -> 0.25), not copied from any archived assumption.
    """

    pytestmark = pytest.mark.usefixtures("_deterministic_rates")

    def test_solo_tasks_no_penalty(self):
        """Solo has 100% success → no penalty."""
        tasks = [{"title": "T1", "task_type": "llm"}]
        assert strategy_risk_penalty(tasks) == 0.0

    def test_dag_tasks_penalty_0_05(self):
        """DAG rate 0.8 → penalty (1-0.8)*0.25 = 0.05."""
        tasks = [
            {"title": "T1", "task_type": "llm"},
            {"title": "T2", "task_type": "code", "dependencies": [0]},
        ]
        assert strategy_risk_penalty(tasks) == pytest.approx(0.05)

    def test_swarm_tasks_penalty_0_1(self):
        """Swarm rate 0.6 → penalty (1-0.6)*0.25 = 0.1."""
        tasks = [
            {"title": "T1", "task_type": "fan_out", "spawn_parallel": True},
        ]
        assert strategy_risk_penalty(tasks) == pytest.approx(0.1)

    def test_pipeline_tasks_penalty_0_1875(self):
        """Pipeline rate 0.25 → penalty (1-0.25)*0.25 = 0.1875."""
        tasks = [
            {"title": "T1", "task_type": "dispatch"},
            {"title": "T2", "task_type": "research"},
            {"title": "T3", "task_type": "draft"},
        ]
        assert strategy_risk_penalty(tasks) == pytest.approx(0.1875)

    def test_penalty_range(self):
        """Penalty is always in [0.0, 0.25]."""
        tasks = [{"title": "T1", "task_type": "llm"}]
        penalty = strategy_risk_penalty(tasks)
        assert 0.0 <= penalty <= 0.25


class TestProductionFallback:
    """Document the CURRENT production contract: no profiling file ⇒ no penalty.

    The profiling JSON (docs/strategy-profiling-results.json) is uncommitted and
    excluded from the Docker build (backend/.dockerignore lists "docs/", and the
    Dockerfile COPY list omits docs/). So _load_profiling_data always hits the 1.0
    fallback, every strategy's success_rate is 1.0, and strategy_risk_penalty is
    0.0. This is a FINDING about the live system, written as an executable guard
    so a future change to packaging/generation is caught. It does NOT alter the
    production contract.
    """

    def test_all_strategies_default_to_1_without_profiling_file(self):
        with patch(
            "app.services.plan_selection.calibration._PROFILING_FILE",
            Path("/nonexistent/file.json"),
        ):
            reset_profiling_cache()
            for s in (
                "solo",
                "dag",
                "graph",
                "pipeline",
                "meta",
                "swarm",
                "langgraph",
            ):
                assert get_strategy_success_rate(s) == 1.0

    def test_no_risk_penalty_applied_without_profiling_file(self):
        with patch(
            "app.services.plan_selection.calibration._PROFILING_FILE",
            Path("/nonexistent/file.json"),
        ):
            reset_profiling_cache()
            solo = [{"title": "T1", "task_type": "llm"}]
            assert strategy_risk_penalty(solo) == 0.0
            swarm = [{"title": "T1", "task_type": "fan_out", "spawn_parallel": True}]
            assert strategy_risk_penalty(swarm) == 0.0


class TestCalibratedConstants:
    """Calibrated normalizing constants are sensible."""

    def test_token_normalizer_is_50k(self):
        assert TOKEN_NORMALIZER == 50_000

    def test_latency_normalizer_is_30s(self):
        assert LATENCY_NORMALIZER_MS == 30_000

    def test_task_count_normalizer_is_10(self):
        assert TASK_COUNT_NORMALIZER == 10
