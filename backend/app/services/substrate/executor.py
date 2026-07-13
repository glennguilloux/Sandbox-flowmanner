# mypy: disable-error-code=attr-defined
"""UnifiedExecutor — single durable executor (H5.1). GA release.

The ONLY entry point for workflow execution.  No subclasses.
All 7 old executors become strategies dispatched from this class.

Every execution through UnifiedExecutor satisfies the 4 guarantees:
1. Durable — every state transition emits a substrate event
2. Type-checked — input/output validated via PydanticAdapter
3. Capability-bounded — tool calls require CapabilityToken
4. Bounded — BudgetEnforcer wraps every LLM call
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from opentelemetry import trace

from app.config import settings
from app.models.capability_models import Budget, BudgetExhausted
from app.models.substrate_models import SubstrateEventType
from app.services.substrate.event_log import EventLog, get_event_log
from app.services.substrate.hitl_pause import HITLPaused
from app.services.substrate.replay_engine import ReplayEngine, get_replay_engine
from app.services.substrate.strategies.base import (
    ExecutionStrategy,
    get_ws_manager,
)
from app.services.substrate.workflow_models import (
    StrategyResult,
    Workflow,
    WorkflowNode,
    WorkflowType,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def _provider_from_model(model_id: str) -> str | None:
    """Extract the provider prefix from a model ID (e.g. ``deepseek/v4`` → ``deepseek``)."""
    if "/" not in model_id:
        return None
    prefix = model_id.split("/", 1)[0].lower()
    # Normalize common aliases
    _ALIASES = {"openai_compatible": "openai"}
    return _ALIASES.get(prefix, prefix)


class LeaseLostError(Exception):
    """Raised when the heartbeat detects a stolen lease mid-execution."""

    pass


class UnifiedExecutor:
    """The single durable executor. No subclasses.

    Usage:
        executor = UnifiedExecutor()
        result = await executor.execute(
            db=session,
            workflow=workflow,
            run_id=str(uuid4()),
        )
    """

    def __init__(
        self,
        event_log: EventLog | None = None,
        replay_engine: ReplayEngine | None = None,
    ) -> None:
        self.event_log = event_log or get_event_log()
        self.replay_engine = replay_engine or get_replay_engine()
        self.ws_manager = get_ws_manager()
        self._abort_signals: dict[str, asyncio.Event] = {}
        self._strategies: dict[WorkflowType, ExecutionStrategy] = {}
        self._strategies_loaded = False
        # Q1-A: Lease manager (lazily initialized per execute() call)
        self._lease_manager: Any = None  # LeaseManager | None

    def _load_strategies(self) -> None:
        """Lazy-load all strategy classes on first use."""
        if self._strategies_loaded:
            return

        from app.services.substrate.strategies.dag import DAGStrategy
        from app.services.substrate.strategies.graph import GraphStrategy
        from app.services.substrate.strategies.langgraph import LangGraphStrategy
        from app.services.substrate.strategies.meta import MetaStrategy
        from app.services.substrate.strategies.pipeline import PipelineStrategy
        from app.services.substrate.strategies.solo import SoloStrategy
        from app.services.substrate.strategies.swarm import SwarmStrategy

        self._strategies = {
            WorkflowType.SOLO: SoloStrategy(),
            WorkflowType.DAG: DAGStrategy(),
            WorkflowType.GRAPH: GraphStrategy(),
            WorkflowType.SWARM: SwarmStrategy(),
            WorkflowType.PIPELINE: PipelineStrategy(),
            WorkflowType.META: MetaStrategy(),
            WorkflowType.LANGGRAPH: LangGraphStrategy(),
        }
        self._strategies_loaded = True
        logger.info("UnifiedExecutor: loaded %d strategies", len(self._strategies))

    def _get_strategy(self, workflow_type: WorkflowType) -> ExecutionStrategy:
        """Get the strategy for a workflow type."""
        self._load_strategies()
        strategy = self._strategies.get(workflow_type)
        if strategy is None:
            raise ValueError(f"No strategy registered for workflow type: {workflow_type}")
        # Gate deprecated strategies (0% success with 27B model per profiling)
        if getattr(strategy, "DEPRECATED", False):
            from app.config import settings

            if not settings.STRATEGY_ALLOW_DEPRECATED:
                raise ValueError(
                    f"Strategy '{workflow_type.value}' is deprecated and unavailable. "
                    f"Choose a non-deprecated strategy, or set STRATEGY_ALLOW_DEPRECATED=true in .env."
                )
        # Gate experimental strategies behind STRATEGY_EXPERIMENTAL env var
        if getattr(strategy, "EXPERIMENTAL", False):
            from app.config import settings

            if not settings.STRATEGY_EXPERIMENTAL:
                raise ValueError(
                    f"Strategy '{workflow_type.value}' is experimental and disabled. "
                    f"Set STRATEGY_EXPERIMENTAL=true in .env to enable it."
                )
        return strategy

    # ── Public API ──────────────────────────────────────────────────

    @asynccontextmanager
    async def _lease_context(self, run_id: str, db: AsyncSession, workflow: Workflow, span: Any):
        """Context manager that claims a lease at entry and releases at exit.

        On entry: claims a lease and spawns a heartbeat.  If the claim fails
        because another worker holds a valid lease, sets
        ``self._lease_already_running`` so the caller can return early.

        On exit: cancels the heartbeat and releases the lease.

        All lease operations are wrapped in try/except so that a failure
        in the lease layer does not crash the executor (graceful degradation).
        """
        self._lease_manager = None
        self._lease_already_running = None  # type: ignore[assignment]
        lease_claimed = False
        heartbeat_task: asyncio.Task | None = None
        heartbeat_stop: asyncio.Event | None = None
        lm = None

        if not settings.FLOWMANNER_LEASE_ENABLED:
            yield
            return

        try:
            from app.services.substrate.lease_manager import LeaseManager

            lm = LeaseManager(event_log=self.event_log)
            self._lease_manager = lm

            try:
                claimed = await lm.claim(run_id, db)
            except Exception as e:
                # Lease claim failure must never crash the executor.
                # Proceed without lease — the 4 guarantees are unchanged.
                logger.warning("Lease claim failed for run %s, proceeding without lease: %s", run_id, e)
                yield
                return

            if not claimed:
                # Another worker holds a valid lease — don't re-execute.
                existing = await lm.get_existing_lease(db, run_id)
                if existing is not None:
                    logger.info(
                        "Run %s already leased by %s — returning existing state",
                        run_id,
                        existing.worker_id,
                    )
                    state = await self.replay_engine.rebuild_state(db, run_id)
                    self._lease_already_running = StrategyResult(
                        success=False,
                        status="already_running",
                        error=f"Run already in progress on worker {existing.worker_id}",
                        completed_nodes=list(state.completed_tasks) if state else [],
                        failed_nodes=list(state.failed_tasks) if state else [],
                        total_tokens=state.total_tokens if state else 0,
                        total_cost_usd=state.total_cost_usd if state else 0.0,
                    )
                    yield
                    return
                # Claim failed but no valid lease exists — retry (rare race).
                claimed = await lm.claim(run_id, db)
                if not claimed:
                    logger.warning("Lease claim failed twice for run %s", run_id)
                    self._lease_already_running = StrategyResult(
                        success=False,
                        status="lease_contention",
                        error="Failed to acquire lease after retry",
                    )
                    yield
                    return

            lease_claimed = True

            # Emit lease.claimed event
            try:
                await self.event_log.append(
                    db,
                    run_id,
                    [
                        {
                            "type": SubstrateEventType.LEASE_CLAIMED,
                            "payload": {
                                "worker_id": lm.worker_id,
                                "run_id": run_id,
                                "ttl_seconds": lm._ttl_seconds,
                            },
                            "actor": "lease_manager",
                            "mission_id": workflow.id,
                        }
                    ],
                )
            except Exception as e:
                logger.debug("Lease claimed event skipped: %s", e)

            # Spawn heartbeat
            heartbeat_stop = asyncio.Event()
            heartbeat_task = asyncio.create_task(lm.heartbeat_loop(db, heartbeat_stop))

            yield

        finally:
            # Cancel heartbeat if it was started
            if heartbeat_task is not None and heartbeat_stop is not None:
                heartbeat_stop.set()
                try:
                    await asyncio.wait_for(heartbeat_task, timeout=5.0)
                except (TimeoutError, asyncio.CancelledError):
                    heartbeat_task.cancel()

            # Release lease only if we actually claimed one
            if lease_claimed and lm is not None:
                reason = "completed"
                if lm.lease_lost:
                    reason = "lost"

                await lm.release(db, reason=reason)

                # Emit lease.released event
                try:
                    await self.event_log.append(
                        db,
                        run_id,
                        [
                            {
                                "type": SubstrateEventType.LEASE_RELEASED,
                                "payload": {
                                    "worker_id": lm.worker_id,
                                    "run_id": run_id,
                                    "reason": reason,
                                },
                                "actor": "lease_manager",
                                "mission_id": workflow.id,
                            }
                        ],
                    )
                except Exception as e:
                    logger.debug("Lease released event skipped: %s", e)

            self._lease_manager = None

    async def execute(
        self,
        db: AsyncSession,
        workflow: Workflow,
        *,
        run_id: str | None = None,
        blueprint_id: str | None = None,
        start_node_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> StrategyResult:
        """Execute a workflow through the unified executor.

        Args:
            db: Async database session.
            workflow: The workflow to execute.
            run_id: Optional existing run ID (for crash recovery).
            start_node_id: Optional node to start from (for partial replay).
            context: Optional initial execution context.

        Returns:
            StrategyResult with success, status, and execution details.
        """
        with tracer.start_as_current_span("unified_executor.execute") as span:
            span.set_attribute("workflow.id", workflow.id)
            span.set_attribute("workflow.type", workflow.type.value)

            # Crash recovery: if a run_id was provided and has events, resume
            run_id = run_id or str(uuid4())
            if start_node_id:
                span.set_attribute("workflow.start_node_id", start_node_id)

            # Check for crash recovery
            if await self.event_log.run_exists(db, run_id):
                logger.info("Resuming run %s for workflow %s", run_id, workflow.id)

                # Item #3: Re-arm abort signal if abort_requested event exists
                self._abort_signals[run_id] = asyncio.Event()
                abort_events = await self.event_log.get_events(
                    db, run_id, event_type=SubstrateEventType.ABORT_REQUESTED
                )
                if abort_events:
                    self._abort_signals[run_id].set()
                    logger.info(
                        "Durable abort re-armed for run %s (reason: %s)",
                        run_id,
                        (abort_events[-1].payload or {}).get("reason", "unknown"),
                    )

                # Q1-A chunk 4: Validate resume state BEFORE rebuilding
                from app.services.substrate.resume_validation import validate_resume_state

                validation = await validate_resume_state(db, run_id, event_log=self.event_log)
                if not validation.is_resumable:
                    await self.event_log.append(
                        db,
                        run_id,
                        [
                            {
                                "type": SubstrateEventType.RUN_FAILED,
                                "payload": {"reason": "unresumable_state", "warnings": validation.warnings},
                                "actor": "resume_validator",
                            }
                        ],
                    )
                    return StrategyResult(
                        success=False,
                        status="failed",
                        error="unresumable_state",
                        data={"validation": validation.warnings},
                    )
                if validation.warnings:
                    _resume_warnings = validation.warnings
                    _resume_from_seq = validation.last_event_sequence
                else:
                    _resume_warnings = None

                state = await self.replay_engine.rebuild_state(db, run_id)

                # Emit run.resumed AFTER rebuild so to_sequence is known
                if _resume_warnings:
                    await self.event_log.append(
                        db,
                        run_id,
                        [
                            {
                                "type": SubstrateEventType.RUN_RESUME_VALIDATED,
                                "payload": {
                                    "from_sequence": _resume_from_seq,
                                    "to_sequence": state.current_sequence,
                                    "warnings": _resume_warnings,
                                },
                                "actor": "resume_validator",
                            }
                        ],
                    )
                if state.status in ("completed", "failed", "aborted"):
                    return StrategyResult(
                        success=state.status == "completed",
                        status=state.status,
                        error=state.error_message,
                        completed_nodes=list(state.completed_tasks),
                        failed_nodes=list(state.failed_tasks),
                        total_tokens=state.total_tokens,
                        total_cost_usd=state.total_cost_usd,
                    )
                if start_node_id is None:
                    # Resume from last completed node
                    start_node_id = _find_resume_point(workflow, state)

            # Q1-A: Lease integration — claim lease, spawn heartbeat, release on exit
            async with self._lease_context(run_id, db, workflow, span):
                # If another worker holds the lease, return existing state
                if self._lease_already_running is not None:
                    return self._lease_already_running

                # Check if heartbeat detected a lost lease
                if self._lease_manager is not None and self._lease_manager.lease_lost:
                    await self._finalize_run(db, workflow, run_id, "aborted", "Lease lost during execution")
                    return StrategyResult(
                        success=False,
                        status="aborted",
                        error="Lease lost during execution",
                    )

                return await self._execute_inner(db, workflow, run_id, blueprint_id, start_node_id, context, span)

    async def _execute_inner(
        self,
        db: AsyncSession,
        workflow: Workflow,
        run_id: str,
        blueprint_id: str | None,
        start_node_id: str | None,
        context: dict[str, Any] | None,
        span: Any,
    ) -> StrategyResult:
        """Core execution logic (extracted so lease context wraps it)."""
        # Record mission.started event
        await self.event_log.append(
            db,
            run_id,
            [
                {
                    "type": SubstrateEventType.MISSION_STARTED,
                    "payload": {
                        "title": workflow.title,
                        "workflow_type": workflow.type.value,
                        "user_id": workflow.user_id,
                        "node_count": len(workflow.nodes),
                        "blueprint_id": blueprint_id,
                    },
                    "actor": "unified_executor",
                    "mission_id": workflow.id,
                    "blueprint_id": blueprint_id,
                }
            ],
            blueprint_id=blueprint_id,
        )

        # Set up abort signal
        self._abort_signals[run_id] = asyncio.Event()

        # Phase 6.4: Initialize circuit breaker for this mission
        await self._ensure_circuit_breaker(db, workflow)

        # Get strategy and validate
        strategy = self._get_strategy(workflow.type)
        errors = await strategy.validate(workflow)
        if errors:
            await self._finalize_run(db, workflow, run_id, "failed", "; ".join(errors))
            return StrategyResult(
                success=False,
                status="failed",
                error=f"Validation failed: {'; '.join(errors)}",
            )

        # Execute through strategy
        start_time = time.monotonic()
        exec_context = context or {}

        try:
            # Q1-A: Check lease_lost before each strategy execution
            if self._lease_manager is not None and self._lease_manager.lease_lost:
                raise LeaseLostError("Lease lost before strategy execution")

            result = await strategy.execute(workflow, exec_context, self, db, run_id)  # type: ignore[arg-type]
        except BudgetExhausted as e:
            logger.warning("Budget exhausted for run %s: %s", run_id, e)
            await self._record_budget_exhausted(db, run_id, workflow, str(e))
            await self._finalize_run(db, workflow, run_id, "failed", str(e))
            return StrategyResult(
                success=False,
                status="failed",
                error=str(e),
                execution_time_ms=(time.monotonic() - start_time) * 1000,
            )
        except HITLPaused as e:
            # Q1-B chunk 1: HITL pause — release lease, emit RUN_PAUSED, return paused status
            logger.info(
                "HITL paused for run %s: node=%s inbox_item=%s",
                run_id,
                e.node_id,
                e.inbox_item_id,
            )
            await self._handle_hitl_pause(db, workflow, run_id, e)
            return StrategyResult(
                success=False,
                status="paused",
                error=f"Waiting for human {e.interrupt_type}: {e.title}",
                data={
                    "hitl_paused": True,
                    "inbox_item_id": e.inbox_item_id,
                    "node_id": e.node_id,
                    "interrupt_type": e.interrupt_type,
                },
                execution_time_ms=(time.monotonic() - start_time) * 1000,
            )
        except LeaseLostError as e:
            logger.warning("Lease lost for run %s: %s", run_id, e)
            await self._finalize_run(db, workflow, run_id, "aborted", str(e))
            return StrategyResult(
                success=False,
                status="aborted",
                error=str(e),
                execution_time_ms=(time.monotonic() - start_time) * 1000,
            )
        except Exception as e:
            logger.exception("Unhandled error in run %s", run_id)
            await self._finalize_run(db, workflow, run_id, "failed", str(e))
            return StrategyResult(
                success=False,
                status="failed",
                error=str(e),
                execution_time_ms=(time.monotonic() - start_time) * 1000,
            )

        result.execution_time_ms = (time.monotonic() - start_time) * 1000
        # Attach the run id so post-execution hooks (analytics, audit, the
        # ReviewerGuard inbox drain) can reference the specific run.
        result.run_id = run_id

        # Finalize run
        await self._finalize_run(db, workflow, run_id, result.status, result.error)

        # Post-execution hooks
        await self._run_post_hooks(db, workflow, result)

        # Cleanup
        self._abort_signals.pop(run_id, None)

        span.set_attribute("workflow.status", result.status)
        span.set_attribute("workflow.completed_nodes", len(result.completed_nodes))
        return result

    async def abort(
        self,
        run_id: str,
        reason: str = "user_requested",
        *,
        db: AsyncSession | None = None,
    ) -> bool:
        """Signal an abort for a running workflow.

        Item #3: Abort is now durable — when ``db`` is provided, an
        ``abort_requested`` event is written to the event log BEFORE
        setting the in-memory signal.  On crash recovery, ``execute()``
        replays the event log and re-arms the abort signal.

        Returns True if the abort signal was set (workflow was running).
        """
        event = self._abort_signals.get(run_id)
        if event is None:
            event = asyncio.Event()
            self._abort_signals[run_id] = event

        if not event.is_set():
            # Item #3: Durable abort — write to event log first
            if db is not None:
                try:
                    await self.event_log.append(
                        db,
                        run_id,
                        [
                            {
                                "type": SubstrateEventType.ABORT_REQUESTED,
                                "payload": {"reason": reason},
                                "actor": "abort_handler",
                            }
                        ],
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to write durable abort event for run %s: %s",
                        run_id,
                        e,
                    )
            event.set()
            logger.info("Abort signal set for run %s: %s", run_id, reason)
            return True
        return False

    async def pause(self, run_id: str) -> bool:
        """Pause a running workflow.  (Future: pause signal propagation.)"""
        logger.info("Pause requested for run %s", run_id)
        # For now, abort is the only signal.  Pause support requires
        # per-strategy pause point handling (future enhancement).
        return False

    async def is_running(self, run_id: str) -> bool:
        """Check if a run is active (not yet aborted/completed)."""
        event = self._abort_signals.get(run_id)
        return event is not None and not event.is_set()

    def is_aborted(self, run_id: str) -> bool:
        """Check if a run's abort signal has been set."""
        event = self._abort_signals.get(run_id)
        return event is not None and event.is_set()

    # ── Shared node execution ───────────────────────────────────────

    async def execute_node(
        self,
        db: AsyncSession,
        node: WorkflowNode,
        context: dict[str, Any],
        budget: Budget,
        run_id: str,
        workflow: Workflow | None = None,
    ) -> dict[str, Any]:
        """Execute a single node — the shared code path for all strategies.

        This is the single code path for executing a node, regardless of
        strategy (~500 lines).  It handles:
        1. Pre-execution budget check
        2. Capability token creation for tool nodes
        3. Node dispatch to the appropriate handler
        4. Fallback strategy execution
        5. Event logging
        6. Retry with budget
        7. LLM call recording

        All LLM calls go through BudgetEnforcer.call().
        All tool calls go through CapabilityEngine.verify().

        Q1-A chunk 4: Idempotency guard.
        Three cases for (run_id, node_id):
        1. node.completed exists  → skip execution, return cached result
        2. node.started exists but no node.completed → re-execute (crash window)
        3. no events at all       → execute normally
        """
        # Q1-A chunk 4: Idempotency guard — check if node already completed
        if run_id:
            prior_completed = await self.event_log.get_events(
                db,
                run_id,
                event_type=SubstrateEventType.NODE_COMPLETED,
            )
            completed_ids = {(ev.payload or {}).get("task_id") for ev in prior_completed}
            if node.id in completed_ids:
                logger.info("node_skipped_idempotent: run=%s node=%s", run_id, node.id)
                # Return cached result from the event payload
                cached = next(ev for ev in prior_completed if (ev.payload or {}).get("task_id") == node.id)
                payload = cached.payload or {}
                return {
                    "success": True,
                    "task_id": node.id,
                    "output": payload.get("output", ""),
                    "tokens_used": payload.get("tokens", 0),
                    "cost_usd": payload.get("cost_usd", 0.0),
                    "skipped_idempotent": True,
                }

        from app.services.substrate.node_executor import NodeExecutor

        node_exec = NodeExecutor(self)
        return await node_exec.execute(db, node, context, budget, run_id, workflow)

    # ── Budget enforcement (delegates to BudgetEnforcer) ─────────────

    async def call_llm(
        self,
        budget: Budget,
        model_id: str,
        messages: list[dict[str, Any]],
        user_id: str | None = None,
        db_session: Any = None,
        run_id: str | None = None,
        mission_id: str | None = None,
        task_id: str | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Make an LLM call through the budget enforcer.

        This is the ONLY LLM call path in the unified executor.
        All strategies MUST use this method for LLM calls.

        When ``workspace_id`` is provided and the substrate circuit breaker
        is enabled, the call is gated by the per-(workspace, provider)
        circuit breaker in ``app.services.substrate.circuit_breaker``.
        """
        from app.services.budget_enforcer import get_budget_enforcer

        # ── Substrate circuit breaker (per-workspace+provider) ──────────
        provider_id = _provider_from_model(model_id)
        cb_allowed = True
        if workspace_id and provider_id and db_session is not None:
            try:
                from app.config import settings as _settings
                from app.services.substrate.circuit_breaker import (
                    CircuitBreakerOpen,
                    check_and_allow,
                )
                from app.services.substrate.circuit_breaker import (
                    record_failure as cb_record_failure,
                )
                from app.services.substrate.circuit_breaker import (
                    record_success as cb_record_success,
                )

                if getattr(_settings, "FLOWMANNER_CIRCUIT_BREAKER_ENABLED", True):
                    cb_result = await check_and_allow(db_session, workspace_id, provider_id)
                    if not cb_result.allowed:
                        logger.warning(
                            "Substrate CB open for %s/%s: %s",
                            workspace_id,
                            provider_id,
                            cb_result.reason,
                        )
                        raise CircuitBreakerOpen(provider_id, cb_result.retry_after_seconds)
                    # Will record success/failure after the call
                    cb_allowed = True
            except CircuitBreakerOpen:
                raise
            except Exception as exc:
                logger.debug("Substrate CB check failed (fail-open): %s", exc)

        enforcer = get_budget_enforcer()
        try:
            result = await enforcer.call(
                budget=budget,
                model_id=model_id,
                messages=messages,
                user_id=user_id,
                db_session=db_session,
                run_id=run_id,
                mission_id=mission_id,
                task_id=task_id,
            )
            # Record success with substrate CB
            if cb_allowed and workspace_id and provider_id and db_session is not None:
                try:
                    from app.services.substrate.circuit_breaker import record_success as _cb_ok

                    await _cb_ok(db_session, workspace_id, provider_id)
                except Exception:
                    pass
            return result
        except Exception:
            # Record failure with substrate CB
            if cb_allowed and workspace_id and provider_id and db_session is not None:
                try:
                    from app.services.substrate.circuit_breaker import record_failure as _cb_fail

                    await _cb_fail(db_session, workspace_id, provider_id)
                except Exception:
                    pass
            raise

    # ── Internal helpers ────────────────────────────────────────────

    async def _finalize_run(
        self,
        db: AsyncSession,
        workflow: Workflow,
        run_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        """Record the terminal event for a run."""
        event_type_map = {
            "completed": SubstrateEventType.MISSION_COMPLETED,
            "failed": SubstrateEventType.MISSION_FAILED,
            "aborted": SubstrateEventType.MISSION_ABORTED,
        }
        event_type = event_type_map.get(status, SubstrateEventType.MISSION_FAILED)

        await self.event_log.append(
            db,
            run_id,
            [
                {
                    "type": event_type,
                    "payload": {"status": status, "error": error},
                    "actor": "unified_executor",
                    "mission_id": workflow.id,
                }
            ],
        )

        logger.info("Run %s finalized: %s", run_id, status)

    async def _record_budget_exhausted(
        self,
        db: AsyncSession,
        run_id: str,
        workflow: Workflow,
        reason: str,
    ) -> None:
        """Record a budget exhaustion event."""
        await self.event_log.append(
            db,
            run_id,
            [
                {
                    "type": SubstrateEventType.BUDGET_EXHAUSTED,
                    "payload": {
                        "reason": reason,
                        "budget": {
                            "max_cost_usd": float(workflow.budget.max_cost_usd),
                            "spent_usd": float(workflow.budget.spent_usd),
                            "iterations_used": workflow.budget.iterations_used,
                            "max_iterations": workflow.budget.max_iterations,
                        },
                    },
                    "actor": "unified_executor",
                    "mission_id": workflow.id,
                }
            ],
        )

    # ── Phase 6.4: Circuit breaker ────────────────────────────────────

    async def _ensure_circuit_breaker(self, db: AsyncSession, workflow: Workflow) -> None:
        """Lazily create or get a circuit breaker for this mission.

        Passes the workflow's budget limits to the circuit breaker so that
        max_cost_usd from the blueprint definition is enforced.
        """
        try:
            from app.services.circuit_breaker_service import CircuitBreakerService

            service = CircuitBreakerService(db)
            workspace_id = getattr(workflow, "workspace_id", None)
            budget = workflow.budget
            # Use a savepoint so a FK failure (e.g. blueprint ID not in missions)
            # doesn't poison the outer transaction.
            async with db.begin_nested():
                await service.get_or_create(
                    mission_id=workflow.id,
                    workspace_id=workspace_id,
                    max_cost_usd=float(budget.max_cost_usd),
                    max_llm_calls=budget.max_iterations,
                    max_duration_seconds=getattr(budget, "max_wall_time_seconds", 300),
                )
        except Exception as e:
            logger.debug("Circuit breaker init skipped: %s", e)

    async def check_circuit_breaker(
        self, db: AsyncSession, mission_id: str, call_type: str = "llm"
    ) -> tuple[bool, str]:
        """Check if the circuit breaker allows a call.

        Returns (allowed, reason). Used by NodeExecutor before calls.

        RELIABILITY — FAIL CLOSED (R-4): if the breaker check itself throws
        (DB error, serialization, etc.), the guardrail is NOT silently skipped.
        By default (FLOWMANNER_CIRCUIT_BREAKER_FAIL_CLOSED=True) we DENY the
        call: a guardrail that can't verify safety must not permit the action.
        The failure is logged at ERROR and emitted as a metric so it is
        observable. The fail-open behaviour is a deliberate, config-gated
        escape hatch that MUST be explicitly opted into and is still loudly
        logged + metered.
        """
        try:
            from app.services.circuit_breaker_service import CircuitBreakerService

            service = CircuitBreakerService(db)
            async with db.begin_nested():
                breaker = await service.get_breaker(mission_id)
                if breaker is None:
                    return True, ""
                return await service.check_before_call(breaker, call_type=call_type)
        except Exception as e:
            # A guardrail that cannot verify safety must deny, not allow.
            fail_closed = True
            try:
                from app.config import settings as _settings

                fail_closed = getattr(_settings, "FLOWMANNER_CIRCUIT_BREAKER_FAIL_CLOSED", True)
            except Exception:
                pass
            try:
                from app.core.metrics import record_circuit_breaker_guard_failure

                record_circuit_breaker_guard_failure("check")
            except Exception:
                pass
            if fail_closed:
                logger.error(
                    "Circuit breaker check FAILED (denying call, fail-closed): %s", e
                )
                return False, "circuit breaker check failed"
            # Deliberate, documented fail-open escape hatch (not recommended).
            logger.error(
                "Circuit breaker check FAILED (fail-open per config, ALLOWING call): %s", e
            )
            return True, ""

    async def record_circuit_breaker_call(
        self,
        db: AsyncSession,
        mission_id: str,
        call_type: str = "llm",
        cost_usd: float = 0.0,
    ) -> None:
        """Record a call in the circuit breaker counters.

        RELIABILITY (R-4): a recording failure must not be silently swallowed.
        Cost/cap violations that go unrecorded defeat the breaker's accounting.
        On any exception we log at ERROR (not debug) and emit a metric so the
        gap is observable. Recording never blocks the call, but it is no longer
        invisible.
        """
        try:
            from app.services.circuit_breaker_service import CircuitBreakerService

            service = CircuitBreakerService(db)
            async with db.begin_nested():
                breaker = await service.get_breaker(mission_id)
                if breaker is not None:
                    await service.record_call(breaker, call_type=call_type, cost_usd=cost_usd)
        except Exception as e:
            logger.error("Circuit breaker record FAILED (call not counted): %s", e)
            try:
                from app.core.metrics import record_circuit_breaker_guard_failure

                record_circuit_breaker_guard_failure("record")
            except Exception:
                pass

    # ── Q1-B: HITL pause handler ────────────────────────────────────

    async def _handle_hitl_pause(
        self,
        db: AsyncSession,
        workflow: Workflow,
        run_id: str,
        hitl: HITLPaused,
    ) -> None:
        """Handle a HITL pause: emit RUN_PAUSED event.

        The lease is released by the _lease_context manager on exit.
        We just need to emit the event so the run can be resumed later.
        """
        await self.event_log.append(
            db,
            run_id,
            [
                {
                    "type": SubstrateEventType.MISSION_PAUSED,
                    "payload": {
                        "reason": f"hitl_{hitl.interrupt_type}",
                        "inbox_item_id": hitl.inbox_item_id,
                        "node_id": hitl.node_id,
                        "interrupt_type": hitl.interrupt_type,
                        "title": hitl.title,
                    },
                    "actor": "hitl_pause",
                    "mission_id": workflow.id,
                    "task_id": hitl.node_id,
                }
            ],
        )
        logger.info(
            "RUN_PAUSED emitted for run %s: HITL %s node=%s",
            run_id,
            hitl.interrupt_type,
            hitl.node_id,
        )

    async def _run_post_hooks(
        self,
        db: AsyncSession,
        workflow: Workflow,
        result: StrategyResult,
    ) -> None:
        """Run all post-execution hooks (analytics, audit, learning, linear, improvement)."""
        # Analytics
        try:
            from app.services.analytics_service import get_analytics_service

            analytics = get_analytics_service(db)
            await analytics.calculate_mission_metrics(workflow.id)
        except Exception as e:
            logger.debug("Analytics hook skipped: %s", e)

        # Audit log
        try:
            from app.api.middleware.audit import log_event

            await log_event(
                workflow.user_id,
                f"workflow_{result.status}",
                {
                    "workflow_id": workflow.id,
                    "title": workflow.title,
                    "completed": len(result.completed_nodes),
                    "failed": len(result.failed_nodes),
                },
            )
        except Exception as e:
            logger.debug("Audit log hook skipped: %s", e)

        # Linear sync
        try:
            from app.services.linear.sync import sync_mission_to_linear

            await sync_mission_to_linear(
                mission_id=workflow.id,
                status=result.status,
                results=result.data,
                error_message=result.error,
            )
        except Exception as e:
            logger.debug("Linear sync hook skipped: %s", e)

        # Learning recording
        try:
            from app.services.learning_service import get_learning_service

            learning = get_learning_service()
            if learning:
                await learning.record_execution(
                    task_description=f"{workflow.title} {workflow.description or ''}",
                    plan={},
                    result=result.data or {},
                    success=result.success,
                    mission_id=workflow.id,
                    user_id=workflow.user_id,  # type: ignore[arg-type]
                    model_used=None,
                    tokens_used=result.total_tokens,
                    duration_seconds=result.execution_time_ms / 1000.0,
                )
        except Exception as e:
            logger.debug("Learning record hook skipped: %s", e)

        # Self-improvement analysis
        try:
            from app.services.improvement import get_improvement_loop

            improvement = get_improvement_loop()
            if improvement:
                await improvement.on_mission_complete(
                    mission_id=workflow.id,
                    agent_id=None,
                    success=result.success,
                    metrics={
                        "task_count": float(len(workflow.nodes)),
                    },
                )
        except Exception as e:
            logger.debug("Improvement analysis hook skipped: %s", e)

        # Phase 6.1: Episodic memory consolidation (gated by feature flag)
        try:
            if settings.FLOWMANNER_CROSS_MISSION_MEMORY and result.success:
                from app.database import AsyncSessionLocal
                from app.services.episodic_memory_worker import EpisodicMemoryWorker

                worker = EpisodicMemoryWorker()
                await worker.process_mission_completed(
                    db,
                    mission_id=workflow.id,
                    run_id=result.run_id or "",
                )
        except Exception as e:
            logger.debug("Episodic memory consolidation skipped: %s", e)

        # Q6 GOLD-LEDGER #2: ReviewerGuard -> HITL inbox drain.  After a run
        # completes, verify each node's output for lexical groundedness and
        # surface any ungrounded claim as an ESCALATION inbox item.  Lexical
        # only ($0 token cost), escalate-only (cannot corrupt run data).
        # Best-effort: failures are swallowed so a guard hiccup never blocks
        # or poisons a completed run.  Gated by a feature flag.
        try:
            if settings.REVIEWER_GUARD_DRAIN_ENABLED:
                await self._run_reviewer_guard_drain(db, workflow, result)
        except Exception as e:
            logger.debug("ReviewerGuard inbox drain skipped: %s", e)

    async def _run_reviewer_guard_drain(
        self,
        db: AsyncSession,
        workflow: Workflow,
        result: StrategyResult,
    ) -> None:
        """Verify a completed run's node outputs and drain escalations.

        Builds the transcript + claims from the run's completed node outputs
        (each output must be grounded in the run's outputs) and, for any
        escalation returned by ReviewerGuard, creates an ESCALATION inbox
        item via HITLService.  Lexical-only → no cross-family LLM call.
        """
        from app.services.reviewer_guard.inbox_drain import (
            build_run_context,
            drain_run_to_inbox,
        )

        ctx = build_run_context(
            run_id=result.run_id or workflow.id,
            mission_id=workflow.id,
            nodes=workflow.nodes,
            user_id=workflow.user_id,
            workspace_id=workflow.workspace_id,
            brief=workflow.description or workflow.title,
        )
        if not ctx.claims:
            return
        drained = await drain_run_to_inbox(db, ctx, reviewer_model="deepseek-v4-flash")
        if drained:
            logger.info(
                "ReviewerGuard drained %d escalation(s) for run=%s",
                drained,
                ctx.run_id,
            )


def _find_resume_point(workflow: Workflow, state: Any) -> str | None:
    """Find the first incomplete node after crash recovery."""
    for node in workflow.nodes:
        if node.id not in state.completed_tasks and node.id not in state.failed_tasks:
            return node.id
    return None


# ── Singleton ──────────────────────────────────────────────────────

_unified_executor: UnifiedExecutor | None = None


def get_unified_executor() -> UnifiedExecutor:
    """Get or create the UnifiedExecutor singleton."""
    global _unified_executor
    if _unified_executor is None:
        _unified_executor = UnifiedExecutor()
    return _unified_executor
