"""Mission advanced models: templates, node groups, versions."""

from uuid import uuid4

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class MissionTemplate(Base, TimestampMixin):
    __tablename__ = "mission_templates"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid4())
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    mission_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    default_plan: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    default_tasks: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    default_constraints: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    tags: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_behaviors: Mapped[list | None] = mapped_column(JSONB, nullable=False, default=list)


class NodeGroup(Base, TimestampMixin):
    __tablename__ = "node_groups"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid4())
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    group_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    owner_id: Mapped[int | None] = mapped_column("user_id", Integer, ForeignKey("users.id"), nullable=True)


class MissionVersion(Base, TimestampMixin):
    """Immutable version snapshot of a Mission definition.

    Each time a mission's plan or configuration changes, a new version
    row is created.  Enables rollback, diffing, and audit trails.

    Note: The original migration (20260518) created individual columns
    instead of a single JSONB snapshot.  The columns are preserved here
    for backward compatibility.  The ``snapshot`` property synthesizes
    a dict from the individual columns for API compatibility.
    """

    __tablename__ = "mission_versions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, default=lambda: uuid4())
    mission_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("missions.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    mission_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    plan: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    tasks_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    constraints: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    @property
    def snapshot(self) -> dict | None:
        """Synthesize a snapshot dict from the individual columns."""
        return {
            "title": self.title,
            "description": self.description,
            "mission_type": self.mission_type,
            "priority": self.priority,
            "plan": self.plan,
            "tasks_snapshot": self.tasks_snapshot,
            "constraints": self.constraints,
        }
