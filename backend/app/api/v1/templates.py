"""Templates API — /api/templates.

Queries MissionTemplate from the database with optional category/style filtering.
Returns enriched data: name, description, category, rating, downloads, author, icon, tags.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.mission_advanced_models import MissionTemplate
from app.models.user import User

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("")
async def list_templates(
    category: str | None = Query(None, description="Filter by category"),
    q: str | None = Query(None, description="Search query for name/description"),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(MissionTemplate, User.email, User.full_name, User.username)
        .outerjoin(User, MissionTemplate.user_id == User.id)
        .where((MissionTemplate.is_public == True) | (MissionTemplate.is_builtin == True))
    )
    if category:
        query = query.where(MissionTemplate.category == category)
    if q:
        like = f"%{q}%"
        query = query.where((MissionTemplate.name.ilike(like)) | (MissionTemplate.description.ilike(like)))
    query = query.order_by(MissionTemplate.usage_count.desc()).limit(50)
    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "id": str(t.id),
            "name": t.name,
            "description": t.description or "",
            "category": t.category,
            "icon": t.icon,
            "tags": t.tags if isinstance(t.tags, list) else [],
            "rating": float(t.rating) if t.rating is not None else None,
            "downloads": t.usage_count or 0,
            "author": full_name or username or email or "Flowmanner",
            "is_public": t.is_public,
            "is_builtin": t.is_builtin,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t, email, full_name, username in rows
    ]
