#!/usr/bin/env python3
"""
Workflow Config Manager

Manages workflow configurations with caching layer (Redis).
Provides CRUD operations for workflow configs and session states.
"""

import json
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from .models import SessionState, WorkflowConfig

logger = logging.getLogger(__name__)


class WorkflowConfigManager:
    """
    Manager for workflow configurations and session states.

    Responsibilities:
    - CRUD operations for workflow configs
    - Session state persistence
    - Redis caching for performance
    - Configuration validation
    """

    def __init__(self, redis_client=None, cache_ttl: int = 3600, session_ttl: int = 86400):
        """
        Initialize config manager.

        Args:
            redis_client: Optional Redis client for caching
            cache_ttl: Cache time-to-live in seconds
            session_ttl: Session state TTL in seconds
        """
        self.redis_client = redis_client
        self.cache_ttl = cache_ttl
        self.session_ttl = session_ttl
        self.logger = logging.getLogger(__name__)

    # Workflow Config Operations

    def save_config(
        self,
        workflow_id: str,
        config_data: dict[str, Any],
        name: str | None = None,
        description: str | None = None,
        user_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Save a workflow configuration.

        Args:
            workflow_id: Workflow identifier
            config_data: Configuration data (JSON)
            name: Optional name for the config
            description: Optional description
            user_id: Optional user ID

        Returns:
            Result dictionary
        """
        try:
            from app.database import SessionLocal

            # Generate config ID
            config_id = f"config_{uuid.uuid4().hex[:16]}"

            # Validate config data
            if not isinstance(config_data, dict):
                return {"success": False, "error": "config_data must be a dictionary"}

            # Create config record
            db = SessionLocal()
            try:
                config = WorkflowConfig(
                    config_id=config_id,
                    workflow_id=workflow_id,
                    name=name or f"Config for {workflow_id}",
                    description=description,
                    config_data=config_data,
                    user_id=user_id,
                    is_active="true",
                )

                db.add(config)
                db.commit()

                # Cache the config
                self._cache_config(config_id, config_data)

                self.logger.info(f"Saved config {config_id} for workflow {workflow_id}")
                return {
                    "success": True,
                    "config_id": config_id,
                    "message": "Configuration saved successfully",
                }

            except Exception as e:
                db.rollback()
                self.logger.error(f"Database error saving config: {e}")
                return {
                    "success": False,
                    "error": f"Failed to save configuration: {e!s}",
                }
            finally:
                db.close()

        except Exception as e:
            self.logger.error(f"Error saving config: {e}")
            return {"success": False, "error": str(e)}

    def get_config(self, config_id: str) -> dict[str, Any]:
        """
        Get a workflow configuration by ID.

        Args:
            config_id: Configuration identifier

        Returns:
            Result dictionary with config data
        """
        try:
            # Try cache first
            cached = self._get_cached_config(config_id)
            if cached:
                self.logger.debug(f"Cache hit for config {config_id}")
                return {
                    "success": True,
                    "config_id": config_id,
                    "config_data": cached,
                    "from_cache": True,
                }

            # Load from database
            from app.database import SessionLocal

            db = SessionLocal()
            try:
                config = (
                    db.query(WorkflowConfig)
                    .filter(
                        WorkflowConfig.config_id == config_id,
                        WorkflowConfig.is_active == "true",
                    )
                    .first()
                )

                if not config:
                    return {"success": False, "error": "Configuration not found"}

                # Update cache
                self._cache_config(config_id, config.config_data)

                return {
                    "success": True,
                    "config_id": config_id,
                    "config_data": config.config_data,
                    "metadata": {
                        "name": config.name,
                        "description": config.description,
                        "workflow_id": config.workflow_id,
                        "user_id": config.user_id,
                        "created_at": (config.created_at.isoformat() if config.created_at else None),
                    },
                }

            finally:
                db.close()

        except Exception as e:
            self.logger.error(f"Error getting config {config_id}: {e}")
            return {"success": False, "error": str(e)}

    def get_workflow_config(self, workflow_id: str) -> dict[str, Any]:
        """
        Get latest configuration for a workflow.

        Args:
            workflow_id: Workflow identifier

        Returns:
            Result dictionary with config data
        """
        try:
            from app.database import SessionLocal

            db = SessionLocal()
            try:
                config = (
                    db.query(WorkflowConfig)
                    .filter(
                        WorkflowConfig.workflow_id == workflow_id,
                        WorkflowConfig.is_active == "true",
                    )
                    .order_by(WorkflowConfig.updated_at.desc())
                    .first()
                )

                if not config:
                    return {
                        "success": False,
                        "error": f"No configuration found for workflow {workflow_id}",
                    }

                return {
                    "success": True,
                    "config_id": config.config_id,
                    "workflow_id": workflow_id,
                    "config_data": config.config_data,
                    "metadata": {
                        "name": config.name,
                        "description": config.description,
                        "user_id": config.user_id,
                        "updated_at": (config.updated_at.isoformat() if config.updated_at else None),
                    },
                }

            finally:
                db.close()

        except Exception as e:
            self.logger.error(f"Error getting workflow config for {workflow_id}: {e}")
            return {"success": False, "error": str(e)}

    def list_configs(
        self,
        workflow_id: str | None = None,
        user_id: int | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        List workflow configurations.

        Args:
            workflow_id: Optional workflow filter
            user_id: Optional user filter
            limit: Maximum number of results

        Returns:
            Result dictionary with list of configs
        """
        try:
            from app.database import SessionLocal

            db = SessionLocal()
            try:
                query = db.query(WorkflowConfig).filter(WorkflowConfig.is_active == "true")

                if workflow_id:
                    query = query.filter(WorkflowConfig.workflow_id == workflow_id)

                if user_id:
                    query = query.filter(WorkflowConfig.user_id == user_id)

                configs = query.order_by(WorkflowConfig.updated_at.desc()).limit(limit).all()

                return {
                    "success": True,
                    "count": len(configs),
                    "configs": [config.to_dict() for config in configs],
                }

            finally:
                db.close()

        except Exception as e:
            self.logger.error(f"Error listing configs: {e}")
            return {"success": False, "error": str(e)}

    def update_config(
        self,
        config_id: str,
        config_data: dict[str, Any] | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """
        Update a workflow configuration.

        Args:
            config_id: Configuration identifier
            config_data: New configuration data
            name: New name
            description: New description

        Returns:
            Result dictionary
        """
        try:
            from app.database import SessionLocal

            db = SessionLocal()
            try:
                config = (
                    db.query(WorkflowConfig)
                    .filter(
                        WorkflowConfig.config_id == config_id,
                        WorkflowConfig.is_active == "true",
                    )
                    .first()
                )

                if not config:
                    return {"success": False, "error": "Configuration not found"}

                # Update fields
                if config_data is not None:
                    config.config_data = config_data
                if name is not None:
                    config.name = name
                if description is not None:
                    config.description = description

                config.updated_at = datetime.now(UTC)
                db.commit()

                # Invalidate cache
                self._invalidate_config_cache(config_id)

                self.logger.info(f"Updated config {config_id}")
                return {
                    "success": True,
                    "message": "Configuration updated successfully",
                }

            except Exception as e:
                db.rollback()
                raise
            finally:
                db.close()

        except Exception as e:
            self.logger.error(f"Error updating config {config_id}: {e}")
            return {"success": False, "error": str(e)}

    def delete_config(self, config_id: str) -> dict[str, Any]:
        """
        Delete a workflow configuration (soft delete).

        Args:
            config_id: Configuration identifier

        Returns:
            Result dictionary
        """
        try:
            from app.database import SessionLocal

            db = SessionLocal()
            try:
                config = db.query(WorkflowConfig).filter(WorkflowConfig.config_id == config_id).first()

                if not config:
                    return {"success": False, "error": "Configuration not found"}

                # Soft delete
                config.is_active = "false"
                config.updated_at = datetime.now(UTC)
                db.commit()

                # Invalidate cache
                self._invalidate_config_cache(config_id)

                self.logger.info(f"Deleted config {config_id}")
                return {
                    "success": True,
                    "message": "Configuration deleted successfully",
                }

            except Exception as e:
                db.rollback()
                raise
            finally:
                db.close()

        except Exception as e:
            self.logger.error(f"Error deleting config {config_id}: {e}")
            return {"success": False, "error": str(e)}

    # Session State Operations

    def save_session_state(
        self, session_id: str, state_data: dict[str, Any], user_id: int | None = None
    ) -> dict[str, Any]:
        """
        Save agent session state.

        Args:
            session_id: Session identifier
            state_data: State data (JSON)
            user_id: Optional user ID

        Returns:
            Result dictionary
        """
        try:
            from app.database import SessionLocal

            # Calculate expiration
            expires_at = datetime.now(UTC) + timedelta(seconds=self.session_ttl)

            db = SessionLocal()
            try:
                # Check if exists
                session = db.query(SessionState).filter(SessionState.session_id == session_id).first()

                if session:
                    # Update
                    session.state_data = state_data
                    session.updated_at = datetime.now(UTC)
                    session.expires_at = expires_at
                else:
                    # Create
                    session = SessionState(
                        session_id=session_id,
                        state_data=state_data,
                        user_id=user_id,
                        expires_at=expires_at,
                    )
                    db.add(session)

                db.commit()

                self.logger.debug(f"Saved session state {session_id}")
                return {"success": True, "message": "Session state saved"}

            except Exception as e:
                db.rollback()
                raise
            finally:
                db.close()

        except Exception as e:
            self.logger.error(f"Error saving session state {session_id}: {e}")
            return {"success": False, "error": str(e)}

    def get_session_state(self, session_id: str) -> dict[str, Any] | None:
        """
        Get agent session state.

        Args:
            session_id: Session identifier

        Returns:
            State data or None
        """
        try:
            from app.database import SessionLocal

            db = SessionLocal()
            try:
                session = (
                    db.query(SessionState)
                    .filter(
                        SessionState.session_id == session_id,
                        SessionState.expires_at > datetime.now(UTC),
                    )
                    .first()
                )

                if not session:
                    return None

                return session.state_data

            finally:
                db.close()

        except Exception as e:
            self.logger.error(f"Error getting session state {session_id}: {e}")
            return None

    def delete_session_state(self, session_id: str) -> bool:
        """
        Delete agent session state.

        Args:
            session_id: Session identifier

        Returns:
            True if deleted, False otherwise
        """
        try:
            from app.database import SessionLocal

            db = SessionLocal()
            try:
                deleted = db.query(SessionState).filter(SessionState.session_id == session_id).delete()
                db.commit()

                self.logger.debug(f"Deleted session state {session_id}")
                return deleted > 0

            except Exception as e:
                db.rollback()
                raise
            finally:
                db.close()

        except Exception as e:
            self.logger.error(f"Error deleting session state {session_id}: {e}")
            return False

    # Cache Helpers

    def _cache_config(self, config_id: str, config_data: dict[str, Any]):
        """Cache configuration in Redis"""
        if not self.redis_client:
            return

        try:
            key = f"workflow_config:{config_id}"
            self.redis_client.setex(key, self.cache_ttl, json.dumps(config_data))
        except Exception as e:
            self.logger.warning(f"Failed to cache config {config_id}: {e}")

    def _get_cached_config(self, config_id: str) -> dict[str, Any] | None:
        """Get cached configuration from Redis"""
        if not self.redis_client:
            return None

        try:
            key = f"workflow_config:{config_id}"
            data = self.redis_client.get(key)
            if data:
                return json.loads(data)
        except Exception as e:
            self.logger.warning(f"Failed to get cached config {config_id}: {e}")

        return None

    def _invalidate_config_cache(self, config_id: str):
        """Invalidate cached configuration"""
        if not self.redis_client:
            return

        try:
            key = f"workflow_config:{config_id}"
            self.redis_client.delete(key)
        except Exception as e:
            self.logger.warning(f"Failed to invalidate cache for {config_id}: {e}")
