"""Phase 6 — Compatibility layer: read from Blueprint/Run tables.

When ``USE_NEW_READS=1`` is set in the environment, mission query handlers
delegate to this module instead of reading from the legacy ``missions`` table.

The converter produces ``MissionResponse`` objects so all existing API
consumers (v1, v2, frontend) continue to work without changes.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import case, func, select

from app.models.blueprint_models import Blueprint, Run
from app.schemas.mission import MissionResponse

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


def use_new_reads() -> bool:
    """Check whether the new-reads feature flag is enabled.

    KILL SWITCH — always False (2026-07-16).

    The Blueprint/Run dual-write was removed 2026-07-07 (commit 5757b0aa;
    see ``docs/DUAL-WRITE-DECISION.md``). Since then, ``commands.py`` performs
    ZERO writes to Blueprint/Run, so those tables are unpopulated. With
    ``USE_NEW_READS=1`` live in ``.env``, the query handlers below would SERVE
    reads from the dormant, empty Blueprint/Run model — silently returning
    empty/phantom mission data in production.

    Mission is the sole source of truth. This function is pinned False so the
    read path can never route to the deprecated model, regardless of env /
    rebuild state. The flag-reading code is intentionally dead (kept so call
    sites continue to import without churn). Re-enabling requires a new
    decision plus a population/backfill path — do not flip without one.
    """
    return False


# ── Mapping helpers ──────────────────────────────────────────────────────

_ACTIVE_RUN_STATUSES = frozenset({"pending", "queued", "executing", "paused"})
_TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "aborted"})


def _blueprint_run_to_mission_response(
    bp: Blueprint,
    latest_run: Run | None = None,
) -> MissionResponse:
    """Convert a Blueprint (+ optional latest Run) into a ``MissionResponse``.

    Column mapping:
        Blueprint.id            → id
        Blueprint.user_id       → user_id
        Blueprint.title         → title
        Blueprint.description   → description
        Blueprint.blueprint_type → mission_type
        Blueprint.definition    → plan
        Blueprint.created_at    → created_at
        Blueprint.updated_at    → updated_at

        Run.status              → status  (overrides Blueprint status)
        Run.total_tokens        → tokens_used
        Run.total_cost_usd      → actual_cost
        Run.started_at          → started_at
        Run.completed_at        → completed_at
        Run.output_data         → results
        Run.error_message       → error_message
    """
    bp_status = bp.status or "draft"
    status = _map_run_status(latest_run.status) if latest_run and latest_run.status else _map_bp_status(bp_status)

    return MissionResponse(
        id=uuid.UUID(str(bp.id)) if bp.id else uuid.uuid4(),
        user_id=bp.user_id,
        title=bp.title or "",
        description=bp.description or "",
        mission_type=bp.blueprint_type or "solo",
        status=status,
        priority="medium",  # Blueprints don't have priority; safe default
        plan=bp.definition if bp.definition else None,
        results=(latest_run.output_data if latest_run and latest_run.output_data else None),
        error_message=latest_run.error_message if latest_run else None,
        tokens_used=latest_run.total_tokens if latest_run else None,
        estimated_cost=None,
        actual_cost=latest_run.total_cost_usd if latest_run else None,
        started_at=latest_run.started_at if latest_run else None,
        completed_at=latest_run.completed_at if latest_run else None,
        created_at=bp.created_at,
        updated_at=bp.updated_at,
    )


def _map_run_status(run_status: str) -> Any:
    """Map Run.status string → MissionStatus enum-compatible value."""
    from app.models.mission_models import MissionStatus

    _MAP = {
        "pending": MissionStatus.PENDING,
        "queued": MissionStatus.QUEUED,
        "executing": MissionStatus.EXECUTING,
        "running": MissionStatus.RUNNING,
        "paused": MissionStatus.PAUSED,
        "completed": MissionStatus.COMPLETED,
        "failed": MissionStatus.FAILED,
        "aborted": MissionStatus.ABORTED,
    }
    return _MAP.get(run_status, MissionStatus.PENDING)


def _map_bp_status(bp_status: str) -> Any:
    """Map Blueprint.status string → MissionStatus enum-compatible value."""
    from app.models.mission_models import MissionStatus

    _MAP = {
        "draft": MissionStatus.PENDING,
        "published": MissionStatus.PLANNED,
        "deprecated": MissionStatus.FAILED,
    }
    return _MAP.get(bp_status, MissionStatus.PENDING)


# ── Workspace access check ───────────────────────────────────────────────


async def _verify_workspace_access(
    db: AsyncSession,
    workspace_id: str | None,
    user_id: int,
) -> None:
    """Verify the user is an active member of the given workspace.

    Mirrors the check in ``require_mission_access``.  Raises
    ``MissionNotFoundError`` if the user is not a member (avoid leaking
    existence of the resource).
    """
    if not workspace_id:
        return  # No workspace → ownership was already checked via user_id

    from app.models.workspace_models import WorkspaceMember
    from app.services.mission_errors import MissionNotFoundError

    result = await db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.is_active == True,
        )
    )
    if result.scalar_one_or_none() is None:
        raise MissionNotFoundError("Mission not found")


# ── Blueprint lookup helpers ──────────────────────────────────────────────


async def _find_blueprint(
    db: AsyncSession,
    mission_id: str,
) -> Blueprint | None:
    """Find a Blueprint by direct ID lookup, then by _source_mission_id fallback."""
    bp = (
        await db.execute(
            select(Blueprint).where(
                Blueprint.id == mission_id,
                Blueprint.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()

    if bp is None:
        # Fallback: search by source_mission_id stored during dual-write
        bp = (
            (
                await db.execute(
                    select(Blueprint).where(
                        Blueprint.definition["_source_mission_id"].astext == mission_id,
                        Blueprint.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .first()
        )

    return bp


async def _get_latest_run(
    db: AsyncSession,
    blueprint_id: str,
) -> Run | None:
    """Fetch the most recent Run for a blueprint."""
    return (
        await db.execute(
            select(Run)
            .where(
                Run.blueprint_id == blueprint_id,
            )
            .order_by(Run.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


# ── Query functions ──────────────────────────────────────────────────────


async def list_missions_from_blueprints(
    db: AsyncSession,
    user_id: int,
    *,
    offset: int = 0,
    limit: int = 20,
    workspace_id: str | None = None,
) -> tuple[list[MissionResponse], int]:
    """Read missions from Blueprint + Run tables, returning MissionResponse DTOs.

    Uses ``DISTINCT ON`` to guarantee exactly one row per blueprint even when
    multiple runs share the same ``created_at`` timestamp.
    """
    # ── Count ────────────────────────────────────────────────────────────
    count_q = select(func.count()).select_from(Blueprint).where(Blueprint.deleted_at.is_(None))
    if workspace_id is not None:
        count_q = count_q.where(Blueprint.workspace_id == workspace_id)
    else:
        count_q = count_q.where(Blueprint.user_id == user_id)
    total = (await db.execute(count_q)).scalar() or 0

    if total == 0:
        return [], 0

    # ── Fetch with DISTINCT ON (PostgreSQL-specific, but this is a PG project) ──
    from sqlalchemy.orm import aliased

    lr = aliased(Run)

    # Subquery: pick the latest run ID per blueprint via DISTINCT ON
    latest_run_ids = (
        select(
            Run.blueprint_id.label("bp_id"),
            Run.id.label("run_id"),
        )
        .order_by(Run.blueprint_id, Run.created_at.desc())
        .distinct(Run.blueprint_id)
        .subquery()
    )

    stmt = (
        select(Blueprint, lr)
        .outerjoin(latest_run_ids, latest_run_ids.c.bp_id == Blueprint.id)
        .outerjoin(lr, lr.id == latest_run_ids.c.run_id)
        .where(Blueprint.deleted_at.is_(None))
    )
    if workspace_id is not None:
        stmt = stmt.where(Blueprint.workspace_id == workspace_id)
    else:
        stmt = stmt.where(Blueprint.user_id == user_id)

    stmt = stmt.order_by(Blueprint.created_at.desc()).offset(offset).limit(limit)
    rows = (await db.execute(stmt)).all()

    items = [_blueprint_run_to_mission_response(bp, run) for bp, run in rows]
    return items, total


async def get_mission_from_blueprint(
    db: AsyncSession,
    mission_id: str | uuid.UUID,
    user_id: int,
) -> MissionResponse:
    """Read a single mission from Blueprint + Run tables.

    The ``mission_id`` is the Blueprint's UUID.  Since dual-write stores the
    ``_source_mission_id`` in ``Blueprint.definition``, we first try a direct
    Blueprint lookup by ID, then fall back to the definition search.

    After finding the blueprint, we verify workspace membership (same check
    that ``require_mission_access`` performs on the missions table).
    """
    bp_id = str(mission_id)
    bp = await _find_blueprint(db, bp_id)

    if bp is None:
        from app.services.mission_errors import MissionNotFoundError

        raise MissionNotFoundError(f"Mission {mission_id} not found")

    # Verify workspace access (mirrors require_mission_access logic)
    await _verify_workspace_access(db, bp.workspace_id, user_id)

    run = await _get_latest_run(db, str(bp.id))
    return _blueprint_run_to_mission_response(bp, run)


# ── Active-mission helpers ────────────────────────────────────────────────────


async def list_active_from_blueprints(
    db: AsyncSession,
    user_id: int,
    workspace_id: str | None = None,
) -> list[MissionShim]:
    """Read active missions from Blueprint + Run tables.

    Active = Run status is pending, queued, executing, or paused.
    Returns MissionShim objects so callers that expect Mission ORM objects
    continue to work (v2 list_active, stream_status, etc.).
    """
    stmt = (
        select(Blueprint, Run)
        .join(Run, Run.blueprint_id == Blueprint.id)
        .where(
            Blueprint.deleted_at.is_(None),
            Run.status.in_(sorted(_ACTIVE_RUN_STATUSES)),
        )
    )
    if workspace_id is not None:
        stmt = stmt.where(Blueprint.workspace_id == workspace_id)
    else:
        stmt = stmt.where(Blueprint.user_id == user_id)

    stmt = stmt.order_by(Run.created_at.desc())
    rows = (await db.execute(stmt)).all()

    return [MissionShim.from_blueprint_run(bp, run) for bp, run in rows]


async def active_missions_from_blueprints(
    db: AsyncSession,
    user_id: int,
    workspace_id: str | None = None,
) -> tuple[list[MissionResponse], int]:
    """Read active missions with progress/ETA from Blueprint + Run tables.

    Progress derives from ``substrate_events`` TASK_COMPLETED counts so
    the function survives phase103 (which drops legacy schema).  Used by
    ``active_missions()`` when ``USE_NEW_READS=1``.
    """
    from datetime import datetime, timedelta

    from app.models.mission_models import MissionStatus
    from app.models.substrate_models import SubstrateEvent, SubstrateEventType

    stmt = (
        select(Blueprint, Run)
        .join(Run, Run.blueprint_id == Blueprint.id)
        .where(
            Blueprint.deleted_at.is_(None),
            Run.status.in_(sorted(_ACTIVE_RUN_STATUSES)),
        )
    )
    if workspace_id is not None:
        stmt = stmt.where(Blueprint.workspace_id == workspace_id)
    else:
        stmt = stmt.where(Blueprint.user_id == user_id)

    stmt = stmt.order_by(Run.created_at.desc())
    rows = (await db.execute(stmt)).all()

    if not rows:
        return [], 0

    # ── B3 FIX (cutover plan §0 B3-A): progress from substrate_events.
    #   Phase 10.1 added substrate_events.blueprint_id as a FK column;
    #   filter on the column (not payload JSONB) for the cutover period.
    #   `total` = static count of nodes in blueprint.definition (pre-exec
    #   baseline).  `completed` = count of TASK_COMPLETED events per run.
    #   func.count + func.sum + TASK_COMPLETED are all kept inline so the
    #   fail-first regression test can verify the math patterns.
    blueprint_ids = [str(bp.id) for bp, _ in rows]
    nodes_by_bp: dict[str, int] = {str(bp.id): len((bp.definition or {}).get("nodes") or []) for bp, _ in rows}
    completed_by_bp: dict[str, int] = {}
    if blueprint_ids:
        event_stats_stmt = (
            select(
                SubstrateEvent.blueprint_id.label("bp_id"),
                func.count(SubstrateEvent.id).label("all_events"),
                func.sum(
                    case(
                        (SubstrateEvent.event_type == SubstrateEventType.TASK_COMPLETED, 1),
                        else_=0,
                    )
                ).label("completed"),
            )
            .where(
                SubstrateEvent.blueprint_id.in_(blueprint_ids),
            )
            .group_by(SubstrateEvent.blueprint_id)
        )
        stats_result = await db.execute(event_stats_stmt)
        for row in stats_result:
            completed_by_bp[str(row.bp_id)] = row.completed or 0

    response: list[MissionResponse] = []
    for bp, run in rows:
        mr = _blueprint_run_to_mission_response(bp, run)

        total = nodes_by_bp.get(str(bp.id), 0)
        completed = completed_by_bp.get(str(bp.id), 0)
        progress = int((completed / total) * 100) if total > 0 else 0
        eta = None
        if mr.status == MissionStatus.RUNNING and mr.started_at and total > 0 and completed > 0:
            elapsed = (datetime.now(UTC) - mr.started_at).total_seconds()
            avg = elapsed / completed
            remaining = total - completed
            eta = datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=int(avg * remaining))

        response.append(
            MissionResponse(
                **{k: v for k, v in mr.model_dump().items() if k not in ("progress", "eta")},
                progress=progress,
                eta=eta,
            )
        )

    return response, len(response)


# ── MissionShim: Mission-compatible object for ORM callers ───────────────


@dataclass
class MissionShim:
    """Lightweight Mission-compatible object built from Blueprint/Run data.

    Callers of ``get_mission()`` expect a ``Mission`` ORM object with specific
    attributes (``id``, ``status``, ``started_at``, ``workspace_id``, etc.).
    This shim provides the same attribute surface so that ``list_tasks``,
    ``list_logs``, ``get_status``, ``stream_status``, and other callers
    continue to work when ``USE_NEW_READS=1``.

    Only the attributes actually accessed by downstream callers are populated.
    """

    id: str
    user_id: int
    title: str
    description: str
    mission_type: str | None
    status: Any  # MissionStatus enum value
    priority: str | None
    plan: dict | None
    results: dict | None
    error_message: str | None
    tokens_used: int | None
    estimated_cost: float | None
    actual_cost: float | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
    workspace_id: str | None
    deleted_at: datetime | None = None
    version: int = 1
    feedback_score: int | None = None
    feedback_text: str | None = None
    output_files: dict | None = None
    parent_mission_id: str | None = None
    constraints: dict | None = None
    context_files: dict | None = None
    context_urls: dict | None = None
    integration_config: dict | None = None
    fallback_strategy: str | None = None

    @classmethod
    def from_blueprint_run(cls, bp: Blueprint, run: Run | None = None) -> MissionShim:
        """Build a MissionShim from a Blueprint ORM object and optional Run."""
        bp_status = bp.status or "draft"
        status = _map_run_status(run.status) if run and run.status else _map_bp_status(bp_status)

        return cls(
            id=str(bp.id),
            user_id=bp.user_id,
            title=bp.title or "",
            description=bp.description or "",
            mission_type=bp.blueprint_type or "solo",
            status=status,
            priority="medium",
            plan=bp.definition if bp.definition else None,
            results=run.output_data if run and run.output_data else None,
            error_message=run.error_message if run else None,
            tokens_used=run.total_tokens if run else None,
            estimated_cost=None,
            actual_cost=run.total_cost_usd if run else None,
            started_at=run.started_at if run else None,
            completed_at=run.completed_at if run else None,
            created_at=bp.created_at,
            updated_at=bp.updated_at,
            workspace_id=bp.workspace_id,
            deleted_at=bp.deleted_at,
            version=bp.version if hasattr(bp, "version") else 1,
        )


async def get_mission_as_shim(
    db: AsyncSession,
    mission_id: str | uuid.UUID,
    user_id: int,
) -> MissionShim:
    """Read a single mission from Blueprint/Run tables, returning a MissionShim.

    Used by ``get_mission()`` when ``USE_NEW_READS=1`` so that callers
    (list_tasks, list_logs, get_status, stream_status, etc.) receive a
    Mission-compatible object without touching the legacy ``missions`` table.
    """
    bp_id = str(mission_id)
    bp = await _find_blueprint(db, bp_id)

    if bp is None:
        from app.services.mission_errors import MissionNotFoundError

        raise MissionNotFoundError(f"Mission {mission_id} not found")

    await _verify_workspace_access(db, bp.workspace_id, user_id)

    run = await _get_latest_run(db, str(bp.id))
    return MissionShim.from_blueprint_run(bp, run)
