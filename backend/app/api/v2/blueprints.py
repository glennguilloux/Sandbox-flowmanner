"""V2 Blueprint API endpoints — CRUD, publish, run, version history.

Follows the CQRS pattern established by mission endpoints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query, status

from app.api._blueprint_cqrs.deps import get_blueprint_commands, get_blueprint_queries
from app.api.deps import get_current_user, get_workspace_id
from app.api.v2.base import ok, paginated
from app.schemas.blueprint import (
    BlueprintCreate,
    BlueprintResponse,
    BlueprintUpdate,
    RunCreate,
    RunResponse,
)

if TYPE_CHECKING:
    from app.api._blueprint_cqrs.commands import BlueprintCommandHandlers
    from app.api._blueprint_cqrs.queries import BlueprintQueryHandlers
    from app.models.user import User

router = APIRouter(prefix="/blueprints", tags=["blueprints-v2"])


# ── List / Create ──────────────────────────────────────────────────────────────


@router.get("")
@router.get("/")
async def list_blueprints(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    blueprint_type: str | None = Query(None, description="Filter by blueprint type (solo, dag, swarm, etc.)"),
    status_filter: str | None = Query(None, alias="status", description="Filter by status (draft, published, deprecated)"),
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    q: BlueprintQueryHandlers = Depends(get_blueprint_queries),
):
    """List blueprints with optional type/status filtering."""
    r = await q.list_blueprints(
        user.id, page=page, per_page=per_page,
        workspace_id=workspace_id, blueprint_type=blueprint_type, status=status_filter,
    )
    return paginated(
        items=[b.model_dump() for b in r.items],
        total=r.total, page=r.page, per_page=r.per_page,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_blueprint(
    payload: BlueprintCreate,
    user: User = Depends(get_current_user),
    workspace_id: str | None = Depends(get_workspace_id),
    c: BlueprintCommandHandlers = Depends(get_blueprint_commands),
):
    """Create a new blueprint."""
    bp = await c.create_blueprint(user, payload, workspace_id=workspace_id)
    return ok(BlueprintResponse.model_validate(bp).model_dump())


# ── CRUD ───────────────────────────────────────────────────────────────────────


@router.get("/{blueprint_id}")
@router.get("/{blueprint_id}/")
async def get_blueprint(
    blueprint_id: str,
    user: User = Depends(get_current_user),
    q: BlueprintQueryHandlers = Depends(get_blueprint_queries),
):
    """Get blueprint details."""
    bp = await q.get_blueprint(user.id, blueprint_id)
    return ok(bp.model_dump())


@router.patch("/{blueprint_id}")
async def update_blueprint(
    blueprint_id: str,
    payload: BlueprintUpdate,
    user: User = Depends(get_current_user),
    c: BlueprintCommandHandlers = Depends(get_blueprint_commands),
):
    """Update blueprint. Creates new version if definition changes."""
    bp = await c.update_blueprint(user, blueprint_id, payload)
    return ok(BlueprintResponse.model_validate(bp).model_dump())


@router.delete("/{blueprint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_blueprint(
    blueprint_id: str,
    user: User = Depends(get_current_user),
    c: BlueprintCommandHandlers = Depends(get_blueprint_commands),
):
    """Soft-delete blueprint."""
    await c.delete_blueprint(user, blueprint_id)


# ── Publish ────────────────────────────────────────────────────────────────────


@router.post("/{blueprint_id}/publish")
async def publish_blueprint(
    blueprint_id: str,
    user: User = Depends(get_current_user),
    c: BlueprintCommandHandlers = Depends(get_blueprint_commands),
):
    """Publish a draft blueprint."""
    bp = await c.publish_blueprint(user, blueprint_id)
    return ok(BlueprintResponse.model_validate(bp).model_dump())


# ── Run ────────────────────────────────────────────────────────────────────────


@router.post("/{blueprint_id}/run", status_code=status.HTTP_201_CREATED)
async def run_blueprint(
    blueprint_id: str,
    payload: RunCreate | None = None,
    user: User = Depends(get_current_user),
    c: BlueprintCommandHandlers = Depends(get_blueprint_commands),
):
    """Create and execute a run from this blueprint."""
    run = await c.run_blueprint(user, blueprint_id, payload)
    return ok(RunResponse.model_validate(run).model_dump())


# ── Versions ───────────────────────────────────────────────────────────────────


@router.get("/{blueprint_id}/versions")
@router.get("/{blueprint_id}/versions/")
async def list_versions(
    blueprint_id: str,
    user: User = Depends(get_current_user),
    q: BlueprintQueryHandlers = Depends(get_blueprint_queries),
):
    """List version history."""
    versions = await q.list_versions(user.id, blueprint_id)
    return ok([v.model_dump() for v in versions])



