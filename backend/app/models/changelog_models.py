"""Changelog models — lightweight, read-only release-notes entries.

A small ``changelog_entries`` table backs the public, read-only
``/api/v2/changelog`` surface. Content is seeded by a baked script
(``scripts/seed_changelog.py``) and via future admin write paths; the API
is strictly read-only (cheap credibility, mirrors the blog/roadmap T1
read-only routers).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class ChangelogEntry(Base):
    """A single changelog/release-notes entry.

    ``version`` is a human label (e.g. ``"R9"``, ``"2026.07"``) used as a
    stable lookup key; ``released_at`` orders entries (desc = newest first).
    """

    __tablename__ = "changelog_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="release")
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
