"""
Memory & Knowledge Tools — Cross-Agent Memory Sharing.

cross_agent_memory_sharing → A shared memory pool for autonomous multi-agent
    teams. Agents can share, access, and update common context using Redis
    for fast access and PostgreSQL for durable persistence.
"""

from __future__ import annotations

import logging
import os
import uuid

import redis
from pydantic import ConfigDict, Field
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.agent import AgentMemory
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Redis connection (lazy, matches project pattern from web_search/cache.py) ──

_redis: redis.Redis | None = None
_redis_available: bool | None = None

REDIS_TTL = int(os.getenv("CROSS_AGENT_REDIS_TTL", "3600"))


def _get_redis() -> redis.Redis | None:
    """Lazy Redis connection with graceful fallback (project convention)."""
    global _redis, _redis_available
    if _redis_available is False:
        return None
    if _redis is None:
        try:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            _redis = redis.from_url(redis_url, decode_responses=True)
            _redis.ping()
            _redis_available = True
        except Exception:
            logger.warning("Redis unavailable; falling back to PostgreSQL-only mode")
            _redis_available = False
            return None
    return _redis


# ── Input ─────────────────────────────────────────────────────────────


class CrossAgentMemorySharingInput(ToolInput):
    model_config = ConfigDict(extra="ignore")

    key: str = Field(..., description="Memory key/identifier in the shared pool")
    value: str | None = Field(
        None, description="Value to store (required for 'share'/'update')"
    )
    action: str = Field(
        "access",
        description="Action: 'share', 'access', 'list', 'update', or 'delete'",
    )
    namespace: str = Field(
        "default",
        description="Namespace for team/workspace isolation",
    )
    agent_id: str = Field(
        "default",
        description="Calling agent identifier (for provenance tracking)",
    )
    user_id: int | None = Field(
        None,
        description="User ID (auto-set from auth context if omitted)",
    )
    limit: int = Field(
        25,
        ge=1,
        le=100,
        description="Max results for list action",
    )
    metadata: dict | None = Field(
        None,
        description="Optional key-value metadata attached to the memory entry",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class CrossAgentMemorySharingTool(BaseTool):
    """Shared memory pool for multi-agent teams.

    Agents write to a namespace-scoped shared pool; any agent in the same
    namespace can read, list, update, or delete entries.  Agent provenance
    is tracked on every write so teams can see who contributed what.
    """

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="cross_agent_memory_sharing",
            name="Cross-Agent Memory Sharing",
            description=(
                "A shared memory pool for autonomous multi-agent teams. "
                "Agents can share, access, and update common context with "
                "agent-level provenance tracking."
            ),
            category="memory",
            input_schema=CrossAgentMemorySharingInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["memory", "agent", "multi-agent", "collaboration", "differentiator"],
            requires_auth=True,
            timeout_seconds=15,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = CrossAgentMemorySharingInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(
                tool_id=self.tool_id, error=f"Invalid input: {e}"
            )

        # Resolve user_id from auth context if not explicitly provided
        context = input_data.get("context", {}) or {}
        user_id = (
            validated.user_id
            if validated.user_id is not None
            else context.get("user_id")
        )
        if user_id is not None:
            try:
                user_id = int(user_id)
            except (ValueError, TypeError):
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"Invalid user_id: {user_id}",
                )

        action = validated.action

        try:
            if action == "share":
                return await self._share(validated, user_id)
            elif action == "access":
                return await self._access(validated, user_id)
            elif action == "list":
                return await self._list_entries(validated, user_id)
            elif action == "update":
                return await self._update(validated, user_id)
            elif action == "delete":
                return await self._delete(validated, user_id)
            else:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=(
                        f"Unknown action: {action}. "
                        "Use 'share', 'access', 'list', 'update', or 'delete'."
                    ),
                )
        except Exception as e:
            logger.exception("cross_agent_memory_sharing failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _redis_key(key: str, namespace: str) -> str:
        return f"crossagent:{namespace}:{key}"

    @staticmethod
    def _agent_id(key: str, namespace: str) -> str:
        return f"{namespace}:{key}"

    # ── share ────────────────────────────────────────────────────

    async def _share(
        self,
        validated: CrossAgentMemorySharingInput,
        user_id: int | None,
    ) -> ToolResult:
        """Write a value into the shared pool, recording agent provenance."""
        if validated.value is None:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="value is required for 'share' action",
            )

        key = validated.key
        namespace = validated.namespace
        agent_id = validated.agent_id
        entry_id = str(uuid.uuid4())

        # Include agent provenance in metadata
        merged_metadata = {
            "source_agent": agent_id,
            "operation": "share",
        }
        if validated.metadata:
            merged_metadata.update(validated.metadata)

        # Persist to PostgreSQL (long-term, durable)
        pg_stored = False
        created_at = None
        try:
            async with AsyncSessionLocal() as session:
                entry = AgentMemory(
                    id=entry_id,
                    user_id=user_id or 0,
                    agent_id=self._agent_id(key, namespace),
                    content=validated.value,
                    content_type="cross_agent_memory",
                    metadata_json=merged_metadata,
                )
                session.add(entry)
                await session.commit()
                pg_stored = True
                created_at = entry.created_at.isoformat() if entry.created_at else None
                logger.info(
                    "Cross-agent memory shared in PG: id=%s key=%s "
                    "namespace=%s source_agent=%s",
                    entry_id,
                    key,
                    namespace,
                    agent_id,
                )
        except Exception as e:
            logger.error("Failed to store cross-agent memory in PG: %s", e)

        # Cache in Redis (short-term, fast reads)
        redis_stored = False
        redis_client = _get_redis()
        if redis_client:
            try:
                rk = self._redis_key(key, namespace)
                redis_client.setex(rk, REDIS_TTL, validated.value)
                redis_stored = True
                logger.debug("Cross-agent memory cached in Redis: key=%s", rk)
            except Exception as e:
                logger.warning("Redis share failed (non-fatal): %s", e)

        if not pg_stored and not redis_stored:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Failed to share memory in both PostgreSQL and Redis",
            )

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "share",
                "id": entry_id,
                "key": key,
                "namespace": namespace,
                "source_agent": agent_id,
                "created_at": created_at,
            },
        )

    # ── access ───────────────────────────────────────────────────

    async def _access(
        self,
        validated: CrossAgentMemorySharingInput,
        user_id: int | None,
    ) -> ToolResult:
        """Read a value from the shared pool. Any agent in the namespace can read."""
        key = validated.key
        namespace = validated.namespace

        # Try Redis first (fast path).
        # Note: Redis caches only the raw value string, so source_agent
        # provenance is not available on this path. Callers needing full
        # metadata should read from the PG fallback explicitly.
        redis_client = _get_redis()
        if redis_client:
            try:
                rk = self._redis_key(key, namespace)
                value = redis_client.get(rk)
                if value:
                    return ToolResult.success_result(
                        tool_id=self.tool_id,
                        result={
                            "action": "access",
                            "key": key,
                            "namespace": namespace,
                            "value": value,
                            "source": "redis",
                        },
                    )
            except Exception as e:
                logger.warning("Redis access failed, falling back to PG: %s", e)

        # Fall back to PostgreSQL
        try:
            async with AsyncSessionLocal() as session:
                stmt = (
                    select(AgentMemory)
                    .where(
                        AgentMemory.agent_id == self._agent_id(key, namespace),
                        AgentMemory.user_id == (user_id or 0),
                        AgentMemory.content_type == "cross_agent_memory",
                    )
                    .order_by(AgentMemory.created_at.desc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                row = result.scalars().first()

                if row is None:
                    return ToolResult.error_result(
                        tool_id=self.tool_id,
                        error=(
                            f"No shared memory found for key='{key}' "
                            f"in namespace='{namespace}'"
                        ),
                    )

                # Extract source agent from metadata
                source_agent = (
                    row.metadata_json.get("source_agent", "unknown")
                    if row.metadata_json
                    else "unknown"
                )

                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "access",
                        "key": key,
                        "namespace": namespace,
                        "value": row.content,
                        "source": "postgresql",
                        "id": row.id,
                        "source_agent": source_agent,
                        "created_at": (
                            row.created_at.isoformat() if row.created_at else None
                        ),
                    },
                )
        except Exception as e:
            logger.exception("PostgreSQL access failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── list ─────────────────────────────────────────────────────

    async def _list_entries(
        self,
        validated: CrossAgentMemorySharingInput,
        user_id: int | None,
    ) -> ToolResult:
        """List all shared entries in a namespace, newest first."""
        namespace = validated.namespace

        try:
            async with AsyncSessionLocal() as session:
                stmt = (
                    select(AgentMemory)
                    .where(
                        AgentMemory.agent_id.like(f"{namespace}:%"),
                        AgentMemory.user_id == (user_id or 0),
                        AgentMemory.content_type == "cross_agent_memory",
                    )
                    .order_by(AgentMemory.created_at.desc())
                    .limit(validated.limit)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()

                entries = [
                    {
                        "id": r.id,
                        # agent_id is stored as "namespace:key"; extract the key.
                        # Falls back to full string for entries created outside this tool.
                        "key": (
                            r.agent_id.split(":", 1)[1]
                            if ":" in r.agent_id
                            else r.agent_id
                        ),
                        "value": r.content,
                        "source_agent": (
                            r.metadata_json.get("source_agent", "unknown")
                            if r.metadata_json
                            else "unknown"
                        ),
                        "created_at": (
                            r.created_at.isoformat() if r.created_at else None
                        ),
                    }
                    for r in rows
                ]

                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "list",
                        "namespace": namespace,
                        "count": len(entries),
                        "entries": entries,
                    },
                )
        except Exception as e:
            logger.exception("PostgreSQL list failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── update ───────────────────────────────────────────────────

    async def _update(
        self,
        validated: CrossAgentMemorySharingInput,
        user_id: int | None,
    ) -> ToolResult:
        """Update an existing shared entry. Only succeeds if the entry exists."""
        if validated.value is None:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="value is required for 'update' action",
            )

        key = validated.key
        namespace = validated.namespace
        agent_id = validated.agent_id
        updated_pg = False
        updated_redis = False

        # Update PostgreSQL
        try:
            async with AsyncSessionLocal() as session:
                stmt = (
                    select(AgentMemory)
                    .where(
                        AgentMemory.agent_id == self._agent_id(key, namespace),
                        AgentMemory.user_id == (user_id or 0),
                        AgentMemory.content_type == "cross_agent_memory",
                    )
                    .order_by(AgentMemory.created_at.desc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                row = result.scalars().first()

                if row is None:
                    return ToolResult.error_result(
                        tool_id=self.tool_id,
                        error=(
                            f"No shared memory found for key='{key}' "
                            f"in namespace='{namespace}'"
                        ),
                    )

                row.content = validated.value
                if row.metadata_json is None:
                    row.metadata_json = {}
                row.metadata_json["source_agent"] = agent_id
                row.metadata_json["operation"] = "update"
                if validated.metadata:
                    row.metadata_json.update(validated.metadata)

                await session.commit()
                updated_pg = True
                logger.info(
                    "Cross-agent memory updated in PG: key=%s namespace=%s "
                    "source_agent=%s",
                    key,
                    namespace,
                    agent_id,
                )
        except Exception as e:
            logger.error("PostgreSQL update failed: %s", e)

        # Update Redis
        redis_client = _get_redis()
        if redis_client:
            try:
                rk = self._redis_key(key, namespace)
                redis_client.setex(rk, REDIS_TTL, validated.value)
                updated_redis = True
            except Exception as e:
                logger.warning("Redis update failed (non-fatal): %s", e)

        if not updated_pg and not updated_redis:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Failed to update memory in both PostgreSQL and Redis",
            )

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "update",
                "key": key,
                "namespace": namespace,
                "source_agent": agent_id,
            },
        )

    # ── delete ───────────────────────────────────────────────────

    async def _delete(
        self,
        validated: CrossAgentMemorySharingInput,
        user_id: int | None,
    ) -> ToolResult:
        """Remove an entry from the shared pool."""
        key = validated.key
        namespace = validated.namespace
        deleted_pg = False
        deleted_redis = False

        # Delete from PostgreSQL
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(AgentMemory).where(
                    AgentMemory.agent_id == self._agent_id(key, namespace),
                    AgentMemory.user_id == (user_id or 0),
                    AgentMemory.content_type == "cross_agent_memory",
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                for row in rows:
                    await session.delete(row)
                if rows:
                    await session.commit()
                    deleted_pg = True
                    logger.info(
                        "Deleted %d cross-agent memory entries: key=%s namespace=%s",
                        len(rows),
                        key,
                        namespace,
                    )
        except Exception as e:
            logger.error("PostgreSQL delete failed: %s", e)

        # Delete from Redis
        redis_client = _get_redis()
        if redis_client:
            try:
                rk = self._redis_key(key, namespace)
                redis_client.delete(rk)
                deleted_redis = True
            except Exception as e:
                logger.warning("Redis delete failed (non-fatal): %s", e)

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "delete",
                "key": key,
                "namespace": namespace,
                "deleted_from_postgresql": deleted_pg,
                "deleted_from_redis": deleted_redis,
            },
        )


# ── Register ──────────────────────────────────────────────────────────

register_tool(CrossAgentMemorySharingTool())
