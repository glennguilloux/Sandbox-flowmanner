from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Query

from app.database import get_db
from app.schemas.agent import AgentCatalogDetail, AgentCatalogItem, DivisionInfo
from app.services.agent_service import (
    get_agent_template_by_slug,
    list_agent_templates,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/domain", tags=["domain-agents"])


@router.get("/agents")
async def list_catalog(
    division: str | None = Query(None, description="Filter by division"),
    search: str | None = Query(None, description="Search name/description"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * per_page
    templates, total = await list_agent_templates(db, division=division, search=search, offset=offset, limit=per_page)
    items = [AgentCatalogItem.from_template(t) for t in templates]
    pages = (total + per_page - 1) // per_page
    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


@router.get("/agents/{slug}", response_model=AgentCatalogDetail)
async def get_catalog_detail(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    template = await get_agent_template_by_slug(db, slug)
    if template is None:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent '{slug}' not found")
    return AgentCatalogDetail.from_template(template)


@router.get("/divisions", response_model=list[DivisionInfo])
async def list_divisions(
    db: AsyncSession = Depends(get_db),
):
    templates, _ = await list_agent_templates(db, limit=10000)
    counter: Counter[str] = Counter()
    for t in templates:
        if t.agent_type:
            counter[t.agent_type] += 1
    return [DivisionInfo(name=name, count=count) for name, count in sorted(counter.items())]


@router.get("/badges")
async def list_badges():
    return {"badges": []}
