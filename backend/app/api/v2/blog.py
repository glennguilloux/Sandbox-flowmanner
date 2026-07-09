"""V2 Blog read-only API — public blog + case-study content.

Per `.sisyphus/plans/T1-blog-roadmap-routers-plan.md`:
- Data source is a new DB table (Glenn's decision, 2026-07-09) — `BlogPost` /
  `BlogTag` / `blog_post_tags` in `app.models.blog_models`.
- Blog reads are PUBLIC (plan §2.3 default A — marketing content; the frontend
  `blog-api.ts` anonymous ISR fetch confirms that was the original intent).
  The exact parent `/api/v2/blog` has no operation; reads live on the
  `/posts` and `/posts/{slug}` children.
- Read-only GET only. Admin/editor write paths are a separate follow-up.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select

from app.api.v2.base import ok, paginated
from app.database import get_db
from app.models.blog_models import BlogPost
from app.schemas.blog_roadmap_v2 import blog_post_to_out

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/blog", tags=["v2-blog"])


@router.get("/posts")
async def list_blog_posts(
    category: str | None = Query(None, pattern="^(blog|case-study)$"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List published blog posts / case studies (public).

    Returns the v2 paginated envelope. Posts are ordered by
    ``published_at`` desc, falling back to ``created_at`` desc.
    """
    filters = [BlogPost.published_at.is_not(None)]
    if category:
        filters.append(BlogPost.category == category)

    total = await db.scalar(select(func.count()).select_from(BlogPost).where(*filters))
    total = total or 0

    stmt = (
        select(BlogPost)
        .where(*filters)
        .order_by(BlogPost.published_at.desc().nullslast(), BlogPost.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.scalars(stmt)).all()

    items = [blog_post_to_out(p) for p in rows]
    page = (offset // limit) + 1 if limit else 1
    return paginated(items=items, total=total, page=page, per_page=limit)


@router.get("/posts/{slug}")
async def get_blog_post(slug: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Fetch a single published post by slug (public). 404 if absent."""
    post = await db.scalar(select(BlogPost).where(BlogPost.slug == slug))
    if post is None or post.published_at is None:
        raise HTTPException(status_code=404, detail=f"blog post not found: {slug}")
    return ok(blog_post_to_out(post))
