"""Roadmap API — items, categories, votes."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import get_current_user
from app.database import get_db
from app.models.roadmap_models import RoadmapItem

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(prefix="/roadmap", tags=["roadmap"])


# ── Schemas ──────────────────────────────────────────────────────────────

class RoadmapItemOut(BaseModel):
    id: str
    title: str
    description: str
    status: str
    category: str
    sort_order: int
    is_public: bool
    vote_count: int
    created_by: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class RoadmapCategoryOut(BaseModel):
    id: str
    name: str
    count: int


class VoteIn(BaseModel):
    item_id: str
    vote_type: str = "up"


class VoteOut(BaseModel):
    success: bool
    vote_count: int


# ── GET /api/roadmap ─────────────────────────────────────────────────────

@router.get("", response_model=list[RoadmapItemOut])
@router.get("/", response_model=list[RoadmapItemOut])
async def list_roadmap_items(
    status: str | None = Query(None),
    category: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List public roadmap items, optionally filtered."""
    query = select(RoadmapItem).where(RoadmapItem.is_public == True)

    if status and status != "all":
        query = query.where(RoadmapItem.status == status)
    if category and category != "all":
        query = query.where(RoadmapItem.category == category)

    query = query.order_by(RoadmapItem.sort_order, RoadmapItem.created_at.desc())
    result = await db.execute(query)
    items = result.scalars().all()

    return [
        RoadmapItemOut(
            id=str(item.id),
            title=item.title,
            description=item.description,
            status=item.status,
            category=item.category,
            sort_order=item.sort_order,
            is_public=item.is_public,
            vote_count=item.vote_count,
            created_by=item.created_by,
            created_at=item.created_at.isoformat() if item.created_at else "",
            updated_at=item.updated_at.isoformat() if item.updated_at else "",
        )
        for item in items
    ]


# ── GET /api/roadmap/categories ──────────────────────────────────────────

@router.get("/categories", response_model=list[RoadmapCategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    """List roadmap categories with item counts."""
    result = await db.execute(
        select(
            RoadmapItem.category,
            func.count(RoadmapItem.id).label("count"),
        )
        .where(RoadmapItem.is_public == True)
        .group_by(RoadmapItem.category)
    )
    rows = result.all()
    return [
        RoadmapCategoryOut(id=row.category, name=row.category, count=row.count)
        for row in rows
    ]


# ── GET /api/roadmap/comments ────────────────────────────────────────────

@router.get("/comments")
async def list_comments(
    item_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """List comments for a roadmap item."""
    from app.models.roadmap_models import RoadmapComment

    result = await db.execute(
        select(RoadmapComment)
        .where(RoadmapComment.roadmap_item_id == uuid.UUID(item_id))
        .order_by(RoadmapComment.created_at.asc())
    )
    comments = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "roadmap_item_id": str(c.roadmap_item_id),
            "user_id": c.user_id,
            "user_name": c.user_name,
            "content": c.content,
            "parent_id": str(c.parent_id) if c.parent_id else None,
            "created_at": c.created_at.isoformat() if c.created_at else "",
            "updated_at": c.updated_at.isoformat() if c.updated_at else "",
        }
        for c in comments
    ]


# ── POST /api/roadmap/comments ──────────────────────────────────────────

@router.post("/comments")
async def add_comment(
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a comment to a roadmap item."""
    from app.models.roadmap_models import RoadmapComment

    item_id = body.get("item_id")
    content = body.get("content", "").strip()
    parent_id = body.get("parent_id")

    if not item_id or not content:
        raise HTTPException(status_code=400, detail="item_id and content required")

    comment = RoadmapComment(
        roadmap_item_id=uuid.UUID(item_id),
        user_id=user.id,
        user_name=user.username or user.email or "",
        content=content,
        parent_id=uuid.UUID(parent_id) if parent_id else None,
    )
    db.add(comment)
    await db.flush()
    await db.refresh(comment)

    return {
        "id": str(comment.id),
        "roadmap_item_id": str(comment.roadmap_item_id),
        "user_id": comment.user_id,
        "user_name": comment.user_name,
        "content": comment.content,
        "parent_id": str(comment.parent_id) if comment.parent_id else None,
        "created_at": comment.created_at.isoformat() if comment.created_at else "",
        "updated_at": comment.updated_at.isoformat() if comment.updated_at else "",
    }
