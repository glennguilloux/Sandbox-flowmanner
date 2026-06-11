"""V2 Run API endpoints — list, get, abort, retry, events, replay, diff.

Follows the CQRS pattern established by mission endpoints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

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
        items=[run.model_dump() for run in r.items],
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
    return ok(run.model_dump())


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
