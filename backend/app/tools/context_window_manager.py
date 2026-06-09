"""
Memory & Knowledge Tools — Context Window Manager.

context_window_manager → Intelligently summarize, prune, and compress LLM
                          context in real time using Redis for short-term
                          caching and PostgreSQL for long-term persistence.
"""

from __future__ import annotations

import logging
import os
import re
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

REDIS_TTL = int(os.getenv("CONTEXT_WINDOW_REDIS_TTL", "3600"))
DEFAULT_MAX_TOKENS = int(os.getenv("CONTEXT_WINDOW_MAX_TOKENS", "4096"))


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


class ContextWindowManagerInput(ToolInput):
    model_config = ConfigDict(extra="ignore")

    key: str = Field(..., description="Memory key/identifier")
    value: str | None = Field(None, description="Value to store")
    action: str = Field(
        "retrieve",
        description="Action: 'store', 'retrieve', 'summarize', 'prune', or 'delete'",
    )
    max_tokens: int = Field(
        DEFAULT_MAX_TOKENS,
        ge=1,
        le=131072,
        description="Max tokens for prune action",
    )
    namespace: str = Field(
        "default",
        description="Namespace for isolation per user/session",
    )
    user_id: int | None = Field(
        None,
        description="User ID (auto-set from auth context if omitted)",
    )
    metadata: dict | None = Field(
        None,
        description="Optional key-value metadata",
    )


# ── Tool ──────────────────────────────────────────────────────────────


class ContextWindowManagerTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="context_window_manager",
            name="Context Window Manager",
            description=(
                "Intelligently summarize, prune, and compress LLM context "
                "in real time. Uses Redis for short-term caching and "
                "PostgreSQL for long-term persistence."
            ),
            category="memory",
            input_schema=ContextWindowManagerInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["memory", "context", "summarize", "prune", "differentiator"],
            requires_auth=True,
            timeout_seconds=15,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = ContextWindowManagerInput(**input_data)
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
            if action == "store":
                return await self._store(validated, user_id)
            elif action == "retrieve":
                return await self._retrieve(validated, user_id)
            elif action == "summarize":
                return await self._summarize(validated, user_id)
            elif action == "prune":
                return await self._prune(validated, user_id)
            elif action == "delete":
                return await self._delete(validated, user_id)
            else:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=(
                        f"Unknown action: {action}. Use 'store', 'retrieve', 'summarize', 'prune', or 'delete'."
                    ),
                )
        except Exception as e:
            logger.exception("context_window_manager failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _redis_key(key: str, namespace: str) -> str:
        return f"ctxwin:{namespace}:{key}"

    @staticmethod
    def _agent_id(key: str, namespace: str) -> str:
        return f"{namespace}:{key}"

    # ── store ────────────────────────────────────────────────────

    async def _store(
        self,
        validated: ContextWindowManagerInput,
        user_id: int | None,
    ) -> ToolResult:
        if validated.value is None:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="value is required for 'store' action",
            )

        key = validated.key
        namespace = validated.namespace
        entry_id = str(uuid.uuid4())

        # Persist to PostgreSQL (long-term)
        pg_stored = False
        try:
            async with AsyncSessionLocal() as session:
                entry = AgentMemory(
                    id=entry_id,
                    user_id=user_id or 0,
                    agent_id=self._agent_id(key, namespace),
                    content=validated.value,
                    content_type="context_window",
                    metadata_json=validated.metadata,
                )
                session.add(entry)
                await session.commit()
                pg_stored = True
                logger.info(
                    "Context window stored in PG: id=%s key=%s namespace=%s",
                    entry_id,
                    key,
                    namespace,
                )
        except Exception as e:
            logger.error("Failed to store in PostgreSQL: %s", e)
            # Continue — Redis is the primary fast path

        # Cache in Redis (short-term)
        redis_stored = False
        redis_client = _get_redis()
        if redis_client:
            try:
                rk = self._redis_key(key, namespace)
                redis_client.setex(rk, REDIS_TTL, validated.value)
                redis_stored = True
                logger.debug("Context window cached in Redis: key=%s", rk)
            except Exception as e:
                logger.warning("Redis store failed (non-fatal): %s", e)

        # If neither PG nor Redis succeeded, return an error
        if not pg_stored and not redis_stored:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Failed to store context in both PostgreSQL and Redis",
            )

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "store",
                "id": entry_id,
                "key": key,
                "namespace": namespace,
            },
        )

    # ── retrieve ─────────────────────────────────────────────────

    async def _retrieve(
        self,
        validated: ContextWindowManagerInput,
        user_id: int | None,
    ) -> ToolResult:
        key = validated.key
        namespace = validated.namespace

        # Try Redis first (fast path)
        redis_client = _get_redis()
        if redis_client:
            try:
                rk = self._redis_key(key, namespace)
                value = redis_client.get(rk)
                if value:
                    return ToolResult.success_result(
                        tool_id=self.tool_id,
                        result={
                            "action": "retrieve",
                            "key": key,
                            "namespace": namespace,
                            "value": value,
                            "source": "redis",
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
                        AgentMemory.agent_id == self._agent_id(key, namespace),
                        AgentMemory.user_id == (user_id or 0),
                        AgentMemory.content_type == "context_window",
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
                            f"No context found for key='{key}' in namespace='{namespace}'"
                        ),
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
                        "created_at": (
                            row.created_at.isoformat() if row.created_at else None
                        ),
                    },
                )
        except Exception as e:
            logger.exception("PostgreSQL retrieve failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── summarize ────────────────────────────────────────────────

    async def _summarize(
        self,
        validated: ContextWindowManagerInput,
        user_id: int | None,
    ) -> ToolResult:
        # Retrieve the stored value first
        retrieve_result = await self._retrieve(validated, user_id)
        if not retrieve_result.success:
            return retrieve_result

        text = retrieve_result.result.get("value", "")
        summary = self._basic_summarize(text)

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "summarize",
                "key": validated.key,
                "namespace": validated.namespace,
                "original_length": len(text),
                "summary": summary,
                "summary_length": len(summary),
                "compression_ratio": round(len(summary) / max(len(text), 1), 4),
            },
        )

    # ── prune ────────────────────────────────────────────────────

    async def _prune(
        self,
        validated: ContextWindowManagerInput,
        user_id: int | None,
    ) -> ToolResult:
        # Retrieve the stored value first
        retrieve_result = await self._retrieve(validated, user_id)
        if not retrieve_result.success:
            return retrieve_result

        text = retrieve_result.result.get("value", "")
        max_tokens = validated.max_tokens

        # Rough token estimation: ~4 chars per token
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return ToolResult.success_result(
                tool_id=self.tool_id,
                result={
                    "action": "prune",
                    "key": validated.key,
                    "namespace": validated.namespace,
                    "original_length": len(text),
                    "pruned_text": text,
                    "pruned_length": len(text),
                    "was_pruned": False,
                    "max_tokens": max_tokens,
                },
            )

        # Simple prune: keep beginning + end, drop middle
        # (production would use semantic chunking)
        head_size = max(int(max_chars * 0.7), 1)
        separator = "\n\n... [pruned] ...\n\n"
        tail_size = max(max_chars - head_size - len(separator), 1)
        pruned = text[:head_size] + separator + text[-tail_size:]

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "prune",
                "key": validated.key,
                "namespace": validated.namespace,
                "original_length": len(text),
                "pruned_text": pruned,
                "pruned_length": len(pruned),
                "was_pruned": True,
                "max_tokens": max_tokens,
            },
        )

    # ── delete ───────────────────────────────────────────────────

    async def _delete(
        self,
        validated: ContextWindowManagerInput,
        user_id: int | None,
    ) -> ToolResult:
        key = validated.key
        namespace = validated.namespace
        deleted_from_pg = False
        deleted_from_redis = False

        # Delete from PostgreSQL
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(AgentMemory).where(
                    AgentMemory.agent_id == self._agent_id(key, namespace),
                    AgentMemory.user_id == (user_id or 0),
                    AgentMemory.content_type == "context_window",
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                for row in rows:
                    await session.delete(row)
                if rows:
                    await session.commit()
                    deleted_from_pg = True
                    logger.info(
                        "Deleted %d context window entries from PG: key=%s namespace=%s",
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
                deleted_from_redis = True
            except Exception as e:
                logger.warning("Redis delete failed (non-fatal): %s", e)

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "delete",
                "key": key,
                "namespace": namespace,
                "deleted_from_postgresql": deleted_from_pg,
                "deleted_from_redis": deleted_from_redis,
            },
        )

    # ── basic summarization ──────────────────────────────────────

    @staticmethod
    def _basic_summarize(text: str) -> str:
        """Extractive summarization: keep first sentences, key sentences, last sentence."""
        if not text or len(text) < 200:
            return text

        sentences = re.split(r"(?<=[.!?])\s+", text)
        if len(sentences) <= 3:
            return text

        # Sentences containing key phrases get priority
        key_phrases = [
            "important",
            "critical",
            "key",
            "must",
            "required",
            "conclusion",
            "summary",
            "therefore",
            "however",
            "decision",
            "action item",
            "deadline",
        ]

        key_sentences = [
            s
            for s in sentences[2:-1]
            if any(phrase in s.lower() for phrase in key_phrases)
        ]

        # Build: first 2 + key sentences (max 5) + last 1
        summary_parts = sentences[:2]
        if key_sentences:
            summary_parts.append("")
            summary_parts.extend(key_sentences[:5])
        summary_parts.append("")
        summary_parts.append(sentences[-1])

        return " ".join(summary_parts)


# ── Register ──────────────────────────────────────────────────────────

register_tool(ContextWindowManagerTool())
