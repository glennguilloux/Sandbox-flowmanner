"""Mission command handlers — mutation operations with explicit transactions."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

logger = logging.getLogger(__name__)
import uuid  # FastAPI/Pydantic v2 needs uuid at runtime for path param resolution
from typing import TYPE_CHECKING

from app.models.mission_advanced_models import MissionTemplate
from app.models.mission_models import (
    AbortReason,
    Mission,
    MissionLog,
    MissionStatus,
    MissionTask,
    MissionTaskStatus,
)
from app.schemas.mission import (
    MissionCreate,
    MissionExecuteRequest,
    MissionExecutionStatus,
    MissionImprovementCreate,
    MissionImprovementResponse,
    MissionLogCreate,
    MissionTaskCreate,
    MissionTaskResponse,
    MissionTaskUpdate,
    MissionUpdate,
    SelectPlanCandidateRequest,
)
from app.services.mission_cache import invalidate_mission_cache, invalidate_user_caches
from app.services.mission_errors import (
    MissionNotFoundError,
    MissionTransitionConflictError,
    MissionValidationError,
)
from app.services.mission_planner import MissionPlanner
from app.services.mission_service import (
    create_mission,
    create_mission_log,
    create_mission_task,
    delete_mission,
    get_mission_tasks,
    require_mission_access,
    update_mission,
)
from app.services.self_improvement import SelfImprovementEngine

from .base import (
    CommandHandlerBase,
    _make_execution_status,
    _schedule_fire_and_forget,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

    from .audit import AuditService


async def _rebuild_tasks_from_candidate(
    session: AsyncSession,
    mission_id: uuid.UUID,
    plan_id: str,
) -> list[MissionTask] | None:
    """Delete existing PENDING tasks for a mission and rebuild them from
    a MissionPlanCandidate.tasks_json row.  Returns the new task list, or
    None if no candidate row matched.

    Caller owns the transaction.  No commit() inside this function.
    """
    from app.models.mission_advanced_models import MissionPlanCandidate

    cand_row = (
        (
            await session.execute(
                select(MissionPlanCandidate).where(
                    MissionPlanCandidate.mission_id == str(mission_id),
                    MissionPlanCandidate.plan_id == plan_id,
                )
            )
        )
        .scalars()
        .first()
    )
    if cand_row is None:
        return None

    task_defs = cand_row.tasks_json
    if not isinstance(task_defs, list):
        return None

    # Delete PENDING tasks only — preserve completed/running/failed history.
    existing = await get_mission_tasks(session, mission_id)
    for t in existing:
        if t.status == MissionTaskStatus.PENDING:
            await session.delete(t)
    await session.flush()

    new_tasks: list[MissionTask] = []
    for idx, task_def in enumerate(task_defs):
        if not isinstance(task_def, dict):
            continue
        new_task = MissionTask(
            id=str(uuid4()),
            mission_id=str(mission_id),
            title=task_def.get("title", f"Task {idx + 1}"),
            description=task_def.get("description", ""),
            task_type=task_def.get("task_type", "llm"),
            order_index=idx,
            dependencies=task_def.get("dependencies", []),
            input_data=task_def.get("input_data"),
            assigned_agent_id=task_def.get("assigned_agent_id"),
            assigned_model=task_def.get("assigned_model"),
            status=MissionTaskStatus.PENDING,
            max_retries=task_def.get("max_retries", 3),
        )
        session.add(new_task)
        new_tasks.append(new_task)
    await session.flush()
    return new_tasks


class MissionCommandHandlers(CommandHandlerBase):
    def __init__(
        self,
        session: AsyncSession,
        audit: AuditService | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(session)
        self.audit = audit
        self._request_id = request_id

    # ── Create ───────────────────────────────────────────────────────────────

    async def create_mission(self, user: User, payload: MissionCreate, workspace_id: str | None = None):
        async def _op():
            result = await create_mission(
                self.session,
                title=payload.title,
                description=payload.description or "",
                mission_type=payload.mission_type,
                priority=payload.priority,
                user_id=user.id,
                status="pending",
                workspace_id=workspace_id,
            )
            if self.audit:
                self.audit.mission_created(
                    mission_id=result.id,
                    actor_id=user.id,
                    request_id=self._request_id,
                    title=payload.title,
                    mission_type=payload.mission_type,
                )
            # Fire-and-forget cache invalidation (failure logged)
            _schedule_fire_and_forget(invalidate_user_caches(user.id))

            return result

        return await self.wrap_command(_op)

    # ── CRUD mutations ──────────────────────────────────────────────────────

    async def update_mission(self, user: User, mission_id: uuid.UUID, payload: MissionUpdate):
        mission = await require_mission_access(self.session, mission_id, user.id)
        old_status = mission.status.value if hasattr(mission.status, "value") else mission.status

        async def _op():
            updated = await update_mission(
                self.session,
                mission_id,
                title=payload.title,
                description=payload.description,
                status=payload.status,
                priority=payload.priority,
                mission_type=payload.mission_type,
                error_message=payload.error_message,
                results=payload.results,
                tokens_used=payload.tokens_used,
                actual_cost=payload.actual_cost,
            )
            if updated is None:
                raise MissionNotFoundError(f"Mission {mission_id} not found")
            new_status = updated.status.value if hasattr(updated.status, "value") else updated.status
            if self.audit:
                self.audit.mission_updated(
                    mission_id=mission_id,
                    actor_id=user.id,
                    old_status=old_status,
                    new_status=new_status,
                    request_id=self._request_id,
                )
            _schedule_fire_and_forget(invalidate_mission_cache(user.id, str(mission_id)))
            return updated

        return await self.wrap_command(_op)

    async def delete_mission(self, user: User, mission_id: uuid.UUID) -> None:
        mission = await require_mission_access(self.session, mission_id, user.id)
        old_status = mission.status.value if hasattr(mission.status, "value") else mission.status

        async def _op():
            if not await delete_mission(self.session, mission_id, deleted_by=user.id):
                raise MissionNotFoundError(f"Mission {mission_id} not found")
            if self.audit:
                self.audit.mission_deleted(
                    mission_id=mission_id,
                    actor_id=user.id,
                    old_status=old_status,
                    request_id=self._request_id,
                )
            # Invalidate both user-wide list caches and per-mission caches
            _schedule_fire_and_forget(invalidate_user_caches(user.id))
            _schedule_fire_and_forget(invalidate_mission_cache(user.id, str(mission_id)))

        await self.wrap_command(_op)

    # ── Tasks ────────────────────────────────────────────────────────────────

    async def create_task(self, user: User, mission_id: uuid.UUID, payload: MissionTaskCreate) -> MissionTask:
        mission = await require_mission_access(self.session, mission_id, user.id)

        async def _op():
            return await create_mission_task(
                self.session,
                mission_id,
                payload.title or "Untitled Task",
                payload.task_type or "general",
                MissionTaskStatus.PENDING,
                payload.order_index,
                payload.input_data,
                payload.description,
                payload.assigned_agent_id,
                payload.assigned_model,
            )

        return await self.wrap_command(_op)

    async def update_task(
        self,
        user: User,
        mission_id: uuid.UUID,
        task_id: uuid.UUID,
        payload: MissionTaskUpdate,
    ) -> MissionTask:
        mission = await require_mission_access(self.session, mission_id, user.id)

        async def _op():
            result = await self.session.execute(
                select(MissionTask).where(
                    MissionTask.id == task_id,
                    MissionTask.mission_id == mission_id,
                )
            )
            task = result.scalar_one_or_none()
            if task is None:
                raise MissionNotFoundError(f"Task {task_id} not found in mission {mission_id}")
            if payload.status is not None:
                task.status = payload.status
            if payload.output_data is not None:
                task.output_data = payload.output_data
            if payload.error_message is not None:
                task.error_message = payload.error_message
            if payload.tokens_used is not None:
                task.tokens_used = payload.tokens_used
            await self.session.flush()
            await self.session.refresh(task)
            return task

        return await self.wrap_command(_op)

    async def select_plan_candidate(
        self,
        user: User,
        mission_id: uuid.UUID,
        payload: SelectPlanCandidateRequest,
    ) -> list[MissionTaskResponse]:
        """Pre-select a non-default plan candidate. Rebuilds MissionTask
        rows from MissionPlanCandidate.tasks_json so the next execute call
        uses the chosen plan.  No-op execution-wise — the actual run is the
        caller's job.

        Returns 404 if no candidate matches. Wrapped in wrap_command() so
        the task rebuild is atomic with the plan_metadata bookkeeping.
        """
        await require_mission_access(self.session, mission_id, user.id)

        async def _op():
            # Verify candidate exists FIRST so callers get a clean 404,
            # not a half-rebuilt mission.
            cand_check = await _rebuild_tasks_from_candidate(self.session, mission_id, payload.plan_id)
            if cand_check is None:
                raise MissionNotFoundError(f"No plan candidate '{payload.plan_id}' for mission {mission_id}")
            new_tasks = cand_check

            # Stash the override in mission.plan["plan_selection"] so
            # downstream tooling can tell auto-pick apart from explicit
            # user override.
            plan_meta = {}
            mission_row = (
                (await self.session.execute(select(Mission).where(Mission.id == str(mission_id)))).scalars().first()
            )
            if mission_row is not None and isinstance(mission_row.plan, dict):
                plan_meta = dict(mission_row.plan)
            plan_meta.setdefault("plan_selection", {})
            plan_meta["plan_selection"]["override_id"] = payload.plan_id
            if mission_row is not None:
                mission_row.plan = plan_meta

            # Emit plan_override_selected substrate event (best-effort).
            try:
                from app.models.substrate_models import SubstrateEventType
                from app.services.substrate.event_log import get_event_log

                await get_event_log().append(
                    self.session,
                    str(mission_id),
                    [
                        {
                            "type": SubstrateEventType.PLAN_OVERRIDE_SELECTED,
                            "payload": {
                                "override_id": payload.plan_id,
                                "actor_id": str(user.id),
                                "task_count": len(new_tasks),
                            },
                            "actor": "user",
                            "mission_id": str(mission_id),
                        }
                    ],
                )
            except Exception as ev_err:
                logger.debug("plan_override_selected_event_failed: %s", ev_err)

            # Audit log (best-effort, like the rest of the command handlers).
            if self.audit is not None:
                self.audit.mission_updated(
                    mission_id=mission_id,
                    actor_id=user.id,
                    old_status="select_plan_candidate",
                    new_status="select_plan_candidate",
                    request_id=self._request_id,
                    override_plan_id=payload.plan_id,
                    task_count=len(new_tasks),
                )

            _schedule_fire_and_forget(invalidate_mission_cache(user.id, str(mission_id)))
            return new_tasks

        tasks = await self.wrap_command(_op)
        return [MissionTaskResponse.model_validate(t) for t in tasks]

    # ── Logs ─────────────────────────────────────────────────────────────────

    async def create_log(self, user: User, mission_id: uuid.UUID, payload: MissionLogCreate) -> MissionLog:
        mission = await require_mission_access(self.session, mission_id, user.id)

        async def _op():
            return await create_mission_log(self.session, mission_id, payload.level, payload.message)

        return await self.wrap_command(_op)

    # ── Planning ─────────────────────────────────────────────────────────────

    async def plan_mission(self, user: User, mission_id: uuid.UUID) -> MissionExecutionStatus:
        mission = await require_mission_access(self.session, mission_id, user.id)

        async def _op():
            from app.services.llm_router import ModelRouter

            planner = MissionPlanner(
                get_model_router=lambda: ModelRouter(user_id=str(user.id)),
            )
            result = await planner.plan_mission(mission_id)
            if not result.get("success"):
                raise MissionValidationError(result.get("error", "Planning failed"))
            tasks = await get_mission_tasks(self.session, mission_id)
            return _make_execution_status(mission, tasks)

        return await self.wrap_command(_op)

    # ── Execution ────────────────────────────────────────────────────────────

    async def execute_mission(
        self,
        user: User,
        mission_id: uuid.UUID,
        payload: MissionExecuteRequest | None = None,
    ) -> MissionExecutionStatus:
        mission = await require_mission_access(self.session, mission_id, user.id)

        old_status = mission.status.value if hasattr(mission.status, "value") else mission.status

        async def _op():
            # Phase 8.1 GA: UnifiedExecutor is the sole execution path.
            from app.services.substrate.adapters import mission_to_workflow
            from app.services.substrate.executor import get_unified_executor

            unified = get_unified_executor()

            # Round-trip: honor MissionExecuteRequest.selected_plan_id
            # by rebuilding the task list from the chosen candidate
            # before the substrate UnifiedExecutor runs.  An unknown
            # plan_id is logged + skipped (we never fail execution
            # because of a missing override).
            tasks = None
            if payload is not None and getattr(payload, "selected_plan_id", None):
                rebuilt = await _rebuild_tasks_from_candidate(self.session, mission_id, payload.selected_plan_id)
                if rebuilt is None:
                    logger.warning(
                        "execute_mission_selected_plan_id_not_found mission_id=%s selected_plan_id=%s",
                        str(mission_id),
                        payload.selected_plan_id,
                    )
                else:
                    tasks = rebuilt
            if tasks is None:
                tasks = await get_mission_tasks(self.session, mission_id)

            workflow = mission_to_workflow(mission, tasks)

            # GC3: mint a FRESH substrate_run_id for this execution and
            # persist it on mission.plan BEFORE the executor runs, so the
            # run is addressable (abort-by-run_id, event-log scoping,
            # replay) and a retry cannot accidentally reuse attempt-1's id.
            # run_id is RUN-SCOPED (GC2) — the event-log idempotency
            # key is keyed on it, so a fresh id == fresh keys == no
            # silent replay of attempt-1 output (FM-1).
            run_id = str(uuid4())
            if mission.plan is None:
                mission.plan = {}
            mission.plan["substrate_run_id"] = run_id
            await self.session.flush()

            strategy_result = await unified.execute(self.session, workflow, run_id=run_id)
            result = {
                "success": strategy_result.success,
                "status": strategy_result.status,
                "completed_tasks": len(strategy_result.completed_nodes),
                "failed_tasks": len(strategy_result.failed_nodes),
                "results": strategy_result.data,
                "error": strategy_result.error,
            }

            # Track analytics event (fire-and-forget)
            try:
                from app.services.analytics_service import EventType, track_event

                if result.get("success"):
                    await track_event(
                        self.session,
                        str(user.id),
                        EventType.WORKFLOW_EXECUTED_SUCCESS,
                        properties={"mission_id": str(mission_id)},
                    )
                else:
                    await track_event(
                        self.session,
                        str(user.id),
                        EventType.WORKFLOW_EXECUTED_FAILED,
                        properties={
                            "mission_id": str(mission_id),
                            "error": result.get("error", ""),
                        },
                    )
            except Exception:
                logger.debug("analytics_track_failed", exc_info=True)

            tasks = await get_mission_tasks(self.session, mission_id)
            new_status = mission.status.value if hasattr(mission.status, "value") else mission.status
            if self.audit:
                self.audit.mission_executed(
                    mission_id=mission_id,
                    actor_id=user.id,
                    old_status=old_status,
                    new_status=new_status,
                    request_id=self._request_id,
                )
            return MissionExecutionStatus(
                mission_id=mission_id,
                status=mission.status,
                total_tasks=len(tasks),
                completed_tasks=sum(1 for t in tasks if t.status == MissionTaskStatus.COMPLETED),
                failed_tasks=sum(1 for t in tasks if t.status == MissionTaskStatus.FAILED),
                total_tokens_used=mission.tokens_used or 0,
                started_at=mission.started_at,
                estimated_completion=None,
            )

        return await self.wrap_command(_op)

    async def execute_async(
        self,
        user: User,
        mission_id: uuid.UUID,
        payload: MissionExecuteRequest | None = None,
    ) -> MissionExecutionStatus:
        # NOTE: not wrapped in wrap_command — multi-commit flow:
        #   1. commit status → QUEUED so the background task sees it
        #   2. commit transition log separately
        #   3. Dispatch to Celery (durable, retryable) instead of fire-and-forget
        mission = await require_mission_access(self.session, mission_id, user.id)

        # Round-trip hook — accept selected_plan_id so the Celery worker
        # dispatches against the rebuilt task list.  Unknown IDs log and
        # fall through.
        if payload is not None and getattr(payload, "selected_plan_id", None):
            rebuilt = await _rebuild_tasks_from_candidate(self.session, mission_id, payload.selected_plan_id)
            if rebuilt is None:
                logger.warning(
                    "execute_async_selected_plan_id_not_found mission_id=%s selected_plan_id=%s",
                    str(mission_id),
                    payload.selected_plan_id,
                )

        prev_status = mission.status.value if hasattr(mission.status, "value") else mission.status
        mission.status = MissionStatus.QUEUED

        # GC3: mint a FRESH substrate_run_id and persist it on mission.plan
        # so the Celery worker (and any future retry) executes against a
        # run-scoped idempotency space (GC2) and never silently replays
        # attempt-1 output into attempt-2 (FM-1).
        run_id = str(uuid4())
        if mission.plan is None:
            mission.plan = {}
        mission.plan["substrate_run_id"] = run_id

        await self.session.commit()

        # Log the transition
        log = MissionLog(
            mission_id=mission_id,
            level="info",
            message=f"Mission queued for async execution (was: {prev_status})",
            data={
                "actor": "api",
                "prev_state": prev_status,
                "next_state": MissionStatus.QUEUED,
                "cause": "Async execution queued by user",
                "user_id": str(user.id),
                "substrate_run_id": run_id,
            },
        )
        self.session.add(log)
        await self.session.commit()

        # B3: Dispatch to Celery for durable execution
        try:
            from app.tasks.mission_execution import dispatch_mission_execution

            dispatch_mission_execution(str(mission_id), user.id, run_id=run_id)
        except Exception:
            # Fallback: use UnifiedExecutor in a background task
            _fallback_log = __import__("structlog").get_logger(__name__)
            _fallback_log.warning("celery_dispatch_failed_fallback", mission_id=str(mission_id))

            async def _run_execution():
                from app.database import AsyncSessionLocal
                from app.services.substrate.adapters import mission_to_workflow
                from app.services.substrate.executor import get_unified_executor

                async with AsyncSessionLocal() as db_session:
                    result = await db_session.execute(select(Mission).where(Mission.id == str(mission_id)))
                    m = result.scalars().first()
                    if m:
                        tasks = await get_mission_tasks(db_session, mission_id)
                        workflow = mission_to_workflow(m, tasks)
                        await get_unified_executor().execute(db_session, workflow)

            import asyncio

            asyncio.create_task(_run_execution())

        tasks = await get_mission_tasks(self.session, mission_id)
        return MissionExecutionStatus(
            mission_id=mission_id,
            status=MissionStatus.QUEUED,
            total_tasks=len(tasks),
            completed_tasks=sum(1 for t in tasks if t.status == MissionTaskStatus.COMPLETED),
            failed_tasks=sum(1 for t in tasks if t.status == MissionTaskStatus.FAILED),
            total_tokens_used=mission.tokens_used or 0,
            started_at=mission.started_at,
        )

    # ── Abort ────────────────────────────────────────────────────────────────

    async def abort_mission(
        self, user: User, mission_id: uuid.UUID, reason_str: str = "user_requested"
    ) -> MissionExecutionStatus:
        # NOTE: not wrapped in wrap_command — multi-commit flow:
        #   1. SELECT … FOR UPDATE locks the mission row atomically
        #   2. commit status → ABORTED + completed_at
        #   3. commit transition log separately
        #   Side-effects (WS emit, analytics) are fire-and-forget
        try:
            abort_reason = AbortReason(reason_str)
        except ValueError:
            raise MissionValidationError(
                f"Invalid abort reason: '{reason_str}'. Valid reasons: {[r.value for r in AbortReason]}"
            )

        # SELECT ... FOR UPDATE to prevent TOCTOU races
        result = await self.session.execute(select(Mission).where(Mission.id == str(mission_id)).with_for_update())
        mission = result.scalars().first()
        if mission is None:
            raise MissionNotFoundError("Mission not found")
        # Workspace-aware access check (post-lock to avoid TOCTOU)
        if mission.workspace_id:
            from sqlalchemy import select as _sel

            from app.models.workspace_models import WorkspaceMember

            member_result = await self.session.execute(
                _sel(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == mission.workspace_id,
                    WorkspaceMember.user_id == user.id,
                    WorkspaceMember.is_active == True,
                )
            )
            if member_result.scalar_one_or_none() is None:
                raise MissionNotFoundError("Mission not found")
        elif mission.user_id != user.id:
            raise MissionNotFoundError("Mission not found")

        abortable = {
            MissionStatus.PENDING,
            MissionStatus.PLANNING,
            MissionStatus.PLANNED,
            MissionStatus.EXECUTING,
            MissionStatus.QUEUED,
            MissionStatus.RUNNING,
            MissionStatus.PAUSED,
        }
        if mission.status not in abortable:
            raise MissionTransitionConflictError(
                f"Cannot abort mission in '{mission.status}' state. Only active missions can be aborted."
            )

        prev_status = mission.status.value if hasattr(mission.status, "value") else mission.status
        mission.status = MissionStatus.ABORTED
        mission.error_message = f"Aborted: {abort_reason.value} (was: {prev_status})"
        mission.completed_at = datetime.now(UTC)
        await self.session.commit()

        # Phase 3.2: Also signal UnifiedExecutor abort if a run is active
        try:
            from app.services.substrate.executor import get_unified_executor

            unified = get_unified_executor()
            # The mission's plan may hold a substrate_run_id from the last execution
            run_id = (mission.plan or {}).get("substrate_run_id")
            if run_id:
                await unified.abort(run_id, reason=abort_reason.value)
            # Also abort by mission_id mapping
            await unified.abort(str(mission_id), reason=abort_reason.value)
        except Exception:
            logger.debug("unified_executor_abort_signal_failed", exc_info=True)

        if self.audit:
            self.audit.mission_aborted(
                mission_id=mission_id,
                actor_id=user.id,
                old_status=prev_status,
                abort_reason=abort_reason.value,
                request_id=self._request_id,
            )

        # Structured state-transition log
        log = MissionLog(
            mission_id=mission_id,
            level="warning",
            message=f"Mission aborted by user (reason: {abort_reason.value})",
            data={
                "actor": "user",
                "prev_state": prev_status,
                "next_state": MissionStatus.ABORTED,
                "cause": f"User requested abort: {abort_reason.value}",
                "user_id": str(user.id),
                "abort_reason": abort_reason.value,
            },
        )
        self.session.add(log)
        await self.session.commit()

        # Fire-and-forget side effects
        try:
            from app.websocket.mission_ws import sio as _sio

            if hasattr(_sio, "emit"):
                await _sio.emit(
                    "mission_aborted",
                    {
                        "mission_id": str(mission_id),
                        "status": MissionStatus.ABORTED,
                        "reason": abort_reason.value,
                        "prev_status": prev_status,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                    room=f"mission_{mission_id}",
                )
        except Exception:
            logger.debug("ws_abort_emit_failed", exc_info=True)
            try:
                from app.services.analytics_service import EventType, track_event

                await track_event(
                    self.session,
                    str(user.id),
                    EventType.WORKFLOW_EXECUTED_FAILED,
                    properties={
                        "mission_id": str(mission_id),
                        "error": "aborted_by_user",
                        "abort_reason": abort_reason.value,
                    },
                )
            except Exception:
                logger.debug("analytics_abort_track_failed", exc_info=True)

        tasks = await get_mission_tasks(self.session, mission_id)
        return MissionExecutionStatus(
            mission_id=mission_id,
            status=MissionStatus.ABORTED,
            total_tasks=len(tasks),
            completed_tasks=sum(1 for t in tasks if t.status == MissionTaskStatus.COMPLETED),
            failed_tasks=sum(1 for t in tasks if t.status == MissionTaskStatus.FAILED),
            total_tokens_used=mission.tokens_used or 0,
            started_at=mission.started_at,
        )

    # ── Lifecycle: Pause / Resume / Retry ────────────────────────────────────

    async def pause_mission(self, user: User, mission_id: uuid.UUID) -> MissionExecutionStatus:
        # NOTE: not wrapped in wrap_command — multi-commit flow:
        #   1. commit status → PAUSED + reset running tasks to PENDING
        #   2. commit transition log separately
        mission = await require_mission_access(self.session, mission_id, user.id)

        if mission.status != MissionStatus.RUNNING:
            raise MissionTransitionConflictError(f"Can only pause a running mission, not '{mission.status}'")

        prev_status = mission.status.value if hasattr(mission.status, "value") else mission.status
        mission.status = MissionStatus.PAUSED

        # Cancel all RUNNING tasks back to PENDING
        task_result = await self.session.execute(
            select(MissionTask).where(
                MissionTask.mission_id == str(mission_id),
                MissionTask.status == MissionTaskStatus.RUNNING,
            )
        )
        for task in task_result.scalars().all():
            task.status = MissionTaskStatus.PENDING

        await self.session.commit()

        if self.audit:
            self.audit.mission_paused(
                mission_id=mission_id,
                actor_id=user.id,
                old_status=prev_status,
                request_id=self._request_id,
            )

        log = MissionLog(
            mission_id=mission_id,
            level="info",
            message=f"Mission paused by user (was: {prev_status})",
            data={
                "actor": "user",
                "prev_state": prev_status,
                "next_state": MissionStatus.PAUSED,
                "cause": "User requested pause",
                "user_id": str(user.id),
            },
        )
        self.session.add(log)
        await self.session.commit()

        tasks = await get_mission_tasks(self.session, mission_id)
        return _make_execution_status(mission, tasks)

    async def resume_mission(self, user: User, mission_id: uuid.UUID) -> MissionExecutionStatus:
        # NOTE: not wrapped in wrap_command — multi-commit flow:
        #   1. commit status → QUEUED
        #   2. commit transition log separately
        mission = await require_mission_access(self.session, mission_id, user.id)

        if mission.status != MissionStatus.PAUSED:
            raise MissionTransitionConflictError(f"Can only resume a paused mission, not '{mission.status}'")

        prev_status = mission.status.value if hasattr(mission.status, "value") else mission.status
        mission.status = MissionStatus.QUEUED
        await self.session.commit()

        if self.audit:
            self.audit.mission_resumed(
                mission_id=mission_id,
                actor_id=user.id,
                old_status=prev_status,
                request_id=self._request_id,
            )

        log = MissionLog(
            mission_id=mission_id,
            level="info",
            message=f"Mission resumed by user (was: {prev_status})",
            data={
                "actor": "user",
                "prev_state": prev_status,
                "next_state": MissionStatus.QUEUED,
                "cause": "User requested resume",
                "user_id": str(user.id),
            },
        )
        self.session.add(log)
        await self.session.commit()

        tasks = await get_mission_tasks(self.session, mission_id)
        return _make_execution_status(mission, tasks)

    async def retry_mission(self, user: User, mission_id: uuid.UUID) -> MissionExecutionStatus:
        # NOTE: not wrapped in wrap_command — multi-commit flow:
        #   1. commit status → PENDING + clear error_message
        #   2. commit transition log separately
        #   3. MissionExecutor.plan_mission runs re-planning (creates internal session)
        mission = await require_mission_access(self.session, mission_id, user.id)

        if mission.status != MissionStatus.FAILED:
            raise MissionTransitionConflictError(f"Can only retry a failed mission, not '{mission.status}'")

        prev_status = mission.status.value if hasattr(mission.status, "value") else mission.status
        mission.status = MissionStatus.PENDING
        mission.error_message = None

        # GC3: mint a FRESH substrate_run_id for the retry. Retrying with the
        # previous run_id is the silent-replay bug (FM-1): the event-log
        # idempotency key is RUN-SCOPED (GC2), so reusing attempt-1's id
        # lets node_executor replay attempt-1 output instead of re-calling the
        # model. The fresh id resets the idempotency space and is persisted
        # on mission.plan so the worker executes attempt-2 in its own scope.
        fresh_run_id = str(uuid4())
        if mission.plan is None:
            mission.plan = {}
        mission.plan["substrate_run_id"] = fresh_run_id

        await self.session.commit()

        if self.audit:
            # GC4 / FM-2: the retry audit is forensic-critical — it MUST
            # survive a rollback of this handler's transaction. Write it in
            # its OWN autonomous session via record_async (MissionLog.mission_id
            # is now a soft reference, no FK). Swallowed + alerted on failure.
            await self.audit.record_async(
                action="mission.retry",
                actor_id=user.id,
                mission_id=mission_id,
                old_status=prev_status,
                new_status=MissionStatus.PENDING.value,
                request_id=self._request_id,
            )

        log = MissionLog(
            mission_id=mission_id,
            level="info",
            message=f"Mission retry initiated by user (was: {prev_status})",
            data={
                "actor": "user",
                "prev_state": prev_status,
                "next_state": MissionStatus.PENDING,
                "cause": "User requested retry",
                "user_id": str(user.id),
            },
        )
        self.session.add(log)
        await self.session.commit()

        from app.services.llm_router import ModelRouter

        planner = MissionPlanner(
            get_model_router=lambda: ModelRouter(user_id=str(user.id)),
        )
        plan_result = await planner.plan_mission(mission_id)
        if not plan_result.get("success"):
            raise MissionValidationError(plan_result.get("error", "Re-planning failed"))

        tasks = await get_mission_tasks(self.session, mission_id)
        return _make_execution_status(mission, tasks)

    # ── Batch Abort ──────────────────────────────────────────────────────────

    async def batch_abort(self, user: User, mission_ids: list[uuid.UUID], reason: str = "user_requested") -> dict:
        # NOTE: not wrapped in wrap_command — single-commit batch flow with
        #   FOR UPDATE: iterates N missions, mutates ORM objects, then one
        #   final commit persists all changes atomically.
        try:
            abort_reason = AbortReason(reason)
        except ValueError:
            raise MissionValidationError(
                f"Invalid abort reason: '{reason}'. Valid reasons: {[r.value for r in AbortReason]}"
            )

        str_ids = [str(mid) for mid in mission_ids]

        result = await self.session.execute(select(Mission).where(Mission.id.in_(str_ids)).with_for_update())
        missions = result.scalars().all()

        results = []
        abortable = {
            MissionStatus.PENDING,
            MissionStatus.PLANNING,
            MissionStatus.PLANNED,
            MissionStatus.EXECUTING,
            MissionStatus.QUEUED,
            MissionStatus.RUNNING,
            MissionStatus.PAUSED,
        }

        # Pre-fetch workspace memberships to avoid N+1 queries
        ws_ids = {m.workspace_id for m in missions if m.workspace_id}
        user_ws_ids: set[str] = set()
        if ws_ids:
            from app.models.workspace_models import WorkspaceMember

            member_result = await self.session.execute(
                select(WorkspaceMember.workspace_id).where(
                    WorkspaceMember.workspace_id.in_(ws_ids),
                    WorkspaceMember.user_id == user.id,
                    WorkspaceMember.is_active == True,
                )
            )
            user_ws_ids = {row[0] for row in member_result.all()}

        for mission in missions:
            # Workspace-aware access check for batch abort
            if (mission.workspace_id and mission.workspace_id not in user_ws_ids) or (
                not mission.workspace_id and mission.user_id != user.id
            ):
                results.append(
                    {
                        "mission_id": str(mission.id),
                        "aborted": False,
                        "error": "Not authorized",
                    }
                )
                continue

            if mission.status not in abortable:
                results.append(
                    {
                        "mission_id": str(mission.id),
                        "aborted": False,
                        "error": f"Cannot abort mission in '{mission.status}' state",
                    }
                )
                continue

            prev_status = mission.status.value if hasattr(mission.status, "value") else mission.status
            mission.status = MissionStatus.ABORTED
            mission.error_message = f"Batch aborted: {abort_reason.value} (was: {prev_status})"
            mission.completed_at = datetime.now(UTC)

            if self.audit:
                self.audit.mission_aborted(
                    mission_id=mission.id,
                    actor_id=user.id,
                    old_status=prev_status,
                    abort_reason=abort_reason.value,
                )

            log = MissionLog(
                mission_id=mission.id,
                level="warning",
                message=f"Mission batch aborted (reason: {abort_reason.value})",
                data={
                    "actor": "user",
                    "prev_state": prev_status,
                    "next_state": MissionStatus.ABORTED,
                    "cause": f"Batch abort: {abort_reason.value}",
                    "user_id": str(user.id),
                },
            )
            self.session.add(log)

            results.append(
                {
                    "mission_id": str(mission.id),
                    "aborted": True,
                    "prev_status": prev_status,
                }
            )

        await self.session.commit()

        return {
            "total_requested": len(mission_ids),
            "total_found": len(missions),
            "total_aborted": sum(1 for r in results if r.get("aborted")),
            "results": results,
        }

    # ── Template ─────────────────────────────────────────────────────────────

    async def create_from_template(self, user: User, template_id: uuid.UUID) -> Mission:
        # NOTE: not wrapped in wrap_command — preserves legacy pattern:
        #   flush to obtain mission.id for FK references, bulk-add child
        #   tasks, then single commit + refresh. (Could be refactored into
        #   wrap_command if the refresh were moved to the caller.)
        result = await self.session.execute(select(MissionTemplate).where(MissionTemplate.id == str(template_id)))
        template = result.scalars().first()
        if template is None:
            raise MissionNotFoundError(f"Template {template_id} not found")

        mission = Mission(
            id=str(uuid4()),
            title=template.name or "Untitled from template",
            description=template.description or "",
            mission_type=template.mission_type,
            priority=template.priority or "medium",
            user_id=user.id,
            status=MissionStatus.PENDING,
            plan=template.default_plan,
            constraints=template.default_constraints,
        )
        self.session.add(mission)
        await self.session.flush()

        default_tasks = template.default_tasks or []
        if isinstance(default_tasks, list):
            for idx, task_def in enumerate(default_tasks):
                if isinstance(task_def, dict):
                    task = MissionTask(
                        id=str(uuid4()),
                        mission_id=mission.id,
                        title=task_def.get("title", f"Task {idx + 1}"),
                        description=task_def.get("description", ""),
                        task_type=task_def.get("task_type", "llm"),
                        order_index=idx,
                        dependencies=task_def.get("dependencies", []),
                        input_data=task_def.get("input_data"),
                        assigned_agent_id=task_def.get("assigned_agent_id"),
                        assigned_model=task_def.get("assigned_model"),
                        status=MissionTaskStatus.PENDING,
                        max_retries=task_def.get("max_retries", 3),
                    )
                    self.session.add(task)

        await self.session.commit()
        await self.session.refresh(mission)
        return mission

    # ── Improvements ─────────────────────────────────────────────────────────

    async def create_improvement(
        self, user: User, mission_id: uuid.UUID, payload: MissionImprovementCreate
    ) -> MissionImprovementResponse:
        # NOTE: not wrapped in wrap_command — SelfImprovementEngine manages its
        #   own persistence internally (generate_strategy creates + commits).
        mission = await require_mission_access(self.session, mission_id, user.id)

        engine = SelfImprovementEngine(self.session, str(user.id))
        improvement = await engine.generate_strategy(
            mission_id,  # type: ignore[arg-type]
            payload.failure_type,
            payload.failure_context or "",
        )
        await self.session.refresh(improvement)
        return MissionImprovementResponse.model_validate(improvement)

    async def apply_improvement(self, user: User, mission_id: uuid.UUID, improvement_id: uuid.UUID) -> bool:
        # NOTE: not wrapped in wrap_command — SelfImprovementEngine manages its
        #   own persistence internally (apply_strategy mutates + commits).
        mission = await require_mission_access(self.session, mission_id, user.id)

        engine = SelfImprovementEngine(self.session, str(user.id))
        return await engine.apply_strategy(improvement_id)  # type: ignore[arg-type]
