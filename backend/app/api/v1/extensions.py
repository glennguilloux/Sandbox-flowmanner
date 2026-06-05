"""Extension / Plugin API routes (Task 3.5)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.extension import Extension
from app.models.user import User
from app.schemas.extension import (
    ExtensionCreate,
    ExtensionListResponse,
    ExtensionResponse,
    ExtensionUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/extensions", tags=["extensions"])


def _to_response(ext: Extension) -> dict:
    return {
        "id": str(ext.id),
        "name": ext.name,
        "version": ext.version,
        "description": ext.description,
        "author": ext.author,
        "status": ext.status,
        "manifest": ext.manifest or {},
        "config": ext.config,
        "created_at": str(ext.created_at) if ext.created_at else None,
        "updated_at": str(ext.updated_at) if ext.updated_at else None,
    }


@router.get("", response_model=ExtensionListResponse)
async def list_extensions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Extension).order_by(Extension.created_at.desc()))
    extensions = result.scalars().all()
    return {
        "extensions": [_to_response(e) for e in extensions],
        "total": len(extensions),
    }


@router.post("", response_model=ExtensionResponse, status_code=status.HTTP_201_CREATED)
async def install_extension(
    payload: ExtensionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ext = Extension(
        name=payload.name,
        version=payload.version,
        description=payload.description,
        author=payload.author,
        manifest=payload.manifest,
        status="disabled",
        workspace_id=str(user.id),
    )
    db.add(ext)
    await db.flush()
    await db.refresh(ext)
    return _to_response(ext)


@router.patch("/{extension_id}", response_model=ExtensionResponse)
async def update_extension(
    extension_id: str,
    payload: ExtensionUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Extension).where(Extension.id == extension_id))
    ext = result.scalar_one_or_none()
    if not ext:
        raise HTTPException(status_code=404, detail="Extension not found")
    if payload.status is not None:
        ext.status = payload.status
    if payload.config is not None:
        ext.config = payload.config
    await db.flush()
    await db.refresh(ext)
    return _to_response(ext)


@router.delete("/{extension_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_extension(
    extension_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(Extension).where(Extension.id == extension_id))
    ext = result.scalar_one_or_none()
    if not ext:
        raise HTTPException(status_code=404, detail="Extension not found")
    await db.delete(ext)
