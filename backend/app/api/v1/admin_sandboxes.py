"""Admin routes for bulk sandbox cleanup."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.api.deps import get_current_user
from app.integrations.sandboxd_client import get_sandboxd_client
from app.models.playground_models import PlaygroundSandbox, PlaygroundSandboxStatus
from app.models.sandbox_models import MissionSandbox
from app.services.playground_service import PlaygroundService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/sandboxes", tags=["admin-sandboxes"])


class PurgeResponse(BaseModel):
    purged_count: int
    message: str


@router.post("/purge-by-user/{user_id}", response_model=PurgeResponse)
async def purge_sandboxes_by_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(get_current_user),
):
    """Purge all sandboxes (mission + playground) owned by a user. Requires admin."""
    if not admin_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    client = get_sandboxd_client()
    count = 0

    # Purge playground sandboxes
    result = await db.execute(
        select(PlaygroundSandbox).where(
            PlaygroundSandbox.user_id == user_id,
            PlaygroundSandbox.status != PlaygroundSandboxStatus.PURGED.value,
        )
    )
    for pg in result.scalars().all():
        try:
            await client.delete(pg.sandbox_id)
        except Exception as e:
            logger.warning("Failed to delete sandboxd container %s: %s", pg.sandbox_id, e)
        pg.status = PlaygroundSandboxStatus.PURGED.value
        count += 1

    # Purge mission sandboxes for this user
    result = await db.execute(
        select(MissionSandbox).where(
            MissionSandbox.status != "purged",
        )
    )
    for ms in result.scalars().all():
        if ms.metadata_ and str(user_id) in str(ms.metadata_):
            try:
                await client.delete(ms.sandbox_id)
            except Exception as e:
                logger.warning("Failed to delete sandboxd container %s: %s", ms.sandbox_id, e)
            ms.status = "purged"
            count += 1

    await db.commit()
    return PurgeResponse(
        purged_count=count,
        message=f"Purged {count} sandboxes for user {user_id}",
    )


@router.post("/purge-expired", response_model=PurgeResponse)
async def purge_expired_sandboxes(
    db: AsyncSession = Depends(get_db),
    admin_user=Depends(get_current_user),
):
    """Purge all expired playground sandboxes (manual trigger). Requires admin."""
    if not admin_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    service = PlaygroundService()
    count = await service.purge_expired(db=db)
    await db.commit()
    return PurgeResponse(
        purged_count=count,
        message=f"Purged {count} expired sandboxes",
    )
