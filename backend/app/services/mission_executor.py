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
    MissionTask as MT,
    MissionTaskStatus,
)
from app.orchestration.human_interrupt import HumanInterrupt, get_hitl_manager
from app.services.browser_task_runner import BrowserTaskRunner
from app.services.cost_tracker import CostTracker
from app.services.llm_executor import LlmExecutor
from app.services.mission_errors import MissionError, PermanentMissionError, RetryableMissionError
from app.services.mission_planner import MissionPlanner
from app.services.task_executor import TaskExecutor

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

    # ── Shared service accessors ──────────────────────────────────────────────

    def _get_model_router(self):
        if self.model_router is None:
            try:
                ModelRouter = _import_model_router()
                self.model_router = ModelRouter()
                logger.info("ModelRouter loaded successfully")
            except PermanentMissionError as e:
                logger.error(f"Permanent error loading ModelRouter: {e}")
                self.model_router = None
            except Exception as e:
                logger.warning(f"Could not load ModelRouter: {e}")
                self.model_router = None
        return self.model_router

    def _get_rag_service(self):
        if self.rag_service is None:
            try:
                RAGService = _import_rag_service()
                self.rag_service = RAGService()
                logger.info("RAGService loaded successfully")
            except PermanentMissionError as e:
                logger.error(f"Permanent error loading RAGService: {e}")
                self.rag_service = None
            except Exception as e:
                logger.warning(f"Could not load RAGService: {e}")
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

    async def _update_step_status(self, db, mission_id: str, step_index: int,
                                   status: str, result: dict = None, error: str = None):
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
                    db, mission_id, step.id, "info",
                    f"Task {step.title} state transition: {prev_state} → {status}",
                    extra_data={
                        "actor": "mission_executor",
                        "prev_state": prev_state,
                        "next_state": status,
                        "cause": error if error else ("completed" if status == "completed" else "status_update"),
                        "task_id": str(step.id),
                        "task_type": step.task_type,
                    },
                )
        except Exception as db_error:
            logger.error(f"Failed to update step status: {db_error}")
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

        if new_status in (MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.ABORTED):
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

    async def execute_mission(self, mission_id: UUID) -> dict[str, Any]:
        """Execute a mission — main orchestrator loop."""

        async with AsyncSessionLocal() as db:
            with tracer.start_as_current_span("mission.execute") as span:
                span.set_attribute("mission.id", str(mission_id))

                try:
                    result = await db.execute(
                        select(Mission)
                        .where(Mission.id == str(mission_id))
                        .with_for_update()
                    )
                    mission = result.scalars().first()
                    if not mission:
                        logger.error(f"Mission {mission_id} not found")
                        span.set_attribute("mission.error", "not_found")
                        return {"success": False, "error": "Mission not found"}

                    # Validate mission is still in a runnable state after acquiring lock
                    if mission.status not in (MissionStatus.QUEUED, MissionStatus.PLANNED):
                        logger.warning(
                            f"Mission {mission_id} cannot execute from '{mission.status}' state"
                        )
                        return {
                            "success": False,
                            "error": f"Cannot execute mission in '{mission.status}' state",
                        }

                    span.set_attribute("mission.user_id", str(mission.user_id))
                    span.set_attribute("mission.title", mission.title)

                    # Wire ModelRouter with user context for BYOK key resolution
                    ModelRouter = _import_model_router()
                    self.model_router = ModelRouter(user_id=str(mission.user_id))

                    # Wire HITLManager for human approval checks
                    self.hitl_manager = get_hitl_manager()

                    prev_status = mission.status
                    mission.status = MissionStatus.EXECUTING
                    mission.started_at = datetime.now(UTC)
                    await db.commit()

                    await self._log(
                        db, mission.id, None, "info",
                        f"Starting mission: {mission.title}",
                        extra_data={
                            "actor": "mission_executor",
                            "prev_state": prev_status,
                            "next_state": MissionStatus.EXECUTING,
                            "cause": "Mission execution started",
                        },
                    )

                    task_result = await db.execute(
                        select(MT)
                        .where(MT.mission_id == str(mission_id))
                        .order_by(MT.order_index)
                    )
                    tasks = list(task_result.scalars().all())

                    if not tasks:
                        await self._log(db, mission.id, None, "error", "No tasks found - mission may need planning first")
                        mission.status = MissionStatus.FAILED
                        mission.error_message = "No tasks to execute. Run mission planning first."
                        mission.completed_at = datetime.now(UTC)
                        await db.commit()
                        return {"success": False, "error": "No tasks to execute - planning required"}

                    task_map = {str(t.id): t for t in tasks}

                    completed: set = set()
                    failed: set = set()
                    skipped: set = set()

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
                                db, mission.id, None, "warning",
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
                            if task.status not in [MissionTaskStatus.PENDING, MissionTaskStatus.RUNNING]:
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
                                # Check for human approval requirement before execution
                                if getattr(task, 'approval_required', False) and self.hitl_manager:
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
                                        db, mission.id, task.id, "info",
                                        f"Mission paused — awaiting human approval for: {task.title}",
                                    )
                                    return {"success": True, "status": MissionStatus.PAUSED}

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

                                    await self._log(db, mission.id, task.id, "info", f"Task completed: {task.title}")
                                else:
                                    if (task.retry_count or 0) < (task.max_retries or 0):
                                        task.retry_count = (task.retry_count or 0) + 1
                                        task.status = MissionTaskStatus.PENDING
                                        await self._log(
                                            db,
                                            mission.id,
                                            task.id,
                                            "warning",
                                            f"Task failed, retrying ({task.retry_count}/{task.max_retries}): {result.get('error')}",
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
                                            f"Task failed after {task.max_retries} retries: {result.get('error')}",
                                        )
                                        await self.task_exec._apply_fallback(db, mission, task, result.get("error"))

                            except Exception as e:
                                logger.exception(f"Error executing task {task.id}")
                                failed.add(str(task.id))
                                task.status = MissionTaskStatus.FAILED
                                task.completed_at = datetime.now(UTC)
                                await self._log(db, mission.id, task.id, "error", f"Exception: {e!s}")

                            await db.commit()

                    mission.completed_at = datetime.now(UTC)
                    prev_status = mission.status

                    if failed:
                        mission.status = MissionStatus.FAILED
                        mission.error_message = f"{len(failed)} tasks failed"
                        span.set_attribute("mission.status", MissionStatus.FAILED)
                        span.set_attribute("mission.tasks_failed", len(failed))
                        await self._log(
                            db, mission.id, None, "error",
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
                            db, mission.id, None, "info",
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
                        logger.info(f"Analytics calculated for mission {mission.id}")
                    except Exception as analytics_error:
                        logger.warning(f"Non-critical failure in analytics: {analytics_error}")

                    await db.commit()

                    # Audit log
                    try:
                        from app.api.middleware.audit import log_event
                        await log_event(
                            mission.user_id,
                            f"mission_{mission.status}",
                            {"mission_id": str(mission.id), "title": mission.title, "completed": len(completed), "failed": len(failed)},
                        )
                    except Exception as audit_error:
                        logger.warning(f"Non-critical failure in audit log: {audit_error}")

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
                        logger.warning(f"Non-critical failure in Linear sync: {linear_err}")

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
                        "results": mission.results,
                    }

                except PermanentMissionError as e:
                    logger.error(f"Permanent error executing mission {mission_id}: {e}")
                    await self._transition_status(
                        db, mission, MissionStatus.FAILED,
                        cause=f"Permanent error: {e}",
                        error_message=str(e),
                        level="error",
                    )
                    return {"success": False, "error": str(e), "permanent": True}
                except RetryableMissionError as e:
                    logger.warning(f"Retryable error executing mission {mission_id}: {e}")
                    raise
                except Exception as e:
                    logger.exception(f"Error executing mission {mission_id}")
                    await self._transition_status(
                        db, mission, MissionStatus.FAILED,
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
                return

            await improvement_loop.on_mission_complete(
                mission_id=str(mission.id),
                agent_id=mission.agent_id,
                success=(mission.status == MissionStatus.COMPLETED),
                metadata={
                    "title": mission.title,
                    "task_count": len(mission.tasks) if hasattr(mission, "tasks") else 0,
                    "error_message": mission.error_message,
                },
            )

            logger.info(f"Improvement analysis completed for mission {mission.id}")
        except Exception as improvement_error:
            logger.warning(f"Non-critical failure in improvement analysis: {improvement_error}")

    # ── Logging ───────────────────────────────────────────────────────────────

    async def _log(self, db, mission_id: UUID, task_id: UUID | None, level: str, message: str, extra_data: dict = None):
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
            logger.error(f"Failed to create log entry: {e}")

    # ── Planning (delegated) ──────────────────────────────────────────────────

    async def plan_mission(self, mission_id: UUID) -> dict[str, Any]:
        """Plan a mission — delegates to MissionPlanner."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Mission).where(Mission.id == str(mission_id))
            )
            mission = result.scalars().first()
            if mission:
                ModelRouter = _import_model_router()
                self.model_router = ModelRouter(user_id=str(mission.user_id))

        return await self.planner.plan_mission(mission_id)


# ── Module-level singleton ────────────────────────────────────────────────────

_executor_instance = None


def get_mission_executor() -> MissionExecutor:
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = MissionExecutor()
    return _executor_instance
