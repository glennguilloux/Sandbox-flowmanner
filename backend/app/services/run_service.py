"""Run service — lifecycle management for Blueprint execution instances.

Creates runs from blueprints, delegates to UnifiedExecutor, manages
abort/retry lifecycle.
"""

from __future__ import annotations

import hashlib
import json as _json
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import func, select

from app.models.blueprint_models import Blueprint, Run, RunStatus
from app.models.mission_models import Mission
from app.models.workspace_models import WorkspaceMember
from app.services.mission_service import create_mission as _create_mission
from app.services.substrate.adapters import InvalidBlueprintGraphError, blueprint_to_workflow
from app.services.substrate.executor import get_unified_executor
from app.services.substrate.replay_engine import get_replay_engine

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.substrate_models import SubstrateEvent


def _topo_layers(workflow: Any) -> list[list[str]]:
    """Kahn's topological sort → execution layers for a Workflow.

    Read-only helper shared by ``get_run_tree``.  Returns layers in
    dependency order (layer 0 = roots).  A cycle (should not happen for a
    validated substrate workflow) yields as many layers as reachable nodes
    and drops the unreachable remainder, matching ``DAGStrategy``'s contract
    that cycles are rejected at validate() time.
    """
    in_deg = workflow.get_in_degree()
    adj: dict[str, list[str]] = {n.id: [] for n in workflow.nodes}
    for e in workflow.edges:
        if e.source in adj and e.target in in_deg:
            adj[e.source].append(e.target)

    queue = [nid for nid, deg in in_deg.items() if deg == 0]
    layers: list[list[str]] = []
    seen = 0
    while queue:
        layers.append(list(queue))
        seen += len(queue)
        next_queue: list[str] = []
        for nid in queue:
            for tgt in adj[nid]:
                in_deg[tgt] -= 1
                if in_deg[tgt] == 0:
                    next_queue.append(tgt)
        queue = next_queue
    # Defensive: if a cycle left nodes unvisited, surface them in a final
    # layer rather than silently dropping them.
    leftover = [nid for nid, deg in in_deg.items() if deg > 0]
    if leftover:
        layers.append(leftover)
    return layers


def _direct_deps(workflow: Any, node_id: str) -> list[str]:
    """Return node ids with a direct edge into ``node_id``."""
    return [e.source for e in workflow.edges if e.target == node_id]


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
        mission_id: str | None = None,
    ) -> Run:
        """Create a Run from a Blueprint.

        1. Load Blueprint
        2. Snapshot Blueprint.definition into Run.snapshot
        3. Create Run record (status=pending)
        4. Return Run (caller decides when to execute)

        The Run is linked to a Mission so the Chat MissionStatusTile can poll
        the mission a run was created from. If ``mission_id`` is caller-supplied
        it is used as-is; otherwise a Mission is created inline from the
        blueprint definition (title/description/workspace) so the link always
        exists. A2a: we use the lightweight ``mission_service.create_mission``
        rather than ``MissionCommandHandlers.create_mission`` to avoid pulling
        the User object, subscription tier checks, cache invalidation, and audit
        side effects into the blueprint-run path — those belong to the mission
        create route, not a run link.
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

        # Link the run to a Mission so the Chat MissionStatusTile has something
        # to poll. Prefer a caller-supplied mission_id; otherwise create one
        # inline from the blueprint definition. Both paths reuse the same
        # session/transaction as the run.
        if mission_id is None:
            mission = await _create_mission(
                db=self.db,
                title=bp.title or "Blueprint run",
                description=bp.description or "",
                mission_type="blueprint_run",
                user_id=user_id,
                status="pending",
                workspace_id=bp.workspace_id,
            )
            mission_id = str(mission.id)

        run.mission_id = mission_id

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

        # Convert snapshot to Workflow. A structurally broken snapshot
        # (e.g. an edge whose source/target names a node id that
        # does not exist, or a self-loop) raises
        # InvalidBlueprintGraphError from the adapter instead of being
        # silently dropped. Surface it as a RunValidationError so the
        # API layer returns a clear 4xx rather than a 500 / silent
        # data loss.
        try:
            workflow = blueprint_to_workflow(
                snapshot=run.snapshot,
                blueprint_id=str(run.blueprint_id) if run.blueprint_id else str(run.id),
                user_id=str(user_id),
            )
        except InvalidBlueprintGraphError as exc:
            raise RunValidationError(str(exc)) from exc

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

    # ── Pause ───────────────────────────────────────────────────────

    async def pause(self, run_id: str, user_id: int) -> Run:
        """Pause a running execution (director control)."""
        run = await self.get(run_id, user_id)

        if run.status != RunStatus.EXECUTING.value:
            raise RunValidationError(f"Cannot pause run in '{run.status}' status. Only executing runs can be paused.")

        run.status = RunStatus.PAUSED.value
        await self.db.flush()

        # Signal UnifiedExecutor pause
        try:
            executor = get_unified_executor()
            await executor.pause(str(run.id), db=self.db)
        except Exception:
            logger.debug("UnifiedExecutor pause signal failed", exc_info=True)

        return run

    # ── Resume ──────────────────────────────────────────────────────

    async def resume(self, run_id: str, user_id: int) -> Run:
        """Resume a paused execution (director control)."""
        run = await self.get(run_id, user_id)

        if run.status != RunStatus.PAUSED.value:
            raise RunValidationError(f"Cannot resume run in '{run.status}' status. Only paused runs can be resumed.")

        run.status = RunStatus.EXECUTING.value
        await self.db.flush()

        # Signal UnifiedExecutor resume
        try:
            executor = get_unified_executor()
            await executor.resume(str(run.id), db=self.db)
        except Exception:
            logger.debug("UnifiedExecutor resume signal failed", exc_info=True)

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

    # ── Provenance ─────────────────────────────────────────────────

    async def get_provenance(
        self,
        run_id: str,
        user_id: int,
        *,
        from_sequence: int = 0,
        limit: int = 10_000,
    ) -> list[dict]:
        """READ over the substrate event log — explainability (Phase 2).

        Provenance answers *why a step happened*: which actor fired it,
        what its causal parent was, what tool/capability/budget it used,
        and a content hash of its payload. No second audit store — this is
        a projection built from the existing append-only ``substrate_events``
        table.

        Per contract 10 (``_blueprint_cqrs`` AGENTS.md), substrate reads use a
        separate read session so this projection never touches the caller's
        write transaction.

        Field extraction is best-effort: ``reasoning``, ``tool_name``,
        ``capability_scope`` and ``budget_spent`` come from the event payload
        when present, otherwise ``None``. ``content_hash`` is derived from the
        payload when the event does not carry one explicitly.
        """
        await self.get(run_id, user_id)  # access/ownership check

        from app.database import AsyncSessionLocal
        from app.services.substrate.event_log import get_event_log

        async with AsyncSessionLocal() as read_session:
            event_log = get_event_log()
            events = await event_log.get_events(
                read_session,
                str(run_id),
                from_sequence=from_sequence,
                limit=limit,
            )
            return [_event_to_provenance(e) for e in events]

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

    async def get_run_tree(self, run_id: str, user_id: int) -> dict:
        """Return the layered step tree for a run, derived from its event log.

        The tree structure (which node sits in which layer, and what each node
        depends on) is the workflow topology stored in the run's ``snapshot``
        — the substrate's durable source of truth for layering.  Node *status*
        (pending / running / completed / failed) is read from the append-only
        event log by replaying it through ``ReplayEngine`` (authoritative), so
        the tree always reflects the real execution state without a separate
        projection table.

        Returns a dict with:
            run_id, workflow_type, status, and
            layers: list of {layer:int, nodes:[{node_id, title, node_type,
                                                 status, depends_on}]}
        in dependency order (layer 0 first).
        """
        run = await self.get(run_id, user_id)  # access check

        # Topology from the stored snapshot (the durable graph). For non-DAG
        # runs this still produces a single layer with one node.
        workflow = blueprint_to_workflow(
            snapshot=run.snapshot or {},
            blueprint_id=str(run.blueprint_id) if run.blueprint_id else str(run.id),
            user_id=str(user_id),
        )

        # Node status from the event log (source of truth).
        replay = get_replay_engine()
        state = await replay.rebuild_state(self.db, str(run.id))
        task_states = state.task_states  # task_id -> {"status": ...}

        layers = _topo_layers(workflow)
        tree_layers: list[dict] = []
        for i, layer in enumerate(layers):
            nodes = []
            for nid in layer:
                node = workflow.node_map.get(nid)
                if node is None:
                    continue
                st = task_states.get(nid, {}).get("status", "pending")
                nodes.append(
                    {
                        "node_id": nid,
                        "title": node.title,
                        "node_type": node.type.value,
                        "status": st,
                        "depends_on": _direct_deps(workflow, nid),
                    }
                )
            tree_layers.append({"layer": i, "nodes": nodes})

        return {
            "run_id": str(run.id),
            "workflow_type": workflow.type.value,
            "status": run.status,
            "layers": tree_layers,
        }

    async def get_run_graph(self, run_id: str, user_id: int) -> dict:
        """Return the full graph for a run (graph promotion, Phase 3).

        Unlike ``get_run_tree`` (which collapses the topology into layers of
        nodes), this returns the *complete* graph: every node, every edge
        (including conditional edges and their ``condition``/``label``), the
        layered execution order, and — derived from the event log — which
        conditional edges were actually *taken* at runtime.  This is what lets
        the frontend render branches and highlight the path that executed,
        distinguishing a graph run from the DAG's pure fan-out.

        Returns a dict with:
            run_id, workflow_type, status,
            nodes: [{
                node_id, title, node_type, status,
                layer, depends_on,
            }],
            edges: [{
                source, target, condition, label, taken,
            }],
        """
        run = await self.get(run_id, user_id)  # access check

        workflow = blueprint_to_workflow(
            snapshot=run.snapshot or {},
            blueprint_id=str(run.blueprint_id) if run.blueprint_id else str(run.id),
            user_id=str(user_id),
        )

        # Node status from the event log (source of truth).
        replay = get_replay_engine()
        state = await replay.rebuild_state(self.db, str(run.id))
        task_states = state.task_states  # task_id -> {"status": ...}

        layers = _topo_layers(workflow)
        node_layer: dict[str, int] = {}
        graph_nodes: list[dict] = []
        for i, layer in enumerate(layers):
            for nid in layer:
                node_layer[nid] = i
                node = workflow.node_map.get(nid)
                if node is None:
                    continue
                st = task_states.get(nid, {}).get("status", "pending")
                graph_nodes.append(
                    {
                        "node_id": nid,
                        "title": node.title,
                        "node_type": node.type.value,
                        "status": st,
                        "layer": i,
                        "depends_on": _direct_deps(workflow, nid),
                    }
                )

        # Which edges were taken? Control actually flows across an edge only
        # if BOTH its source AND target executed (reached a terminal status).
        # A branch edge whose source (e.g. `decide`) fired but whose target
        # (e.g. `branch_a`) never ran is NOT taken — that is the signal the
        # frontend uses to render "this branch was skipped." A plain
        # dependency edge (source never ran) is also not taken.
        executed = {nid for nid, ts in task_states.items() if ts.get("status") in ("completed", "failed")}
        graph_edges: list[dict] = []
        for e in workflow.edges:
            taken = e.source in executed and e.target in executed
            graph_edges.append(
                {
                    "source": e.source,
                    "target": e.target,
                    "condition": e.condition,
                    "label": e.label,
                    "taken": taken,
                }
            )

        return {
            "run_id": str(run.id),
            "workflow_type": workflow.type.value,
            "status": run.status,
            "nodes": graph_nodes,
            "edges": graph_edges,
        }

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


# ── Provenance projection helper ──────────────────────────────────
#
# Module-level so tests can call it directly without a DB session.
# Best-effort extraction from the substrate event: model fields give the
# structural provenance (seq / actor / causal_parent / type) and the payload
# is mined for explainability fields (reasoning / tool / capability / budget).
# Anything not emitted by the event log falls back to ``None``.


def _event_to_provenance(event: Any) -> dict:
    """Project a substrate event into a provenance record.

    Returns a flat dict with keys:
        seq, actor, causal_parent, type, reasoning, tool_name,
        capability_scope, budget_spent, content_hash

    ``content_hash`` is taken from the payload's ``content_hash`` key when
    present, otherwise computed as a sha256 of the canonical payload JSON so
    two events with identical payloads always hash identically.
    """
    payload: dict = event.payload or {}

    # ── tool_name: several emit shapes ──
    tool_name = (
        payload.get("tool_name")
        or payload.get("tool")
        or (payload.get("tool_call") or {}).get("name")
        or (payload.get("tool_call") or {}).get("tool")
        or (payload.get("tool_result") or {}).get("tool")
        or payload.get("node_type")
    )

    # ── capability_scope: explicit key, or nested under capability token ──
    capability_scope = (
        payload.get("capability_scope")
        or (payload.get("capability_token") or {}).get("scope")
        or (payload.get("capability") or {}).get("scope")
    )

    # ── budget_spent: explicit cost keys ──
    budget_spent = payload.get("budget_spent") or payload.get("cost_usd") or payload.get("spent_usd")
    # Coerce to float when numeric so the contract stays typed.
    if budget_spent is not None:
        try:
            budget_spent = float(budget_spent)
        except (TypeError, ValueError):
            budget_spent = None

    # ── reasoning ──
    reasoning = payload.get("reasoning") or payload.get("rationale")

    # ── content_hash ──
    content_hash = payload.get("content_hash")
    if content_hash is None:
        content_hash = hashlib.sha256(_json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    return {
        "seq": event.sequence,
        "actor": event.actor,
        "causal_parent": event.causal_parent,
        "type": event.type,
        "reasoning": reasoning,
        "tool_name": tool_name,
        "capability_scope": capability_scope,
        "budget_spent": budget_spent,
        "content_hash": content_hash,
    }
