"""Mission Program service — CRUD + ownership + budget checks (plan §T5).

This service is the canonical write/read surface for ``MissionProgram`` and
``ProgramRun`` rows. It implements:

* CRUD: ``create``, ``get``, ``list_programs``, ``update``, ``archive``
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
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, func, or_, select

if TYPE_CHECKING:
    import uuid
    from collections.abc import Callable

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

    def __init__(
        self,
        db: AsyncSession,
        audit: Any | None = None,
        get_personal_memory_service: Callable[[], Any] | None = None,
    ) -> None:
        self.db = db
        self.audit = audit or _NoOpAudit()
        # T22: late-binding callable (per services/AGENTS.md rule 2)
        # for the personal-memory service used by ``consolidate_learning``
        # to cross-pollinate the user's top-N claims into the brief.
        # When the callable returns ``None`` (no service registered) or
        # raises, the brief carries ``user_personal_claims=[]``.
        self._get_personal_memory_service: Callable[[], Any] = get_personal_memory_service or (lambda: None)

    # ── CRUD ──────────────────────────────────────────────────────────

    async def create(self, user_id: int, workspace_id: str, payload: ProgramCreate) -> MissionProgram:
        """Insert a new program. Status defaults to ``"active"``."""
        trigger_cfg = (
            payload.trigger_config.model_dump()
            if hasattr(payload.trigger_config, "model_dump")
            else payload.trigger_config
        )
        program = MissionProgram(
            user_id=user_id,
            workspace_id=workspace_id,
            name=payload.name,
            description=payload.description or "",
            mission_type=payload.mission_type,
            base_constraints=payload.base_constraints,
            base_context_files=payload.base_context_files,
            base_context_urls=payload.base_context_urls,
            trigger_config=trigger_cfg,
            status="active",
            learning_brief=None,
            per_run_budget_usd=payload.per_run_budget_usd,
            monthly_budget_usd=payload.monthly_budget_usd,
        )
        # Compute next_fire_at for cron programs (T15 fix).
        if trigger_cfg and trigger_cfg.get("type") == "cron" and trigger_cfg.get("expression"):
            program.next_fire_at = self._compute_next_fire(
                trigger_cfg["expression"],
                trigger_cfg.get("timezone", "UTC"),
            )
        self.db.add(program)
        await self.db.flush()
        await self.db.refresh(program)
        self._safe_audit("program_created", program_id=str(program.id), user_id=user_id)
        return program

    async def get(self, user_id: int, program_id: uuid.UUID) -> MissionProgram:
        """Fetch a program; raise ``ProgramNotFound`` or ``ProgramForbidden``."""
        result = await self.db.execute(select(MissionProgram).where(MissionProgram.id == program_id))
        program = result.scalar_one_or_none()
        if program is None:
            raise ProgramNotFound(f"Program {program_id} not found")
        if not await self._user_can_access(user_id, program):
            raise ProgramForbidden("user is not owner or workspace member")
        return program

    async def list_programs(  # Renamed from list: shadows builtin inside class body
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
        count_stmt = select(func.count()).select_from(MissionProgram).where(access_predicate)
        if workspace_id is not None:
            count_stmt = count_stmt.where(MissionProgram.workspace_id == workspace_id)
        total = (await self.db.execute(count_stmt)).scalar_one()
        # Page
        offset = (page - 1) * per_page
        stmt = stmt.order_by(MissionProgram.created_at.desc()).offset(offset).limit(per_page)
        items = list((await self.db.execute(stmt)).scalars().all())
        return items, int(total)

    async def update(self, user_id: int, program_id: uuid.UUID, patch: ProgramUpdate) -> MissionProgram:
        """PATCH semantics — only fields explicitly set in ``patch`` are
        applied. Status transitions are validated via ``ProgramStatus.can_transition_to``.
        """
        program = await self.get(user_id, program_id)
        if program.status == "archived":
            raise ProgramTransitionConflict("cannot update an archived program")

        data = patch.model_dump(exclude_unset=True)
        trigger_config_changed = False
        for field, value in data.items():
            if field == "status":
                try:
                    current = ProgramStatus(program.status)
                    target = ProgramStatus(value)
                except ValueError as exc:
                    raise ProgramValidationError(str(exc)) from exc
                if not current.can_transition_to(target):
                    raise ProgramTransitionConflict(f"cannot transition {current.value} -> {target.value}")
            if field == "trigger_config" and value is not None and hasattr(value, "model_dump"):
                value = value.model_dump()
            if field == "trigger_config":
                trigger_config_changed = True
            setattr(program, field, value)

        # Recompute next_fire_at if trigger_config changed.
        if trigger_config_changed:
            cfg = program.trigger_config or {}
            if cfg.get("type") == "cron" and cfg.get("expression"):
                program.next_fire_at = self._compute_next_fire(
                    cfg["expression"],
                    cfg.get("timezone", "UTC"),
                )
            else:
                program.next_fire_at = None

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
            raise ProgramTransitionConflict(f"cannot transition {current.value} -> archived")
        program.status = "archived"
        await self.db.flush()
        await self.db.refresh(program)
        # Archive is logged as "deleted" semantically (soft-delete).
        self._safe_audit("program_deleted", program_id=str(program.id), user_id=user_id)
        return program

        # ── Runs ──────────────────────────────────────────────────────────

    async def list_runs(self, program_id: uuid.UUID, page: int, per_page: int) -> tuple[list[ProgramRun], int]:
        """Paginated listing of runs for a program (newest first)."""
        offset = (page - 1) * per_page
        total = (
            await self.db.execute(
                select(func.count()).select_from(ProgramRun).where(ProgramRun.program_id == program_id)
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
            raise ProgramTransitionConflict(f"cannot fire program in status {program.status!r} (must be 'active')")

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
        result = await self.db.execute(select(MissionProgram.learning_brief).where(MissionProgram.id == program_id))
        return result.scalar_one_or_none()

    async def update_user_notes(self, user_id: int, program_id: uuid.UUID, notes: str) -> MissionProgram:
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

    # ── T9: consolidate_learning (real implementation) ──────────────

    async def consolidate_learning(
        self,
        user_id: int,
        program_id: uuid.UUID,
        limit: int = 10,
        critic_payload: dict | None = None,
    ) -> ConsolidateResponse:
        """Synthesize a new learning brief from the last N terminal runs.

        Algorithm:
        1. Load program (ownership check); reject if archived.
        2. Query last ``limit`` runs with status IN
           ('completed', 'failed', 'aborted') — NEVER 'running'.
        3. If zero → return consolidated_runs=0, brief=existing, no error.
        4. Fetch per-run episode summaries from EpisodicMemoryService.
        5. Call BudgetEnforcer for LLM synthesis of structured fields.
        6. Merge: structured fields from LLM + existing user_notes
           (NEVER overwritten) + last_consolidated_at timestamp.
        7. Persist via column-level UPDATE on ``learning_brief``.
        8. Audit log (non-blocking).

        The ``user_notes`` field is owned by the user path
        (``update_user_notes``) and is intentionally never overwritten
        by this method, even if the LLM happens to return a
        ``user_notes`` key in its response.
        """
        import json
        import re
        import time as _time
        from datetime import UTC, datetime
        from decimal import Decimal

        from app.models.capability_models import Budget
        from app.schemas.program import LearningBriefBase
        from app.services.budget_enforcer import get_budget_enforcer
        from app.services.episodic_memory_service import (
            get_episodic_memory_service,
        )

        start = _time.monotonic()

        # 1. Load program (raises ProgramNotFound / ProgramForbidden).
        program = await self.get(user_id, program_id)

        # 2. Reject archived programs (consolidation on archived is invalid).
        if program.status == "archived":
            raise ProgramTransitionConflict("cannot consolidate learning for an archived program")

        # 3. Query last `limit` terminal runs (NEVER 'running').
        terminal_runs = list(
            (
                await self.db.execute(
                    select(ProgramRun)
                    .where(ProgramRun.program_id == program_id)
                    .where(ProgramRun.status.in_(("completed", "failed", "aborted")))
                    .order_by(ProgramRun.created_at.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

        if not terminal_runs:
            return ConsolidateResponse(
                consolidated_runs=0,
                brief=LearningBriefBase(**(program.learning_brief or {})),
                duration_ms=int((_time.monotonic() - start) * 1000),
            )

        # 4. Episode summaries (per-run). Failures are isolated — one bad
        # run does not poison the whole consolidation.
        # Gated: episodic memory is a sunset candidate (feature flag default off).
        memory = get_episodic_memory_service()  # Returns None when flag is off
        summaries: list[dict] = []
        for run in terminal_runs:
            if memory is not None:
                try:
                    episodes = await memory.get_episodes_for_mission(
                        self.db,
                        mission_id=str(run.mission_id),
                        workspace_id=program.workspace_id,
                        user_id=user_id,
                    )
                    summaries.append(
                        {
                            "run_id": str(run.id),
                            "mission_id": str(run.mission_id),
                            "status": run.status,
                            "cost_usd": run.cost_usd,
                            "tokens_used": run.tokens_used,
                            "duration_seconds": run.duration_seconds,
                            "outcome_summary": run.outcome_summary,
                            "episode_count": len(episodes) if episodes else 0,
                        }
                    )
                except Exception as exc:
                    logger.warning(
                        "episode fetch failed for run %s: %s",
                        run.id,
                        exc,
                        exc_info=True,
                    )
                    summaries.append(
                        {
                            "run_id": str(run.id),
                            "status": run.status,
                            "cost_usd": run.cost_usd,
                        }
                    )
            else:
                # Cross-mission memory disabled — still include run metadata
                summaries.append(
                    {
                        "run_id": str(run.id),
                        "mission_id": str(run.mission_id),
                        "status": run.status,
                        "cost_usd": run.cost_usd,
                        "tokens_used": run.tokens_used,
                        "duration_seconds": run.duration_seconds,
                        "outcome_summary": run.outcome_summary,
                        "episode_count": 0,
                    }
                )

        # 5. LLM synthesis via BudgetEnforcer.
        new_structured: dict = {}
        try:
            enforcer = get_budget_enforcer()
            budget = Budget(max_cost_usd=Decimal("0.10"))
            prompt = (
                f"Analyze {len(summaries)} runs of mission program "
                f"'{program.name}'. Return a JSON object with: "
                f"total_runs (int), success_rate (float 0-1), "
                f"avg_cost_usd (float), avg_tokens (int), "
                f"common_failures (list of {{pattern, count, mitigation}}), "
                f"effective_tools (list of strings), "
                f"ineffective_tools (list of strings), "
                f"hitl_history (list of {{outcome, count}}), "
                f"plan_adjustments (string ≤ 500 chars). "
                f"Run summaries:\n{json.dumps(summaries, indent=2, default=str)}\n"
                f"Return ONLY the JSON object, no other text."
            )
            response = await enforcer.call(
                budget=budget,
                model_id="claude-sonnet-4",
                messages=[{"role": "user", "content": prompt}],
            )
            content = response.get("content", "") if isinstance(response, dict) else str(response)
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                new_structured = json.loads(match.group(0))
        except Exception as exc:
            logger.warning("consolidation LLM call failed: %s", exc, exc_info=True)

        if not new_structured:
            # Fallback: bump total_runs on the existing brief so we still
            # have a non-trivial merged result.
            existing = dict(program.learning_brief or {})
            existing["total_runs"] = (existing.get("total_runs") or 0) + len(terminal_runs)
            new_structured = existing

        # 6.5. Fetch user personal claims (T22 cross-pollination).
        # Defence-in-depth: try/except so a personal-memory failure
        # never breaks the consolidation flow. Top-20 cap (vs the
        # planner's 10) because a program-level brief is rendered
        # more deliberately and can carry a longer context.
        user_personal_claims: list[dict] = []
        try:
            pm_service = self._get_personal_memory_service()
            if pm_service is not None:
                claims, _total = await pm_service.recall(
                    user_id=user_id,
                    workspace_id=program.workspace_id,
                    query="",  # recall all eligible
                    scopes=["personal", "workspace", "program"],
                    top_k=20,
                    min_confidence=0.0,
                )
                # Belt-and-suspenders: even though recall scopes already
                # exclude "private", re-filter at the renderer seam in
                # case recall ever loosens its scope contract. Then
                # apply the top-20 cap explicitly (the recall top_k
                # is a hint, not a contract — mocks and future
                # implementations may return more).
                eligible = [
                    c
                    for c in (claims or [])
                    if getattr(c, "sensitivity", "normal") != "restricted"
                    and getattr(c, "scope", "personal") != "private"
                ][:20]
                user_personal_claims = [
                    {
                        "id": str(c.id),
                        "subject": c.subject,
                        "predicate": c.predicate,
                        "object": c.object,
                        "claim_type": c.claim_type,
                        "scope": c.scope,
                        "confidence": c.confidence,
                        "importance": c.importance,
                        "source_type": c.source_type,
                    }
                    for c in eligible
                ]
        except Exception as exc:
            logger.warning(
                "consolidation: personal memory fetch failed: %s",
                exc,
                exc_info=True,
            )
            # user_personal_claims stays []

        # 7. Merge: new structured fields + existing user_notes (NEVER
        # overwritten) + last_consolidated_at + user_personal_claims.
        existing = dict(program.learning_brief or {})
        existing_user_notes = existing.get("user_notes", "")
        merged = {
            **new_structured,
            "user_notes": existing_user_notes,
            "last_consolidated_at": datetime.now(UTC).isoformat(),
            "user_personal_claims": user_personal_claims,
        }
        # T27 (D30-60): if the caller supplied a critic_payload (e.g. the
        # latest ``CriticOutput`` from the executor hook), merge its
        # structured fields into the brief. The same non-destructive
        # discipline applies: the LLM-synthesized fields win for the
        # top-level keys (plan_adjustments, common_failures, etc.),
        # user_notes and user_personal_claims stay owned by the
        # user/T22 paths.
        if critic_payload:
            for k, v in critic_payload.items():
                # Defence in depth: never let a critic payload overwrite
                # the user-owned fields. The LLM synthesis happens
                # FIRST so its keys land in new_structured; critic
                # fields are additive only.
                if k in {"user_notes", "user_personal_claims"}:
                    continue
                merged[k] = v

        # 8. Persist (column-level UPDATE — touches learning_brief only).
        program.learning_brief = merged
        await self.db.flush()
        await self.db.refresh(program)

        # 9. Audit (non-blocking).
        self._safe_audit(
            "program_consolidated",
            program_id=str(program.id),
            runs=len(terminal_runs),
            user_id=user_id,
        )

        return ConsolidateResponse(
            consolidated_runs=len(terminal_runs),
            brief=LearningBriefBase(**merged),
            duration_ms=int((_time.monotonic() - start) * 1000),
        )

    # ── T27 (D30-60): apply_improvement_batch ────────────────────────

    # Top-N cap for each list field in the brief. Mirrors the T22 cap
    # on user_personal_claims (top 20) — bigger than the planner's
    # top-10 because a program-level brief is rendered more deliberately
    # and can carry a longer context. The cap is per-list; the brief
    # total is unbounded but bounded in practice by how often the
    # executor hook fires.
    _CRITIC_LIST_CAP = 20

    async def apply_improvement_batch(
        self,
        *,
        user_id: int,
        program_id: uuid.UUID,
        batch: Any,  # ImprovementBatch — type hint avoided to break the
        # import cycle (improvement_generator imports
        # nothing from this module, but keeping the hint
        # as Any future-proofs the wiring).
    ) -> None:
        """Append a ``CriticOutput``-derived ``ImprovementBatch`` to the
        program's learning_brief.

        Non-destructive merge semantics — same discipline as the
        ``user_personal_claims`` cross-pollination in
        ``consolidate_learning`` (T22): the existing ``plan_adjustments``
        string, ``user_notes``, and ``user_personal_claims`` are NOT
        overwritten. Instead, three NEW additive fields
        (``critic_plan_adjustments``, ``critic_tool_suggestions``,
        ``critic_common_failure_patterns``) are appended to and
        top-20-capped.

        The caller (the executor's ``_trigger_critique_analysis`` hook)
        owns the transaction — this method only ``flush()``-es so the
        caller's commit/rollback decision is the one that finalizes
        the write (per ``services/AGENTS.md`` rule 3).

        Empty batches are a no-op (early return) to avoid dirtying the
        brief on no-op critic runs.
        """
        # 1. Load the program (raises ProgramNotFound / ProgramForbidden).
        program = await self.get(user_id, program_id)

        # 2. Reject archived programs (same discipline as consolidate_learning).
        if program.status == "archived":
            raise ProgramTransitionConflict("cannot apply improvement batch to an archived program")

        # 3. Empty-batch short-circuit.
        has_content = (
            bool(batch.plan_adjustments) or bool(batch.tool_suggestions) or bool(batch.common_failure_patterns)
        )
        if not has_content:
            logger.debug(
                "apply_improvement_batch: empty batch, no-op program_id=%s",
                program_id,
            )
            return

        # 4. Build the merge payload — dict-shaped, mirroring the
        #    LearningBriefBase critic_* fields added in T27.
        existing = dict(program.learning_brief or {})
        now_iso = datetime.now(UTC).isoformat()

        new_adjustments = [
            {
                "description": a.description,
                "category": a.category,
                "confidence": a.confidence,
                "source": a.source,
            }
            for a in batch.plan_adjustments
        ]
        new_tools = [
            {
                "tool_name": t.tool_name,
                "reason": t.reason,
                "confidence": t.confidence,
            }
            for t in batch.tool_suggestions
        ]
        new_failures = list(batch.common_failure_patterns)

        merged_adjustments = (list(existing.get("critic_plan_adjustments", [])) + new_adjustments)[
            -self._CRITIC_LIST_CAP :
        ]
        merged_tools = (list(existing.get("critic_tool_suggestions", [])) + new_tools)[-self._CRITIC_LIST_CAP :]
        merged_failures = (list(existing.get("critic_common_failure_patterns", [])) + new_failures)[
            -self._CRITIC_LIST_CAP :
        ]

        merged = {
            **existing,
            "critic_plan_adjustments": merged_adjustments,
            "critic_tool_suggestions": merged_tools,
            "critic_common_failure_patterns": merged_failures,
            "critic_last_applied_at": now_iso,
            # T27 discipline: never overwrite user-owned fields.
            # If the existing brief had user_notes or
            # user_personal_claims, they are preserved via the
            # ``**existing`` spread. If not, the brief gets
            # empty-list defaults via the LearningBriefBase schema
            # when the JSONB is re-hydrated.
        }

        # 5. Persist (column-level UPDATE — touches learning_brief only).
        program.learning_brief = merged
        await self.db.flush()
        await self.db.refresh(program)

        # 6. Audit (non-blocking).
        self._safe_audit(
            "program_improvement_batch_applied",
            program_id=str(program.id),
            user_id=user_id,
            adjustments=len(new_adjustments),
            tool_suggestions=len(new_tools),
            failure_patterns=len(new_failures),
        )

        logger.info(
            "program.improvement_batch_applied program_id=%s user_id=%s adjustments=%d tools=%d failures=%d",
            program_id,
            user_id,
            len(new_adjustments),
            len(new_tools),
            len(new_failures),
        )

    # ── Budget helper (T10) ──────────────────────────────────────────

    async def _check_program_budget(self, program: MissionProgram, estimated_cost_usd: float) -> None:
        """Per-run + monthly budget pre-check.

        Called by ``fire_program`` (T8) BEFORE creating a new Mission to
        reject obviously-over-budget fires. Independent of the
        workspace-level ``BudgetEnforcer`` (per plan §T10 guardrail).

        Both caps being None means no enforcement. Raises
        ``ProgramBudgetExceeded`` if any cap would be exceeded.
        """
        # Per-run cap.
        if program.per_run_budget_usd is not None and estimated_cost_usd > program.per_run_budget_usd:
            raise ProgramBudgetExceeded(
                f"per_run budget exceeded: estimated ${estimated_cost_usd:.4f} > cap ${program.per_run_budget_usd:.4f}"
            )
        # Monthly cap.
        if program.monthly_budget_usd is not None:
            month_start = func.date_trunc("month", func.now())
            spend_stmt = (
                select(func.coalesce(func.sum(ProgramRun.cost_usd), 0.0))
                .where(ProgramRun.program_id == program.id)
                .where(ProgramRun.status.in_(("completed", "failed", "aborted")))
                .where(ProgramRun.created_at >= month_start)
            )
            current_spend = float((await self.db.execute(spend_stmt)).scalar_one() or 0.0)
            projected = current_spend + estimated_cost_usd
            if projected > program.monthly_budget_usd:
                raise ProgramBudgetExceeded(
                    f"monthly budget exceeded: ${projected:.4f} > cap ${program.monthly_budget_usd:.4f}"
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

    @staticmethod
    def _compute_next_fire(expression: str, timezone_str: str = "UTC") -> datetime | None:
        """Compute the next fire time from a cron expression.

        Same logic as ``trigger_service._compute_next_fire`` — uses
        ``croniter`` to evaluate the expression against the current time.
        """
        from typing import Any

        from croniter import croniter

        try:
            from zoneinfo import ZoneInfo

            tz: Any = ZoneInfo(timezone_str)
        except Exception:
            tz = UTC

        now = datetime.now(tz)
        cron = croniter(expression, now)
        next_fire = cron.get_next(datetime)
        if next_fire.tzinfo is None:
            next_fire = next_fire.replace(tzinfo=UTC)
        return next_fire

    def _safe_audit(self, method_name: str, **kwargs: Any) -> None:
        """Call ``self.audit.<method_name>(**kwargs)``; swallow + log failures.

        Audit MUST NOT break the business flow.
        """
        try:
            getattr(self.audit, method_name)(**kwargs)
        except Exception:  # pragma: no cover — defensive
            logger.warning("%s audit failed (non-blocking)", method_name, exc_info=True)
