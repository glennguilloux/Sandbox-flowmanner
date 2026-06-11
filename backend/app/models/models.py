"""Core models: LogEntry, Marketplace, and AgentReview models.

Orchestration and community routes use raw SQL queries against
the real orchestration_agents, orchestration_teams, orchestration_tasks
and community_templates tables.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class LogEntry(Base, TimestampMixin):
    __tablename__ = "log_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    level: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON


class ComposedCapabilityModel(Base, TimestampMixin):
    __tablename__ = "composed_capabilities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    capability_ids: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    composition_strategy: Mapped[str | None] = mapped_column(String(100), nullable=True)
    config: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON


class MarketplaceListingModel(Base, TimestampMixin):
    __tablename__ = "marketplace_listings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)  # v2: workspace scoping
    category_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    listing_type: Mapped[str] = mapped_column(String(50), nullable=False)  # agent, tool, template, workflow
    artifact_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # tool, capability, agent_template, workflow
    artifact_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # FK to catalog table row
    artifact_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # FK to version snapshot row
    price: Mapped[float] = mapped_column(Float, default=0.0)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)  # v2: draft/published/deprecated
    version: Mapped[str | None] = mapped_column(String(20), default="1.0.0", nullable=True)  # v2: semver
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # v2
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)  # v2: explicit count
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    integrations: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of integration slugs
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of tags


class MarketplaceCategoryModel(Base, TimestampMixin):
    __tablename__ = "marketplace_categories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    listing_count: Mapped[int] = mapped_column(Integer, default=0)


class MarketplaceReviewModel(Base, TimestampMixin):
    __tablename__ = "marketplace_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    listing_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)  # v2
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)


class UserInstallationModel(Base, TimestampMixin):
    __tablename__ = "user_installations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    listing_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    config: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON


class AgentReview(Base, TimestampMixin):
    __tablename__ = "agent_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False)
