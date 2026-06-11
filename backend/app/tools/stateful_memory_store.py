"""
AI Agent-Specific Tools — Stateful Memory Store.

stateful_memory_store → Save and retrieve long-term context across multiple agent sessions.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import UTC, datetime

import redis.asyncio as redis_asyncio
from pydantic import Field
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.agent import AgentMemory
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Redis connection (lazy) ──────────────────────────────────────────────

_redis: redis_asyncio.Redis | None = None
_redis_available: bool | None = None
MEMORY_TTL = int(os.getenv("STATEFUL_MEMORY_TTL", "86400"))  # 24h default


def _get_redis() -> redis_asyncio.Redis | None:
    global _redis, _redis_available
    if _redis_available is False:
        return None
    if _redis is None:
        try:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            _redis = redis_asyncio.from_url(redis_url, decode_responses=True)
            _redis_available = True
        except Exception:
            logger.warning("Redis unavailable for stateful memory store")
            _redis_available = False
            return None
    return _redis


# ── Input ─────────────────────────────────────────────────────────────────


class StatefulMemoryStoreInput(ToolInput):
    action: str = Field(
        ...,
        description="Action: 'save', 'retrieve', 'search', 'list', 'delete', 'update'",
    )
    key: str | None = Field(
        None,
        description="Memory key/identifier for save/retrieve/update/delete",
    )
    value: str | None = Field(
        None,
        description="Content to store",
    )
    query: str | None = Field(
        None,
        description="Search query for 'search' action (fuzzy text match)",
    )
    namespace: str = Field(
        "default",
        description="Namespace for memory isolation (e.g., user_id, project_name)",
    )
    metadata: dict | None = Field(
        None,
        description="Optional key-value metadata tags",
    )
    max_results: int = Field(
        10,
        ge=1,
        le=100,
        description="Max results for 'list' or 'search' actions",
    )
    user_id: int | None = Field(
        None,
        description="User ID (auto-set from auth context if omitted)",
    )


# ── Tool ──────────────────────────────────────────────────────────────────


class StatefulMemoryStoreTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="stateful_memory_store",
            name="Stateful Memory Store",
            description="Save and retrieve long-term context across multiple agent sessions",
            category="ai-agent",
            input_schema=StatefulMemoryStoreInput.schema_extra(),
            tags=[
                "memory",
                "stateful",
                "persistence",
                "context",
                "agent",
                "differentiator",
            ],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    # ── execute ────────────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = StatefulMemoryStoreInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        # Resolve user_id from auth context if not explicitly provided
        context = input_data.get("context", {}) or {}
        user_id = validated.user_id if validated.user_id is not None else context.get("user_id")
        if user_id is not None:
            try:
                user_id = int(user_id)
            except (ValueError, TypeError):
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"Invalid user_id: {user_id}",
                )

        action = validated.action.lower().strip()

        try:
            if action == "save":
                return await self._save(validated, user_id)
            elif action == "retrieve":
                return await self._retrieve(validated, user_id)
            elif action == "search":
                return await self._search(validated, user_id)
            elif action == "list":
                return await self._list(validated, user_id)
            elif action == "delete":
                return await self._delete(validated, user_id)
            elif action == "update":
                return await self._update(validated, user_id)
            else:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=(
                        f"Unknown action: {action}. Use 'save', 'retrieve', 'search', 'list', 'delete', or 'update'."
                    ),
                )
        except Exception as e:
            logger.exception("stateful_memory_store failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _redis_key(namespace: str, key: str) -> str:
        return f"smem:{namespace}:{key}"

    @staticmethod
    def _agent_id(namespace: str, key: str) -> str:
        return f"{namespace}:{key}"

    # ── save ────────────────────────────────────────────────────────────

    async def _save(
        self,
        validated: StatefulMemoryStoreInput,
        user_id: int | None,
    ) -> ToolResult:
        if not validated.key or not validated.value:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Both 'key' and 'value' are required for 'save' action",
            )

        key = validated.key
        namespace = validated.namespace
        entry_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        # Persist to PostgreSQL (long-term)
        pg_stored = False
        try:
            async with AsyncSessionLocal() as session:
                entry = AgentMemory(
                    id=entry_id,
                    user_id=user_id or 0,
                    agent_id=self._agent_id(namespace, key),
                    content=validated.value,
                    content_type="stateful_memory",
                    metadata_json=validated.metadata,
                )
                session.add(entry)
                await session.commit()
                pg_stored = True
                logger.info(
                    "Stateful memory saved to PG: id=%s key=%s namespace=%s",
                    entry_id,
                    key,
                    namespace,
                )
        except Exception as e:
            logger.error("Failed to save stateful memory to PostgreSQL: %s", e)

        # Cache in Redis (fast path)
        redis_stored = False
        redis_client = await _get_redis() if callable(_get_redis) else _get_redis()
        try:
            r = _get_redis()
        except Exception:
            r = None

        # Handle both sync and async Redis clients
        if r:
            try:
                rk = self._redis_key(namespace, key)
                payload = json.dumps(
                    {
                        "id": entry_id,
                        "key": key,
                        "value": validated.value,
                        "metadata": validated.metadata,
                        "created_at": now.isoformat(),
                    }
                )
                # Try async first, fall back to sync
                try:
                    await r.setex(rk, MEMORY_TTL, payload)
                except (TypeError, AttributeError):
                    r.setex(rk, MEMORY_TTL, payload)
                redis_stored = True
            except Exception as e:
                logger.warning("Redis save failed (non-fatal): %s", e)

        if not pg_stored and not redis_stored:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Failed to save memory in both PostgreSQL and Redis",
            )

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "save",
                "id": entry_id,
                "key": key,
                "namespace": namespace,
                "created_at": now.isoformat(),
                "persisted_to": [s for s, ok in [("postgresql", pg_stored), ("redis", redis_stored)] if ok],
            },
        )

    # ── retrieve ────────────────────────────────────────────────────────

    async def _retrieve(
        self,
        validated: StatefulMemoryStoreInput,
        user_id: int | None,
    ) -> ToolResult:
        if not validated.key:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="'key' is required for 'retrieve' action",
            )

        key = validated.key
        namespace = validated.namespace

        # Try Redis first
        r = _get_redis()
        if r:
            try:
                rk = self._redis_key(namespace, key)
                try:
                    raw = await r.get(rk)
                except (TypeError, AttributeError):
                    raw = r.get(rk)
                if raw:
                    data = json.loads(raw) if isinstance(raw, str) else raw
                    return ToolResult.success_result(
                        tool_id=self.tool_id,
                        result={
                            "action": "retrieve",
                            "key": key,
                            "namespace": namespace,
                            "value": (data.get("value", raw) if isinstance(data, dict) else raw),
                            "source": "redis",
                            "id": data.get("id") if isinstance(data, dict) else None,
                            "metadata": (data.get("metadata") if isinstance(data, dict) else None),
                            "created_at": (data.get("created_at") if isinstance(data, dict) else None),
                        },
                    )
            except Exception as e:
                logger.warning("Redis retrieve failed, falling back to PG: %s", e)

        # Fall back to PostgreSQL
        try:
            async with AsyncSessionLocal() as session:
                stmt = (
                    select(AgentMemory)
                    .where(
                        AgentMemory.agent_id == self._agent_id(namespace, key),
                        AgentMemory.user_id == (user_id or 0),
                        AgentMemory.content_type == "stateful_memory",
                    )
                    .order_by(AgentMemory.created_at.desc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                row = result.scalars().first()

                if row is None:
                    return ToolResult.error_result(
                        tool_id=self.tool_id,
                        error=f"No memory found for key='{key}' in namespace='{namespace}'",
                    )

                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "retrieve",
                        "key": key,
                        "namespace": namespace,
                        "value": row.content,
                        "source": "postgresql",
                        "id": row.id,
                        "created_at": (row.created_at.isoformat() if row.created_at else None),
                        "metadata": row.metadata_json,
                    },
                )
        except Exception as e:
            logger.exception("PostgreSQL retrieve failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── search ──────────────────────────────────────────────────────────

    async def _search(
        self,
        validated: StatefulMemoryStoreInput,
        user_id: int | None,
    ) -> ToolResult:
        if not validated.query:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="'query' is required for 'search' action",
            )

        query = validated.query
        namespace = validated.namespace

        try:
            async with AsyncSessionLocal() as session:
                stmt = (
                    select(AgentMemory)
                    .where(
                        AgentMemory.user_id == (user_id or 0),
                        AgentMemory.content_type == "stateful_memory",
                        AgentMemory.agent_id.like(f"{namespace}:%"),
                        AgentMemory.content.ilike(f"%{query}%"),
                    )
                    .order_by(AgentMemory.created_at.desc())
                    .limit(validated.max_results)
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()

                memories = [
                    {
                        "id": row.id,
                        "key": (row.agent_id.replace(f"{namespace}:", "", 1) if row.agent_id else ""),
                        "namespace": namespace,
                        "value": (row.content[:500] + "..." if len(row.content) > 500 else row.content),
                        "created_at": (row.created_at.isoformat() if row.created_at else None),
                        "metadata": row.metadata_json,
                    }
                    for row in rows
                ]

                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "search",
                        "query": query,
                        "namespace": namespace,
                        "results_count": len(memories),
                        "results": memories,
                    },
                )
        except Exception as e:
            logger.exception("Memory search failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── list ────────────────────────────────────────────────────────────

    async def _list(
        self,
        validated: StatefulMemoryStoreInput,
        user_id: int | None,
    ) -> ToolResult:
        namespace = validated.namespace

        try:
            async with AsyncSessionLocal() as session:
                stmt = (
                    select(AgentMemory)
                    .where(
                        AgentMemory.user_id == (user_id or 0),
                        AgentMemory.content_type == "stateful_memory",
                        (AgentMemory.agent_id.like(f"{namespace}:%") if namespace != "*" else True),
                    )
                    .order_by(AgentMemory.created_at.desc())
                    .limit(validated.max_results)
                )

                if namespace == "*":
                    stmt = stmt.where(True)  # no namespace filter

                result = await session.execute(stmt)
                rows = result.scalars().all()

                memories = [
                    {
                        "id": row.id,
                        "key": (row.agent_id.split(":", 1)[1] if ":" in (row.agent_id or "") else row.agent_id),
                        "namespace": (
                            row.agent_id.split(":", 1)[0] if row.agent_id and ":" in row.agent_id else namespace
                        ),
                        "value_preview": (row.content[:200] + "..." if len(row.content) > 200 else row.content),
                        "created_at": (row.created_at.isoformat() if row.created_at else None),
                    }
                    for row in rows
                ]

                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "list",
                        "namespace": namespace,
                        "results_count": len(memories),
                        "results": memories,
                    },
                )
        except Exception as e:
            logger.exception("Memory list failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── delete ──────────────────────────────────────────────────────────

    async def _delete(
        self,
        validated: StatefulMemoryStoreInput,
        user_id: int | None,
    ) -> ToolResult:
        if not validated.key:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="'key' is required for 'delete' action",
            )

        key = validated.key
        namespace = validated.namespace
        deleted_pg = False
        deleted_redis = False

        # Delete from PostgreSQL
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(AgentMemory).where(
                    AgentMemory.agent_id == self._agent_id(namespace, key),
                    AgentMemory.user_id == (user_id or 0),
                    AgentMemory.content_type == "stateful_memory",
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                for row in rows:
                    await session.delete(row)
                if rows:
                    await session.commit()
                    deleted_pg = True
        except Exception as e:
            logger.error("PostgreSQL delete failed: %s", e)

        # Delete from Redis
        r = _get_redis()
        if r:
            try:
                rk = self._redis_key(namespace, key)
                try:
                    await r.delete(rk)
                except (TypeError, AttributeError):
                    r.delete(rk)
                deleted_redis = True
            except Exception as e:
                logger.warning("Redis delete failed: %s", e)

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

    # ── update ──────────────────────────────────────────────────────────

    async def _update(
        self,
        validated: StatefulMemoryStoreInput,
        user_id: int | None,
    ) -> ToolResult:
        if not validated.key or not validated.value:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Both 'key' and 'value' are required for 'update' action",
            )

        # Delete old, then save new
        await self._delete(validated, user_id)
        return await self._save(validated, user_id)


# ── Register ──────────────────────────────────────────────────────────────

register_tool(StatefulMemoryStoreTool())
