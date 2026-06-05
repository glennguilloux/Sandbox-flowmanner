#!/usr/bin/env python3
"""
LangGraph Agent Persistence

Handles persistence of:
- Agent states (sessions)
- Tool definitions
- Tool execution history
- Saved/reusable tool configurations
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any, TypedDict

from .state import AgentState, ToolExecution, dict_to_state, state_to_dict

logger = logging.getLogger(__name__)


class ToolDefinition(TypedDict):
    """Represents a tool definition"""

    tool_id: str
    tool_name: str
    description: str
    parameters_schema: dict[str, Any]
    category: str
    is_safe: bool  # Whether tool is safe to auto-approve
    requires_approval: bool
    created_at: str
    updated_at: str


class SavedToolConfiguration(TypedDict):
    """Represents a saved/reusable tool configuration"""

    config_id: str
    tool_id: str
    tool_name: str
    name: str
    description: str
    parameters: dict[str, Any]
    user_id: int
    created_at: str
    updated_at: str
    usage_count: int


class AgentPersistence:
    """
    Handles persistence for LangGraph agent states and tool configurations.

    Uses Redis for session caching and PostgreSQL for long-term storage.
    Falls back to in-memory storage when Redis is not available.
    """

    def __init__(self, redis_client=None):
        """
        Initialize persistence layer.

        Args:
            redis_client: Optional Redis client for caching
        """
        self.redis_client = redis_client
        self.session_ttl = 3600  # 1 hour default TTL
        self.config_ttl = 86400 * 7  # 7 days for saved configs
        self._in_memory_states = {}  # Fallback for when Redis is not available
        logger.info(
            f"[DEBUG] AgentPersistence initialized with id={id(self)}, redis_client={redis_client is not None}"
        )

    def save_state(self, state: AgentState, ttl: int | None = None) -> bool:
        """
        Save agent state to Redis cache or in-memory fallback.

        Args:
            state: Agent state to save
            ttl: Optional time-to-live in seconds

        Returns:
            True if saved successfully
        """
        try:
            data = state_to_dict(state)
            session_id = state["session_id"]

            logger.info(
                f"[DEBUG] save_state called for session {session_id}, has_redis={self.redis_client is not None}, persistence_id={id(self)}, dict_id={id(self._in_memory_states)}"
            )

            if self.redis_client:
                # Use Redis if available
                key = f"langgraph:state:{session_id}"
                ttl = ttl or self.session_ttl
                self.redis_client.setex(key, ttl, json.dumps(data))
                logger.debug(f"Saved state for session {session_id}")
            else:
                # Use in-memory fallback
                logger.info(
                    f"[DEBUG] Saving to in-memory states dict, dict_id={id(self._in_memory_states)}, current keys: {list(self._in_memory_states.keys())}"
                )
                self._in_memory_states[session_id] = data
                logger.info(
                    f"[DEBUG] After save - in-memory states dict_id={id(self._in_memory_states)}, has {len(self._in_memory_states)} entries: {list(self._in_memory_states.keys())}, session_id in dict: {session_id in self._in_memory_states}"
                )
                logger.debug(f"Saved state in-memory for session {session_id}")

            return True
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            import traceback

            traceback.print_exc()
            return False

    def load_state(self, session_id: str) -> AgentState | None:
        """
        Load agent state from Redis cache or in-memory fallback.

        Args:
            session_id: Session identifier

        Returns:
            Agent state if found, None otherwise
        """
        try:
            logger.info(
                f"[DEBUG] load_state called for session {session_id}, has_redis={self.redis_client is not None}, persistence_id={id(self)}, dict_id={id(self._in_memory_states)}, available keys: {list(self._in_memory_states.keys())}"
            )

            if self.redis_client:
                # Try Redis first
                key = f"langgraph:state:{session_id}"
                logger.info(f"[DEBUG] Redis key: {key}")
                data = self.redis_client.get(key)
                logger.info(
                    f"[DEBUG] Redis get() returned: {data is not None}, type: {type(data)}"
                )

                if data:
                    state = dict_to_state(json.loads(data))
                    logger.info(
                        f"[DEBUG] Successfully loaded state from Redis for session {session_id}"
                    )
                    return state
                else:
                    logger.warning(f"[DEBUG] No data found in Redis for key: {key}")
            else:
                # Try in-memory fallback
                logger.info(
                    f"[DEBUG] Redis not available, checking in-memory states, session_id in dict: {session_id in self._in_memory_states}"
                )
                if session_id in self._in_memory_states:
                    state = dict_to_state(self._in_memory_states[session_id])
                    logger.debug(f"Loaded state for session {session_id} from memory")
                    return state
                else:
                    logger.info(
                        f"[DEBUG] Session {session_id} not found in in-memory states"
                    )
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            import traceback

            traceback.print_exc()

        logger.warning(f"[DEBUG] load_state returning None for session {session_id}")
        return None

    def delete_state(self, session_id: str) -> bool:
        """
        Delete agent state from Redis cache.

        Args:
            session_id: Session identifier

        Returns:
            True if deleted successfully
        """
        if not self.redis_client:
            return False

        try:
            key = f"langgraph:state:{session_id}"
            self.redis_client.delete(key)
            logger.debug(f"Deleted state for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete state: {e}")
            return False

    def save_tool_execution(
        self,
        session_id: str,
        tool_execution: ToolExecution,
    ) -> bool:
        """
        Save a tool execution to history.

        Args:
            session_id: Session identifier
            tool_execution: Tool execution to save

        Returns:
            True if saved successfully
        """
        if not self.redis_client:
            return False

        try:
            key = f"langgraph:history:{session_id}"
            history = self.redis_client.lrange(key, 0, -1)

            # Add new execution
            self.redis_client.lpush(key, json.dumps(tool_execution))

            # Keep only last 100 executions
            self.redis_client.ltrim(key, 0, 99)

            # Set TTL
            self.redis_client.expire(key, self.session_ttl * 24)  # 24 hours

            logger.debug(f"Saved tool execution for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save tool execution: {e}")
            return False

    def get_tool_history(
        self,
        session_id: str,
        limit: int = 50,
    ) -> list[ToolExecution]:
        """
        Get tool execution history for a session.

        Args:
            session_id: Session identifier
            limit: Maximum number of executions to return

        Returns:
            List of tool executions
        """
        if not self.redis_client:
            return []

        try:
            key = f"langgraph:history:{session_id}"
            data = self.redis_client.lrange(key, 0, limit - 1)

            history = []
            for item in data:
                try:
                    history.append(json.loads(item))
                except Exception:
                    logger.debug("Failed to parse tool history item")

            return history
        except Exception as e:
            logger.error(f"Failed to get tool history: {e}")
            return []

    def save_tool_configuration(
        self,
        user_id: int,
        tool_id: str,
        tool_name: str,
        name: str,
        description: str,
        parameters: dict[str, Any],
    ) -> str | None:
        """
        Save a reusable tool configuration.

        Args:
            user_id: User ID
            tool_id: Tool identifier
            tool_name: Tool name
            name: Configuration name
            description: Configuration description
            parameters: Tool parameters

        Returns:
            Configuration ID if saved successfully, None otherwise
        """
        if not self.redis_client:
            return None

        try:
            import uuid

            config_id = f"config_{uuid.uuid4().hex[:16]}"

            config: SavedToolConfiguration = {
                "config_id": config_id,
                "tool_id": tool_id,
                "tool_name": tool_name,
                "name": name,
                "description": description,
                "parameters": parameters,
                "user_id": user_id,
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
                "usage_count": 0,
            }

            key = f"langgraph:config:{config_id}"
            self.redis_client.setex(key, self.config_ttl, json.dumps(config))

            # Add to user's config list
            user_key = f"langgraph:user_configs:{user_id}"
            self.redis_client.sadd(user_key, config_id)
            self.redis_client.expire(user_key, self.config_ttl)

            logger.info(f"Saved tool configuration {config_id} for user {user_id}")
            return config_id
        except Exception as e:
            logger.error(f"Failed to save tool configuration: {e}")
            return None

    def get_tool_configuration(
        self,
        config_id: str,
    ) -> SavedToolConfiguration | None:
        """
        Get a saved tool configuration.

        Args:
            config_id: Configuration identifier

        Returns:
            Saved configuration if found, None otherwise
        """
        if not self.redis_client:
            return None

        try:
            key = f"langgraph:config:{config_id}"
            data = self.redis_client.get(key)

            if data:
                config = json.loads(data)

                # Increment usage count
                config["usage_count"] = config.get("usage_count", 0) + 1
                config["updated_at"] = datetime.now(UTC).isoformat()

                self.redis_client.setex(key, self.config_ttl, json.dumps(config))

                return config
        except Exception as e:
            logger.error(f"Failed to get tool configuration: {e}")

        return None

    def list_user_configurations(
        self,
        user_id: int,
        tool_id: str | None = None,
    ) -> list[SavedToolConfiguration]:
        """
        List all saved configurations for a user.

        Args:
            user_id: User ID
            tool_id: Optional filter by tool ID

        Returns:
            List of saved configurations
        """
        if not self.redis_client:
            return []

        try:
            user_key = f"langgraph:user_configs:{user_id}"
            config_ids = self.redis_client.smembers(user_key)

            configs = []
            for config_id in config_ids:
                config = self.get_tool_configuration(config_id)
                if config and (tool_id is None or config["tool_id"] == tool_id):
                    configs.append(config)

            return configs
        except Exception as e:
            logger.error(f"Failed to list user configurations: {e}")
            return []

    def delete_tool_configuration(
        self,
        user_id: int,
        config_id: str,
    ) -> bool:
        """
        Delete a saved tool configuration.

        Args:
            user_id: User ID
            config_id: Configuration identifier

        Returns:
            True if deleted successfully
        """
        if not self.redis_client:
            return False

        try:
            key = f"langgraph:config:{config_id}"
            config = self.get_tool_configuration(config_id)

            if config and config["user_id"] == user_id:
                self.redis_client.delete(key)

                # Remove from user's config list
                user_key = f"langgraph:user_configs:{user_id}"
                self.redis_client.srem(user_key, config_id)

                logger.info(f"Deleted tool configuration {config_id}")
                return True
        except Exception as e:
            logger.error(f"Failed to delete tool configuration: {e}")

        return False

    def update_tool_configuration(
        self,
        config_id: str,
        user_id: int,
        updates: dict[str, Any],
    ) -> bool:
        """
        Update a saved tool configuration.

        Args:
            config_id: Configuration identifier
            user_id: User ID
            updates: Dictionary of fields to update

        Returns:
            True if updated successfully
        """
        if not self.redis_client:
            return False

        try:
            config = self.get_tool_configuration(config_id)
            if not config or config["user_id"] != user_id:
                return False

            # Update allowed fields
            allowed_fields = {"name", "description", "parameters"}
            for field, value in updates.items():
                if field in allowed_fields:
                    config[field] = value

            # Update timestamp
            config["updated_at"] = datetime.now(UTC).isoformat()

            # Save updated config
            key = f"langgraph:config:{config_id}"
            self.redis_client.setex(key, self.config_ttl, json.dumps(config))

            logger.info(f"Updated tool configuration {config_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update tool configuration: {e}")

        return False

    def get_recent_tools(
        self,
        user_id: int,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Get recently used tools for a user.

        Args:
            user_id: User ID
            limit: Maximum number of tools to return

        Returns:
            List of recently used tools with usage counts
        """
        if not self.redis_client:
            return []

        try:
            key = f"langgraph:recent_tools:{user_id}"
            data = self.redis_client.lrange(key, 0, limit - 1)

            recent_tools = []
            for item in data:
                try:
                    tool_data = json.loads(item)
                    recent_tools.append(tool_data)
                except Exception:
                    logger.debug("Failed to parse recent tool item")

            return recent_tools
        except Exception as e:
            logger.error(f"Failed to get recent tools: {e}")
            return []

    def record_tool_usage(
        self,
        user_id: int,
        tool_id: str,
        tool_name: str,
        parameters: dict[str, Any],
    ) -> bool:
        """
        Record tool usage for analytics and recommendations.

        Args:
            user_id: User ID
            tool_id: Tool identifier
            tool_name: Tool name
            parameters: Tool parameters used

        Returns:
            True if recorded successfully
        """
        if not self.redis_client:
            return False

        try:
            key = f"langgraph:recent_tools:{user_id}"

            usage_data = {
                "tool_id": tool_id,
                "tool_name": tool_name,
                "parameters": parameters,
                "timestamp": datetime.now(UTC).isoformat(),
            }

            # Add to recent tools
            self.redis_client.lpush(key, json.dumps(usage_data))

            # Keep only last 50
            self.redis_client.ltrim(key, 0, 49)

            # Set TTL
            self.redis_client.expire(key, self.session_ttl * 24 * 7)  # 7 days

            return True
        except Exception as e:
            logger.error(f"Failed to record tool usage: {e}")
            return False


# Global persistence instance
_persistence = None
_redis_client_instance = None


def get_persistence(redis_client=None) -> AgentPersistence:
    """
    Get singleton persistence instance.

    Args:
        redis_client: Optional Redis client (only used on first call)

    Returns:
        AgentPersistence instance
    """
    global _persistence, _redis_client_instance
    if _persistence is None:
        # Store the Redis client for future reference
        _redis_client_instance = redis_client
        _persistence = AgentPersistence(redis_client)
        logger.info(
            f"[DEBUG] Created new persistence instance: id={id(_persistence)}, redis_client={redis_client is not None}"
        )
    else:
        # If called again with a different redis_client, log it but keep using the original
        if redis_client != _redis_client_instance:
            logger.warning(
                f"[DEBUG] get_persistence called again with different redis_client. Original: {_redis_client_instance is not None}, New: {redis_client is not None}. Using original instance."
            )
        logger.info(
            f"[DEBUG] Reusing existing persistence instance: id={id(_persistence)}, redis_client={_persistence.redis_client is not None}"
        )
    return _persistence
