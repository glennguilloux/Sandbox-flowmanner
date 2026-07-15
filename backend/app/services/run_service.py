"""Run service — lifecycle management for Blueprint execution instances.

Creates runs from blueprints, delegates to UnifiedExecutor, manages
abort/retry lifecycle.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from sqlalchemy import func, select

from app.models.blueprint_models import Blueprint, Run, RunStatus
from app.models.workspace_models import WorkspaceMember
from app.services.substrate.adapters import blueprint_to_workflow
from app.services.substrate.executor import get_unified_executor
from app.services.substrate.replay_engine import get_replay_engine

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.substrate_models import SubstrateEvent

logger = logging.getLogger(__name__)


class RunNotFoundError(Exception):
    """Raised when a run is not found or access is denied."""

    pass


class RunValidationError(Exception):
    """Raised when a run operation is invalid."""

    pass


class RunService:
    """Run lifecycle management — create, execute, abort, retry."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Create from Blueprint ───────────────────────────────────────

    async def create_from_blueprint(
        self,
        blueprint_id: str,
        user_id: int,
        input_data: dict | None = None,
        budget_override: dict | None = None,
    ) -> Run:
        """Create a Run from a Blueprint.

        1. Load Blueprint
        2. Snapshot Blueprint.definition into Run.snapshot
        3. Create Run record (status=pending)
        4. Return Run (caller decides when to execute)
        """
        result = await self.db.execute(
            select(Blueprint).where(
                Blueprint.id == str(blueprint_id),
                Blueprint.deleted_at.is_(None),
            )
        )
        bp = result.scalar_one_or_none()
        if bp is None:
            raise RunValidationError(f"Blueprint {blueprint_id} not found")

        # Build snapshot from current blueprint definition
        snapshot = {
            "blueprint_type": bp.blueprint_type,
            "title": bp.title,
            "description": bp.description,
            **(bp.definition or {}),
        }

        # Apply budget override if provided
        if budget_override:
            snapshot["budget"] = budget_override

        # Calculate budget limit for the run
        budget = snapshot.get("budget", {})
        budget_limit = budget.get("max_cost_usd")

        run = Run(
            id=str(uuid4()),
            blueprint_id=str(bp.id),
            workspace_id=bp.workspace_id,
            user_id=user_id,
            status=RunStatus.PENDING.value,
            snapshot=snapshot,
            input_data=input_data,
            budget_limit_usd=budget_limit,
        )
        self.db.add(run)
        await self.db.flush()
        return run

    # ── Execute ─────────────────────────────────────────────────────

    async def execute(self, run_id: str, user_id: int) -> Run:
        """Execute a run through UnifiedExecutor.

        1. Load Run + snapshot
        2. Convert snapshot to Workflow via blueprint_to_workflow()
        3. Call UnifiedExecutor.execute(db, workflow, run_id=run.id)
        4. Update Run from StrategyResult
        5. Update Blueprint.run_count and Blueprint.last_run_at
        """
        run = await self.get(run_id, user_id)

        if run.status not in (RunStatus.PENDING.value, RunStatus.QUEUED.value):
            raise RunValidationError(
                f"Cannot execute run in '{run.status}' status. Only pending or queued runs can be executed."
            )

        # Mark as executing
        run.status = RunStatus.EXECUTING.value
        run.started_at = datetime.now(UTC)
        await self.db.flush()

        # Convert snapshot to Workflow
        workflow = blueprint_to_workflow(
            snapshot=run.snapshot,
            blueprint_id=str(run.blueprint_id) if run.blueprint_id else str(run.id),
            user_id=str(user_id),
        )

        # Execute through unified executor
        executor = get_unified_executor()
        context = {"inputs": run.input_data or {}}
        result = await executor.execute(
            db=self.db,
            workflow=workflow,
            run_id=str(run.id),
            blueprint_id=str(run.blueprint_id) if run.blueprint_id else None,
            context=context,
        )

        # Update run from result
        run.status = result.status
        run.total_tokens = result.total_tokens
        run.total_cost_usd = result.total_cost_usd
        run.error_message = result.error
        if result.status in ("completed", "failed", "aborted"):
            run.completed_at = datetime.now(UTC)
        if result.data is not None:
            run.output_data = result.data if isinstance(result.data, dict) else {"result": result.data}

        # Update blueprint stats
        if run.blueprint_id:
            bp_result = await self.db.execute(select(Blueprint).where(Blueprint.id == run.blueprint_id))
            bp = bp_result.scalar_one_or_none()
            if bp:
                bp.run_count = (bp.run_count or 0) + 1
                bp.last_run_at = datetime.now(UTC)

        await self.db.flush()
        return run

    async def execute_async(self, run_id: str, user_id: int) -> Run:
        """Queue run for async execution via Celery."""
        run = await self.get(run_id, user_id)
        run.status = RunStatus.QUEUED.value
        await self.db.flush()

        # B5 FIX (cutover plan §0 B5): dispatch to Celery directly.
        # No silent asyncio.create_task fallback — under a Celery outage,
        # we surface the failure so callers see the real error rather than
        # an orphaned background task that dies with the worker process.
        from app.tasks.mission_execution import dispatch_mission_execution

        dispatch_mission_execution(str(run.id), user_id)

        return run

    # ── Abort ───────────────────────────────────────────────────────

    async def abort(self, run_id: str, user_id: int, reason: str = "user_requested") -> Run:
        """Abort a running execution."""
        run = await self.get(run_id, user_id)

        active_statuses = {
            RunStatus.PENDING.value,
            RunStatus.QUEUED.value,
            RunStatus.EXECUTING.value,
            RunStatus.PAUSED.value,
        }
        if run.status not in active_statuses:
            raise RunValidationError(f"Cannot abort run in '{run.status}' status. Only active runs can be aborted.")

        run.status = RunStatus.ABORTED.value
        run.error_message = f"Aborted: {reason}"
        run.completed_at = datetime.now(UTC)
        await self.db.flush()

        # Signal UnifiedExecutor abort
        try:
            executor = get_unified_executor()
            await executor.abort(str(run.id), reason=reason)
        except Exception:
            logger.debug("UnifiedExecutor abort signal failed", exc_info=True)

        return run

    # ── Retry ───────────────────────────────────────────────────────

    async def retry(self, run_id: str, user_id: int) -> Run:
        """Retry a failed run — creates a NEW run from the same blueprint."""
        original = await self.get(run_id, user_id)

        if original.status != RunStatus.FAILED.value:
            raise RunValidationError(f"Can only retry a failed run, not '{original.status}'.")

        # Create new run from same blueprint/snapshot
        new_run = Run(
            id=str(uuid4()),
            blueprint_id=original.blueprint_id,
            workspace_id=original.workspace_id,
            user_id=user_id,
            status=RunStatus.PENDING.value,
            snapshot=original.snapshot,
            input_data=original.input_data,
            budget_limit_usd=original.budget_limit_usd,
        )
        self.db.add(new_run)
        await self.db.flush()
        return new_run

    # ── Read ────────────────────────────────────────────────────────

    async def get(self, run_id: str, user_id: int) -> Run:
        """Get run with ownership/workspace check."""
        result = await self.db.execute(select(Run).where(Run.id == str(run_id)))
        run = result.scalar_one_or_none()
        if run is None:
            raise RunNotFoundError(f"Run {run_id} not found")

        await self._check_access(run, user_id)
        return run

    async def list_runs(  # renamed from `list` (couldn't be `list`: shadows builtin inside class body)
        self,
        user_id: int,
        page: int = 1,
        per_page: int = 20,
        workspace_id: str | None = None,
        blueprint_id: str | None = None,
        status: str | None = None,
    ) -> tuple[list[Run], int]:
        """List runs with filtering and pagination.

        Renamed from ``list`` to ``list_runs`` because class-method ``list``
        shadows ``builtins.list`` inside the class body, making mypy reject
        ``-> list[Run]`` with [valid-type].  Run-service callers now
        invoke ``svc.list_runs(...)`` instead of ``svc.list(...)``.
        """
        stmt = select(Run)

        if workspace_id is not None:
            stmt = stmt.where(Run.workspace_id == workspace_id)
        else:
            stmt = stmt.where(Run.user_id == user_id)

        if blueprint_id is not None:
            stmt = stmt.where(Run.blueprint_id == str(blueprint_id))
        if status is not None:
            stmt = stmt.where(Run.status == status)

        # Count
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar() or 0

        # Paginate
        offset = (page - 1) * per_page
        stmt = stmt.order_by(Run.created_at.desc()).offset(offset).limit(per_page)
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    # ── Events ──────────────────────────────────────────────────────

    async def get_events(
        self,
        run_id: str,
        user_id: int,
        from_sequence: int = 0,
        limit: int = 1000,
    ) -> list[SubstrateEvent]:
        """Get substrate events for a run."""
        await self.get(run_id, user_id)  # access check

        from app.services.substrate.event_log import get_event_log

        event_log = get_event_log()
        return await event_log.get_events(
            self.db,
            str(run_id),
            from_sequence=from_sequence,
            limit=limit,
        )

    # ── Replay ──────────────────────────────────────────────────────

    async def replay_state(self, run_id: str, user_id: int, at_sequence: int | None = None) -> dict:
        """Replay events to rebuild run state.

        If at_sequence is provided, rebuild state at that point (time-travel).
        """
        await self.get(run_id, user_id)  # access check

        replay = get_replay_engine()
        if at_sequence is not None:
            state = await replay.rebuild_state_at_sequence(self.db, str(run_id), at_sequence)
        else:
            state = await replay.rebuild_state(self.db, str(run_id))
        return state.to_dict()

    # ── Assertions ──────────────────────────────────────────────────

    async def get_assertions(self, run_id: str, user_id: int) -> dict:
        """Auto-generate and evaluate assertions for a completed run.

        Uses BaselineExtractor to generate expected behaviors from the run,
        then evaluates them with ReplayAssertionEngine.
        """
        run = await self.get(run_id, user_id)  # access check

        from app.services.substrate.assertion_engine import get_assertion_engine
        from app.services.substrate.baseline_extractor import get_baseline_extractor

        extractor = get_baseline_extractor()
        engine = get_assertion_engine()

        # Extract expected behaviors from this run
        expected_behaviors = await extractor.extract_from_run(self.db, str(run_id))

        # Evaluate them
        results = await engine.evaluate(self.db, str(run_id), expected_behaviors)

        return {
            "run_id": str(run_id),
            "status": run.status,
            "total_cost_usd": run.total_cost_usd,
            "total_tokens": run.total_tokens,
            "assertions": [r.to_dict() for r in results],
            "assertion_count": len(results),
            "passed_count": sum(1 for r in results if r.passed),
            "failed_count": sum(1 for r in results if not r.passed),
        }

    # ── Diff ────────────────────────────────────────────────────────

    async def diff_runs(self, run_a_id: str, run_b_id: str, user_id: int) -> dict:
        """Compare two runs of the same blueprint."""
        run_a = await self.get(run_a_id, user_id)
        run_b = await self.get(run_b_id, user_id)

        replay = get_replay_engine()
        state_a = await replay.rebuild_state(self.db, str(run_a_id))
        state_b = await replay.rebuild_state(self.db, str(run_b_id))

        return {
            "run_a": {
                "id": str(run_a.id),
                "status": run_a.status,
                "total_tokens": run_a.total_tokens,
                "total_cost_usd": run_a.total_cost_usd,
                "state": state_a.to_dict(),
            },
            "run_b": {
                "id": str(run_b.id),
                "status": run_b.status,
                "total_tokens": run_b.total_tokens,
                "total_cost_usd": run_b.total_cost_usd,
                "state": state_b.to_dict(),
            },
            "diff": {
                "token_delta": (run_b.total_tokens or 0) - (run_a.total_tokens or 0),
                "cost_delta": (run_b.total_cost_usd or 0) - (run_a.total_cost_usd or 0),
                "status_match": run_a.status == run_b.status,
                "completed_a": len(state_a.completed_tasks),
                "completed_b": len(state_b.completed_tasks),
                "failed_a": len(state_a.failed_tasks),
                "failed_b": len(state_b.failed_tasks),
            },
        }

    # ── Internal ────────────────────────────────────────────────────

    async def _check_access(self, run: Run, user_id: int) -> None:
        """Check if user has access to the run."""
        if run.user_id == user_id:
            return

        if run.workspace_id:
            result = await self.db.execute(
                select(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == run.workspace_id,
                    WorkspaceMember.user_id == user_id,
                    WorkspaceMember.is_active == True,
                )
            )
            if result.scalar_one_or_none() is not None:
                return

        raise RunNotFoundError(f"Run {run.id} not found")
