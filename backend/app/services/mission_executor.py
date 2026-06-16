# mypy: disable-error-code=attr-defined
#!/usr/bin/env python3
"""Mission Executor Service — async SQLAlchemy compatible.

Orchestrates autonomous mission execution:
- Executes approved missions
- Runs tasks in dependency order
- Integrates with tools (ModelRouter, RAG, code execution)
- Updates task status and logs progress
- Handles retries and fallback strategies

Delegates to focused sub-modules:
  cost_tracker.py      — cost estimation + LLM call recording
  mission_planner.py    — plan generation via LLM
  llm_executor.py       — LLM task execution
  browser_task_runner.py — browser tool execution
  task_executor.py      — task dispatch + tool delegation
"""

import logging
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from opentelemetry import trace
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.mission_models import (
    Mission,
    MissionLog,
    MissionStatus,
    MissionTaskStatus,
)
from app.models.mission_models import (
    MissionTask as MT,
)
from app.orchestration.human_interrupt import HumanInterrupt, get_hitl_manager
from app.services.browser_task_runner import BrowserTaskRunner
from app.services.cost_tracker import CostTracker
from app.services.llm_executor import LlmExecutor
from app.services.mission_errors import (
    MissionError,
    PermanentMissionError,
    RetryableMissionError,
)
from app.services.mission_planner import MissionPlanner
from app.services.sandbox_service import SandboxService
from app.services.task_executor import TaskExecutor
from app.services.depth_policy import DepthPolicy
from app.models.depth_models import DepthLevel
from app.models.substrate_models import SubstrateEventType
from app.services.recovery_policy import RecoveryAction
from app.services.self_correction_loop import SelfCorrectionBudget, SelfCorrectionLoop
from app.tools._sandbox_context import set_current_sandbox_id

logger = logging.getLogger(__name__)

tracer = trace.get_tracer(__name__)


# ── Lazy import helpers ────────────────────────────────────────────────────────


def _import_model_router():
    from app.services.llm_router import ModelRouter

    return ModelRouter


def _import_rag_service():
    from app.services.rag_service import RAGService

    return RAGService


# ── MissionExecutor (orchestrator) ────────────────────────────────────────────


class MissionExecutor:
    """Orchestrates mission execution by wiring sub-modules and running the main loop."""

    def __init__(self):
        self.model_router = None
        self.rag_service = None
        self.workspace = tempfile.mkdtemp(prefix="mission_")
        self.resource_limits = {
            "cpu_seconds": settings.MISSION_RESOURCE_CPU_SECONDS,
            "memory_mb": settings.MISSION_RESOURCE_MEMORY_MB,
            "file_size_mb": settings.MISSION_RESOURCE_FILE_SIZE_MB,
        }

        # Sub-modules — wired with callbacks for logging/transitions
        self.cost_tracker = CostTracker()
        self.browser_runner = BrowserTaskRunner()
        self.llm_exec = LlmExecutor(
            cost_tracker=self.cost_tracker,
            get_model_router=self._get_model_router,
        )
        self.planner = MissionPlanner(
            cost_tracker=self.cost_tracker,
            get_model_router=self._get_model_router,
            log_callback=self._log,
            transition_callback=self._transition_status,
        )
        self.task_exec = TaskExecutor(
            llm_executor=self.llm_exec,
            browser_runner=self.browser_runner,
            cost_tracker=self.cost_tracker,
            get_rag_service=self._get_rag_service,
            workspace=self.workspace,
            resource_limits=self.resource_limits,
            log_callback=self._log,
        )
        # Q2-Q3 Chunk 4: Depth policy for adaptive reasoning
        self.depth_policy = DepthPolicy()
        # Q2-Q3 Chunk 6: Self-correction loop with cost ceilings
        self.self_correction = SelfCorrectionLoop()

    # ── Shared service accessors ──────────────────────────────────────────────

    def _get_model_router(self, user_id: str | None = None):
        """Return the ModelRouter for the current execution context.

        If ``user_id`` is provided, the cached router is replaced with a
        user_id-aware router (so BYOK key resolution uses the right user).
        If ``user_id`` is None, the cached router is returned, or a
        no-arg fallback is created if no router has been wired yet.

        The no-arg fallback path is preserved for non-mission callers
        (chat, background jobs) where no user context is available.
        """
        needs_rebuild = user_id is not None and (
            self.model_router is None
            or getattr(self.model_router, "user_id", None) != user_id
        )
        if needs_rebuild:
            try:
                ModelRouter = _import_model_router()
                self.model_router = ModelRouter(user_id=user_id)
                logger.info("ModelRouter wired for user_id=%s", user_id)
            except PermanentMissionError as e:
                logger.error("Permanent error loading ModelRouter: %s", e)
                self.model_router = None
            except Exception as e:
                logger.warning("Could not load ModelRouter: %s", e)
                self.model_router = None
        elif self.model_router is None:
            # Fallback lazy loader: no user_id, no cached router
            try:
                ModelRouter = _import_model_router()
                self.model_router = ModelRouter()
                logger.info("ModelRouter loaded successfully (fallback, no user_id)")
            except PermanentMissionError as e:
                logger.error("Permanent error loading ModelRouter: %s", e)
                self.model_router = None
            except Exception as e:
                logger.warning("Could not load ModelRouter: %s", e)
                self.model_router = None
        return self.model_router

    def _get_rag_service(self):
        if self.rag_service is None:
            try:
                RAGService = _import_rag_service()
                self.rag_service = RAGService()
                logger.info("RAGService loaded successfully")
            except PermanentMissionError as e:
                logger.error("Permanent error loading RAGService: %s", e)
                self.rag_service = None
            except Exception as e:
                logger.warning("Could not load RAGService: %s", e)
                self.rag_service = None
        return self.rag_service

    # ── Error classification ──────────────────────────────────────────────────

    def _classify_error(self, exc: Exception) -> MissionError:
        """Classify an exception as retryable or permanent."""
        if isinstance(exc, MissionError):
            return exc
        if isinstance(exc, httpx.TimeoutException):
            return RetryableMissionError(f"Timeout: {exc}")
        if isinstance(exc, httpx.HTTPStatusError):
            if exc.response.status_code in (429, 500, 502, 503, 504):
                return RetryableMissionError(f"HTTP {exc.response.status_code}: {exc}")
            if exc.response.status_code in (401, 403, 404):
                return PermanentMissionError(f"HTTP {exc.response.status_code}: {exc}")
        if isinstance(exc, (httpx.ConnectError, httpx.RemoteProtocolError)):
            return RetryableMissionError(f"Connection error: {exc}")
        return RetryableMissionError(f"Unknown error: {exc}")

    # ── Step status / transition / logging ────────────────────────────────────

    async def _update_step_status(
        self,
        db,
        mission_id: str,
        step_index: int,
        status: str,
        result: dict = None,
        error: str = None,
    ):
        """Update mission step status for resumability."""
        try:
            step_result = await db.execute(
                select(MT).where(
                    MT.mission_id == mission_id,
                    MT.order_index == step_index,
                )
            )
            step = step_result.scalars().first()
            if step:
                prev_state = step.status
                step.status = status
                if result:
                    step.output_data = result
                if error:
                    step.error_message = error
                if status in (MissionTaskStatus.COMPLETED, MissionTaskStatus.FAILED):
                    step.completed_at = datetime.now(UTC)
                await db.commit()
                await self._log(
                    db,
                    mission_id,
                    step.id,
                    "info",
                    f"Task {step.title} state transition: {prev_state} → {status}",
                    extra_data={
                        "actor": "mission_executor",
                        "prev_state": prev_state,
                        "next_state": status,
                        "cause": (error if error else ("completed" if status == "completed" else "status_update")),
                        "task_id": str(step.id),
                        "task_type": step.task_type,
                    },
                )
        except Exception as db_error:
            logger.error("Failed to update step status: %s", db_error)
            await db.rollback()

    async def _transition_status(
        self,
        db,
        mission,
        new_status: str,
        *,
        cause: str = "",
        error_message: str | None = None,
        level: str = "info",
    ) -> None:
        """Central method for mission status transitions — always logs + updates + commits."""
        prev_status = mission.status
        mission.status = new_status

        if error_message:
            mission.error_message = error_message

        if new_status in (
            MissionStatus.COMPLETED,
            MissionStatus.FAILED,
            MissionStatus.ABORTED,
        ):
            mission.completed_at = datetime.now(UTC)

        await db.commit()

        await self._log(
            db,
            mission.id,
            None,
            level,
            f"Mission {mission.title}: {prev_status} → {new_status}" + (f" — {cause}" if cause else ""),
            extra_data={
                "actor": "mission_executor",
                "prev_state": prev_status,
                "next_state": new_status,
                "cause": cause or f"Transitioned to {new_status}",
                "error_message": error_message,
            },
        )

    # ── Main execution loop ───────────────────────────────────────────────────

    async def execute_mission(self, mission_id: UUID, *, enable_depth_policy: bool = True) -> dict[str, Any]:
        """Execute a mission — main orchestrator loop.

        Args:
            mission_id: UUID of the mission to execute.
            enable_depth_policy: If True (default), uses the adaptive depth
                policy to decide reasoning depth per step.  If False, uses
                the legacy "one depth for all steps" behavior.
        """

        async with AsyncSessionLocal() as db:
            with tracer.start_as_current_span("mission.execute") as span:
                span.set_attribute("mission.id", str(mission_id))

                try:
                    result = await db.execute(select(Mission).where(Mission.id == str(mission_id)).with_for_update())
                    mission = result.scalars().first()
                    if not mission:
                        logger.error("Mission %s not found", mission_id)
                        span.set_attribute("mission.error", "not_found")
                        return {"success": False, "error": "Mission not found"}

                    # Validate mission is still in a runnable state after acquiring lock
                    if mission.status not in (
                        MissionStatus.QUEUED,
                        MissionStatus.PLANNED,
                    ):
                        logger.warning(
                            "Mission %s cannot execute from '%s' state",
                            mission_id,
                            mission.status,
                        )
                        return {
                            "success": False,
                            "error": f"Cannot execute mission in '{mission.status}' state",
                        }

                    span.set_attribute("mission.user_id", str(mission.user_id))
                    span.set_attribute("mission.title", mission.title)

                    # Wire ModelRouter with user context for BYOK key resolution
                    self.model_router = self._get_model_router(user_id=str(mission.user_id))

                    # Wire HITLManager for human approval checks
                    self.hitl_manager = get_hitl_manager()

                    prev_status = mission.status
                    mission.status = MissionStatus.EXECUTING
                    mission.started_at = datetime.now(UTC)
                    await db.commit()

                    await self._log(
                        db,
                        mission.id,
                        None,
                        "info",
                        f"Starting mission: {mission.title}",
                        extra_data={
                            "actor": "mission_executor",
                            "prev_state": prev_status,
                            "next_state": MissionStatus.EXECUTING,
                            "cause": "Mission execution started",
                        },
                    )

                    # Create sandbox for this mission (sandboxd integration)
                    sandbox_id: str | None = None
                    sandbox_svc: SandboxService | None = None
                    if settings.SANDBOXD_ENABLED:
                        try:
                            sandbox_svc = SandboxService()
                            sandbox_id = await sandbox_svc.ensure_sandbox_for_mission(
                                str(mission.id),
                                str(mission.user_id),
                                db=db,
                            )
                            set_current_sandbox_id(sandbox_id)
                            await self._log(
                                db,
                                mission.id,
                                None,
                                "info",
                                f"Sandbox {sandbox_id} ready for mission",
                            )
                        except Exception as sb_err:
                            logger.warning(
                                "sandboxd unavailable, falling back to subprocess sandboxes: %s",
                                sb_err,
                            )

                    task_result = await db.execute(
                        select(MT).where(MT.mission_id == str(mission_id)).order_by(MT.order_index)
                    )
                    tasks = list(task_result.scalars().all())

                    if not tasks:
                        await self._log(
                            db,
                            mission.id,
                            None,
                            "error",
                            "No tasks found - mission may need planning first",
                        )
                        mission.status = MissionStatus.FAILED
                        mission.error_message = "No tasks to execute. Run mission planning first."
                        mission.completed_at = datetime.now(UTC)
                        await db.commit()
                        return {
                            "success": False,
                            "error": "No tasks to execute - planning required",
                        }

                    task_map = {str(t.id): t for t in tasks}

                    completed: set = set()
                    failed: set = set()
                    skipped: set = set()
                    # Surface the first task error in the final return so callers
                    # can see what went wrong (e.g. ModelRouter BYOK failures) without
                    # having to dig through the mission log.
                    first_task_error: str | None = None

                    max_iterations = len(tasks) * settings.MISSION_MAX_ITERATION_MULTIPLIER
                    iteration = 0

                    while len(completed) + len(failed) + len(skipped) < len(tasks):
                        iteration += 1
                        if iteration > max_iterations:
                            await self._log(db, mission.id, None, "error", "Max iterations exceeded")
                            break

                        await db.refresh(mission)
                        if mission.status == MissionStatus.PAUSED:
                            await self._log(db, mission.id, None, "info", "Mission paused")
                            return {"success": True, "status": MissionStatus.PAUSED}
                        if mission.status == MissionStatus.ABORTED:
                            await self._log(
                                db,
                                mission.id,
                                None,
                                "warning",
                                "Mission aborted during execution — stopping",
                                extra_data={
                                    "actor": "mission_executor",
                                    "prev_state": MissionStatus.EXECUTING,
                                    "next_state": MissionStatus.ABORTED,
                                    "cause": "Abort signal received",
                                },
                            )
                            return {"success": False, "status": MissionStatus.ABORTED}

                        ready = []
                        for task in tasks:
                            if task.status not in [
                                MissionTaskStatus.PENDING,
                                MissionTaskStatus.RUNNING,
                            ]:
                                continue

                            deps_met = True
                            for dep_idx in task.dependencies or []:
                                dep_task = next((t for t in tasks if t.order_index == dep_idx), None)
                                if dep_task and str(dep_task.id) not in completed:
                                    deps_met = False
                                    break

                            if deps_met and task.status == MissionTaskStatus.PENDING:
                                ready.append(task)

                        if not ready:
                            pending = [t for t in tasks if t.status == MissionTaskStatus.PENDING]
                            if pending:
                                await self._log(
                                    db,
                                    mission.id,
                                    None,
                                    "error",
                                    f"Deadlock detected: {len(pending)} tasks pending but none ready",
                                )
                                for t in pending:
                                    t.status = MissionTaskStatus.FAILED
                                    failed.add(str(t.id))
                                await db.commit()
                            break

                        for task in ready:
                            try:
                                # Q2-Q3 Chunk 4: Depth policy decision
                                if enable_depth_policy:
                                    depth_decision = self.depth_policy.decide(
                                        risk=getattr(task, "risk_level", "low") or "low",
                                        uncertainty=getattr(task, "uncertainty", 0.5) or 0.5,
                                        budget_remaining_usd=Decimal(str(mission.budget_remaining or "0")) if hasattr(mission, "budget_remaining") and mission.budget_remaining else Decimal("5.00"),
                                        prior_failures=getattr(task, "prior_failures", 0) or 0,
                                        tool_requires_approval=getattr(task, "requires_approval", False) or False,
                                        retry_count=getattr(task, "retry_count", 0) or 0,
                                        policy_override=getattr(task, "policy_override", False) or False,
                                    )

                                    # Set reflection iterations based on depth
                                    task.max_reflection_iterations = depth_decision.estimated_reflection_iterations

                                    # Emit depth_decided audit event
                                    await self._emit_depth_event(
                                        db,
                                        mission,
                                        task,
                                        depth_decision,
                                        risk=getattr(task, "risk_level", "low") or "low",
                                        uncertainty=getattr(task, "uncertainty", 0.5) or 0.5,
                                    )

                                    # Check for HITL escalation from depth policy
                                    if depth_decision.escalate_to_hitl:
                                        hitl_title = f"HITL escalation: {depth_decision.hitl_reason}"
                                        if depth_decision.hitl_reason == "tool_requires_approval":
                                            hitl_title = f"Approval required for: {task.title}"

                                        interrupt = HumanInterrupt(
                                            mission_id=str(mission.id),
                                            interrupt_type="approval",
                                            context={
                                                "mission_title": mission.title,
                                                "task_title": task.title,
                                                "task_description": task.description,
                                                "task_type": task.task_type,
                                                "depth_level": depth_decision.level.value,
                                                "depth_reason": depth_decision.reason,
                                                "hitl_reason": depth_decision.hitl_reason,
                                            },
                                            proposed_action={
                                                "action": "execute_task",
                                                "task_id": str(task.id),
                                                "depth_level": depth_decision.level.value,
                                            },
                                            confidence=0.5,
                                        )
                                        await self.hitl_manager.raise_interrupt(db, interrupt)
                                        mission.status = MissionStatus.PAUSED
                                        await db.commit()
                                        await self._log(
                                            db,
                                            mission.id,
                                            task.id,
                                            "info",
                                            f"Mission paused — HITL escalation ({depth_decision.hitl_reason}): {task.title}",
                                        )
                                        return {
                                            "success": True,
                                            "status": MissionStatus.PAUSED,
                                        }

                                # Legacy path: check for human approval requirement (always runs)
                                if getattr(task, "approval_required", False) and self.hitl_manager:
                                    interrupt = HumanInterrupt(
                                        mission_id=str(mission.id),
                                        interrupt_type="approval",
                                        context={
                                            "mission_title": mission.title,
                                            "task_title": task.title,
                                            "task_description": task.description,
                                            "task_type": task.task_type,
                                        },
                                        proposed_action={
                                            "action": "execute_task",
                                            "task_id": str(task.id),
                                        },
                                        confidence=0.5,
                                    )
                                    await self.hitl_manager.raise_interrupt(db, interrupt)
                                    mission.status = MissionStatus.PAUSED
                                    await db.commit()
                                    await self._log(
                                        db,
                                        mission.id,
                                        task.id,
                                        "info",
                                        f"Mission paused — awaiting human approval for: {task.title}",
                                    )
                                    return {
                                        "success": True,
                                        "status": MissionStatus.PAUSED,
                                    }

                                # Delegate to TaskExecutor
                                result = await self.task_exec.execute_task(db, mission, task, task_map)

                                if result.get("success"):
                                    completed.add(str(task.id))
                                    task.status = MissionTaskStatus.COMPLETED
                                    task.output_data = result.get("output")
                                    task.completed_at = datetime.now(UTC)

                                    tokens = result.get("tokens", 0)
                                    if tokens:
                                        task.tokens_used = tokens
                                        mission.tokens_used = (mission.tokens_used or 0) + tokens
                                        cost_per_1m = self.cost_tracker.COST_PER_1M_TOKENS.get(
                                            task.assigned_model or "deepseek-chat",
                                            self.cost_tracker.COST_PER_1M_TOKENS["default"],
                                        )
                                        task.cost = (tokens / settings.MISSION_COST_DIVISOR) * cost_per_1m
                                        mission.actual_cost = (mission.actual_cost or 0) + task.cost

                                    await self._log(
                                        db,
                                        mission.id,
                                        task.id,
                                        "info",
                                        f"Task completed: {task.title}",
                                    )
                                else:
                                    # Capture the first task error so the final return
                                    # value can surface what went wrong (ModelRouter
                                    # failures, BYOK missing keys, etc.).
                                    if first_task_error is None:
                                        first_task_error = result.get("error") or "Task failed (no error message)"
                                    # Q2-Q3 Chunk 6: Self-correction loop
                                    task_error = Exception(result.get("error", "Task failed"))
                                    sc_context = {
                                        "task_id": str(task.id),
                                        "mission_id": str(mission.id),
                                        "task_type": task.task_type,
                                        "retry_count": task.retry_count or 0,
                                        "max_retries": task.max_retries or 0,
                                    }
                                    # Create event emitter that uses the event log
                                    async def _emit_sc_event(run_id, events):
                                        from app.services.substrate.event_log import get_event_log
                                        el = get_event_log()
                                        await el.append(db, run_id, events, mission_id=str(mission.id))

                                    sc_result = await self.self_correction.correct(
                                        error=task_error,
                                        context=sc_context,
                                        event_emitter=_emit_sc_event,
                                    )

                                    # NOTE: FALLBACK_PROVIDER currently behaves like RETRY
                                    # (re-queue without provider switching).  Actual provider
                                    # switching is deferred to a future chunk when the
                                    # ModelRouter supports per-task provider override.
                                    if sc_result.action_taken in (
                                        RecoveryAction.RETRY,
                                        RecoveryAction.REFLECT,
                                        RecoveryAction.FALLBACK_PROVIDER,
                                    ):
                                        if (task.retry_count or 0) < (task.max_retries or 0):
                                            task.retry_count = (task.retry_count or 0) + 1
                                            task.status = MissionTaskStatus.PENDING
                                            await self._log(
                                                db,
                                                mission.id,
                                                task.id,
                                                "warning",
                                                f"Task failed ({sc_result.analysis.error_class.value if sc_result.analysis else 'unknown'}), "
                                                f"{sc_result.action_taken.value} ({task.retry_count}/{task.max_retries}): {result.get('error')}",
                                            )
                                        else:
                                            failed.add(str(task.id))
                                            task.status = MissionTaskStatus.FAILED
                                            task.completed_at = datetime.now(UTC)
                                            await self._log(
                                                db,
                                                mission.id,
                                                task.id,
                                                "error",
                                                f"Task failed after {task.max_retries} retries ({sc_result.action_taken.value}): {result.get('error')}",
                                            )
                                            await self.task_exec._apply_fallback(db, mission, task, result.get("error"))

                                    elif sc_result.action_taken == RecoveryAction.ASK_HITL:
                                        hitl_reason = sc_result.analysis.root_cause if sc_result.analysis else "unknown failure"
                                        interrupt = HumanInterrupt(
                                            mission_id=str(mission.id),
                                            interrupt_type="approval",
                                            context={
                                                "mission_title": mission.title,
                                                "task_title": task.title,
                                                "failure_reason": hitl_reason,
                                                "error_class": sc_result.analysis.error_class.value if sc_result.analysis else None,
                                            },
                                            proposed_action={
                                                "action": "retry_task",
                                                "task_id": str(task.id),
                                            },
                                            confidence=0.3,
                                        )
                                        await self.hitl_manager.raise_interrupt(db, interrupt)
                                        mission.status = MissionStatus.PAUSED
                                        await db.commit()
                                        await self._log(
                                            db,
                                            mission.id,
                                            task.id,
                                            "warning",
                                            f"Mission paused — self-correction HITL escalation: {hitl_reason}",
                                        )
                                        return {
                                            "success": True,
                                            "status": MissionStatus.PAUSED,
                                        }

                                    else:  # ABORT
                                        failed.add(str(task.id))
                                        task.status = MissionTaskStatus.FAILED
                                        task.completed_at = datetime.now(UTC)
                                        abort_reason = sc_result.aborted_reason or "Self-correction budget exhausted"
                                        await self._log(
                                            db,
                                            mission.id,
                                            task.id,
                                            "error",
                                            f"Task aborted by self-correction: {abort_reason}",
                                        )
                                        await self.task_exec._apply_fallback(db, mission, task, abort_reason)

                            except Exception as e:
                                logger.exception("Error executing task %s", task.id)
                                failed.add(str(task.id))
                                task.status = MissionTaskStatus.FAILED
                                task.completed_at = datetime.now(UTC)
                                await self._log(
                                    db,
                                    mission.id,
                                    task.id,
                                    "error",
                                    f"Exception: {e!s}",
                                )

                            await db.commit()

                    # Reap sandbox on mission terminal transition
                    if sandbox_id and sandbox_svc:
                        try:
                            await sandbox_svc.reap_sandbox(str(mission.id), db=db)
                            set_current_sandbox_id(None)
                        except Exception as reap_err:
                            logger.warning("Failed to reap sandbox: %s", reap_err)

                    mission.completed_at = datetime.now(UTC)
                    prev_status = mission.status

                    if failed:
                        mission.status = MissionStatus.FAILED
                        mission.error_message = f"{len(failed)} tasks failed"
                        span.set_attribute("mission.status", MissionStatus.FAILED)
                        span.set_attribute("mission.tasks_failed", len(failed))
                        await self._log(
                            db,
                            mission.id,
                            None,
                            "error",
                            f"Mission failed: {len(failed)} tasks failed",
                            extra_data={
                                "actor": "mission_executor",
                                "prev_state": prev_status,
                                "next_state": MissionStatus.FAILED,
                                "cause": f"{len(failed)} task(s) failed, {len(completed)} completed",
                            },
                        )
                    else:
                        mission.status = MissionStatus.COMPLETED
                        mission.results = self.task_exec._aggregate_results(tasks)
                        span.set_attribute("mission.status", MissionStatus.COMPLETED)
                        span.set_attribute("mission.tasks_completed", len(completed))
                        await self._log(
                            db,
                            mission.id,
                            None,
                            "info",
                            f"Mission completed: {len(completed)} tasks",
                            extra_data={
                                "actor": "mission_executor",
                                "prev_state": prev_status,
                                "next_state": MissionStatus.COMPLETED,
                                "cause": f"All {len(completed)} task(s) completed successfully",
                            },
                        )

                    try:
                        from app.services.analytics_service import get_analytics_service

                        analytics_service = get_analytics_service(db)
                        await analytics_service.calculate_mission_metrics(mission.id)
                        logger.info("Analytics calculated for mission %s", mission.id)
                    except Exception as analytics_error:
                        logger.warning("Non-critical failure in analytics: %s", analytics_error)

                    await db.commit()

                    # Audit log
                    try:
                        from app.api.middleware.audit import log_event

                        await log_event(
                            mission.user_id,
                            f"mission_{mission.status}",
                            {
                                "mission_id": str(mission.id),
                                "title": mission.title,
                                "completed": len(completed),
                                "failed": len(failed),
                            },
                        )
                    except Exception as audit_error:
                        logger.warning("Non-critical failure in audit log: %s", audit_error)

                    # Sync to Linear if linked
                    try:
                        from app.services.linear.sync import sync_mission_to_linear

                        await sync_mission_to_linear(
                            mission_id=str(mission.id),
                            status=mission.status,
                            results=mission.results,
                            error_message=mission.error_message,
                        )
                    except Exception as linear_err:
                        logger.warning("Non-critical failure in Linear sync: %s", linear_err)

                    # Record execution for learning
                    try:
                        from app.services.learning_service import get_learning_service

                        learning_svc = get_learning_service()
                        if learning_svc:
                            duration = None
                            if mission.started_at and mission.completed_at:
                                duration = (mission.completed_at - mission.started_at).total_seconds()
                            await learning_svc.record_execution(
                                task_description=f"{mission.title} {mission.description or ''}",
                                plan=mission.plan or {},
                                result=mission.results or {},
                                success=(mission.status == MissionStatus.COMPLETED),
                                mission_id=str(mission.id),
                                user_id=mission.user_id,
                                model_used=None,
                                tokens_used=mission.tokens_used,
                                duration_seconds=duration,
                            )
                    except Exception as learn_err:
                        logger.debug("Learning record_execution skipped: %s", learn_err)

                    return {
                        "success": mission.status == MissionStatus.COMPLETED,
                        "status": mission.status,
                        "completed_tasks": len(completed),
                        "failed_tasks": len(failed),
                        "error": first_task_error or mission.error_message,
                        "results": mission.results,
                    }

                except PermanentMissionError as e:
                    logger.error("Permanent error executing mission %s: %s", mission_id, e)
                    await self._transition_status(
                        db,
                        mission,
                        MissionStatus.FAILED,
                        cause=f"Permanent error: {e}",
                        error_message=str(e),
                        level="error",
                    )
                    return {"success": False, "error": str(e), "permanent": True}
                except RetryableMissionError as e:
                    logger.warning("Retryable error executing mission %s: %s", mission_id, e)
                    raise
                except Exception as e:
                    logger.exception("Error executing mission %s", mission_id)
                    await self._transition_status(
                        db,
                        mission,
                        MissionStatus.FAILED,
                        cause=f"Execution error: {e}",
                        error_message=str(e),
                        level="error",
                    )
                    return {"success": False, "error": str(e)}

    # ── Improvement analysis ──────────────────────────────────────────────────

    async def _trigger_improvement_analysis(self, mission) -> None:
        try:
            from app.services.improvement import get_improvement_loop

            improvement_loop = get_improvement_loop()
            if improvement_loop is None:
                logger.debug("Improvement loop not initialized, skipping analysis")
            else:
                await improvement_loop.on_mission_complete(
                    mission_id=str(mission.id),
                    agent_id=mission.agent_id,
                    success=(mission.status == MissionStatus.COMPLETED),
                    metrics={
                        "title": mission.title,
                        "task_count": float(len(mission.tasks) if hasattr(mission, "tasks") else 0),
                        "error_message": mission.error_message,
                    },
                )
                logger.info("Improvement analysis completed for mission %s", mission.id)
        except Exception as improvement_error:
            logger.warning("Non-critical failure in improvement analysis: %s", improvement_error)

        # D30-60 T27: run the critic after the existing improvement loop.
        # Failures here must NEVER break mission completion — wrapped
        # defensively in a sibling try/except.
        try:
            await self._trigger_critique_analysis(mission)
        except Exception as critic_error:
            logger.warning("Non-critical failure in critic analysis: %s", critic_error)

    # ── Critic analysis (D30-60 T27) ────────────────────────────────────────

    async def _trigger_critique_analysis(self, mission) -> None:
        """Run the CriticAgent + ImprovementGenerator and persist a
        ``Critique`` row for the just-completed mission.

        If the mission belongs to a program, also feed the resulting
        ``ImprovementBatch`` into the program's learning_brief via
        ``MissionProgramService.apply_improvement_batch`` (non-destructive
        merge). The mission's program_id is looked up via the latest
        ``ProgramRun`` for the mission (Mission has no program_id column
        directly — programs and missions are linked via ProgramRun).

        Wrapped at the caller (``_trigger_improvement_analysis``) in
        try/except so a critic failure does not break mission execution.
        """
        # Lazy imports to avoid an import cycle and to keep the
        # import-time cost off the hot path.
        from app.services.critic import CriticAgent, CriticInput
        from app.services.critique_service import CritiqueService
        from app.services.improvement_generator import (
            ImprovementGenerator,
            MissionContext,
        )

        # 1. Build the CriticInput from the mission. The plan and outcome
        #    are duck-typed (dict or stringified) — T25's CriticInput
        #    accepts both. We fall back to a stringified view if either
        #    attribute is missing.
        goal = (
            getattr(mission, "description", None)
            or getattr(mission, "title", "")
            or ""
        )
        plan: Any = getattr(mission, "plan", None) or {}
        outcome: Any = getattr(mission, "results", None) or {}
        critic_input = CriticInput(mission_goal=goal, plan=plan, outcome=outcome)

        # 2. Invoke the critic + generate the improvement batch.
        critic = CriticAgent()
        critic_output = await critic.critique(
            mission_goal=goal,
            plan=plan,
            outcome=outcome,
            user_id=str(getattr(mission, "user_id", "")),
            workspace_id=str(getattr(mission, "workspace_id", "")),
        )
        generator = ImprovementGenerator()
        batch = generator.generate(
            critic_output,
            MissionContext(
                mission_id=str(mission.id),
                goal=goal,
                plan=plan if isinstance(plan, dict) else {},
                outcome=outcome if isinstance(outcome, dict) else {},
                user_id=int(getattr(mission, "user_id", 0) or 0),
                workspace_id=str(getattr(mission, "workspace_id", "")),
            ),
        )

        # 3. Look up the program_id for this mission (Mission has no
        #    program_id column — programs and missions are linked via
        #    ProgramRun.mission_id). If no run exists, program_id stays
        #    None and we still persist the critique at the mission level.
        program_id = await self._lookup_program_id_for_mission(mission.id)

        # 4. Persist the critique row. CritiqueService never commits —
        #    the caller of _trigger_critique_analysis owns the
        #    transaction. The mission_executor orchestrator has already
        #    committed the mission state by this point, so the new
        #    critique row is written in a follow-up transaction.
        critique_service = CritiqueService(self.session)  # type: ignore[attr-defined]
        await critique_service.create_from_critic(
            user_id=int(getattr(mission, "user_id", 0) or 0),
            workspace_id=str(getattr(mission, "workspace_id", "")),
            mission_id=mission.id,
            program_id=program_id,
            critic_output=critic_output,
            critic_kind="critic",
        )

        # 5. If the mission belongs to a program, feed the improvement
        #    batch into the program's learning_brief (non-destructive
        #    merge).
        if program_id is not None:
            try:
                from app.services.mission_program_service import (
                    MissionProgramService,
                )

                program_service = MissionProgramService(self.session)  # type: ignore[attr-defined]
                await program_service.apply_improvement_batch(
                    user_id=int(getattr(mission, "user_id", 0) or 0),
                    program_id=program_id,
                    batch=batch,
                )
                logger.info(
                    "critic.improvements_applied mission_id=%s program_id=%s "
                    "adjustments=%d tool_suggestions=%d",
                    mission.id,
                    program_id,
                    len(batch.plan_adjustments),
                    len(batch.tool_suggestions),
                )
            except Exception as apply_err:
                logger.warning(
                    "critic.improvements_apply_failed mission_id=%s program_id=%s: %s",
                    mission.id,
                    program_id,
                    apply_err,
                )

        logger.info(
            "critic.analysis_completed mission_id=%s score_overall=%s "
            "recommendation=%s",
            mission.id,
            critic_output.score_overall,
            batch.overall_recommendation,
        )

    async def _lookup_program_id_for_mission(
        self, mission_id: Any
    ) -> Any:
        """Find the most-recent ProgramRun.program_id for a given mission.

        Returns ``None`` if the mission has no ProgramRun rows (i.e. it
        was fired outside any program). The lookup is defensive: a
        failure to query ProgramRun is logged and treated as "no program"
        so the critic surface stays mission-level when the program
        association is unavailable.
        """
        try:
            from app.models.mission_program_models import ProgramRun

            result = await self.session.execute(  # type: ignore[attr-defined]
                select(ProgramRun.program_id)
                .where(ProgramRun.mission_id == mission_id)
                .order_by(ProgramRun.created_at.desc())
                .limit(1)
            )
            row = result.first()
            return row[0] if row else None
        except Exception as lookup_err:
            logger.debug(
                "critic.program_lookup_failed mission_id=%s: %s",
                mission_id,
                lookup_err,
            )
            return None

    # ── Logging ───────────────────────────────────────────────────────────────

    async def _log(
        self,
        db,
        # MissionLog.mission_id and .task_id are typed as `Mapped[str]` in
        # `app/models/mission_models.py` (DB column `UUID(as_uuid=True)`),
        # and all call sites pass ORM attributes (`mission.id`, `task.id`)
        # that are also `str` at the type level. Accept `str` to match.
        mission_id: str,
        task_id: str | None,
        level: str,
        message: str,
        extra_data: dict = None,
    ):
        try:
            log = MissionLog(
                mission_id=mission_id,
                task_id=task_id,
                level=level,
                message=message,
                data=extra_data or {},
            )
            db.add(log)
            await db.commit()
            logger.log(
                getattr(logging, level.upper(), logging.INFO),
                f"[Mission {mission_id}] {message}",
            )
        except Exception as e:
            logger.error("Failed to create log entry: %s", e)

    # ── Depth policy audit event ──────────────────────────────────────────

    async def _emit_depth_event(
        self,
        db,
        mission,
        task,
        depth_decision,
        *,
        risk: str = "low",
        uncertainty: float = 0.5,
    ) -> None:
        """Emit a depth_decided substrate event for audit/replay.

        Uses the caller's `db` session (orchestrator fix 2026-06-12):
        the previous implementation opened its own AsyncSessionLocal()
        which committed the event in a SEPARATE transaction from the
        mission execution.  That caused audit/replay divergence: if the
        parent mission transaction rolled back, the depth event would
        stay in the DB.  Using the caller's session keeps the event
        atomically consistent with the parent transaction.

        Wrapped in try/except so a failure to write the audit event does
        not abort mission execution (audit is non-critical).
        """
        try:
            from app.services.substrate.event_log import get_event_log

            audit_event = self.depth_policy.build_audit_event(
                depth_decision,
                risk=risk,
                uncertainty=uncertainty,
                budget_remaining_usd=Decimal(str(getattr(mission, "budget_remaining", "5.00") or "5.00")),
                prior_failures=getattr(task, "prior_failures", 0) or 0,
                retry_count=getattr(task, "retry_count", 0) or 0,
                step_id=str(task.id),
                mission_id=str(mission.id),
                workspace_id=getattr(mission, "workspace_id", None),
                user_id=getattr(mission, "user_id", None),
            )

            # Use a run_id equal to mission_id for substrate events
            run_id = str(mission.id)

            event_log = get_event_log()
            await event_log.append(
                db,
                run_id,
                [{
                    "type": SubstrateEventType.DEPTH_DECIDED,
                    "payload": audit_event.model_dump(),
                    "actor": "depth_policy",
                    "task_id": str(task.id),
                    "mission_id": str(mission.id),
                }],
            )

            logger.debug(
                "Depth event emitted: task=%s level=%s hitl=%s",
                task.id,
                depth_decision.level.value,
                depth_decision.escalate_to_hitl,
            )
        except Exception as e:
            # Depth audit is non-critical — log and continue
            logger.debug("Failed to emit depth event: %s", e)

    # ── Planning (delegated) ──────────────────────────────────────────────────

    async def plan_mission(self, mission_id: UUID) -> dict[str, Any]:
        """Plan a mission — delegates to MissionPlanner."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Mission).where(Mission.id == str(mission_id)))
            mission = result.scalars().first()
            if mission:
                self.model_router = self._get_model_router(user_id=str(mission.user_id))

        return await self.planner.plan_mission(mission_id)


# ── Module-level singleton ────────────────────────────────────────────────────

_executor_instance = None


def get_mission_executor() -> MissionExecutor:
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = MissionExecutor()
    return _executor_instance
