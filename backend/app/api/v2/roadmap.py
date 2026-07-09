"""V2 Roadmap read-only API.

Per `.sisyphus/plans/T1-blog-roadmap-routers-plan.md`:
- The public items list is live (backed by `RoadmapItem`).
- `/categories` is AUTH-REQUIRED (api-client.test.ts:80-81) and derived live
  via GROUP BY — there is no dedicated `roadmap_categories` table (plan §2.2).
- `/comments` (GET/POST) are auth-required and out of read-only T1 scope.

The exact parent `/api/v2/roadmap` carries the public list; both `/api/v2/roadmap`
and `/api/v2/roadmap/` are served to mirror the SDK's two call forms.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import get_current_user
from app.api.v2.base import ok
from app.database import get_db
from app.models.roadmap_models import RoadmapItem
from app.schemas.blog_roadmap_v2 import roadmap_item_to_out

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

router = APIRouter(prefix="/roadmap", tags=["v2-roadmap"])


@router.get("")
@router.get("/")
async def list_roadmap_items(
    status: str | None = Query(None),
    category: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List public roadmap items (public)."""
    stmt = select(RoadmapItem).where(RoadmapItem.is_public.is_(True))
    if status:
        stmt = stmt.where(RoadmapItem.status == status)
    if category:
        stmt = stmt.where(RoadmapItem.category == category)
    stmt = stmt.order_by(RoadmapItem.sort_order.asc())
    items = (await db.scalars(stmt)).all()
    return ok([roadmap_item_to_out(i) for i in items])


@router.get("/categories")
async def list_roadmap_categories(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Derived roadmap categories (auth-required).

    Aggregates `COUNT(*)` per non-null category over public items. Returns
    `{id, name, count}` matching the frontend `RoadmapCategoryOut` shape;
    `id` is the category slug itself (no dedicated table exists).
    """
    rows = (
        await db.execute(
            select(RoadmapItem.category, func.count().label("cnt"))
            .where(RoadmapItem.is_public.is_(True))
            .where(RoadmapItem.category.is_not(None))
            .group_by(RoadmapItem.category)
        )
    ).all()

    categories = [{"id": cat, "name": cat, "count": cnt} for cat, cnt in rows]
    return ok(categories)
