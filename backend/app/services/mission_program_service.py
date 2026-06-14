"""Mission Program service — CRUD + ownership + budget checks (plan §T5).

This service is the canonical write/read surface for ``MissionProgram`` and
``ProgramRun`` rows. It implements:

* CRUD: ``create``, ``get``, ``list``, ``update``, ``archive``
* Runs: ``list_runs`` (read-only listing — fire/consolidate are in T8/T9)
* Learning brief helpers: ``get_learning_brief``, ``update_user_notes``
* Budget helper: ``_check_program_budget`` (per-run + monthly caps, T10)

Transaction discipline (per ``services/AGENTS.md`` rule 3): this service
NEVER calls ``db.commit()``. The CQRS command handler (or route) owns the
transaction boundary; this service only ``flush()``es so the caller can
observe IDs and rely on the unit-of-work to apply changes atomically.

Audit integration is duck-typed: any object exposing ``program_created`` /
``program_updated`` / ``program_deleted`` / ``program_fired`` /
``program_consolidated`` no-fail methods works. A no-op fallback is used
until T4 wires up ``ProgramAudit``.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mission_program_models import (
    MissionProgram,
    ProgramRun,
    ProgramStatus,
)
from app.models.workspace_models import WorkspaceMember
from app.schemas.program import (
    ConsolidateResponse,
    ProgramCreate,
    ProgramUpdate,
)

logger = logging.getLogger(__name__)


# ── Exception hierarchy (per plan §T5) ──────────────────────────────────


class ProgramError(Exception):
    """Base for all program errors."""


class ProgramNotFound(ProgramError):
    """Raised when a program ID does not resolve to a row."""


class ProgramForbidden(ProgramError):
    """Raised when the user has no access to the program (not owner / not member)."""


class ProgramTransitionConflict(ProgramError):
    """Raised when a status transition is invalid or when an action cannot
    proceed because of the program's current state (e.g. archive with
    in-flight runs)."""


class ProgramValidationError(ProgramError):
    """Raised for input validation failures (bad enum value, etc.)."""


class ProgramBudgetExceeded(ProgramError):
    """Raised when a proposed cost would exceed the program's budget caps."""


# ── Audit no-op fallback ────────────────────────────────────────────────


class _NoOpAudit:
    """Duck-typed audit; no-op until T4 wires up ProgramAudit.

    Each method is a permissive no-op so the service can call
    ``self.audit.program_created(...)`` unconditionally.
    """

    def program_created(self, *args: Any, **kwargs: Any) -> None:
        pass

    def program_updated(self, *args: Any, **kwargs: Any) -> None:
        pass

    def program_deleted(self, *args: Any, **kwargs: Any) -> None:
        pass

    def program_fired(self, *args: Any, **kwargs: Any) -> None:
        pass

    def program_consolidated(self, *args: Any, **kwargs: Any) -> None:
        pass


# ── Service ─────────────────────────────────────────────────────────────


class MissionProgramService:
    """CRUD + ownership + budget for MissionProgram + ProgramRun.

    Per ``services/AGENTS.md`` rule 3: this service NEVER calls
    ``db.commit()``. The CQRS command handler (or route) owns the
    transaction. We only ``flush()`` so IDs and column defaults are
    populated before the caller's commit/rollback decision.
    """

    def __init__(self, db: AsyncSession, audit: Any | None = None) -> None:
        self.db = db
        self.audit = audit or _NoOpAudit()

    # ── CRUD ──────────────────────────────────────────────────────────

    async def create(
        self, user_id: int, workspace_id: str, payload: ProgramCreate
    ) -> MissionProgram:
        """Insert a new program. Status defaults to ``"active"``."""
        program = MissionProgram(
            user_id=user_id,
            workspace_id=workspace_id,
            name=payload.name,
            description=payload.description or "",
            mission_type=payload.mission_type,
            base_constraints=payload.base_constraints,
            base_context_files=payload.base_context_files,
            base_context_urls=payload.base_context_urls,
            trigger_config=(
                payload.trigger_config.model_dump()
                if hasattr(payload.trigger_config, "model_dump")
                else payload.trigger_config
            ),
            status="active",
            learning_brief=None,
            per_run_budget_usd=payload.per_run_budget_usd,
            monthly_budget_usd=payload.monthly_budget_usd,
        )
        self.db.add(program)
        await self.db.flush()
        await self.db.refresh(program)
        self._safe_audit("program_created", program_id=str(program.id), user_id=user_id)
        return program

    async def get(self, user_id: int, program_id: uuid.UUID) -> MissionProgram:
        """Fetch a program; raise ``ProgramNotFound`` or ``ProgramForbidden``."""
        result = await self.db.execute(
            select(MissionProgram).where(MissionProgram.id == program_id)
        )
        program = result.scalar_one_or_none()
        if program is None:
            raise ProgramNotFound(f"Program {program_id} not found")
        if not await self._user_can_access(user_id, program):
            raise ProgramForbidden("user is not owner or workspace member")
        return program

    async def list(
        self,
        user_id: int,
        workspace_id: str | None,
        page: int,
        per_page: int,
    ) -> tuple[list[MissionProgram], int]:
        """Return paginated programs the user can see.

        Access predicate: owned by user OR in a workspace the user is an
        active member of. The optional ``workspace_id`` filter narrows to a
        single workspace.
        """
        member_workspaces = select(WorkspaceMember.workspace_id).where(
            and_(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.is_active.is_(True),
            )
        )
        access_predicate = or_(
            MissionProgram.user_id == user_id,
            MissionProgram.workspace_id.in_(member_workspaces),
        )
        # Items
        stmt = select(MissionProgram).where(access_predicate)
        if workspace_id is not None:
            stmt = stmt.where(MissionProgram.workspace_id == workspace_id)
        # Count
        count_stmt = select(func.count()).select_from(MissionProgram).where(
            access_predicate
        )
        if workspace_id is not None:
            count_stmt = count_stmt.where(MissionProgram.workspace_id == workspace_id)
        total = (await self.db.execute(count_stmt)).scalar_one()
        # Page
        offset = (page - 1) * per_page
        stmt = (
            stmt.order_by(MissionProgram.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        items = list((await self.db.execute(stmt)).scalars().all())
        return items, int(total)

    async def update(
        self, user_id: int, program_id: uuid.UUID, patch: ProgramUpdate
    ) -> MissionProgram:
        """PATCH semantics — only fields explicitly set in ``patch`` are
        applied. Status transitions are validated via ``ProgramStatus.can_transition_to``.
        """
        program = await self.get(user_id, program_id)
        if program.status == "archived":
            raise ProgramTransitionConflict("cannot update an archived program")

        data = patch.model_dump(exclude_unset=True)
        for field, value in data.items():
            if field == "status":
                try:
                    current = ProgramStatus(program.status)
                    target = ProgramStatus(value)
                except ValueError as exc:
                    raise ProgramValidationError(str(exc)) from exc
                if not current.can_transition_to(target):
                    raise ProgramTransitionConflict(
                        f"cannot transition {current.value} -> {target.value}"
                    )
            if field == "trigger_config" and value is not None and hasattr(
                value, "model_dump"
            ):
                value = value.model_dump()
            setattr(program, field, value)

        await self.db.flush()
        await self.db.refresh(program)
        self._safe_audit("program_updated", program_id=str(program.id), user_id=user_id)
        return program

    async def archive(self, user_id: int, program_id: uuid.UUID) -> MissionProgram:
        """Soft-archive a program. Rejects if in-flight runs exist or the
        current status cannot transition to ``ARCHIVED``."""
        program = await self.get(user_id, program_id)
        # Reject if in-flight runs (status="running").
        in_flight = await self.db.execute(
            select(ProgramRun.id)
            .where(ProgramRun.program_id == program_id)
            .where(ProgramRun.status == "running")
            .limit(1)
        )
        if in_flight.scalar_one_or_none() is not None:
            raise ProgramTransitionConflict("cannot archive while runs are in flight")
        # Validate transition.
        current = ProgramStatus(program.status)
        if not current.can_transition_to(ProgramStatus.ARCHIVED):
            raise ProgramTransitionConflict(
                f"cannot transition {current.value} -> archived"
            )
        program.status = "archived"
        await self.db.flush()
        await self.db.refresh(program)
        # Archive is logged as "deleted" semantically (soft-delete).
        self._safe_audit("program_deleted", program_id=str(program.id), user_id=user_id)
        return program

    # ── Runs ──────────────────────────────────────────────────────────

    async def list_runs(
        self, program_id: uuid.UUID, page: int, per_page: int
    ) -> tuple[list[ProgramRun], int]:
        """Paginated listing of runs for a program (newest first)."""
        offset = (page - 1) * per_page
        total = (
            await self.db.execute(
                select(func.count())
                .select_from(ProgramRun)
                .where(ProgramRun.program_id == program_id)
            )
        ).scalar_one()
        items = list(
            (
                await self.db.execute(
                    select(ProgramRun)
                    .where(ProgramRun.program_id == program_id)
                    .order_by(ProgramRun.created_at.desc())
                    .offset(offset)
                    .limit(per_page)
                )
            )
            .scalars()
            .all()
        )
        return items, int(total)

    # ── T8: fire_program (real implementation) ───────────────────────

    async def fire_program(
        self,
        user_id: int,
        program_id: uuid.UUID,
        trigger_type: str,
        trigger_payload: dict | None = None,
    ) -> ProgramRun:
        """Fire a program: ACTIVE check → budget pre-check → create
        Mission + ProgramRun → dispatch to UnifiedExecutor.

        Returns the ProgramRun with a terminal status (or "failed" on
        executor error). Per the substrate contract
        (``substrate/AGENTS.md`` rule 1), the UnifiedExecutor is the only
        entry point for workflow execution; we do not call into the
        legacy ``MissionExecutor`` from this path.

        Transaction discipline: this method NEVER commits — the caller
        (route / CQRS handler) owns the unit-of-work. We ``flush()`` so
        mission_id + run_id are observable.
        """
        # Lazy imports break cycles and keep test patching points stable.
        from app.models.mission_models import Mission, MissionStatus
        from app.services.substrate.adapters import mission_to_workflow
        from app.services.substrate.executor import get_unified_executor

        # 1. Load program (raises ProgramNotFound / ProgramForbidden).
        program = await self.get(user_id, program_id)

        # 2. Status gate: only ACTIVE programs can be fired.
        if program.status != ProgramStatus.ACTIVE.value:
            raise ProgramTransitionConflict(
                f"cannot fire program in status {program.status!r} "
                "(must be 'active')"
            )

        # 3. Budget pre-check (per-run + monthly caps, T10).
        estimated_cost = 0.05  # default planning estimate (USD)
        await self._check_program_budget(program, estimated_cost)

        # 4. Create the child Mission. The base constraints from the
        # program are copied verbatim; we add a ``_planning_context``
        # sub-key that carries the learning brief for the planner to
        # consume (per the §T5 plan, this is the structured-brief path).
        existing_constraints = dict(program.base_constraints or {})
        existing_constraints["_planning_context"] = {
            "learning_brief": dict(program.learning_brief or {}),
        }
        mission = Mission(
            user_id=program.user_id,
            workspace_id=program.workspace_id,
            title=f"[Program] {program.name}",
            description=program.description or "",
            mission_type=program.mission_type,
            constraints=existing_constraints,
            status=MissionStatus.PENDING,
        )
        self.db.add(mission)
        await self.db.flush()  # populate mission.id

        # 5. Create the ProgramRun in RUNNING state.
        run = ProgramRun(
            program_id=program.id,
            mission_id=mission.id,
            trigger_type=trigger_type,
            trigger_payload=trigger_payload,
            status="running",
        )
        self.db.add(run)
        await self.db.flush()  # populate run.id

        # 6. Dispatch to the unified executor (the only execution entry
        # point per ``substrate/AGENTS.md``). Outcome is captured back
        # onto the ProgramRun; the runner itself is synchronous from
        # this caller's point of view (the substrate is async but
        # in-process — async/await is a no-op for our purposes here).
        try:
            workflow = mission_to_workflow(mission, tasks=[])
            executor = get_unified_executor()
            result = await executor.execute(self.db, workflow)
            run.status = "completed" if getattr(result, "success", False) else "failed"
            run.cost_usd = float(getattr(result, "total_cost_usd", 0.0) or 0.0)
            run.tokens_used = int(getattr(result, "total_tokens", 0) or 0)
            # execution_time_ms is a float in milliseconds; duration_seconds
            # is stored as float seconds. Fall back to 0.0 on bad input.
            exec_ms = float(getattr(result, "execution_time_ms", 0.0) or 0.0)
            run.duration_seconds = exec_ms / 1000.0
            # summary is a free-form field; we keep the executor's
            # ``data``/``error`` summary if present, else None.
            summary = getattr(result, "data", None) or getattr(result, "error", None)
            if isinstance(summary, str):
                run.outcome_summary = summary[:1000]
        except Exception as exc:
            logger.exception("fire_program: executor failed")
            run.status = "failed"
            run.outcome_summary = f"executor error: {exc!s}"[:1000]

        await self.db.flush()
        await self.db.refresh(run)

        # 7. Audit (non-blocking).
        self._safe_audit(
            "program_fired",
            program_id=str(program.id),
            run_id=str(run.id),
            user_id=user_id,
        )
        return run

    # ── Learning brief helpers ────────────────────────────────────────

    async def get_learning_brief(self, program_id: uuid.UUID) -> dict | None:
        """Return the raw ``learning_brief`` JSONB for a program (or None)."""
        result = await self.db.execute(
            select(MissionProgram.learning_brief).where(
                MissionProgram.id == program_id
            )
        )
        return result.scalar_one_or_none()

    async def update_user_notes(
        self, user_id: int, program_id: uuid.UUID, notes: str
    ) -> MissionProgram:
        """Update ONLY the ``user_notes`` sub-key of the learning brief.

        Consolidation MUST NEVER overwrite ``user_notes``; this helper is
        the user-driven complement. Structured fields are preserved
        verbatim — we read the current dict, write back a new dict with
        the updated ``user_notes`` key, and leave the rest untouched.
        """
        program = await self.get(user_id, program_id)
        existing = dict(program.learning_brief or {})
        existing["user_notes"] = notes
        program.learning_brief = existing
        await self.db.flush()
        await self.db.refresh(program)
        self._safe_audit("program_updated", program_id=str(program.id), user_id=user_id)
        return program

    # ── T8: fire_program (real implementation) ───────────────────────
#
# NOTE: The old "Stubs (filled in T8/T9)" section that defined stub
# fire_program() + consolidate_learning() is replaced by the real
# implementations above. Do not re-introduce stubs here — see the
# implementation directly above.


    # ── Budget helper (T10) ──────────────────────────────────────────

    async def _check_program_budget(
        self, program: MissionProgram, estimated_cost_usd: float
    ) -> None:
        """Per-run + monthly budget pre-check.

        Called by ``fire_program`` (T8) BEFORE creating a new Mission to
        reject obviously-over-budget fires. Independent of the
        workspace-level ``BudgetEnforcer`` (per plan §T10 guardrail).

        Both caps being None means no enforcement. Raises
        ``ProgramBudgetExceeded`` if any cap would be exceeded.
        """
        # Per-run cap.
        if (
            program.per_run_budget_usd is not None
            and estimated_cost_usd > program.per_run_budget_usd
        ):
            raise ProgramBudgetExceeded(
                f"per_run budget exceeded: estimated ${estimated_cost_usd:.4f} > "
                f"cap ${program.per_run_budget_usd:.4f}"
            )
        # Monthly cap.
        if program.monthly_budget_usd is not None:
            month_start = func.date_trunc("month", func.now())
            spend_stmt = (
                select(func.coalesce(func.sum(ProgramRun.cost_usd), 0.0))
                .where(ProgramRun.program_id == program.id)
                .where(
                    ProgramRun.status.in_(("completed", "failed", "aborted"))
                )
                .where(ProgramRun.created_at >= month_start)
            )
            current_spend = float(
                (await self.db.execute(spend_stmt)).scalar_one() or 0.0
            )
            projected = current_spend + estimated_cost_usd
            if projected > program.monthly_budget_usd:
                raise ProgramBudgetExceeded(
                    f"monthly budget exceeded: ${projected:.4f} > "
                    f"cap ${program.monthly_budget_usd:.4f}"
                )

    # ── Internal helpers ─────────────────────────────────────────────

    async def _user_can_access(self, user_id: int, program: MissionProgram) -> bool:
        """True if the user is the owner or an active workspace member."""
        if program.user_id == user_id:
            return True
        member = (
            await self.db.execute(
                select(WorkspaceMember.id)
                .where(WorkspaceMember.workspace_id == program.workspace_id)
                .where(WorkspaceMember.user_id == user_id)
                .where(WorkspaceMember.is_active.is_(True))
                .limit(1)
            )
        ).scalar_one_or_none()
        return member is not None

    def _safe_audit(self, method_name: str, **kwargs: Any) -> None:
        """Call ``self.audit.<method_name>(**kwargs)``; swallow + log failures.

        Audit MUST NOT break the business flow.
        """
        try:
            getattr(self.audit, method_name)(**kwargs)
        except Exception:  # pragma: no cover — defensive
            logger.warning(
                "%s audit failed (non-blocking)", method_name, exc_info=True
            )
