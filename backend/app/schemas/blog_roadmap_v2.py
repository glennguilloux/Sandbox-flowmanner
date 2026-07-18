"""v2 response schemas for the blog + roadmap read-only routers (T1).

Shapes mirror the frontend contracts described in
``.sisyphus/plans/T1-blog-roadmap-routers-plan.md``:

- ``src/lib/blog-api.ts``  — ``BlogTag {id,name,slug}``,
  ``BlogPost {id,slug,title,excerpt,content,author_name,published_at,
  view_count,is_featured,featured_image_url?,category,tags[]}``,
  ``CaseStudy extends BlogPost`` (+ client_name/industry/challenge/
  solution/results/metrics).
- ``RoadmapService`` SDK ``RoadmapItemOut`` =
  ``{id,title,description,status,category,sort_order,is_public,
  vote_count,created_by,created_at,updated_at}`` and
  ``RoadmapCategoryOut`` = ``{id,name,count}``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from datetime import datetime

# ── Blog ───────────────────────────────────────────────────────────────────


class BlogTagOut(BaseModel):
    """A relational blog tag (``{id,name,slug}``)."""

    id: str
    name: str
    slug: str

    model_config = ConfigDict(from_attributes=True)


class BlogPostOut(BaseModel):
    """A blog post or case study (``category`` discriminates)."""

    id: str
    slug: str
    title: str
    excerpt: str
    content: str
    author_name: str
    published_at: str | None = None
    view_count: int = 0
    is_featured: bool = False
    featured_image_url: str | None = None
    category: str
    tags: list[BlogTagOut] = Field(default_factory=list)

    # Case-study extension fields (present only when category == "case-study")
    client_name: str | None = None
    industry: str | None = None
    challenge: str | None = None
    solution: str | None = None
    results: str | None = None
    metrics: str | None = None

    model_config = ConfigDict(from_attributes=True)


class BlogListResponse(BaseModel):
    """Paginated blog list payload (v2 paginated envelope ``data``)."""

    items: list[BlogPostOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 20
    pages: int = 0


# ── Roadmap ─────────────────────────────────────────────────────────────────


class RoadmapItemOut(BaseModel):
    """Roadmap item — matches ``RoadmapItem`` ORM field-for-field."""

    id: str
    title: str
    description: str
    status: str
    category: str
    sort_order: int
    is_public: bool
    vote_count: int
    created_by: str
    created_at: str | None = None
    updated_at: str | None = None

    model_config = ConfigDict(from_attributes=True)


class RoadmapCategoryOut(BaseModel):
    """Derived roadmap category (no dedicated table — aggregated live)."""

    id: str
    name: str
    count: int


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def blog_post_to_out(post: Any) -> dict[str, Any]:
    """Map a ``BlogPost`` ORM row to the v2 ``BlogPostOut`` dict."""
    tags = [BlogTagOut(id=str(t.id), name=t.name, slug=t.slug) for t in (post.tags or [])]
    return BlogPostOut(
        id=str(post.id),
        slug=post.slug,
        title=post.title,
        excerpt=post.excerpt,
        content=post.content,
        author_name=post.author_name,
        published_at=_iso(post.published_at),
        view_count=post.view_count,
        is_featured=post.is_featured,
        featured_image_url=post.featured_image_url,
        category=post.category,
        tags=tags,
        client_name=post.client_name,
        industry=post.industry,
        challenge=post.challenge,
        solution=post.solution,
        results=post.results,
        metrics=post.metrics,
    ).model_dump()


def roadmap_item_to_out(item: Any) -> dict[str, Any]:
    """Map a ``RoadmapItem`` ORM row to the v2 ``RoadmapItemOut`` dict."""
    return RoadmapItemOut(
        id=str(item.id),
        title=item.title,
        description=item.description,
        status=item.status,
        category=item.category,
        sort_order=item.sort_order,
        is_public=item.is_public,
        vote_count=item.vote_count,
        created_by=item.created_by,
        created_at=_iso(item.created_at),
        updated_at=_iso(item.updated_at),
    ).model_dump()
