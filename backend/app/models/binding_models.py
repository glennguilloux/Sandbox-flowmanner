"""Normalized binding tables — Phase 2.3.

Links agents (via agent_templates) to the tools and capabilities they
are allowed to use.  Also models capability-to-capability dependency
graphs.

These tables replace the ad-hoc JSON arrays previously stored inside
``agent_templates.model_config`` and ``agent_capabilities.tools``.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class AgentToolBinding(Base, TimestampMixin):
    """Many-to-many: which tools each agent template can call.

    ``agent_id`` references ``agent_templates.template_id``.
    ``tool_id`` references ``tools_catalog.id``.
    """

    __tablename__ = "agent_tool_bindings"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: __import__("uuid").uuid4().__str__(),
    )
    agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_templates.template_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("tools_catalog.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    config_override: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)


class AgentCapabilityBinding(Base, TimestampMixin):
    """Many-to-many: which capabilities each agent template has.

    ``agent_id`` references ``agent_templates.template_id``.
    ``capability_id`` references ``capabilities_catalog.id``.
    """

    __tablename__ = "agent_capability_bindings"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: __import__("uuid").uuid4().__str__(),
    )
    agent_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("agent_templates.template_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    capability_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("capabilities_catalog.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    config_override: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)


class CapabilityDependency(Base, TimestampMixin):
    """Directed graph of capability-to-capability dependencies.

    ``capability_id`` depends on ``depends_on_id`` — i.e. to execute
    capability A, capability B must also be available.

    ``dependency_type`` can be ``required``, ``optional``, or ``preferred``.
    """

    __tablename__ = "capability_dependencies"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: __import__("uuid").uuid4().__str__(),
    )
    capability_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("capabilities_catalog.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    depends_on_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("capabilities_catalog.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dependency_type: Mapped[str] = mapped_column(
        String(20), default="required", nullable=False,
    )
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
