from __future__ import annotations

import json

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base, TimestampMixin


class UserAPIKey(Base, TimestampMixin):
    """Stores user-provided API keys (BYOK) encrypted at rest."""

    __tablename__ = "user_api_keys"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)  # Phase 8.2: workspace scoping
    provider: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., "openai", "anthropic", "openrouter"
    encrypted_key: Mapped[str] = mapped_column(String(500), nullable=False)  # AES-256 encrypted
    key_label: Mapped[str | None] = mapped_column(String(100), nullable=True)  # User-friendly label
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Custom API base URL
    models: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array of supported model IDs

    # Relationship
    user = relationship("User", back_populates="api_keys")

    __table_args__ = (
        Index("ix_user_api_keys_workspace_user", "workspace_id", "user_id"),
    )

    def get_api_key(self) -> str:
        """Decrypt and return the API key."""
        from app.utils.encryption import decrypt_api_key
        return decrypt_api_key(self.encrypted_key)

    def get_models_list(self) -> list[str]:
        """Return models as a Python list."""
        if not self.models:
            return []
        try:
            return json.loads(self.models)
        except (json.JSONDecodeError, TypeError):
            return []
