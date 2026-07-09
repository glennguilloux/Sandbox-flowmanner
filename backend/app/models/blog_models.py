"""Blog + case-study models (T1 — DB-backed blog).

New tables per Glenn's decision (2026-07-09): blog content is a new DB
table rather than Markdown/MDX or a CMS. ``BlogPost`` carries the shared
fields for both blog posts and case studies; the ``category`` column
(``"blog"`` | ``"case-study"``) discriminates, and the case-study-only
fields are nullable on the same row. ``BlogTag`` + ``blog_post_tags`` give
the relational ``tags`` the frontend ``BlogPost`` contract expects.

No write paths exist yet — these are surfaced read-only by
``app/api/v2/blog.py``. Admin/editor endpoints are a separate follow-up.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from datetime import datetime

# Association table: BlogPost (N) <--> BlogTag (N)
blog_post_tags = Table(
    "blog_post_tags",
    Base.metadata,
    Column(
        "post_id",
        UUID(as_uuid=True),
        ForeignKey("blog_posts.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "tag_id",
        UUID(as_uuid=True),
        ForeignKey("blog_tags.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class BlogPost(Base):
    __tablename__ = "blog_posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    author_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    featured_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="blog")

    # Case-study extension fields (nullable; only populated when category == "case-study")
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    challenge: Mapped[str | None] = mapped_column(Text, nullable=True)
    solution: Mapped[str | None] = mapped_column(Text, nullable=True)
    results: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tags: Mapped[list[BlogTag]] = relationship(secondary=blog_post_tags, back_populates="posts", lazy="selectin")


class BlogTag(Base):
    __tablename__ = "blog_tags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    posts: Mapped[list[BlogPost]] = relationship(secondary=blog_post_tags, back_populates="tags", lazy="selectin")
