"""
Proactive Improvement Scheduler for Autonomous Self-Improvement System.

This module schedules improvements before failures occur based on
predictions from temporal analysis, enabling proactive optimization.

Phase 6F of the Autonomous Self-Improvement Architecture.
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

# Import from previous phases
import contextlib

from .causal_decomposer import StrategyType
from .failure_types import FailureSeverity, FailureType
from .knob_manager import KnobManager
from .temporal_analyzer import Prediction, TemporalAnalyzer, TemporalCycle

if TYPE_CHECKING:
    from collections.abc import Callable

# ============================================================================
# ENUMS AND DATA CLASSES
# ============================================================================


class SchedulePriority(str, Enum):
    """Priority of scheduled actions."""

    CRITICAL = "critical"  # Must execute immediately
    HIGH = "high"  # Execute within next window
    MEDIUM = "medium"  # Execute during low-traffic
    LOW = "low"  # Execute when convenient
    BACKGROUND = "background"  # Best effort


class ScheduleStatus(str, Enum):
    """Status of a scheduled action."""

    PENDING = "pending"  # Waiting for execution time
    QUEUED = "queued"  # Ready to execute
    RUNNING = "running"  # Currently executing
    COMPLETED = "completed"  # Successfully completed
    FAILED = "failed"  # Execution failed
    CANCELLED = "cancelled"  # Manually cancelled
    SKIPPED = "skipped"  # Skipped due to conditions


class ActionType(str, Enum):
    """Types of proactive actions."""

    PREVENTIVE = "preventive"  # Prevent predicted failure
    OPTIMIZATION = "optimization"  # Proactive optimization
    CONSOLIDATION = "consolidation"  # Knowledge consolidation
    EVOLUTION = "evolution"  # Strategy evolution
    CLEANUP = "cleanup"  # Resource cleanup
    PREWARM = "prewarm"  # Pre-warm resources


@dataclass
class ScheduledAction:
    """A scheduled proactive action."""

    action_id: str
    action_type: ActionType
    priority: SchedulePriority

    # Scheduling
    scheduled_time: datetime
    execution_window: timedelta = field(default_factory=lambda: timedelta(minutes=30))

    # Action details
    failure_type: FailureType | None = None
    strategy_type: StrategyType | None = None
    knob_adjustments: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)

    # Source
    prediction_id: str | None = None
    cycle_id: str | None = None
    reason: str = ""

    # Status
    status: ScheduleStatus = ScheduleStatus.PENDING
    attempts: int = 0
    max_attempts: int = 3

    # Execution
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = None

    # Conditions
    conditions: dict[str, Any] = field(default_factory=dict)

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    agent_id: str | None = None

    def is_ready(self) -> bool:
        """Check if action is ready to execute."""
        now = datetime.now(UTC)
        window_start = self.scheduled_time
        window_end = self.scheduled_time + self.execution_window

        return (
            self.status == ScheduleStatus.PENDING and window_start <= now <= window_end
        )

    def is_expired(self) -> bool:
        """Check if action has expired."""
        now = datetime.now(UTC)
        return now > self.scheduled_time + self.execution_window

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "action_id": self.action_id,
            "action_type": self.action_type.value,
            "priority": self.priority.value,
            "scheduled_time": self.scheduled_time.isoformat(),
            "execution_window_seconds": self.execution_window.total_seconds(),
            "failure_type": self.failure_type.value if self.failure_type else None,
            "strategy_type": self.strategy_type.value if self.strategy_type else None,
            "knob_adjustments": self.knob_adjustments,
            "parameters": self.parameters,
            "prediction_id": self.prediction_id,
            "cycle_id": self.cycle_id,
            "reason": self.reason,
            "status": self.status.value,
            "attempts": self.attempts,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "result": self.result,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
            "agent_id": self.agent_id,
        }


@dataclass
class SchedulerConfig:
    """Configuration for the proactive scheduler."""

    # Execution intervals
    check_interval_seconds: int = 60
    consolidation_interval_hours: int = 6
    evolution_interval_hours: int = 24
    cleanup_interval_hours: int = 12

    # Limits
    max_concurrent_actions: int = 5
    max_pending_actions: int = 100
    action_timeout_seconds: int = 300

    # Priorities
    low_traffic_hours: list[int] = field(default_factory=lambda: [2, 3, 4, 5])  # 2-5 AM
    high_priority_window_minutes: int = 30

    # Thresholds
    min_prediction_confidence: float = 0.6
    min_cycle_confidence: float = 0.7


# ============================================================================
# PROACTIVE SCHEDULER
# ============================================================================


class ProactiveScheduler:
    """
    Schedules and executes proactive improvements.

    This class uses predictions from temporal analysis to schedule
    preventive actions before failures occur.
    """

    def __init__(
        self,
        temporal_analyzer: TemporalAnalyzer | None = None,
        knob_manager: KnobManager | None = None,
        knowledge_graph=None,
        strategy_evolver=None,
        config: SchedulerConfig | None = None,
    ):
        """
        Initialize the proactive scheduler.

        Args:
            temporal_analyzer: Optional temporal analyzer for predictions
            knob_manager: Optional knob manager for adjustments
            knowledge_graph: Optional knowledge graph for consolidation
            strategy_evolver: Optional strategy evolver for evolution
            config: Optional scheduler configuration
        """
        self.temporal_analyzer = temporal_analyzer
        self.knob_manager = knob_manager
        self.knowledge_graph = knowledge_graph
        self.strategy_evolver = strategy_evolver
        self.config = config or SchedulerConfig()

        # Action storage
        self._scheduled_actions: dict[str, ScheduledAction] = {}
        self._pending_queue: list[str] = []
        self._running_actions: set[str] = set()

        # Execution tracking
        self._execution_history: list[ScheduledAction] = []
        self._action_handlers: dict[ActionType, Callable] = {}

        # Background task
        self._running = False
        self._scheduler_task: asyncio.Task | None = None

        # Register default handlers
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register default action handlers."""
        self._action_handlers = {
            ActionType.PREVENTIVE: self._handle_preventive_action,
            ActionType.OPTIMIZATION: self._handle_optimization_action,
            ActionType.CONSOLIDATION: self._handle_consolidation_action,
            ActionType.EVOLUTION: self._handle_evolution_action,
            ActionType.CLEANUP: self._handle_cleanup_action,
            ActionType.PREWARM: self._handle_prewarm_action,
        }

    # ========================================================================
    # SCHEDULING
    # ========================================================================

    async def schedule_preventive_action(
        self,
        prediction: Prediction,
        lead_time_minutes: int = 30,
    ) -> ScheduledAction:
        """
        Schedule a preventive action based on a prediction.

        Args:
            prediction: The prediction to act on
            lead_time_minutes: Minutes before predicted failure

        Returns:
            The scheduled action
        """
        # Calculate scheduled time
        scheduled_time = prediction.predicted_time - timedelta(
            minutes=lead_time_minutes
        )

        # Don't schedule in the past
        if scheduled_time < datetime.now(UTC):
            scheduled_time = datetime.now(UTC) + timedelta(minutes=5)

        # Determine priority based on severity and confidence
        if prediction.predicted_severity == FailureSeverity.CRITICAL:
            priority = SchedulePriority.CRITICAL
        elif prediction.confidence > 0.8:
            priority = SchedulePriority.HIGH
        else:
            priority = SchedulePriority.MEDIUM

        # Create action
        action_id = f"preventive_{prediction.prediction_id}"

        action = ScheduledAction(
            action_id=action_id,
            action_type=ActionType.PREVENTIVE,
            priority=priority,
            scheduled_time=scheduled_time,
            failure_type=prediction.failure_type,
            prediction_id=prediction.prediction_id,
            cycle_id=prediction.based_on_pattern,
            reason=f"Preventive action for predicted {prediction.failure_type.value}",
            parameters={
                "recommended_actions": prediction.recommended_actions,
            },
            agent_id=prediction.agent_id,
        )

        # Store action
        self._scheduled_actions[action_id] = action
        self._pending_queue.append(action_id)

        logger.info(
            "Scheduled preventive action %s for %s at %s",
            action_id,
            prediction.failure_type.value,
            scheduled_time.isoformat(),
        )

        return action

    async def schedule_knowledge_consolidation(
        self,
        scheduled_time: datetime | None = None,
    ) -> ScheduledAction:
        """
        Schedule a knowledge consolidation task.

        Args:
            scheduled_time: Optional specific time, defaults to next low-traffic

        Returns:
            The scheduled action
        """
        if not scheduled_time:
            # Schedule for next low-traffic period
            now = datetime.now(UTC)
            if now.hour in self.config.low_traffic_hours:
                scheduled_time = now + timedelta(minutes=30)
            else:
                # Find next low-traffic hour
                hours_ahead = min(
                    (h - now.hour) % 24 for h in self.config.low_traffic_hours
                )
                scheduled_time = now.replace(
                    minute=0, second=0, microsecond=0
                ) + timedelta(hours=hours_ahead)

        action_id = f"consolidation_{scheduled_time.strftime('%Y%m%d_%H%M')}"

        action = ScheduledAction(
            action_id=action_id,
            action_type=ActionType.CONSOLIDATION,
            priority=SchedulePriority.LOW,
            scheduled_time=scheduled_time,
            execution_window=timedelta(hours=2),
            reason="Periodic knowledge graph consolidation",
        )

        self._scheduled_actions[action_id] = action
        self._pending_queue.append(action_id)

        return action

    async def schedule_strategy_evolution(
        self,
        scheduled_time: datetime | None = None,
    ) -> ScheduledAction:
        """
        Schedule a strategy evolution task.

        Args:
            scheduled_time: Optional specific time

        Returns:
            The scheduled action
        """
        if not scheduled_time:
            # Schedule for next low-traffic period
            now = datetime.now(UTC)
            hours_ahead = min(
                (h - now.hour) % 24 for h in self.config.low_traffic_hours
            )
            scheduled_time = now.replace(minute=0, second=0, microsecond=0) + timedelta(
                hours=hours_ahead
            )

        action_id = f"evolution_{scheduled_time.strftime('%Y%m%d_%H%M')}"

        action = ScheduledAction(
            action_id=action_id,
            action_type=ActionType.EVOLUTION,
            priority=SchedulePriority.LOW,
            scheduled_time=scheduled_time,
            execution_window=timedelta(hours=1),
            reason="Periodic strategy evolution cycle",
        )

        self._scheduled_actions[action_id] = action
        self._pending_queue.append(action_id)

        return action

    async def schedule_prewarm(
        self,
        cycle: TemporalCycle,
        lead_time_minutes: int = 15,
    ) -> ScheduledAction:
        """
        Schedule a resource pre-warming action.

        Args:
            cycle: The temporal cycle to pre-warm for
            lead_time_minutes: Minutes before predicted spike

        Returns:
            The scheduled action
        """
        if not cycle.next_predicted:
            raise ValueError("Cycle has no next predicted time")

        scheduled_time = cycle.next_predicted - timedelta(minutes=lead_time_minutes)

        if scheduled_time < datetime.now(UTC):
            scheduled_time = datetime.now(UTC) + timedelta(minutes=5)

        action_id = f"prewarm_{cycle.cycle_id}_{scheduled_time.strftime('%Y%m%d_%H%M')}"

        action = ScheduledAction(
            action_id=action_id,
            action_type=ActionType.PREWARM,
            priority=SchedulePriority.HIGH,
            scheduled_time=scheduled_time,
            failure_type=cycle.failure_type,
            cycle_id=cycle.cycle_id,
            reason=f"Pre-warm resources for predicted {cycle.failure_type.value} spike",
            parameters={
                "expected_load": cycle.avg_failures_per_cycle,
                "hour": cycle.hour,
            },
            agent_id=cycle.agent_id,
        )

        self._scheduled_actions[action_id] = action
        self._pending_queue.append(action_id)

        return action

    # ========================================================================
    # EXECUTION
    # ========================================================================

    async def start(self) -> None:
        """Start the scheduler loop."""
        if self._running:
            return

        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())

        logger.info("Proactive scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False

        if self._scheduler_task:
            self._scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._scheduler_task

        logger.info("Proactive scheduler stopped")

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                # Check for ready actions
                await self._process_ready_actions()

                # Clean up expired actions
                await self._cleanup_expired_actions()

                # Generate new predictions and schedule actions
                await self._generate_proactive_actions()

                # Wait for next check
                await asyncio.sleep(self.config.check_interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Scheduler loop error: %s", e)
                await asyncio.sleep(60)

    async def _process_ready_actions(self) -> None:
        """Process actions that are ready to execute."""
        ready_actions = []

        for action_id in list(self._pending_queue):
            action = self._scheduled_actions.get(action_id)
            if not action:
                self._pending_queue.remove(action_id)
                continue

            if action.is_ready():
                ready_actions.append(action)

        # Sort by priority
        priority_order = {
            SchedulePriority.CRITICAL: 0,
            SchedulePriority.HIGH: 1,
            SchedulePriority.MEDIUM: 2,
            SchedulePriority.LOW: 3,
            SchedulePriority.BACKGROUND: 4,
        }
        ready_actions.sort(key=lambda a: priority_order.get(a.priority, 5))

        # Execute up to max concurrent
        available_slots = self.config.max_concurrent_actions - len(
            self._running_actions
        )

        for action in ready_actions[:available_slots]:
            asyncio.create_task(self._execute_action(action))

    async def _execute_action(self, action: ScheduledAction) -> None:
        """Execute a scheduled action."""
        action.status = ScheduleStatus.RUNNING
        action.started_at = datetime.now(UTC)
        action.attempts += 1

        self._running_actions.add(action.action_id)
        self._pending_queue.remove(action.action_id)

        logger.info(
            "Executing action %s (attempt %s)", action.action_id, action.attempts
        )

        try:
            # Get handler
            handler = self._action_handlers.get(action.action_type)

            if not handler:
                raise ValueError(f"No handler for action type {action.action_type}")

            # Execute with timeout
            result = await asyncio.wait_for(
                handler(action),
                timeout=self.config.action_timeout_seconds,
            )

            action.result = result
            action.status = ScheduleStatus.COMPLETED
            action.completed_at = datetime.now(UTC)

            logger.info("Action %s completed successfully", action.action_id)

        except TimeoutError:
            action.error_message = "Action timed out"
            action.status = ScheduleStatus.FAILED
            logger.error("Action %s timed out", action.action_id)

        except Exception as e:
            action.error_message = str(e)

            if action.attempts < action.max_attempts:
                # Retry
                action.status = ScheduleStatus.PENDING
                self._pending_queue.append(action.action_id)
                logger.warning("Action %s failed, will retry: %s", action.action_id, e)
            else:
                action.status = ScheduleStatus.FAILED
                logger.error(
                    "Action %s failed after %s attempts: %s",
                    action.action_id,
                    action.attempts,
                    e,
                )

        finally:
            self._running_actions.discard(action.action_id)
            self._execution_history.append(action)

    async def _cleanup_expired_actions(self) -> None:
        """Remove expired actions."""
        expired = []

        for action_id in list(self._pending_queue):
            action = self._scheduled_actions.get(action_id)
            if action and action.is_expired():
                expired.append(action_id)

        for action_id in expired:
            action = self._scheduled_actions.get(action_id)
            if action:
                action.status = ScheduleStatus.SKIPPED
                action.error_message = "Action expired"
                self._execution_history.append(action)

            self._pending_queue.remove(action_id)
            logger.debug("Skipped expired action %s", action_id)

    async def _generate_proactive_actions(self) -> None:
        """Generate new proactive actions from predictions."""
        if not self.temporal_analyzer:
            return

        # Get predictions
        predictions = await self.temporal_analyzer.predict_failures(horizon_hours=2)

        for prediction in predictions:
            if prediction.confidence < self.config.min_prediction_confidence:
                continue

            # Check if already scheduled
            action_id = f"preventive_{prediction.prediction_id}"
            if action_id in self._scheduled_actions:
                continue

            # Schedule preventive action
            await self.schedule_preventive_action(prediction)

    # ========================================================================
    # ACTION HANDLERS
    # ========================================================================

    async def _handle_preventive_action(
        self,
        action: ScheduledAction,
    ) -> dict[str, Any]:
        """Handle a preventive action."""
        result = {"actions_taken": []}

        if not action.failure_type:
            return result

        # Apply preventive measures based on failure type
        preventive_measures = {
            FailureType.RATE_LIMITED: [
                ("reduce_concurrency", 0.5),
                ("enable_queuing", True),
            ],
            FailureType.TOOL_TIMEOUT: [
                ("increase_timeout", 1.5),
                ("enable_early_cancel", True),
            ],
            FailureType.MEMORY_EXHAUSTION: [
                ("reduce_cache_size", 0.7),
                ("trigger_gc", True),
            ],
            FailureType.LLM_TIMEOUT: [
                ("reduce_prompt_size", 0.8),
                ("enable_streaming", True),
            ],
        }

        measures = preventive_measures.get(action.failure_type, [])

        for measure_name, measure_value in measures:
            if self.knob_manager:
                try:
                    await self.knob_manager.set_knob(
                        knob_name=measure_name,
                        value=measure_value,
                        reason=f"Preventive for {action.failure_type.value}",
                    )
                    result["actions_taken"].append(measure_name)
                except Exception as e:
                    logger.warning("Failed to apply %s: %s", measure_name, e)

        return result

    async def _handle_optimization_action(
        self,
        action: ScheduledAction,
    ) -> dict[str, Any]:
        """Handle an optimization action."""
        result = {"optimizations": []}

        # Apply knob adjustments if specified
        for knob_name, knob_value in action.knob_adjustments.items():
            if self.knob_manager:
                try:
                    await self.knob_manager.set_knob(
                        knob_name=knob_name,
                        value=knob_value,
                        reason=action.reason,
                    )
                    result["optimizations"].append(knob_name)
                except Exception as e:
                    logger.warning("Failed to set %s: %s", knob_name, e)

        return result

    async def _handle_consolidation_action(
        self,
        action: ScheduledAction,
    ) -> dict[str, Any]:
        """Handle a knowledge consolidation action."""
        result = {
            "nodes_consolidated": 0,
            "edges_consolidated": 0,
            "patterns_merged": 0,
        }

        if self.knowledge_graph:
            # Prune low-weight edges
            stats = self.knowledge_graph.get_statistics()
            result["nodes_before"] = stats.get("total_nodes", 0)
            result["edges_before"] = stats.get("total_edges", 0)

            # Save to database
            await self.knowledge_graph.save_to_database()

            result["saved"] = True

        return result

    async def _handle_evolution_action(
        self,
        action: ScheduledAction,
    ) -> dict[str, Any]:
        """Handle a strategy evolution action."""
        result = {
            "strategies_evolved": 0,
            "new_variants": 0,
            "promotions": 0,
            "deprecations": 0,
        }

        if self.strategy_evolver:
            evolution_results = await self.strategy_evolver.run_evolution_cycle()

            for ev_result in evolution_results:
                if ev_result.action.value == "mutate":
                    result["new_variants"] += 1
                elif ev_result.action.value == "promote":
                    result["promotions"] += 1
                elif ev_result.action.value == "deprecate":
                    result["deprecations"] += 1

            result["strategies_evolved"] = len(evolution_results)

        return result

    async def _handle_cleanup_action(
        self,
        action: ScheduledAction,
    ) -> dict[str, Any]:
        """Handle a cleanup action."""
        result = {
            "cleaned_items": 0,
        }

        # Clean up old execution history
        cutoff = datetime.now(UTC) - timedelta(days=7)
        old_count = len(self._execution_history)

        self._execution_history = [
            a for a in self._execution_history if a.created_at >= cutoff
        ]

        result["cleaned_items"] = old_count - len(self._execution_history)

        return result

    async def _handle_prewarm_action(
        self,
        action: ScheduledAction,
    ) -> dict[str, Any]:
        """Handle a pre-warm action."""
        result = {
            "resources_prewarmed": [],
        }

        # Pre-warm based on failure type
        if action.failure_type == FailureType.RATE_LIMITED:
            # Pre-warm rate limit tokens
            result["resources_prewarmed"].append("rate_limit_tokens")

        elif action.failure_type == FailureType.TOOL_TIMEOUT:
            # Pre-cache common results
            result["resources_prewarmed"].append("tool_cache")

        elif action.failure_type == FailureType.MEMORY_EXHAUSTION:
            # Trigger early GC
            result["resources_prewarmed"].append("memory_pools")

        return result

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    def get_action(self, action_id: str) -> ScheduledAction | None:
        """Get an action by ID."""
        return self._scheduled_actions.get(action_id)

    def get_pending_actions(
        self,
        limit: int = 50,
    ) -> list[ScheduledAction]:
        """Get pending actions."""
        actions = [
            self._scheduled_actions[aid]
            for aid in self._pending_queue
            if aid in self._scheduled_actions
        ]
        return actions[:limit]

    def get_running_actions(self) -> list[ScheduledAction]:
        """Get currently running actions."""
        return [
            self._scheduled_actions[aid]
            for aid in self._running_actions
            if aid in self._scheduled_actions
        ]

    async def cancel_action(self, action_id: str) -> bool:
        """Cancel a pending action."""
        action = self._scheduled_actions.get(action_id)
        if not action:
            return False

        if action.status not in (ScheduleStatus.PENDING, ScheduleStatus.QUEUED):
            return False

        action.status = ScheduleStatus.CANCELLED

        if action_id in self._pending_queue:
            self._pending_queue.remove(action_id)

        return True

    def get_statistics(self) -> dict[str, Any]:
        """Get scheduler statistics."""
        status_counts = defaultdict(int)
        for action in self._execution_history:
            status_counts[action.status.value] += 1

        return {
            "running": self._running,
            "pending_actions": len(self._pending_queue),
            "running_actions": len(self._running_actions),
            "total_scheduled": len(self._scheduled_actions),
            "execution_history_size": len(self._execution_history),
            "by_status": dict(status_counts),
        }


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

_proactive_scheduler: ProactiveScheduler | None = None


def get_proactive_scheduler() -> ProactiveScheduler:
    """Get the singleton proactive scheduler instance."""
    global _proactive_scheduler
    if _proactive_scheduler is None:
        _proactive_scheduler = ProactiveScheduler()
    return _proactive_scheduler


def initialize_proactive_scheduler(
    temporal_analyzer: TemporalAnalyzer | None = None,
    knob_manager: KnobManager | None = None,
    knowledge_graph=None,
    strategy_evolver=None,
    config: SchedulerConfig | None = None,
) -> ProactiveScheduler:
    """Initialize the proactive scheduler."""
    global _proactive_scheduler
    _proactive_scheduler = ProactiveScheduler(
        temporal_analyzer=temporal_analyzer,
        knob_manager=knob_manager,
        knowledge_graph=knowledge_graph,
        strategy_evolver=strategy_evolver,
        config=config,
    )
    return _proactive_scheduler
