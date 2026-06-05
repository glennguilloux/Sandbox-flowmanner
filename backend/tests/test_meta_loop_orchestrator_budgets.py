"""Unit tests for MetaLoopOrchestrator budget enforcement (H2.2).

NOTE: Due to an upstream bug in orchestrator.py where _nexus_orchestrator
is defined inside a class method instead of at module level, the
MetaLoopOrchestrator import must be patched to mock the orchestrator
get_nexus_orchestrator before module load.

Covers:
- plan_execute_observe() resets budgets for new mission_id
- _get_effective_max_depth() clamps with capability lattice
- _handle_failure() calls analyzer with wall_clock_ms and cost_usd
- recoverable retry path recurses
- non-recoverable path returns failure with failure_analysis payload
"""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
from uuid import uuid4

import pytest


# ── Pre-mock to work around upstream _nexus_orchestrator bug ───────
# The orchestrator.py file defines _nexus_orchestrator inside a class
# method body, not at module level. This causes NameError when
# get_nexus_orchestrator() is called. Pre-mock before import.

_mock_nexus_orch_instance = MagicMock()
_mock_nexus_orch_instance.plan_and_execute = AsyncMock(
    return_value=MagicMock(
        success=True, data={"ok": True}, error=None, capabilities_used=["test:cap"]
    )
)
_mock_nexus_orch_instance.initialize = AsyncMock()

_mock_orchestrator_module = MagicMock()
_mock_orchestrator_module.NexusOrchestrator = MagicMock(
    return_value=_mock_nexus_orch_instance
)
_mock_orchestrator_module.ExecutionContext = MagicMock()
_mock_orchestrator_module.OperationResult = MagicMock()
_mock_orchestrator_module.get_nexus_orchestrator = MagicMock(
    return_value=_mock_nexus_orch_instance
)

sys.modules["app.services.nexus.orchestrator"] = _mock_orchestrator_module
# Also mock capability_registry and distributed_executor that orchestrator imports
sys.modules["app.services.nexus.capability_registry"] = MagicMock()
sys.modules["app.services.nexus.distributed_executor"] = MagicMock()
sys.modules["app.services.learning_service"] = MagicMock()

from app.services.nexus.failure_analyzer import (
    ErrorClass,
    ErrorBudget,
    FailureAnalysisResult,
    FailureAnalyzer,
)
from app.services.nexus.meta_loop_orchestrator import (
    MetaLoopOrchestrator,
    MetaLoopResult,
    get_meta_loop_orchestrator,
)


# ── Helpers ────────────────────────────────────────────────────────


def _mock_analyzer():
    """Create a mock FailureAnalyzer."""
    analyzer = MagicMock(spec=FailureAnalyzer)
    analyzer.reset_budgets = MagicMock()

    analysis = FailureAnalysisResult(
        error_class=ErrorClass.TIMEOUT,
        root_cause="Test timeout",
        is_recoverable=True,
        suggested_recovery="Retry",
        retry_recommended=True,
    )
    analyzer.analyze_failure = MagicMock(return_value=analysis)
    return analyzer


# ═══════════════════════════════════════════════════════════════════
# MetaLoopOrchestrator: plan_execute_observe() budget reset
# ═══════════════════════════════════════════════════════════════════


class TestPlanExecuteObserveBudgetReset:

    def test_resets_budgets_for_new_mission(self):
        """plan_execute_observe() resets budgets when mission_id changes."""
        analyzer = _mock_analyzer()
        orch = MetaLoopOrchestrator(
            nexus_orchestrator=_mock_nexus_orch_instance,
            failure_analyzer=analyzer,
        )

        mission_id_1 = str(uuid4())
        asyncio.run(orch.plan_execute_observe("goal 1", mission_id=mission_id_1))
        assert analyzer.reset_budgets.call_count == 1

        mission_id_2 = str(uuid4())
        asyncio.run(orch.plan_execute_observe("goal 2", mission_id=mission_id_2))
        assert analyzer.reset_budgets.call_count == 2

    def test_does_not_reset_budgets_for_same_mission(self):
        """plan_execute_observe() does NOT reset budgets for same mission_id."""
        analyzer = _mock_analyzer()
        orch = MetaLoopOrchestrator(
            nexus_orchestrator=_mock_nexus_orch_instance,
            failure_analyzer=analyzer,
        )

        mission_id = str(uuid4())
        asyncio.run(orch.plan_execute_observe("goal 1", mission_id=mission_id))
        asyncio.run(orch.plan_execute_observe("goal 2", mission_id=mission_id))
        asyncio.run(orch.plan_execute_observe("goal 3", mission_id=mission_id))

        assert analyzer.reset_budgets.call_count == 1

    def test_no_mission_id_does_not_call_reset(self):
        """plan_execute_observe() without mission_id does not call reset_budgets."""
        analyzer = _mock_analyzer()
        orch = MetaLoopOrchestrator(
            nexus_orchestrator=_mock_nexus_orch_instance,
            failure_analyzer=analyzer,
        )

        asyncio.run(orch.plan_execute_observe("goal"))
        analyzer.reset_budgets.assert_not_called()

    def test_successful_execution_returns_meta_loop_result(self):
        """plan_execute_observe() returns MetaLoopResult on success."""
        analyzer = _mock_analyzer()
        orch = MetaLoopOrchestrator(
            nexus_orchestrator=_mock_nexus_orch_instance,
            failure_analyzer=analyzer,
        )

        result = asyncio.run(
            orch.plan_execute_observe("solve everything", mission_id=str(uuid4()))
        )

        assert isinstance(result, MetaLoopResult)
        assert result.success is True
        assert result.data == {"ok": True}
        assert result.depth_reached == 0

    def test_successful_execution_includes_execution_log(self):
        """MetaLoopResult includes execution_log on success."""
        analyzer = _mock_analyzer()
        orch = MetaLoopOrchestrator(
            nexus_orchestrator=_mock_nexus_orch_instance,
            failure_analyzer=analyzer,
        )

        result = asyncio.run(orch.plan_execute_observe("task"))

        assert len(result.execution_log) > 0
        obs = result.execution_log[0]
        assert obs["status"] == "success"


# ═══════════════════════════════════════════════════════════════════
# MetaLoopOrchestrator: _handle_failure()
# ═══════════════════════════════════════════════════════════════════


class TestHandleFailure:

    def test_handle_failure_passes_wall_clock_and_cost(self):
        """_handle_failure() passes wall_clock_ms and cost_usd to analyzer."""
        nexus = MagicMock()
        nexus.plan_and_execute = AsyncMock(
            return_value=MagicMock(
                success=False,
                error="timeout error",
                data=None,
                capabilities_used=["test:cap"],
            )
        )
        analyzer = _mock_analyzer()
        orch = MetaLoopOrchestrator(nexus_orchestrator=nexus, failure_analyzer=analyzer)

        mission_id = str(uuid4())
        asyncio.run(orch.plan_execute_observe("goal", mission_id=mission_id))

        assert analyzer.analyze_failure.call_count > 0
        call_kwargs = analyzer.analyze_failure.call_args
        assert "wall_clock_ms" in call_kwargs.kwargs
        assert "cost_usd" in call_kwargs.kwargs

    def test_recoverable_with_retry_recommended_recurses(self):
        """Recoverable + retry_recommended → recursive call with depth."""
        nexus = MagicMock()
        nexus.plan_and_execute = AsyncMock(
            return_value=MagicMock(
                success=False,
                error="timeout",
                data=None,
                capabilities_used=["test:cap"],
            )
        )
        analyzer = _mock_analyzer()
        analyzer.analyze_failure.return_value = FailureAnalysisResult(
            error_class=ErrorClass.TIMEOUT,
            root_cause="Timeout",
            is_recoverable=True,
            suggested_recovery="Retry",
            retry_recommended=True,
        )
        orch = MetaLoopOrchestrator(nexus_orchestrator=nexus, failure_analyzer=analyzer)

        asyncio.run(orch.plan_execute_observe("goal", mission_id=str(uuid4())))

        # Should have retried: at least 2 calls
        assert nexus.plan_and_execute.call_count >= 2

    def test_non_recoverable_returns_failure_payload(self):
        """Non-recoverable path returns MetaLoopResult with failure_analysis."""
        nexus = MagicMock()
        nexus.plan_and_execute = AsyncMock(
            return_value=MagicMock(
                success=False,
                error="permission denied",
                data=None,
                capabilities_used=[],
            )
        )
        analyzer = _mock_analyzer()
        analyzer.analyze_failure.return_value = FailureAnalysisResult(
            error_class=ErrorClass.PERMISSION,
            root_cause="No access",
            is_recoverable=False,
            suggested_recovery="Check permissions",
            retry_recommended=False,
            alternative_tools=[],
        )
        orch = MetaLoopOrchestrator(nexus_orchestrator=nexus, failure_analyzer=analyzer)

        result = asyncio.run(orch.plan_execute_observe("goal", mission_id=str(uuid4())))

        assert result.success is False
        assert result.failure_analysis is not None
        assert result.failure_analysis["error_class"] == "permission"
        assert result.failure_analysis["is_recoverable"] is False

    def test_non_recoverable_no_retry(self):
        """Non-recoverable failure does NOT retry."""
        nexus = MagicMock()
        nexus.plan_and_execute = AsyncMock(
            return_value=MagicMock(
                success=False,
                error="permission denied",
                data=None,
                capabilities_used=[],
            )
        )
        analyzer = _mock_analyzer()
        analyzer.analyze_failure.return_value = FailureAnalysisResult(
            error_class=ErrorClass.PERMISSION,
            root_cause="No access",
            is_recoverable=False,
            suggested_recovery="Check permissions",
            retry_recommended=False,
            alternative_tools=[],
        )
        orch = MetaLoopOrchestrator(nexus_orchestrator=nexus, failure_analyzer=analyzer)

        asyncio.run(orch.plan_execute_observe("goal", mission_id=str(uuid4())))

        assert nexus.plan_and_execute.call_count == 1

    def test_exception_in_plan_and_execute_is_handled(self):
        """Exceptions from plan_and_execute are caught and analyzed."""
        nexus = MagicMock()
        nexus.plan_and_execute = AsyncMock(side_effect=RuntimeError("unexpected boom"))
        analyzer = _mock_analyzer()
        orch = MetaLoopOrchestrator(nexus_orchestrator=nexus, failure_analyzer=analyzer)

        result = asyncio.run(orch.plan_execute_observe("goal", mission_id=str(uuid4())))

        assert analyzer.analyze_failure.call_count >= 1
        assert result.success is False


# ═══════════════════════════════════════════════════════════════════
# MetaLoopOrchestrator: _get_effective_max_depth()
# ═══════════════════════════════════════════════════════════════════


class TestGetEffectiveMaxDepth:

    def test_falls_back_to_requested_when_no_lattice(self):
        """_get_effective_max_depth() returns requested when lattice import fails."""
        orch = MetaLoopOrchestrator(nexus_orchestrator=_mock_nexus_orch_instance)
        with patch(
            "app.services.nexus.capability_lattice.get_capability_lattice",
            side_effect=ImportError("no lattice"),
        ):
            depth = orch._get_effective_max_depth(5)
        assert depth == 5

    def test_clamps_to_lattice_max_depth(self):
        """_get_effective_max_depth() clamps to CapabilityLattice.max_depth."""
        with patch(
            "app.services.nexus.capability_lattice.get_capability_lattice"
        ) as mock_get_lattice:
            mock_lattice = MagicMock()
            mock_lattice.max_depth = 3
            mock_get_lattice.return_value = mock_lattice

            orch = MetaLoopOrchestrator(nexus_orchestrator=_mock_nexus_orch_instance)
            depth = orch._get_effective_max_depth(10)
            assert depth == 3

    def test_clamps_when_requested_equals_lattice(self):
        """_get_effective_max_depth() works when requested equals lattice max."""
        with patch(
            "app.services.nexus.capability_lattice.get_capability_lattice"
        ) as mock_get_lattice:
            mock_lattice = MagicMock()
            mock_lattice.max_depth = 3
            mock_get_lattice.return_value = mock_lattice

            orch = MetaLoopOrchestrator(nexus_orchestrator=_mock_nexus_orch_instance)
            depth = orch._get_effective_max_depth(3)
            assert depth == 3


# ═══════════════════════════════════════════════════════════════════
# MetaLoopOrchestrator: max depth reached
# ═══════════════════════════════════════════════════════════════════


class TestMaxDepthReached:

    def test_returns_failure_when_max_depth_reached(self):
        """plan_execute_observe() returns failure when depth limit reached."""
        analyzer = _mock_analyzer()
        orch = MetaLoopOrchestrator(
            nexus_orchestrator=_mock_nexus_orch_instance,
            failure_analyzer=analyzer,
        )

        result = asyncio.run(
            orch.plan_execute_observe("goal", max_depth=0, mission_id=str(uuid4()))
        )

        assert result.success is False
        assert "depth" in (result.error or "").lower()


# ═══════════════════════════════════════════════════════════════════
# MetaLoopOrchestrator: alternative tools path
# ═══════════════════════════════════════════════════════════════════


class TestAlternativeToolsPath:

    def test_alternative_tools_triggered_when_recoverable_no_retry(self):
        """When recoverable but no retry recommended with alt tools."""
        nexus = MagicMock()
        nexus.plan_and_execute = AsyncMock(
            return_value=MagicMock(
                success=False,
                error="not found",
                data=None,
                capabilities_used=[],
            )
        )
        analyzer = _mock_analyzer()
        analyzer.analyze_failure.return_value = FailureAnalysisResult(
            error_class=ErrorClass.NOT_FOUND,
            root_cause="Resource not found",
            is_recoverable=True,
            suggested_recovery="Use alternative",
            retry_recommended=False,
            alternative_tools=["search_knowledge", "web_search"],
        )
        orch = MetaLoopOrchestrator(nexus_orchestrator=nexus, failure_analyzer=analyzer)

        asyncio.run(orch.plan_execute_observe("goal", mission_id=str(uuid4())))

        # Should have tried alternatives
        assert nexus.plan_and_execute.call_count >= 2


# ═══════════════════════════════════════════════════════════════════
# MetaLoopOrchestrator: singleton
# ═══════════════════════════════════════════════════════════════════


class TestMetaLoopOrchestratorSingleton:

    def test_get_orchestrator_returns_same_instance(self):
        mlo1 = get_meta_loop_orchestrator()
        mlo2 = get_meta_loop_orchestrator()
        assert mlo1 is mlo2
        assert isinstance(mlo1, MetaLoopOrchestrator)
