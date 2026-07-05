"""Prompt Version CRUD API — versioned system prompts per workspace."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from app.api.deps import get_current_user
from app.database import get_db
from app.models.prompt_version_models import PromptVersion
from app.services.chat_service import invalidate_prompt_version_cache

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompts", tags=["prompts"])


# ── Request / Response schemas ──────────────────────────────────────


class CreatePromptRequest(BaseModel):
    workspace_id: str
    name: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1)


class PromptVersionResponse(BaseModel):
    id: int
    workspace_id: str
    name: str
    content: str
    version: int
    is_active: bool
    created_by: int | None
    created_at: str | None
    updated_at: str | None

    class Config:
        from_attributes = True


class PromptVersionListResponse(BaseModel):
    items: list[PromptVersionResponse]
    total: int


# ── Helpers ─────────────────────────────────────────────────────────


def _to_response(pv: PromptVersion) -> PromptVersionResponse:
    return PromptVersionResponse(
        id=pv.id,
        workspace_id=pv.workspace_id,
        name=pv.name,
        content=pv.content,
        version=pv.version,
        is_active=pv.is_active,
        created_by=pv.created_by,
        created_at=pv.created_at.isoformat() if pv.created_at else None,
        updated_at=pv.updated_at.isoformat() if pv.updated_at else None,
    )


async def _next_version(db: AsyncSession, workspace_id: str, name: str) -> int:
    """Compute the next version number for a (workspace_id, name) group."""
    result = await db.execute(
        select(func.max(PromptVersion.version)).where(
            PromptVersion.workspace_id == workspace_id,
            PromptVersion.name == name,
        )
    )
    max_ver = result.scalar()
    return (max_ver or 0) + 1


# ── Endpoints ───────────────────────────────────────────────────────


@router.get("", response_model=PromptVersionListResponse)
async def list_prompts(
    workspace_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    name: str | None = None,
    include_inactive: bool = False,
):
    """List prompt versions for a workspace. Optionally filter by name."""
    stmt = select(PromptVersion).where(PromptVersion.workspace_id == workspace_id)
    if not include_inactive:
        stmt = stmt.where(PromptVersion.is_active == True)
    if name:
        stmt = stmt.where(PromptVersion.name == name)
    stmt = stmt.order_by(PromptVersion.name, PromptVersion.version.desc())

    result = await db.execute(stmt)
    items = list(result.scalars().all())

    return PromptVersionListResponse(
        items=[_to_response(pv) for pv in items],
        total=len(items),
    )


@router.post("", response_model=PromptVersionResponse, status_code=201)
async def create_prompt(
    body: CreatePromptRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new prompt version. Auto-increments version number per (workspace_id, name)."""
    version = await _next_version(db, body.workspace_id, body.name)

    pv = PromptVersion(
        workspace_id=body.workspace_id,
        name=body.name,
        content=body.content,
        version=version,
        is_active=True,
        created_by=user.id,
    )
    db.add(pv)

    # Deactivate previous active version for this name group
    await db.execute(
        update(PromptVersion)
        .where(
            PromptVersion.workspace_id == body.workspace_id,
            PromptVersion.name == body.name,
            PromptVersion.id != pv.id,  # type: ignore[arg-type]
            PromptVersion.is_active == True,
        )
        .values(is_active=False)
    )

    await db.flush()
    await db.refresh(pv)

    # Invalidate cache for this workspace+name group
    asyncio.create_task(invalidate_prompt_version_cache(body.workspace_id, body.name))

    return _to_response(pv)


@router.get("/{prompt_id}", response_model=PromptVersionResponse)
async def get_prompt(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a specific prompt version by ID."""
    result = await db.execute(select(PromptVersion).where(PromptVersion.id == prompt_id))
    pv = result.scalar_one_or_none()
    if pv is None:
        raise HTTPException(status_code=404, detail="Prompt version not found")
    return _to_response(pv)


@router.put("/{prompt_id}/activate", response_model=PromptVersionResponse)
async def activate_prompt(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Set this prompt version as the active one for its name group.

    Deactivates all other versions with the same (workspace_id, name).
    """
    result = await db.execute(select(PromptVersion).where(PromptVersion.id == prompt_id))
    pv = result.scalar_one_or_none()
    if pv is None:
        raise HTTPException(status_code=404, detail="Prompt version not found")

    # Deactivate all other versions in the same name group
    await db.execute(
        update(PromptVersion)
        .where(
            PromptVersion.workspace_id == pv.workspace_id,
            PromptVersion.name == pv.name,
            PromptVersion.id != prompt_id,
            PromptVersion.is_active == True,
        )
        .values(is_active=False)
    )

    # Activate the target
    pv.is_active = True
    await db.flush()
    await db.refresh(pv)

    # Invalidate cache for this workspace+name group
    asyncio.create_task(invalidate_prompt_version_cache(pv.workspace_id, pv.name))

    return _to_response(pv)


@router.delete("/{prompt_id}", status_code=204)
async def delete_prompt(
    prompt_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Soft-delete a prompt version (set is_active=False)."""
    result = await db.execute(select(PromptVersion).where(PromptVersion.id == prompt_id))
    pv = result.scalar_one_or_none()
    if pv is None:
        raise HTTPException(status_code=404, detail="Prompt version not found")

    pv.is_active = False
    await db.flush()

    # Invalidate cache for this workspace+name group
    asyncio.create_task(invalidate_prompt_version_cache(pv.workspace_id, pv.name))

    return None
