"""Canonical Tool models — Postgres-native tool catalog (Phase 1).

These tables are the source of truth for all tools. In-memory ToolRegistry
is a hydrated projection of this table.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class Tool(Base, TimestampMixin):
    """Canonical tool definition stored in Postgres.

    ``handler_ref`` is a Python dotted path (e.g.
    ``app.tools.browser_ping.BrowserPingTool``) that the hydration
    pipeline resolves at startup to populate the in-memory ToolRegistry.
    """

    __tablename__ = "tools_catalog"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: __import__("uuid").uuid4().__str__(),
    )
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    tool_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="builtin",
    )
    handler_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    input_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    auth_policy: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    visibility: Mapped[str] = mapped_column(String(50), default="public")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(50), default="db")
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    tier: Mapped[int] = mapped_column(Integer, default=1)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30)
    requires_auth: Mapped[bool] = mapped_column(Boolean, default=True)
    workspace_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True,
        comment="NULL = builtin/global tool, non-NULL = workspace-specific custom tool",
    )


class ToolVersion(Base, TimestampMixin):
    """Immutable version snapshot of a tool definition."""

    __tablename__ = "tool_versions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: __import__("uuid").uuid4().__str__(),
    )
    tool_id: Mapped[str] = mapped_column(
        String(36), nullable=False, index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
