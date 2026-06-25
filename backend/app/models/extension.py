"""Extension / Plugin model (Task 3.5)."""

import uuid

from sqlalchemy import JSON, Column, DateTime, String, Text
from sqlalchemy.sql import func

from app.models import Base


class Extension(Base):
    __tablename__ = "extensions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    version = Column(String(50), nullable=False, default="1.0.0")
    description = Column(Text, nullable=True)
    author = Column(String(255), nullable=True)
    manifest = Column(JSON, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="disabled")  # enabled, disabled, error
    workspace_id = Column(String, nullable=True)
    config = Column(JSON, nullable=True, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
