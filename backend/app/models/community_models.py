"""Community models — CommunityTemplate and threaded comments.

CommunityTemplate resolves the FK target for CommunityComment.template_id
that Alembic's `alembic check` could not find (NoReferencedTableError).
The table itself is created by raw SQL in community.py's _ensure_table();
this class declares the ORM model so SQLAlchemy metadata resolves the FK.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class CommunityTemplate(Base, TimestampMixin):
    """ORM model for the community_templates table.

    Matches the live DB schema created by _ensure_table() in community.py.
    Columns: id, title, description, author_id, author_name, category,
    tags, content, rating, rating_count, fork_count, use_count,
    is_featured, created_at, updated_at (15 total; created_at/updated_at
    from TimestampMixin).
    """

    __tablename__ = "community_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[str] = mapped_column(String(36), nullable=False)
    author_name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[float] = mapped_column(Float, nullable=True, server_default="0.0")
    rating_count: Mapped[int] = mapped_column(Integer, nullable=True, server_default="0")
    fork_count: Mapped[int] = mapped_column(Integer, nullable=True, server_default="0")
    use_count: Mapped[int] = mapped_column(Integer, nullable=True, server_default="0")
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=True, server_default="false")


class CommunityComment(Base, TimestampMixin):
    """A comment on a community template, supporting threaded replies.

    Cascade delete: deleting a template deletes all its comments.
    """

    __tablename__ = "community_comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    template_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("community_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    author_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    parent_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("community_comments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")
