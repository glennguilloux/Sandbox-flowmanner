"""V2 Search endpoint — unified search with standardized envelope."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.api.v2.base import ok
from app.database import get_db
from app.services.search_service import get_search_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(prefix="/search", tags=["v2-search"])


@router.get("")
async def search(
    q: str = Query(..., min_length=2, max_length=200),
    type: str = Query("", description="Comma-separated entity types: missions,agents,knowledge"),
    limit: int = Query(20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = get_search_service()
    entity_types = [t.strip() for t in type.split(",") if t.strip()] if type else None

    results = await service.search(
        db=db,
        query=q,
        entity_types=entity_types,
        user_id=user.id,
        limit=limit,
    )

    return ok(results)


@router.get("/suggestions")
async def search_suggestions(
    q: str = Query(..., min_length=1, max_length=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = get_search_service()
    suggestions = await service.get_suggestions(db=db, query=q, limit=5)
    return ok({"suggestions": suggestions})
