"""V2 Run API endpoints — list, get, abort, retry, events, replay, diff.

Follows the CQRS pattern established by mission endpoints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Body, Depends, Query

from app.api._blueprint_cqrs.deps import get_run_commands, get_run_queries
from app.api.deps import get_current_user, get_workspace_id
from app.api.v2.base import ok, paginated
from app.schemas.blueprint import RunResponse

if TYPE_CHECKING:
    from app.api._blueprint_cqrs.commands import RunCommandHandlers
    from app.api._blueprint_cqrs.queries import RunQueryHandlers
    from app.models.user import User

router = APIRouter(prefix="/runs", tags=["runs-v2"])


# ── List ───────────────────────────────────────────────────────────────────────


@router.get("")
@router.get("/")
async def list_runs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    blueprint_id: str | None = Query(None, description="Filter by blueprint ID"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status"),
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    q: RunQueryHandlers = Depends(get_run_queries),
):
    """List all runs, filterable by blueprint and status."""
    r = await q.list_runs(
        user.id,
        page=page,
        per_page=per_page,
        workspace_id=workspace_id,
        blueprint_id=blueprint_id,
        status=status_filter,
    )
    return paginated(
        items=[RunResponse.model_validate(run).model_dump() for run in r.items],
        total=r.total,
        page=r.page,
        per_page=r.per_page,
    )


# ── Get ────────────────────────────────────────────────────────────────────────


@router.get("/{run_id}")
@router.get("/{run_id}/")
async def get_run(
    run_id: str,
    user: User = Depends(get_current_user),
    q: RunQueryHandlers = Depends(get_run_queries),
):
    """Get run details and current state."""
    run = await q.get_run(user.id, run_id)
    return ok(RunResponse.model_validate(run).model_dump())


# ── Abort ──────────────────────────────────────────────────────────────────────


@router.post("/{run_id}/abort")
async def abort_run(
    run_id: str,
    reason: str = "user_requested",
    user: User = Depends(get_current_user),
    c: RunCommandHandlers = Depends(get_run_commands),
):
    """Abort a running execution."""
    run = await c.abort_run(user, run_id, reason)
    return ok(RunResponse.model_validate(run).model_dump())


# ── Pause ──────────────────────────────────────────────────────────────────────


@router.post("/{run_id}/pause")
async def pause_run(
    run_id: str,
    user: User = Depends(get_current_user),
    c: RunCommandHandlers = Depends(get_run_commands),
):
    """Pause a running execution."""
    run = await c.pause_run(user, run_id)
    return ok(RunResponse.model_validate(run).model_dump())


# ── Resume ─────────────────────────────────────────────────────────────────────


@router.post("/{run_id}/resume")
async def resume_run(
    run_id: str,
    user: User = Depends(get_current_user),
    c: RunCommandHandlers = Depends(get_run_commands),
):
    """Resume a paused execution."""
    run = await c.resume_run(user, run_id)
    return ok(RunResponse.model_validate(run).model_dump())


# ── Retry ──────────────────────────────────────────────────────────────────────


@router.post("/{run_id}/retry")
async def retry_run(
    run_id: str,
    user: User = Depends(get_current_user),
    c: RunCommandHandlers = Depends(get_run_commands),
):
    """Retry a failed run (creates new run from same blueprint)."""
    run = await c.retry_run(user, run_id)
    return ok(RunResponse.model_validate(run).model_dump())


# ── Fork ──────────────────────────────────────────────────────────────────────

@router.post("/{run_id}/fork")
async def fork_run(
    run_id: str,
    user: User = Depends(get_current_user),
    c: RunCommandHandlers = Depends(get_run_commands),
    from_sequence: int = Body(..., description="Replay checkpoint sequence to fork from"),
    instruction: str = Body(..., description="Edited instruction for the forked node"),
):
    """Fork a run from a mid-step edit (graph promotion / compounding, Phase 3).

    Replays the original run's event log up to ``from_sequence`` to locate the
    active node, patches that node's instruction with ``instruction``, and
    dispatches a NEW run (linked via ``parent_run_id``) through the unified
    executor. The returned ``new_run_id`` can be compared with the original via
    ``/diff/{new_run_id}``.
    """
    result = await c.fork_run(
        user, run_id, from_sequence=from_sequence, instruction=instruction
    )
    return ok(result)


# ── Events ─────────────────────────────────────────────────────────────────────


@router.get("/{run_id}/events")
@router.get("/{run_id}/events/")
async def get_run_events(
    run_id: str,
    from_sequence: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=10000),
    user: User = Depends(get_current_user),
    q: RunQueryHandlers = Depends(get_run_queries),
):
    """Get substrate event stream for this run."""
    events = await q.get_events(user.id, run_id, from_sequence=from_sequence, limit=limit)
    return ok(
        {
            "run_id": run_id,
            "events": [e.model_dump() for e in events],
            "count": len(events),
        }
    )


# ── Provenance ──────────────────────────────────────────────────────────────


@router.get("/{run_id}/provenance")
@router.get("/{run_id}/provenance/")
async def get_run_provenance(
    run_id: str,
    from_sequence: int = Query(0, ge=0, description="Inclusive lower bound on sequence"),
    limit: int = Query(10000, ge=1, le=100000, description="Max events to project"),
    user: User = Depends(get_current_user),
    q: RunQueryHandlers = Depends(get_run_queries),
):
    """Provenance READ over the substrate event log (explainability).

    Returns one projection per event: which actor fired it, its causal
    parent, the reasoning/tool/capability/budget behind it, and a content
    hash. No second audit store — this is a read-only projection over the
    existing append-only event log. Missing fields are returned as null.
    """
    provenance = await q.get_provenance(user.id, run_id, from_sequence=from_sequence, limit=limit)
    return ok(
        {
            "run_id": run_id,
            "provenance": provenance,
            "count": len(provenance),
        }
    )


# ── Replay ─────────────────────────────────────────────────────────────────────


@router.get("/{run_id}/replay")
@router.get("/{run_id}/replay/")
async def replay_run(
    run_id: str,
    at_sequence: int | None = Query(None, ge=0, description="Replay up to this sequence (time-travel)"),
    user: User = Depends(get_current_user),
    q: RunQueryHandlers = Depends(get_run_queries),
):
    """Replay run state. If at_sequence is given, rebuild state at that point."""
    state = await q.replay_state(user.id, run_id, at_sequence=at_sequence)
    return ok(state)


# ── Assertions ────────────────────────────────────────────────────────────────


@router.get("/{run_id}/assertions")
@router.get("/{run_id}/assertions/")
async def get_run_assertions(
    run_id: str,
    user: User = Depends(get_current_user),
    q: RunQueryHandlers = Depends(get_run_queries),
):
    """Auto-generate and evaluate assertions for a completed run."""
    result = await q.get_assertions(user.id, run_id)
    return ok(result)


# ── Tree (layered step tree) ───────────────────────────────────────


@router.get("/{run_id}/tree")
@router.get("/{run_id}/tree/")
async def get_run_tree(
    run_id: str,
    user: User = Depends(get_current_user),
    q: RunQueryHandlers = Depends(get_run_queries),
):
    """Get the layered step tree for a run (DAG promotion, Phase 2).

    Returns the run's nodes grouped by execution layer, each node carrying
    its current status (derived from the event log) and what it depends on.
    Solo/single-node runs return a single layer with one node.
    """
    tree = await q.get_run_tree(user.id, run_id)
    return ok(tree)


# ── Diff ───────────────────────────────────────────────────────────────────────


@router.get("/{run_id}/diff/{other_run_id}")
async def diff_runs(
    run_id: str,
    other_run_id: str,
    user: User = Depends(get_current_user),
    q: RunQueryHandlers = Depends(get_run_queries),
):
    """Compare two runs of the same blueprint."""
    diff = await q.diff_runs(user.id, run_id, other_run_id)
    return ok(diff)
