#!/usr/bin/env python3
"""
Workflow Config Database Models

Database models for storing workflow configurations and session states.
"""

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class WorkflowConfig(Base):
    """
    Workflow configuration model.

    Stores workflow configurations with metadata for reuse.
    """

    __tablename__ = "workflow_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(String(255), unique=True, nullable=False, index=True)
    workflow_id = Column(String(255), nullable=False, index=True)
    name = Column(String(255))
    description = Column(Text)
    config_data = Column(JSON, nullable=False)
    user_id = Column(Integer)
    is_active = Column(String(10), default="true")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("idx_workflow_configs_workflow_id", "workflow_id"),
        Index("idx_workflow_configs_user_id", "user_id"),
    )

    def to_dict(self):
        return {
            "config_id": self.config_id,
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "config_data": self.config_data,
            "user_id": self.user_id,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SessionState(Base):
    """
    Agent session state model.

    Stores LangGraph agent session states for persistence.
    """

    __tablename__ = "session_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    state_data = Column(JSON, nullable=False)
    user_id = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime)

    # Indexes
    __table_args__ = (
        Index("idx_session_states_user_id", "user_id"),
        Index("idx_session_states_expires_at", "expires_at"),
    )

    def to_dict(self):
        return {
            "session_id": self.session_id,
            "state_data": self.state_data,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
