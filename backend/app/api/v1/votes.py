"""Roadmap votes API."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import get_current_user
from app.database import get_db
from app.models.roadmap_models import RoadmapItem, RoadmapVote

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(prefix="/votes", tags=["votes"])


class VoteIn(BaseModel):
    item_id: str
    vote_type: str = "up"


class VoteOut(BaseModel):
    success: bool
    vote_count: int


@router.post("", response_model=VoteOut)
@router.post("/", response_model=VoteOut)
async def cast_vote(
    body: VoteIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cast or update a vote on a roadmap item."""
    try:
        item_uuid = uuid.UUID(body.item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid item_id")

    # Check item exists
    result = await db.execute(select(RoadmapItem).where(RoadmapItem.id == item_uuid))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Roadmap item not found")

    # Check existing vote
    result = await db.execute(
        select(RoadmapVote).where(
            RoadmapVote.item_id == item_uuid,
            RoadmapVote.user_id == user.id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        if existing.vote_type == body.vote_type:
            # Same vote — remove it (toggle off)
            await db.delete(existing)
            item.vote_count = max(0, item.vote_count - 1)
        else:
            # Change vote direction
            existing.vote_type = body.vote_type
            # Net zero change (was up now down or vice versa)
    else:
        # New vote
        vote = RoadmapVote(
            item_id=item_uuid,
            user_id=user.id,
            vote_type=body.vote_type,
        )
        db.add(vote)
        item.vote_count += 1

    await db.flush()
    await db.refresh(item)

    return VoteOut(success=True, vote_count=item.vote_count)


@router.delete("", response_model=VoteOut)
@router.delete("/", response_model=VoteOut)
async def remove_vote(
    item_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a vote from a roadmap item."""
    try:
        item_uuid = uuid.UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid item_id")

    result = await db.execute(select(RoadmapItem).where(RoadmapItem.id == item_uuid))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Roadmap item not found")

    result = await db.execute(
        select(RoadmapVote).where(
            RoadmapVote.item_id == item_uuid,
            RoadmapVote.user_id == user.id,
        )
    )
    vote = result.scalar_one_or_none()
    if vote:
        await db.delete(vote)
        item.vote_count = max(0, item.vote_count - 1)
        await db.flush()
        await db.refresh(item)

    return VoteOut(success=True, vote_count=item.vote_count)
