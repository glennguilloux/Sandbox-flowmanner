"""Mission query handlers — read-only operations."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

logger = logging.getLogger(__name__)
import uuid  # FastAPI/Pydantic v2 needs uuid at runtime for path param resolution
from typing import TYPE_CHECKING, cast

from app.models.mission_models import (
    Mission,
    MissionStatus,
    MissionTask,
    MissionTaskStatus,
)
from app.schemas.mission import (
    MissionExecutionStatus,
    MissionImprovementResponse,
    MissionListResult,
    MissionLogResponse,
    MissionResponse,
    MissionTaskResponse,
    PlanCandidateResponse,
)
from app.services.mission_analytics import (
    get_failure_analysis,
    get_mission_analytics,
    get_mission_analytics_over_time,
    get_token_usage_breakdown,
)
from app.services.mission_cache import (
    cache_active,
    cache_get,
    cache_get_improvements,
    cache_get_logs,
    cache_get_status,
    cache_list,
    cache_set,
    cache_set_active,
    cache_set_improvements,
    cache_set_list,
    cache_set_logs,
    cache_set_status,
    cache_set_tasks,
)
from app.services.mission_errors import MissionForbiddenError, MissionNotFoundError
from app.services.mission_service import (
    get_mission_logs,
    get_mission_tasks,
    list_missions,
    require_mission_access,
)
from app.services.self_improvement import SelfImprovementEngine

from .base import QueryHandlerBase, _make_execution_status, _schedule_fire_and_forget
from .compat import (
    MissionShim,
    active_missions_from_blueprints,
    get_mission_as_shim,
    get_mission_from_blueprint,
    list_active_from_blueprints,
    list_missions_from_blueprints,
    use_new_reads,
)


@dataclass(slots=True)
class PaginatedMissions:
    items: list[MissionResponse]
    total: int
    page: int
    per_page: int

    @property
    def pages(self) -> int:
        n = self.per_page or 1
        return (self.total + n - 1) // n


class MissionQueryHandlers(QueryHandlerBase):
    # ── List / Create ────────────────────────────────────────────────────────

    async def list_missions(
        self, user_id: int, page: int, per_page: int, workspace_id: str | None = None
    ) -> PaginatedMissions:
        # Try cache first (fail-open: cache miss falls through to DB)
        cached = await cache_list(user_id, page, per_page, workspace_id=workspace_id)
        if cached is not None:
            return PaginatedMissions(
                items=[MissionResponse.model_validate(item) for item in cached["items"]],
                total=cached["total"],
                page=cached["page"],
                per_page=cached["per_page"],
            )

        offset = (page - 1) * per_page

        # Phase 6: Read from Blueprint/Run tables when feature flag is enabled
        if use_new_reads():
            items, total = await list_missions_from_blueprints(
                self.session,
                user_id,
                offset=offset,
                limit=per_page,
                workspace_id=workspace_id,
            )
        else:
            mission_items, total = await list_missions(
                self.session,
                user_id,
                offset=offset,
                limit=per_page,
                workspace_id=workspace_id,
            )
            items = [MissionResponse.model_validate(m) for m in mission_items]

        result = PaginatedMissions(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
        )

        # Populate cache (fire-and-forget, failure logged)
        _schedule_fire_and_forget(
            cache_set_list(
                user_id,
                page,
                per_page,
                {
                    "items": [r.model_dump() for r in result.items],
                    "total": result.total,
                    "page": result.page,
                    "per_page": result.per_page,
                },
                workspace_id=workspace_id,
            )
        )
        return result

    # ── CRUD reads ──────────────────────────────────────────────────────────

    async def get_mission(self, user_id: int, mission_id: uuid.UUID) -> Mission | MissionShim:
        """ORM fetch path — always hits DB, used by internal callers that need
        real ORM objects (list_tasks, list_logs, get_status, etc.).

        Uses workspace-aware access: if the mission belongs to a workspace,
        verifies the user is a member of that workspace. Otherwise falls back
        to user_id ownership check.

        When ``USE_NEW_READS=1``, returns a ``MissionShim`` from the
        Blueprint/Run tables instead of hitting the legacy ``missions`` table.

        For the v2 GET endpoint use get_mission_response() which is cache-aside.
        """
        # Phase 6: Read from Blueprint/Run tables when feature flag is enabled
        if use_new_reads():
            shim = await get_mission_as_shim(self.session, mission_id, user_id)
            # Write-through cache populate (fire-and-forget, failure logged)
            try:
                _schedule_fire_and_forget(
                    cache_set(
                        user_id,
                        str(mission_id),
                        MissionResponse.model_validate(shim).model_dump(),
                    )
                )
            except Exception:
                logger.debug("cache_set_serialization_failed", exc_info=True)
            return shim

        mission = await require_mission_access(self.session, mission_id, user_id)

        # Write-through cache populate (fire-and-forget, failure logged)
        try:
            _schedule_fire_and_forget(
                cache_set(
                    user_id,
                    str(mission_id),
                    MissionResponse.model_validate(mission).model_dump(),
                )
            )
        except Exception:
            logger.debug("cache_set_serialization_failed", exc_info=True)
        return mission

    async def get_mission_response(self, user_id: int, mission_id: uuid.UUID) -> MissionResponse:
        """Read-model cache-aside path for the v2 GET endpoint.

        Returns a MissionResponse (DTO) without ever hitting DB on cache hit.
        Ownership is enforced on both cache-hit and cache-miss paths.
        """
        # Cache hit: validate ownership and return immediately (no DB)
        cached = await cache_get(user_id, str(mission_id))
        if cached is not None:
            if cached.get("user_id") != user_id:
                raise MissionNotFoundError("Mission not found")
            try:
                return MissionResponse.model_validate(cached)
            except Exception:
                logger.debug("cache_get_deserialization_failed", exc_info=True)

        # Phase 6: Read from Blueprint/Run tables when feature flag is enabled
        if use_new_reads():
            response = await get_mission_from_blueprint(
                self.session,
                mission_id,
                user_id,
            )
        else:
            # Cache miss: fetch from DB, validate workspace access, populate cache
            mission = await require_mission_access(self.session, mission_id, user_id)
            response = MissionResponse.model_validate(mission)

        try:
            _schedule_fire_and_forget(cache_set(user_id, str(mission_id), response.model_dump()))
        except Exception:
            logger.debug("cache_set_response_failed", exc_info=True)
        return response

    # ── Tasks ────────────────────────────────────────────────────────────────

    async def list_tasks(self, user_id: int, mission_id: uuid.UUID) -> list[MissionTask]:
        await self.get_mission(user_id, mission_id)  # ownership check
        tasks = await get_mission_tasks(self.session, mission_id)
        # Write-through cache populate (fire-and-forget, failure logged)
        try:
            _schedule_fire_and_forget(
                cache_set_tasks(
                    user_id,
                    str(mission_id),
                    {
                        "tasks": [MissionTaskResponse.model_validate(t).model_dump() for t in tasks],
                    },
                )
            )
        except Exception:
            logger.debug("cache_set_tasks_failed", exc_info=True)
        return tasks

    # ── Logs ─────────────────────────────────────────────────────────────────

    async def list_logs(self, user_id: int, mission_id: uuid.UUID) -> list[MissionLogResponse]:
        await self.get_mission(user_id, mission_id)

        # Try cache first
        cached = await cache_get_logs(user_id, str(mission_id))
        if cached is not None:
            try:
                return [MissionLogResponse.model_validate(l) for l in cached["logs"]]
            except Exception:
                logger.debug("cache_get_logs_deserialization_failed", exc_info=True)

        logs = await get_mission_logs(self.session, mission_id)
        result = [MissionLogResponse.model_validate(log) for log in logs]
        # Populate cache (fire-and-forget, failure logged)
        try:
            _schedule_fire_and_forget(
                cache_set_logs(
                    user_id,
                    str(mission_id),
                    {
                        "logs": [r.model_dump() for r in result],
                    },
                )
            )
        except Exception:
            logger.debug("cache_set_logs_failed", exc_info=True)
        return result

    # ── Status ───────────────────────────────────────────────────────────────

    async def get_status(self, user_id: int, mission_id: uuid.UUID) -> MissionExecutionStatus:
        mission = await self.get_mission(user_id, mission_id)

        # Try cache first (before hitting DB for tasks)
        cached = await cache_get_status(user_id, str(mission_id))
        if cached is not None:
            try:
                return MissionExecutionStatus.model_validate(cached)
            except Exception:
                logger.debug("cache_get_status_deserialization_failed", exc_info=True)

        tasks = await get_mission_tasks(self.session, mission_id)
        status = _make_execution_status(mission, tasks)  # type: ignore[arg-type]
        # Populate cache (fire-and-forget, failure logged)
        try:
            _schedule_fire_and_forget(cache_set_status(user_id, str(mission_id), status.model_dump()))
        except Exception:
            logger.debug("cache_set_status_failed", exc_info=True)
        return status

    # ── Active ───────────────────────────────────────────────────────────────

    async def list_active(self, user_id: int, workspace_id: str | None = None) -> list[Mission | MissionShim]:
        # Try cache first (workspace-scoped)
        cached = await cache_active(user_id, workspace_id)
        if cached is not None and "active_ids" in cached:
            ids = cached["active_ids"]
            if not ids:
                return []
            if use_new_reads():
                # Cache stores blueprint IDs when new reads are on
                from app.models.blueprint_models import Blueprint, Run

                from .compat import _ACTIVE_RUN_STATUSES

                stmt_bp = (
                    select(Blueprint, Run)
                    .join(Run, Run.blueprint_id == Blueprint.id)
                    .where(
                        Blueprint.id.in_(ids),
                        Blueprint.deleted_at.is_(None),
                        Run.status.in_(sorted(_ACTIVE_RUN_STATUSES)),
                    )
                    .order_by(Run.created_at.desc())
                )
                rows = (await self.session.execute(stmt_bp)).all()
                return [MissionShim.from_blueprint_run(bp, run) for bp, run in rows]
            # Legacy path: re-fetch from Mission table
            stmt = (
                select(Mission)
                .where(Mission.id.in_(ids), Mission.deleted_at.is_(None))
                .order_by(Mission.started_at.desc())
            )
            return list((await self.session.execute(stmt)).scalars().all())

        # Phase 6: Read from Blueprint/Run tables when feature flag is enabled
        if use_new_reads():
            shims = await list_active_from_blueprints(
                self.session,
                user_id,
                workspace_id=workspace_id,
            )
            # Populate cache with mission IDs (workspace-scoped)
            _schedule_fire_and_forget(
                cache_set_active(
                    user_id,
                    {
                        "active_ids": [s.id for s in shims],
                    },
                    workspace_id=workspace_id,
                )
            )
            return cast("list[Mission | MissionShim]", shims)

        base_filter = Mission.workspace_id == workspace_id if workspace_id is not None else Mission.user_id == user_id

        stmt = (
            select(Mission)
            .where(
                base_filter,
                Mission.status.in_([MissionStatus.QUEUED, MissionStatus.RUNNING]),
                Mission.deleted_at.is_(None),
            )
            .order_by(Mission.started_at.desc())
        )
        missions = list((await self.session.execute(stmt)).scalars().all())

        # Populate cache with mission IDs (workspace-scoped)
        _schedule_fire_and_forget(
            cache_set_active(
                user_id,
                {
                    "active_ids": [m.id for m in missions],
                },
                workspace_id=workspace_id,
            )
        )
        return cast("list[Mission | MissionShim]", missions)

    async def active_missions(
        self,
        user_id: int,
        user_role: str = "",
        is_pro: bool = False,
        workspace_id: str | None = None,
    ) -> MissionListResult:
        """Active missions with progress/ETA — requires pro subscription."""
        if user_role != "pro" and not is_pro:
            raise MissionForbiddenError("Pro subscription required")

        # Try cache first (workspace-scoped)
        cached = await cache_active(user_id, workspace_id)
        if cached is not None and "missions" in cached:
            try:
                # Filter out soft-deleted records that may have been cached
                # before deletion
                items = [MissionResponse.model_validate(m) for m in cached["missions"] if not m.get("deleted_at")]
                return MissionListResult(missions=items, total=len(items))
            except Exception:
                logger.debug("cache_active_deserialization_failed", exc_info=True)

        # Phase 6: Read from Blueprint/Run tables when feature flag is enabled
        if use_new_reads():
            items, total = await active_missions_from_blueprints(
                self.session,
                user_id,
                workspace_id=workspace_id,
            )
            # Populate cache (fire-and-forget, failure logged)
            _schedule_fire_and_forget(
                cache_set_active(
                    user_id,
                    {
                        "missions": [r.model_dump() for r in items],
                        "total": total,
                    },
                    workspace_id=workspace_id,
                )
            )
            return MissionListResult(missions=items, total=total)

        base_filter = Mission.workspace_id == workspace_id if workspace_id is not None else Mission.user_id == user_id

        result = await self.session.execute(
            select(Mission)
            .where(
                base_filter,
                Mission.status.in_([MissionStatus.QUEUED, MissionStatus.RUNNING]),
                Mission.deleted_at.is_(None),
            )
            .order_by(Mission.started_at.desc())
        )
        missions = result.scalars().all()
        if not missions:
            return MissionListResult(missions=[], total=0)

        # B1: N+1 prevention — single aggregate subquery for task stats
        mission_ids = [m.id for m in missions]
        from sqlalchemy import case, func

        task_stats_stmt = (
            select(
                MissionTask.mission_id,
                func.count(MissionTask.id).label("total"),
                func.sum(case((MissionTask.status == MissionTaskStatus.COMPLETED, 1), else_=0)).label("completed"),
                func.sum(case((MissionTask.status == MissionTaskStatus.FAILED, 1), else_=0)).label("failed"),
            )
            .where(MissionTask.mission_id.in_(mission_ids))
            .group_by(MissionTask.mission_id)
        )
        stats_result = await self.session.execute(task_stats_stmt)
        stats_by_mission: dict[str, dict] = {}
        for row in stats_result:
            stats_by_mission[row.mission_id] = {
                "total": row.total,
                "completed": row.completed or 0,
                "failed": row.failed or 0,
            }

        response = []
        for m in missions:
            stats = stats_by_mission.get(m.id, {"total": 0, "completed": 0, "failed": 0})
            total = stats["total"]
            completed = stats["completed"]
            progress = int((completed / total) * 100) if total > 0 else 0
            eta = None
            if m.status == MissionStatus.RUNNING and m.started_at and total > 0 and completed > 0:
                elapsed = (datetime.now(UTC) - m.started_at).total_seconds()
                avg = elapsed / completed
                remaining = total - completed
                eta = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=int(avg * remaining))
            response.append(
                MissionResponse(
                    id=uuid.UUID(m.id),
                    user_id=m.user_id,
                    title=m.title,
                    description=m.description,
                    mission_type=m.mission_type,
                    status=m.status,
                    priority=m.priority,
                    plan=m.plan,
                    results=m.results,
                    error_message=m.error_message,
                    tokens_used=m.tokens_used,
                    estimated_cost=m.estimated_cost,
                    actual_cost=m.actual_cost,
                    started_at=m.started_at,
                    completed_at=m.completed_at,
                    created_at=m.created_at,
                    updated_at=m.updated_at,
                    progress=progress,
                    eta=eta,
                )
            )
        # Populate cache (fire-and-forget, failure logged)
        _schedule_fire_and_forget(
            cache_set_active(
                user_id,
                {
                    "missions": [r.model_dump() for r in response],
                    "total": len(response),
                },
                workspace_id=workspace_id,
            )
        )
        return MissionListResult(missions=response, total=len(response))

    # ── Improvements ─────────────────────────────────────────────────────────

    async def list_improvements(self, user_id: int, mission_id: uuid.UUID) -> list[MissionImprovementResponse]:
        await self.get_mission(user_id, mission_id)

        # Try cache first
        cached = await cache_get_improvements(user_id, str(mission_id))
        if cached is not None:
            try:
                return [MissionImprovementResponse.model_validate(i) for i in cached["improvements"]]
            except Exception:
                logger.debug("cache_get_improvements_deserialization_failed", exc_info=True)

        engine = SelfImprovementEngine(self.session, str(user_id))
        improvements = await engine.get_improvements(mission_id)  # type: ignore[arg-type]
        result = [MissionImprovementResponse.model_validate(i) for i in improvements]
        # Populate cache (fire-and-forget, failure logged)
        try:
            _schedule_fire_and_forget(
                cache_set_improvements(
                    user_id,
                    str(mission_id),
                    {
                        "improvements": [r.model_dump() for r in result],
                    },
                )
            )
        except Exception:
            logger.debug("cache_set_improvements_failed", exc_info=True)
        return result

    # ── Plan Candidates ──────────────────────────────────────────────────────

    async def list_plan_candidates(self, user_id: int, mission_id: uuid.UUID) -> list[PlanCandidateResponse]:
        """Return ranked plan candidates for a mission (cost-aware plan selection)."""
        await self.get_mission(user_id, mission_id)  # ownership check

        from sqlalchemy import select

        from app.models.mission_advanced_models import MissionPlanCandidate

        stmt = (
            select(MissionPlanCandidate)
            .where(MissionPlanCandidate.mission_id == str(mission_id))
            .order_by(MissionPlanCandidate.rank.asc())
        )
        result = await self.session.execute(stmt)
        candidates = result.scalars().all()
        return [PlanCandidateResponse.from_model(c) for c in candidates]

    # ── Analytics ────────────────────────────────────────────────────────────

    async def mission_analytics(self, user_id: int, mission_id: uuid.UUID, days: int) -> dict:
        await self.get_mission(user_id, mission_id)
        analytics = await get_mission_analytics(self.session, user_id)
        over_time = await get_mission_analytics_over_time(self.session, user_id, days)
        token_usage = await get_token_usage_breakdown(self.session, user_id)
        failures = await get_failure_analysis(self.session, user_id)
        return {
            "summary": analytics,
            "over_time": over_time,
            "token_usage": token_usage,
            "failure_analysis": failures,
        }

    async def global_analytics(self, user_id: int) -> dict:
        return await get_mission_analytics(self.session, user_id)

    # ── Event History (Phase 3.2) ───────────────────────────────────────────────

    async def get_events(
        self,
        user_id: int,
        mission_id: uuid.UUID,
        *,
        from_sequence: int = 0,
        limit: int = 100,
    ) -> list[dict]:
        """Retrieve substrate event history for a mission.

        Events come from the substrate_events table (append-only log).
        Returns events ordered by sequence ascending.
        """
        await self.get_mission(user_id, mission_id)  # ownership check

        from app.database import AsyncSessionLocal
        from app.services.substrate.event_log import get_event_log

        # Find the run_id for this mission from substrate_events
        async with AsyncSessionLocal() as read_session:
            from sqlalchemy import func, select

            from app.models.substrate_models import SubstrateEvent

            # Find run_ids associated with this mission (latest first)
            run_stmt = (
                select(
                    SubstrateEvent.run_id,
                    func.max(SubstrateEvent.timestamp).label("last_ts"),
                )
                .where(SubstrateEvent.mission_id == str(mission_id))
                .group_by(SubstrateEvent.run_id)
                .order_by(func.max(SubstrateEvent.timestamp).desc())
                .limit(10)
            )
            run_result = await read_session.execute(run_stmt)
            run_ids = [row[0] for row in run_result.all()]

            if not run_ids:
                return []

            event_log = get_event_log()
            all_events = []
            for run_id in run_ids:
                events = await event_log.get_events(
                    read_session,
                    str(run_id),
                    from_sequence=from_sequence,
                    limit=limit,
                )
                all_events.extend(events)

            # Sort by timestamp (cross-run safe) then sequence for stability
            all_events.sort(key=lambda e: (e.timestamp, e.sequence))
            return [
                {
                    "id": str(e.id),
                    "sequence": e.sequence,
                    "run_id": str(e.run_id),
                    "type": e.type,
                    "payload": e.payload,
                    "actor": e.actor,
                    "task_id": str(e.task_id) if e.task_id else None,
                    "causal_parent": e.causal_parent,
                    "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                }
                for e in all_events[:limit]
            ]

    async def get_substrate_state(
        self,
        user_id: int,
        mission_id: uuid.UUID,
    ) -> dict:
        """Reconstruct mission state from the substrate event log.

        Uses the ReplayEngine to rebuild the current state by replaying
        all events for the mission's latest run.
        """
        await self.get_mission(user_id, mission_id)  # ownership check

        from app.database import AsyncSessionLocal
        from app.services.substrate.replay_engine import get_replay_engine

        async with AsyncSessionLocal() as read_session:
            from sqlalchemy import select

            from app.models.substrate_models import SubstrateEvent

            # Find the latest run_id for this mission
            run_stmt = (
                select(
                    SubstrateEvent.run_id,
                    func.max(SubstrateEvent.timestamp).label("last_ts"),
                )
                .where(SubstrateEvent.mission_id == str(mission_id))
                .group_by(SubstrateEvent.run_id)
                .order_by(func.max(SubstrateEvent.timestamp).desc())
                .limit(1)
            )
            run_result = await read_session.execute(run_stmt)
            run_row = run_result.first()

            if run_row is None:
                return {
                    "mission_id": str(mission_id),
                    "has_events": False,
                    "state": None,
                }

            latest_run_id = str(run_row[0])

            # Rebuild state from the most recent run
            replay = get_replay_engine()
            state = await replay.rebuild_state(read_session, latest_run_id)

            return {
                "mission_id": str(mission_id),
                "has_events": True,
                "run_id": latest_run_id,
                "state": state.to_dict(),
            }

    # ── SSE Stream ───────────────────────────────────────────────────────────

    def stream_status(
        self,
        user_id: int,
        mission_id: uuid.UUID,
        initial_mission: Mission | MissionShim,
    ) -> StreamingResponse:
        """CQRS SSE stream handler — polls mission status until terminal.

        Synchronous wrapper that returns a StreamingResponse with an async
        generator.  Ownership check is performed by the caller (v1/v2 route)
        via get_mission() before invoking this method.
        """
        session = self.session

        async def event_generator():
            mission = initial_mission
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "status",
                        "mission_id": str(mission_id),
                        "status": mission.status,
                    }
                )
                + "\n\n"
            )

            tasks = await get_mission_tasks(session, mission_id)
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "task_count",
                        "total": len(tasks),
                        "completed": sum(1 for t in tasks if t.status == MissionTaskStatus.COMPLETED),
                        "failed": sum(1 for t in tasks if t.status == MissionTaskStatus.FAILED),
                    }
                )
                + "\n\n"
            )

            for t in tasks:
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "type": "task",
                            "task_id": str(t.id),
                            "title": t.title,
                            "status": t.status,
                        }
                    )
                    + "\n\n"
                )

            terminal_states = {
                MissionStatus.COMPLETED,
                MissionStatus.FAILED,
                MissionStatus.ABORTED,
            }
            if mission.status not in terminal_states:
                for _ in range(150):
                    await asyncio.sleep(2)
                    # Use handler's get_mission() which respects USE_NEW_READS
                    try:
                        mission = await self.get_mission(user_id, mission_id)
                    except MissionNotFoundError:
                        break
                    tasks = await get_mission_tasks(session, mission_id)
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "type": "status",
                                "mission_id": str(mission_id),
                                "status": mission.status,
                                "completed": sum(1 for t in tasks if t.status == MissionTaskStatus.COMPLETED),
                                "failed": sum(1 for t in tasks if t.status == MissionTaskStatus.FAILED),
                            }
                        )
                        + "\n\n"
                    )
                    if mission.status in terminal_states:
                        break

            yield "data: [DONE]\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
