"""
Meta-Loop Orchestrator - Recursive Planning with Failure Analysis

Extends the Nexus Orchestrator with a recursive plan-execute-observe loop
that wires FailureAnalyzer into the error path for intelligent recovery.

When a step execution fails:
1. FailureAnalyzer.analyze_failure() is called with the error, context, and execution log
2. The analysis result informs re-planning decisions:
   - Recoverable + retry recommended: retry with context updates applied
   - Recoverable + no retry: try alternative tools
   - Not recoverable: break and return failure with analysis attached
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Optional

from .failure_analyzer import (
    ExecutionObservation,
    FailureAnalyzer,
    get_failure_analyzer,
)
from .orchestrator import ExecutionContext, NexusOrchestrator, get_nexus_orchestrator

logger = logging.getLogger(__name__)


@dataclass
class MetaLoopResult:
    success: bool
    data: Any = None
    error: str | None = None
    execution_time_ms: float = 0
    capabilities_used: list[str] = field(default_factory=list)
    failure_analysis: dict[str, Any] | None = None
    execution_log: list[dict[str, Any]] = field(default_factory=list)
    depth_reached: int = 0


class MetaLoopOrchestrator:
    """Recursive planning/execution orchestrator with failure analysis and budgets (H2.2)."""

    # H2.2: Per-error-class budgets enforced via FailureAnalyzer
    BUDGET_RESET_ON_NEW_MISSION = True

    def __init__(
        self,
        nexus_orchestrator: NexusOrchestrator | None = None,
        failure_analyzer: FailureAnalyzer | None = None,
    ):
        self.nexus = nexus_orchestrator or get_nexus_orchestrator()
        self.analyzer = failure_analyzer or get_failure_analyzer()
        self._current_mission_id: str | None = None

    def _ensure_budgets_fresh(self, mission_id: str) -> None:
        """Reset error-class budgets when a new mission starts (H2.2)."""
        if self.BUDGET_RESET_ON_NEW_MISSION and self._current_mission_id != mission_id:
            self._current_mission_id = mission_id
            self.analyzer.reset_budgets()
            logger.info("Error-class budgets reset for mission %s", mission_id)

    def _get_effective_max_depth(self, requested_max_depth: int) -> int:
        """Get the effective max recursion depth, clamped by CapabilityLattice (H2.3).

        The CapabilityLattice is the source of truth for depth bounds.
        If the lattice is not available, falls back to the requested value.
        """
        try:
            from .capability_lattice import get_capability_lattice

            lattice = get_capability_lattice()
            return min(requested_max_depth, lattice.max_depth)
        except ImportError:
            return requested_max_depth

    async def plan_execute_observe(
        self,
        goal: str,
        ctx: ExecutionContext | None = None,
        max_depth: int = 3,
        *,
        mission_id: str | None = None,
    ) -> MetaLoopResult:
        """Main entry point: plan, execute, observe, and recover from failures.

        H2.2: Resets error-class budgets when a new mission starts.
        """
        logger.info('MetaLoop: Starting plan_execute_observe for goal: %s...', goal[:100])

        # H2.2: Reset budgets for new mission
        if mission_id:
            self._ensure_budgets_fresh(mission_id)

        return await self._run_recursive_cycle(
            goal=goal,
            ctx=ctx,
            max_depth=max_depth,
            current_depth=0,
            execution_log=[],
            context_updates={},
        )

    async def _run_recursive_cycle(
        self,
        goal: str,
        ctx: ExecutionContext | None,
        max_depth: int,
        current_depth: int,
        execution_log: list[ExecutionObservation],
        context_updates: dict[str, Any],
    ) -> MetaLoopResult:
        """Recursive execution cycle with FailureAnalyzer wired into the error path.

        H2.3: max_depth is now validated against the CapabilityLattice's global
        limit.  The CapabilityLattice is the source of truth for depth bounds.
        """
        # H2.3: Clamp max_depth to CapabilityLattice limit
        effective_max = self._get_effective_max_depth(max_depth)

        if current_depth >= effective_max:
            logger.warning('MetaLoop: Max depth (%s) reached for goal: %s...', effective_max, goal[:80])
            return MetaLoopResult(
                success=False,
                error=f"Max recursion depth ({max_depth}) reached",
                execution_log=[obs.to_dict() for obs in execution_log],
                depth_reached=current_depth,
            )

        start_time = datetime.now(UTC)
        capabilities_used = []

        try:
            plan_result = await self.nexus.plan_and_execute(goal, ctx)

            observation = ExecutionObservation(
                tool_id="nexus:plan_and_execute",
                status="success" if plan_result.success else "failure",
                output=plan_result.data if plan_result.success else None,
                error=plan_result.error if not plan_result.success else None,
                duration_ms=(datetime.now(UTC) - start_time).total_seconds() * 1000,
            )
            execution_log.append(observation)
            capabilities_used.extend(plan_result.capabilities_used)

            if not plan_result.success:
                return await self._handle_failure(
                    goal=goal,
                    ctx=ctx,
                    error=Exception(plan_result.error or "Unknown execution error"),
                    execution_log=execution_log,
                    max_depth=max_depth,
                    current_depth=current_depth,
                    context_updates=context_updates,
                    capabilities_used=capabilities_used,
                )

            execution_time = (datetime.now(UTC) - start_time).total_seconds() * 1000
            logger.info('MetaLoop: Success at depth %s', current_depth)

            return MetaLoopResult(
                success=True,
                data=plan_result.data,
                execution_time_ms=execution_time,
                capabilities_used=capabilities_used,
                execution_log=[obs.to_dict() for obs in execution_log],
                depth_reached=current_depth,
            )

        except Exception as e:
            observation = ExecutionObservation(
                tool_id="nexus:plan_and_execute",
                status="failure",
                error=str(e),
                duration_ms=(datetime.now(UTC) - start_time).total_seconds() * 1000,
            )
            execution_log.append(observation)

            return await self._handle_failure(
                goal=goal,
                ctx=ctx,
                error=e,
                execution_log=execution_log,
                max_depth=max_depth,
                current_depth=current_depth,
                context_updates=context_updates,
                capabilities_used=capabilities_used,
            )

    async def _handle_failure(
        self,
        goal: str,
        ctx: ExecutionContext | None,
        error: Exception,
        execution_log: list[ExecutionObservation],
        max_depth: int,
        current_depth: int,
        context_updates: dict[str, Any],
        capabilities_used: list[str],
    ) -> MetaLoopResult:
        """Analyze failure via FailureAnalyzer and attempt recovery through re-planning.

        H2.2: Passes wall-clock and cost estimates to the analyzer for budget tracking.
        """
        logger.warning('MetaLoop: Failure at depth %s: %s', current_depth, error)

        analysis_context = {
            "goal": goal,
            "user_id": ctx.user_id if ctx else None,
            "session_id": ctx.session_id if ctx else None,
            "depth": current_depth,
            "context_updates": context_updates,
        }

        # H2.2: Estimate wall-clock and cost for budget tracking
        last_obs = execution_log[-1] if execution_log else None
        wall_clock_ms = last_obs.duration_ms if last_obs else 0.0
        cost_usd = 0.0  # Could be plumbed from tool execution context in future

        analysis = self.analyzer.analyze_failure(
            error=error,
            context=analysis_context,
            execution_log=execution_log,
            wall_clock_ms=wall_clock_ms,
            cost_usd=cost_usd,
        )

        logger.info('MetaLoop: Analysis - class=%s, recoverable=%s, retry=%s', analysis.error_class.value, analysis.is_recoverable, analysis.retry_recommended)

        merged_context = {**context_updates, **analysis.context_updates}

        if analysis.is_recoverable and analysis.retry_recommended:
            logger.info('MetaLoop: Retrying with context updates at depth %s', current_depth + 1)
            return await self._run_recursive_cycle(
                goal=goal,
                ctx=ctx,
                max_depth=max_depth,
                current_depth=current_depth + 1,
                execution_log=execution_log,
                context_updates=merged_context,
            )

        if analysis.is_recoverable and analysis.alternative_tools:
            logger.info('MetaLoop: Trying alternative tools: %s', analysis.alternative_tools)
            alt_goal = f"{goal} (using alternative approach: {', '.join(analysis.alternative_tools)})"
            return await self._run_recursive_cycle(
                goal=alt_goal,
                ctx=ctx,
                max_depth=max_depth,
                current_depth=current_depth + 1,
                execution_log=execution_log,
                context_updates=merged_context,
            )

        logger.warning('MetaLoop: Failure not recoverable: %s', analysis.root_cause)
        execution_time = (
            (datetime.now(UTC) - execution_log[0].timestamp).total_seconds() * 1000
            if execution_log
            else 0
        )

        return MetaLoopResult(
            success=False,
            error=f"{analysis.root_cause}: {error}",
            failure_analysis=analysis.to_dict(),
            execution_time_ms=execution_time,
            capabilities_used=capabilities_used,
            execution_log=[obs.to_dict() for obs in execution_log],
            depth_reached=current_depth,
        )


_meta_loop_orchestrator: Optional["MetaLoopOrchestrator"] = None


def get_meta_loop_orchestrator() -> MetaLoopOrchestrator:
    """Get or create the meta-loop orchestrator singleton."""
    global _meta_loop_orchestrator
    if _meta_loop_orchestrator is None:
        _meta_loop_orchestrator = MetaLoopOrchestrator()
    return _meta_loop_orchestrator
