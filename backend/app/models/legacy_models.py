"""Legacy models — tables with existing production data that must be preserved.

These tables were created by older migrations and contain data (audit trail).
Model classes are added here so SQLAlchemy metadata recognizes them and
Alembic stops trying to drop them.

audit_logs: 1,765 rows (audit trail)

Note: ``refresh_tokens`` (801 rows) is NOT here — its model class already
lives in ``app.services.auth_service`` and is registered via __init__.py.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class AuditLog(Base):
    """Audit log entries — tracks user actions across the platform."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    action_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default="now()",
    )
