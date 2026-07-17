"""V2 Changelog read-only API — public release-notes content.

Per R9 (swarm audit REPORT.md §4): roadmap/changelog were deleted in a prior
pruning phase; a lightweight read-only changelog is cheap credibility.
Reuses the blog/roadmap read-only pattern (T1): DB-backed table,
GET-only, no auth on the public list, no write paths.

The exact parent ``/api/v2/changelog`` carries the public list; both
``/api/v2/changelog`` and ``/api/v2/changelog/`` are served to mirror the
SDK's two call forms (see ``roadmap.py``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.api.v2.base import ok, paginated
from app.database import get_db
from app.models.changelog_models import ChangelogEntry

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/changelog", tags=["v2-changelog"])


def _entry_to_out(entry: ChangelogEntry) -> dict:
    return {
        "id": str(entry.id),
        "version": entry.version,
        "title": entry.title,
        "summary": entry.summary,
        "body": entry.body,
        "category": entry.category,
        "is_featured": entry.is_featured,
        "released_at": entry.released_at.isoformat() if entry.released_at else None,
        "sort_order": entry.sort_order,
    }


@router.get("")
@router.get("/")
async def list_changelog(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List changelog entries, newest-first (public)."""
    total = await db.scalar(select(func.count()).select_from(ChangelogEntry))
    total = total or 0

    stmt = (
        select(ChangelogEntry)
        .order_by(
            ChangelogEntry.released_at.desc().nullslast(),
            ChangelogEntry.sort_order.desc(),
            ChangelogEntry.created_at.desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.scalars(stmt)).all()
    items = [_entry_to_out(e) for e in rows]
    page = (offset // limit) + 1 if limit else 1
    return paginated(items=items, total=total, page=page, per_page=limit)


@router.get("/{version}")
async def get_changelog_version(version: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Fetch a single changelog entry by its version label (public). 404 if absent."""
    entry = await db.scalar(select(ChangelogEntry).where(ChangelogEntry.version == version))
    if entry is None:
        raise HTTPException(status_code=404, detail=f"changelog version not found: {version}")
    return ok(_entry_to_out(entry))
