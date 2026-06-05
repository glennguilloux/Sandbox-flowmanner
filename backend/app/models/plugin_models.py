"""Plugin models — installed plugins per workspace.

Each row represents a plugin installed in a workspace, tracking its
lifecycle state (installed → loaded → enabled → disabled → uninstalled).
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base, TimestampMixin


class PluginStatus:
    """Plugin lifecycle states."""

    INSTALLED = "installed"
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    UNINSTALLED = "uninstalled"
    ERROR = "error"

    ALL = {INSTALLED, LOADED, ENABLED, DISABLED, UNINSTALLED, ERROR}


class InstalledPlugin(Base, TimestampMixin):
    """A plugin installed in a workspace.

    Lifecycle: installed → loaded → enabled ⇄ disabled → uninstalled
    """

    __tablename__ = "installed_plugins"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Manifest stored as JSON text for re-validation and metadata queries
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False)

    # Plugin source: "marketplace", "upload", "git"
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="upload")
    # Marketplace listing ID if installed from marketplace
    listing_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )

    # Filesystem path where the plugin was unpacked
    install_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Lifecycle state
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PluginStatus.INSTALLED, index=True
    )

    # Runtime health tracking
    execution_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    last_executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Permissions declared by the plugin (JSON array)
    permissions_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Node types provided (JSON array of {id, label, category})
    node_types_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Plugin-level config (JSON object)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Phase 9.6: Security review and approval
    review_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )  # pending, approved, rejected
    scan_risk_score: Mapped[int] = mapped_column(Integer, default=0)
    scan_result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Phase 9.6: Runtime monitoring
    p99_latency_ms: Mapped[float] = mapped_column(default=0.0, server_default="0")
    crash_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_health_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def is_enabled(self) -> bool:
        return self.status == PluginStatus.ENABLED

    @property
    def is_loaded(self) -> bool:
        return self.status in {PluginStatus.LOADED, PluginStatus.ENABLED}
