#!/usr/bin/env python3
"""
Improvement Loop v2 - Autonomous Self-Improvement Synthesis Layer

This module provides the main orchestration layer for autonomous improvement:
- Triggers on mission completion or scheduled intervals
- Analyzes weak areas from failure telemetry
- Generates improvement strategies via causal decomposition
- Tests strategies through hypothesis testing
- Applies verified improvements with rollback support

Key Design Principle: Every improvement is a hypothesis that must be verified.
The system learns from both successes and failures, building a knowledge graph
of what works and what doesn't.

Architecture:
    Failure Telemetry → Causal Decomposition → Hypothesis Testing → Improvement Application
           ↑                                                                    │
           └────────────────── Feedback Loop ──────────────────────────────────┘
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import uuid4

from .causal_decomposer import (
    CausalDecomposer,
    ImprovementStrategy,
    KnobType,
    RiskLevel,
    StrategyType,
    WeakArea,
)
from .failure_types import (
    FailureContext,
    FailureType,
    capture_success_metrics,
)
from .hypothesis_tester import (
    HypothesisState,
    HypothesisTest,
    HypothesisTester,
    TestResult,
)
from .knob_manager import (
    KnobAdjustment,
    KnobManager,
    initialize_default_knobs,
)

logger = logging.getLogger(__name__)


# ============================================================================
# IMPROVEMENT SESSION
# ============================================================================


class SessionState(str, Enum):
    """States of an improvement session"""

    PENDING = "pending"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    TESTING = "testing"
    APPLYING = "applying"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ImprovementSession:
    """
    Represents a single improvement session.

    A session is triggered by:
    - Mission completion
    - Scheduled interval
    - Manual trigger
    - Error threshold breach
    """

    # Identification
    session_id: str = field(default_factory=lambda: str(uuid4()))

    # Trigger info
    trigger_type: str = "manual"  # "mission_complete", "scheduled", "manual", "threshold"
    trigger_context: dict[str, Any] = field(default_factory=dict)

    # State
    state: SessionState = SessionState.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Analysis results
    weak_areas: list[WeakArea] = field(default_factory=list)
    failure_patterns: dict[FailureType, int] = field(default_factory=dict)

    # Generated strategies
    strategies: list[ImprovementStrategy] = field(default_factory=list)
    selected_strategy: ImprovementStrategy | None = None

    # Hypothesis test
    hypothesis_test: HypothesisTest | None = None
    test_result: TestResult | None = None

    # Applied improvement
    applied_adjustment: KnobAdjustment | None = None

    # Metrics
    baseline_metrics: dict[str, float] = field(default_factory=dict)
    final_metrics: dict[str, float] = field(default_factory=dict)

    # Metadata
    agent_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "trigger_type": self.trigger_type,
            "trigger_context": self.trigger_context,
            "state": self.state.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (self.completed_at.isoformat() if self.completed_at else None),
            "weak_areas": [wa.to_dict() for wa in self.weak_areas],
            "failure_patterns": {ft.value: count for ft, count in self.failure_patterns.items()},
            "strategies": [s.to_dict() for s in self.strategies],
            "selected_strategy_id": (self.selected_strategy.strategy_id if self.selected_strategy else None),
            "hypothesis_test_id": (self.hypothesis_test.test_id if self.hypothesis_test else None),
            "test_result": self.test_result.to_dict() if self.test_result else None,
            "agent_id": self.agent_id,
            "created_at": self.created_at.isoformat(),
            "notes": self.notes,
        }


# ============================================================================
# IMPROVEMENT KNOWLEDGE
# ============================================================================


@dataclass
class ImprovementSessionData:
    """Data transfer object for improvement sessions"""

    session_id: str
    state: SessionState
    trigger_type: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    weak_areas_count: int = 0
    strategies_count: int = 0
    selected_strategy_id: str | None = None
    test_result_success: bool | None = None
    agent_id: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_session(cls, session: "ImprovementSession") -> "ImprovementSessionData":
        """Create from full ImprovementSession"""
        return cls(
            session_id=session.session_id,
            state=session.state,
            trigger_type=session.trigger_type,
            started_at=session.started_at,
            completed_at=session.completed_at,
            weak_areas_count=len(session.weak_areas),
            strategies_count=len(session.strategies),
            selected_strategy_id=(session.selected_strategy.strategy_id if session.selected_strategy else None),
            test_result_success=(session.test_result.success if session.test_result else None),
            agent_id=session.agent_id,
            created_at=session.created_at,
        )


@dataclass
class ImprovementKnowledge:
    """
    Accumulated knowledge about what improvements work.

    This builds a knowledge graph of:
    - Which strategies work for which failure types
    - Which knobs are most effective
    - Which combinations to avoid (oscillation prevention)
    """

    # Strategy effectiveness: strategy_type -> {success_count, failure_count}
    strategy_effectiveness: dict[StrategyType, dict[str, int]] = field(default_factory=dict)

    # Knob effectiveness: knob_type -> {success_count, failure_count, avg_improvement}
    knob_effectiveness: dict[KnobType, dict[str, Any]] = field(default_factory=dict)

    # Failure type to strategy mapping: what works for each failure type
    failure_strategy_map: dict[FailureType, dict[StrategyType, float]] = field(default_factory=dict)

    # Oscillation patterns: knob -> list of recent values to avoid
    oscillation_patterns: dict[KnobType, list[Any]] = field(default_factory=dict)

    # Recent sessions for pattern analysis
    recent_sessions: list[ImprovementSession] = field(default_factory=list)

    def record_success(self, strategy: ImprovementStrategy, improvement_delta: float):
        """Record a successful improvement"""
        # Update strategy effectiveness
        if strategy.strategy_type not in self.strategy_effectiveness:
            self.strategy_effectiveness[strategy.strategy_type] = {
                "success": 0,
                "failure": 0,
            }
        self.strategy_effectiveness[strategy.strategy_type]["success"] += 1

        # Update knob effectiveness
        if strategy.knob not in self.knob_effectiveness:
            self.knob_effectiveness[strategy.knob] = {
                "success": 0,
                "failure": 0,
                "total_improvement": 0.0,
                "count": 0,
            }
        self.knob_effectiveness[strategy.knob]["success"] += 1
        self.knob_effectiveness[strategy.knob]["total_improvement"] += improvement_delta
        self.knob_effectiveness[strategy.knob]["count"] += 1

        # Update failure-strategy map
        for ft in strategy.applicable_failure_types:
            if ft not in self.failure_strategy_map:
                self.failure_strategy_map[ft] = {}
            if strategy.strategy_type not in self.failure_strategy_map[ft]:
                self.failure_strategy_map[ft][strategy.strategy_type] = 0.0
            # Weighted average with recency bias
            self.failure_strategy_map[ft][strategy.strategy_type] = (
                0.7 * self.failure_strategy_map[ft][strategy.strategy_type] + 0.3 * improvement_delta
            )

    def record_failure(self, strategy: ImprovementStrategy):
        """Record a failed improvement"""
        if strategy.strategy_type not in self.strategy_effectiveness:
            self.strategy_effectiveness[strategy.strategy_type] = {
                "success": 0,
                "failure": 0,
            }
        self.strategy_effectiveness[strategy.strategy_type]["failure"] += 1

        if strategy.knob not in self.knob_effectiveness:
            self.knob_effectiveness[strategy.knob] = {
                "success": 0,
                "failure": 0,
                "total_improvement": 0.0,
                "count": 0,
            }
        self.knob_effectiveness[strategy.knob]["failure"] += 1

    def get_best_strategy_for_failure(self, failure_type: FailureType) -> StrategyType | None:
        """Get the best strategy for a given failure type based on history"""
        if failure_type not in self.failure_strategy_map:
            return None

        strategies = self.failure_strategy_map[failure_type]
        if not strategies:
            return None

        return max(strategies.keys(), key=lambda s: strategies[s])

    def get_average_improvement(self, knob: KnobType) -> float:
        """Get average improvement for a knob"""
        if knob not in self.knob_effectiveness:
            return 0.0

        data = self.knob_effectiveness[knob]
        if data["count"] == 0:
            return 0.0

        return data["total_improvement"] / data["count"]

    def add_session(self, session: ImprovementSession):
        """Add a session to recent history"""
        self.recent_sessions.append(session)
        # Keep only last 100 sessions
        if len(self.recent_sessions) > 100:
            self.recent_sessions = self.recent_sessions[-100:]


# ============================================================================
# IMPROVEMENT LOOP v2 - Main Class
# ============================================================================


class ImprovementLoopV2:
    """
    Main orchestration layer for autonomous self-improvement.

    This class coordinates:
    - Failure telemetry collection
    - Causal decomposition
    - Hypothesis testing
    - Improvement application

    The loop runs:
    - After mission completion (if enabled)
    - On scheduled intervals
    - On demand
    """

    def __init__(
        self,
        db_session,
        causal_decomposer: CausalDecomposer | None = None,
        knob_manager: KnobManager | None = None,
        hypothesis_tester: HypothesisTester | None = None,
        enable_auto_improve: bool = True,
        min_failures_for_analysis: int = 5,
        improvement_interval_hours: int = 6,
    ):
        self.db_session = db_session
        self.causal_decomposer = causal_decomposer or CausalDecomposer()
        self.knob_manager = knob_manager or KnobManager(db_session=db_session)
        self.hypothesis_tester = hypothesis_tester or HypothesisTester(knob_manager=self.knob_manager)

        self.enable_auto_improve = enable_auto_improve
        self.min_failures_for_analysis = min_failures_for_analysis
        self.improvement_interval = timedelta(hours=improvement_interval_hours)

        # Knowledge base
        self.knowledge = ImprovementKnowledge()

        # Active sessions
        self._active_sessions: dict[str, ImprovementSession] = {}

        # Failure buffer for batch analysis
        self._failure_buffer: list[FailureContext] = []

        # Last improvement time
        self._last_improvement: datetime | None = None

    async def on_mission_complete(
        self,
        mission_id: str,
        agent_id: str,
        success: bool,
        metrics: dict[str, float],
    ):
        """
        Hook called when a mission completes.

        This triggers improvement analysis if:
        - Mission failed
        - Enough failures have accumulated
        - Scheduled interval has passed

        Args:
            mission_id: The completed mission ID
            agent_id: The agent that ran the mission
            success: Whether the mission succeeded
            metrics: Performance metrics from the mission
        """
        logger.info("Mission complete hook: mission=%s, success=%s", mission_id, success)

        # Capture success metrics for learning
        if success:
            await capture_success_metrics(
                agent_id=agent_id,
                mission_id=mission_id,
                metrics=metrics,
            )

        # Check if we should trigger improvement
        should_trigger = False
        trigger_type = "mission_complete"

        if not success:
            # Always analyze after failure
            should_trigger = True
            trigger_type = "mission_failure"
        elif len(self._failure_buffer) >= self.min_failures_for_analysis:
            # Analyze when enough failures accumulated
            should_trigger = True
            trigger_type = "threshold"
        elif self._last_improvement:
            # Check scheduled interval
            if datetime.now(UTC) - self._last_improvement > self.improvement_interval:
                should_trigger = True
                trigger_type = "scheduled"

        if should_trigger and self.enable_auto_improve:
            await self.run_improvement_session(
                agent_id=agent_id,
                trigger_type=trigger_type,
                trigger_context={
                    "mission_id": mission_id,
                    "success": success,
                    "metrics": metrics,
                },
            )

        # Background self-improvement review — fires for every mission
        # completion (subject to the skip rules inside the task).
        # Fire-and-forget per services/AGENTS.md §10: never blocks the
        # caller. The Celery task is best-effort — a failure inside
        # ``review_mission`` is logged but does NOT propagate here.
        # Per the task decision, the hook ALWAYS enqueues; the skip
        # logic (duration<10s OR turns<3) lives INSIDE the Celery
        # task, because ``on_mission_complete`` does not receive
        # duration / turn_count in its signature.
        try:
            import asyncio

            from app.tasks.background_review_tasks import review_mission

            asyncio.create_task(self._dispatch_background_review(review_mission, mission_id))
        except Exception as exc:
            logger.debug(
                "Background review dispatch unavailable for mission=%s: %s",
                mission_id,
                exc,
            )

    async def _dispatch_background_review(
        self,
        review_mission: Any,
        mission_id: str,
    ) -> None:
        """Fire-and-forget wrapper for ``review_mission.delay``.

        Lives on the same instance so the existing improvement loop
        singleton is the single owner of the dispatch. The ``.delay``
        call is sync (kombu) so this coroutine returns almost
        immediately; keeping it ``async`` lets us add a retry/audit
        layer here without churning the Celery signature.
        """
        try:
            review_mission.delay(mission_id)
        except Exception as exc:
            logger.debug(
                "Background review enqueue failed for mission=%s: %s",
                mission_id,
                exc,
            )

    async def on_failure(
        self,
        failure_context: FailureContext,
    ):
        """
        Hook called when a failure is captured.

        Adds the failure to the buffer for batch analysis.

        Args:
            failure_context: The captured failure context
        """
        self._failure_buffer.append(failure_context)

        # Keep buffer manageable
        if len(self._failure_buffer) > 1000:
            self._failure_buffer = self._failure_buffer[-500:]

        logger.debug(
            "Failure buffered: %s, buffer size: %s",
            failure_context.failure_type.value,
            len(self._failure_buffer),
        )

    async def run_improvement_session(
        self,
        agent_id: str | None = None,
        trigger_type: str = "manual",
        trigger_context: dict[str, Any] | None = None,
    ) -> ImprovementSession:
        """
        Run a complete improvement session.

        This is the main entry point for improvement analysis.

        Steps:
        1. Analyze failures to find weak areas
        2. Generate improvement strategies
        3. Select best strategy
        4. Create and run hypothesis test
        5. Apply improvement if test passes

        Args:
            agent_id: Optional agent to focus on
            trigger_type: What triggered this session
            trigger_context: Additional context

        Returns:
            ImprovementSession with results
        """
        session = ImprovementSession(
            agent_id=agent_id,
            trigger_type=trigger_type,
            trigger_context=trigger_context or {},
        )

        self._active_sessions[session.session_id] = session
        session.started_at = datetime.now(UTC)

        try:
            # Step 1: Analyze failures
            session.state = SessionState.ANALYZING
            session.weak_areas, session.failure_patterns = await self._analyze_failures(agent_id)

            if not session.weak_areas:
                session.state = SessionState.COMPLETED
                session.notes = "No weak areas identified"
                return session

            # Step 2: Generate strategies
            session.state = SessionState.GENERATING
            session.strategies = await self._generate_strategies(session.weak_areas)

            if not session.strategies:
                session.state = SessionState.COMPLETED
                session.notes = "No strategies generated"
                return session

            # Step 3: Select best strategy
            session.selected_strategy = await self._select_best_strategy(session.strategies)

            if not session.selected_strategy:
                session.state = SessionState.FAILED
                session.notes = "Failed to select strategy"
                return session

            # Step 4: Run hypothesis test
            session.state = SessionState.TESTING
            session.hypothesis_test = await self.hypothesis_tester.create_test(
                strategy=session.selected_strategy,
                agent_id=agent_id,
            )

            # Capture baseline metrics
            session.baseline_metrics = await self._get_current_metrics(agent_id)
            session.hypothesis_test.baseline_metrics = session.baseline_metrics

            # Start the test
            test_started = await self.hypothesis_tester.start_test(session.hypothesis_test)

            if not test_started:
                session.state = SessionState.FAILED
                session.notes = "Failed to start hypothesis test"
                return session

            # Wait for test to complete (simplified - in production would be async)
            # For now, we simulate immediate evaluation
            current_metrics = await self._get_current_metrics(agent_id)
            session.test_result = await self.hypothesis_tester.evaluate_test(
                session.hypothesis_test,
                current_metrics,
            )

            # Step 5: Apply improvement if test passed
            if session.test_result.recommendation == "apply":  # type: ignore[attr-defined]
                session.state = SessionState.APPLYING
                session.applied_adjustment = await self.knob_manager.apply_strategy(
                    session.selected_strategy,
                    agent_id,
                )

                if session.applied_adjustment:
                    # Record success
                    self.knowledge.record_success(
                        session.selected_strategy,
                        session.test_result.improvement_delta,  # type: ignore[attr-defined]
                    )
                    session.final_metrics = current_metrics
                    session.state = SessionState.COMPLETED
                    session.notes = f"Improvement applied: {session.test_result.improvement_delta:.2%} improvement"  # type: ignore[attr-defined]
                else:
                    session.state = SessionState.FAILED
                    session.notes = "Failed to apply improvement"
            else:
                # Test failed or inconclusive
                if session.test_result.state == HypothesisState.ROLLED_BACK:  # type: ignore[attr-defined]
                    session.notes = "Improvement rolled back due to regression"
                else:
                    session.notes = f"Improvement not applied: {session.test_result.recommendation}"  # type: ignore[attr-defined]

                self.knowledge.record_failure(session.selected_strategy)
                session.state = SessionState.COMPLETED

        except Exception as e:
            logger.error("Improvement session failed: %s", e)
            session.state = SessionState.FAILED
            session.notes = str(e)

        finally:
            session.completed_at = datetime.now(UTC)
            self._last_improvement = datetime.now(UTC)
            self.knowledge.add_session(session)

            # Clear failure buffer after analysis
            self._failure_buffer = []

        logger.info(
            "Improvement session %s completed: %s",
            session.session_id,
            session.state.value,
        )
        return session

    async def _analyze_failures(
        self,
        agent_id: str | None = None,
    ) -> tuple[list[WeakArea], dict[FailureType, int]]:
        """
        Analyze accumulated failures to identify weak areas.

        Args:
            agent_id: Optional agent to filter by

        Returns:
            (list of weak areas, failure type counts)
        """
        failures = self._failure_buffer

        if agent_id:
            failures = [f for f in failures if f.agent_id == agent_id]

        # Augment with DB-loaded failure contexts when buffer is thin
        if len(failures) < self.min_failures_for_analysis and self.db_session:
            try:
                db_contexts = await self.causal_decomposer.decompose_failures(
                    WeakArea(
                        area_type="auto",
                        success_rate=0.0,
                        total_attempts=0,
                        failure_count=0,
                    ),
                    failure_contexts=None,
                    db_session=self.db_session,
                )
                if db_contexts:
                    failures = failures + db_contexts
                    logger.info(
                        "Augmented failure buffer with %d contexts from DB (total: %d)",
                        len(db_contexts),
                        len(failures),
                    )
            except Exception as e:
                logger.warning("Failed to load failure contexts from DB: %s", e)

        if not failures:
            return [], {}

        # Count failure types
        failure_counts: dict[FailureType, int] = {}
        for f in failures:
            failure_counts[f.failure_type] = failure_counts.get(f.failure_type, 0) + 1

        # Use causal decomposer to identify weak areas
        weak_areas = self.causal_decomposer.analyze_failure_patterns(failures)  # type: ignore[attr-defined]

        return weak_areas, failure_counts

    async def _generate_strategies(
        self,
        weak_areas: list[WeakArea],
    ) -> list[ImprovementStrategy]:
        """
        Generate improvement strategies for weak areas.

        Args:
            weak_areas: Identified weak areas

        Returns:
            List of potential strategies
        """
        strategies = []

        for area in weak_areas:
            area_strategies = self.causal_decomposer.generate_strategies(area)  # type: ignore[attr-defined]
            strategies.extend(area_strategies)

        # Sort by confidence and risk
        strategies.sort(key=lambda s: (s.confidence, -s.risk_level.value), reverse=True)

        return strategies[:5]  # Return top 5 strategies

    async def _select_best_strategy(
        self,
        strategies: list[ImprovementStrategy],
    ) -> ImprovementStrategy | None:
        """
        Select the best strategy from candidates.

        Selection criteria:
        1. Historical effectiveness
        2. Confidence score
        3. Risk level (prefer lower risk)
        4. Oscillation avoidance

        Args:
            strategies: Candidate strategies

        Returns:
            Best strategy or None
        """
        if not strategies:
            return None

        best_strategy = None
        best_score = -1

        for strategy in strategies:
            # Base score from confidence
            score = strategy.confidence

            # Boost if historically effective
            avg_improvement = self.knowledge.get_average_improvement(strategy.knob)
            score += avg_improvement * 0.5

            # Penalty for high risk
            if strategy.risk_level == RiskLevel.HIGH:
                score *= 0.5
            elif strategy.risk_level == RiskLevel.MEDIUM:
                score *= 0.8

            # Check oscillation risk
            if strategy.knob in self.knowledge.oscillation_patterns:
                if strategy.knob_value in self.knowledge.oscillation_patterns[strategy.knob]:
                    score *= 0.3  # Heavy penalty for oscillation

            if score > best_score:
                best_score = score  # type: ignore[assignment]
                best_strategy = strategy

        return best_strategy

    async def _get_current_metrics(
        self,
        agent_id: str | None = None,
    ) -> dict[str, float]:
        """
        Get current performance metrics from the database.

        Queries real mission execution data for success rates,
        latency, and error rates. Falls back to sensible defaults
        if no data is available.

        Args:
            agent_id: Optional agent to filter by

        Returns:
            Dict of metric name -> value
        """
        try:
            from sqlalchemy import case, func, select

            from app.models.mission_models import Mission

            # Build base query for recent missions
            base_query = select(
                func.count().label("total"),
                func.sum(case((Mission.status == "completed", 1), else_=0)).label("completed"),
                func.sum(case((Mission.status == "failed", 1), else_=0)).label("failed"),
                func.avg(func.extract("epoch", Mission.completed_at - Mission.started_at)).label("avg_duration"),
            )

            if agent_id:
                try:
                    user_id_int = int(agent_id)
                    base_query = base_query.where(Mission.user_id == user_id_int)
                except (ValueError, TypeError):
                    logger.warning(
                        "agent_id %s is not a valid integer user ID, querying all missions",
                        agent_id,
                    )

            result = await self.db_session.execute(base_query)
            row = result.one_or_none()

            # Query tool analytics for tool success rate
            try:
                from app.models.tool_models import ToolAnalytics

                tool_query = select(
                    func.count().label("total_tool_calls"),
                    func.sum(case((ToolAnalytics.success == True, 1), else_=0)).label("successful_tool_calls"),
                )

                if agent_id:
                    try:
                        user_id_str = str(int(agent_id))
                        tool_query = tool_query.where(ToolAnalytics.user_id == user_id_str)
                    except (ValueError, TypeError):
                        pass

                tool_result = await self.db_session.execute(tool_query)
                tool_row = tool_result.one_or_none()

                if tool_row and tool_row.total_tool_calls and tool_row.total_tool_calls > 0:
                    tool_success_rate = (tool_row.successful_tool_calls or 0) / tool_row.total_tool_calls
                else:
                    tool_success_rate = 0.85  # default when no tool data available
            except Exception as tool_e:
                logger.warning(
                    "Failed to query tool analytics: %s, using default tool_success_rate",
                    tool_e,
                )
                tool_success_rate = 0.85

            if row and row.total and row.total > 0:
                total = row.total
                success_rate = (row.completed or 0) / total
                error_rate = (row.failed or 0) / total
                avg_duration_ms = (row.avg_duration or 0) * 1000

                return {
                    "success_rate": round(success_rate, 3),
                    "latency_p95": round(avg_duration_ms * 1.5, 1),  # p95 estimate
                    "error_rate": round(error_rate, 3),
                    "tool_success_rate": round(tool_success_rate, 3),
                    "total_missions": total,
                }

        except Exception as e:
            logger.warning("Failed to query mission metrics: %s, using defaults", e)

        # Fallback to sensible defaults when no data is available or query fails
        return {
            "success_rate": 0.85,
            "latency_p95": 2500.0,
            "error_rate": 0.05,
            "tool_success_rate": 0.85,
        }

    def get_session(self, session_id: str) -> ImprovementSession | None:
        """Get a session by ID"""
        return self._active_sessions.get(session_id)

    def get_recent_sessions(self, limit: int = 10) -> list[ImprovementSession]:
        """Get recent improvement sessions"""
        return self.knowledge.recent_sessions[-limit:]

    def get_knowledge_summary(self) -> dict[str, Any]:
        """Get summary of accumulated knowledge"""
        return {
            "strategy_effectiveness": {st.value: data for st, data in self.knowledge.strategy_effectiveness.items()},
            "knob_effectiveness": {kt.value: data for kt, data in self.knowledge.knob_effectiveness.items()},
            "total_sessions": len(self.knowledge.recent_sessions),
            "pending_failures": len(self._failure_buffer),
        }


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_improvement_loop: ImprovementLoopV2 | None = None


def get_improvement_loop(
    db_session=None,
    **kwargs,
) -> ImprovementLoopV2:
    """Get or create the improvement loop singleton"""
    global _improvement_loop

    if _improvement_loop is None:
        _improvement_loop = ImprovementLoopV2(db_session=db_session, **kwargs)

    return _improvement_loop


async def initialize_improvement_loop(
    db_session,
    enable_auto_improve: bool = True,
) -> ImprovementLoopV2:
    """
    Initialize the improvement loop system.

    This should be called during application startup.

    Args:
        db_session: Database session
        enable_auto_improve: Whether to enable automatic improvement

    Returns:
        Initialized ImprovementLoopV2 instance
    """
    loop = get_improvement_loop(
        db_session=db_session,
        enable_auto_improve=enable_auto_improve,
    )

    # Initialize default knobs
    await initialize_default_knobs(db_session)

    logger.info("Improvement loop v2 initialized")
    return loop


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "ImprovementKnowledge",
    # Classes
    "ImprovementLoopV2",
    # Dataclasses
    "ImprovementSession",
    # Enums
    "SessionState",
    # Functions
    "get_improvement_loop",
    "initialize_improvement_loop",
]
