"""
Memory & Knowledge Tools — Memory Summarization.

memory_summarization → Auto-compress long conversations into dense
    foundational memories. Supports extractive, bullet-point, and
    keyword extraction strategies with Redis caching and PostgreSQL
    persistence.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from collections import Counter

import redis
from pydantic import ConfigDict, Field
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.agent import AgentMemory
from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

# ── Redis connection (lazy, matches project pattern) ──────────────────

_redis: redis.Redis | None = None
_redis_available: bool | None = None

REDIS_TTL = int(os.getenv("MEMORY_SUMMARIZATION_REDIS_TTL", "86400"))  # 24h


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


class MemorySummarizationInput(ToolInput):
    model_config = ConfigDict(extra="ignore")

    key: str = Field(..., description="Memory key/identifier")
    value: str | None = Field(
        None,
        description="Text to summarize (if omitted, retrieves from stored key)",
    )
    action: str = Field(
        "summarize",
        description=(
            "Action: 'summarize' (dense paragraph), 'compress' (aggressive short), "
            "'bullet_points' (key points list), 'keywords' (extract terms), "
            "'retrieve' (read stored summary), or 'delete' (remove stored summary)"
        ),
    )
    strategy: str = Field(
        "extractive",
        description=(
            "Summarization strategy (reserved for future use; currently all "
            "actions use extractive summarization): 'extractive', 'paragraph', 'hybrid'"
        ),
    )
    max_sentences: int = Field(
        5,
        ge=1,
        le=20,
        description="Maximum sentences in the summary",
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


class MemorySummarizationTool(BaseTool):
    """Auto-compress long conversations into dense foundational memories.

    Accepts raw text or retrieves from a stored key, applies the requested
    summarization strategy, and persists the result for future retrieval.
    """

    def __init__(self):
        metadata = ToolMetadata(
            tool_id="memory_summarization",
            name="Memory Summarization",
            description=(
                "Auto-compress long conversations into dense foundational "
                "memories. Supports extractive, bullet-point, and keyword "
                "extraction strategies."
            ),
            category="memory",
            input_schema=MemorySummarizationInput.schema_extra(),
            output_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "object"},
                    "success": {"type": "boolean"},
                },
            },
            tags=["memory", "summarize", "compress", "conversation", "nlp"],
            requires_auth=True,
            timeout_seconds=20,
        )
        super().__init__(metadata=metadata)

    # ── execute ──────────────────────────────────────────────────

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = MemorySummarizationInput(**input_data)
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
            if action == "summarize":
                return await self._summarize(validated, user_id)
            elif action == "compress":
                return await self._compress(validated, user_id)
            elif action == "bullet_points":
                return await self._bullet_points(validated, user_id)
            elif action == "keywords":
                return await self._keywords(validated, user_id)
            elif action == "retrieve":
                return await self._retrieve(validated, user_id)
            elif action == "delete":
                return await self._delete(validated, user_id)
            else:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=(
                        f"Unknown action: {action}. "
                        "Use 'summarize', 'compress', 'bullet_points', "
                        "'keywords', 'retrieve', or 'delete'."
                    ),
                )
        except Exception as e:
            logger.exception("memory_summarization failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── helpers ──────────────────────────────────────────────────

    @staticmethod
    def _redis_key(key: str, namespace: str) -> str:
        return f"memsum:{namespace}:{key}"

    @staticmethod
    def _agent_id(key: str, namespace: str) -> str:
        return f"{namespace}:{key}"

    async def _resolve_text(
        self,
        validated: MemorySummarizationInput,
        user_id: int | None,
    ) -> tuple[str, str]:
        """Resolve the text to summarize: use direct input or retrieve from store."""
        if validated.value is not None:
            return validated.value, "direct_input"

        # Retrieve from stored context_window or cross_agent entries
        text, source = await self._fetch_text(validated, user_id)
        if text is None:
            raise ValueError(
                f"No text found for key='{validated.key}' "
                f"in namespace='{validated.namespace}'. "
                "Provide a 'value' or ensure the key exists."
            )
        return text, source

    async def _fetch_text(
        self,
        validated: MemorySummarizationInput,
        user_id: int | None,
    ) -> tuple[str | None, str]:
        """Try Redis, then PostgreSQL for stored text."""
        key = validated.key
        namespace = validated.namespace

        # Try Redis (check prefixes from sibling tools + our own).
        # Coupled to context_window_manager ("ctxwin") and
        # cross_agent_memory_sharing ("crossagent") key patterns.
        redis_client = _get_redis()
        if redis_client:
            for prefix in ("ctxwin", "crossagent", "memsum"):
                try:
                    rk = f"{prefix}:{namespace}:{key}"
                    value = redis_client.get(rk)
                    if value:
                        return value, f"redis:{prefix}"
                except Exception:
                    continue

        # Fall back to PostgreSQL
        try:
            async with AsyncSessionLocal() as session:
                stmt = (
                    select(AgentMemory)
                    .where(
                        AgentMemory.agent_id == self._agent_id(key, namespace),
                        AgentMemory.user_id == (user_id or 0),
                    )
                    .order_by(AgentMemory.created_at.desc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                row = result.scalars().first()
                if row:
                    return row.content, f"postgresql:{row.content_type}"
        except Exception as e:
            logger.warning("PostgreSQL fetch failed: %s", e)

        return None, "not_found"

    async def _persist_summary(
        self,
        validated: MemorySummarizationInput,
        user_id: int | None,
        summary: str,
        action: str,
        stats: dict,
    ) -> dict:
        """Store the summary in PostgreSQL and cache in Redis.

        Returns a dict with 'persisted' flags so callers can report storage status.
        """
        key = validated.key
        namespace = validated.namespace
        entry_id = str(uuid.uuid4())

        merged_metadata = {
            "action": action,
            "strategy": validated.strategy,
            **stats,
        }
        if validated.metadata:
            merged_metadata.update(validated.metadata)

        pg_stored = False
        redis_stored = False

        # PostgreSQL
        try:
            async with AsyncSessionLocal() as session:
                entry = AgentMemory(
                    id=entry_id,
                    user_id=user_id or 0,
                    agent_id=self._agent_id(key, namespace),
                    content=summary,
                    content_type="memory_summary",
                    metadata_json=merged_metadata,
                )
                session.add(entry)
                await session.commit()
                pg_stored = True
                logger.info(
                    "Memory summary persisted in PG: id=%s key=%s action=%s",
                    entry_id,
                    key,
                    action,
                )
        except Exception as e:
            logger.error("Failed to persist summary in PG: %s", e)

        # Redis cache
        redis_client = _get_redis()
        if redis_client:
            try:
                rk = self._redis_key(key, namespace)
                redis_client.setex(rk, REDIS_TTL, summary)
                redis_stored = True
            except Exception as e:
                logger.warning("Redis cache failed (non-fatal): %s", e)

        return {
            "persisted_pg": pg_stored,
            "persisted_redis": redis_stored,
            "id": entry_id if pg_stored else None,
        }

    # ── summarize ────────────────────────────────────────────────

    async def _summarize(
        self,
        validated: MemorySummarizationInput,
        user_id: int | None,
    ) -> ToolResult:
        """Dense paragraph summary of the input text."""
        try:
            text, source = await self._resolve_text(validated, user_id)
        except ValueError as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

        summary = self._extractive_summary(text, validated.max_sentences)
        stats = {
            "original_length": len(text),
            "summary_length": len(summary),
            "original_sentences": len(re.split(r"(?<=[.!?])\s+", text)),
            "summary_sentences": len(re.split(r"(?<=[.!?])\s+", summary)),
            "compression_ratio": round(len(summary) / max(len(text), 1), 4),
        }

        persist_info = await self._persist_summary(
            validated, user_id, summary, "summarize", stats
        )

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "summarize",
                "key": validated.key,
                "namespace": validated.namespace,
                "source": source,
                "summary": summary,
                **persist_info,
                **stats,
            },
        )

    # ── compress ─────────────────────────────────────────────────

    async def _compress(
        self,
        validated: MemorySummarizationInput,
        user_id: int | None,
    ) -> ToolResult:
        """Aggressive short-form compression — 1-2 sentence gist."""
        try:
            text, source = await self._resolve_text(validated, user_id)
        except ValueError as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

        # Generate a full summary first, then compress further
        full_summary = self._extractive_summary(text, max_sentences=3)
        sentences = re.split(r"(?<=[.!?])\s+", full_summary)

        # Keep only the most information-dense sentences
        compressed = " ".join(sentences[:2]) if len(sentences) >= 2 else full_summary

        stats = {
            "original_length": len(text),
            "compressed_length": len(compressed),
            "compression_ratio": round(len(compressed) / max(len(text), 1), 4),
        }

        persist_info = await self._persist_summary(
            validated, user_id, compressed, "compress", stats
        )

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "compress",
                "key": validated.key,
                "namespace": validated.namespace,
                "source": source,
                "compressed": compressed,
                **persist_info,
                **stats,
            },
        )

    # ── bullet_points ────────────────────────────────────────────

    async def _bullet_points(
        self,
        validated: MemorySummarizationInput,
        user_id: int | None,
    ) -> ToolResult:
        """Extract key points as a bulleted list."""
        try:
            text, source = await self._resolve_text(validated, user_id)
        except ValueError as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

        summary_sentences = self._extractive_summary(
            text,
            validated.max_sentences,
        )
        summary_list = re.split(r"(?<=[.!?])\s+", summary_sentences)

        # Format as bullet points, stripping trailing whitespace
        bullets = [f"• {s.strip().rstrip('.')}" for s in summary_list if s.strip()]

        bullet_text = "\n".join(bullets)
        stats = {
            "original_length": len(text),
            "bullet_count": len(bullets),
            "compression_ratio": round(len(bullet_text) / max(len(text), 1), 4),
        }

        persist_info = await self._persist_summary(
            validated,
            user_id,
            bullet_text,
            "bullet_points",
            stats,
        )

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "bullet_points",
                "key": validated.key,
                "namespace": validated.namespace,
                "source": source,
                "bullets": bullets,
                "bullet_text": bullet_text,
                **persist_info,
                **stats,
            },
        )

    # ── keywords ─────────────────────────────────────────────────

    async def _keywords(
        self,
        validated: MemorySummarizationInput,
        user_id: int | None,
    ) -> ToolResult:
        """Extract important keywords and named entities from the text."""
        try:
            text, source = await self._resolve_text(validated, user_id)
        except ValueError as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

        keywords = self._extract_keywords(text)
        stats = {
            "original_length": len(text),
            "keyword_count": len(keywords),
        }

        persist_info = await self._persist_summary(
            validated,
            user_id,
            ", ".join(keywords),
            "keywords",
            stats,
        )

        return ToolResult.success_result(
            tool_id=self.tool_id,
            result={
                "action": "keywords",
                "key": validated.key,
                "namespace": validated.namespace,
                "source": source,
                "keywords": keywords,
                **persist_info,
                **stats,
            },
        )

    # ── retrieve ─────────────────────────────────────────────────

    async def _retrieve(
        self,
        validated: MemorySummarizationInput,
        user_id: int | None,
    ) -> ToolResult:
        """Read a previously stored summary."""
        key = validated.key
        namespace = validated.namespace

        # Try Redis
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
                            "summary": value,
                            "source": "redis",
                        },
                    )
            except Exception as e:
                logger.warning("Redis retrieve failed: %s", e)

        # Fall back to PostgreSQL
        try:
            async with AsyncSessionLocal() as session:
                stmt = (
                    select(AgentMemory)
                    .where(
                        AgentMemory.agent_id == self._agent_id(key, namespace),
                        AgentMemory.user_id == (user_id or 0),
                        AgentMemory.content_type == "memory_summary",
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
                            f"No summary found for key='{key}' "
                            f"in namespace='{namespace}'"
                        ),
                    )

                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "retrieve",
                        "key": key,
                        "namespace": namespace,
                        "summary": row.content,
                        "source": "postgresql",
                        "id": row.id,
                        "metadata": row.metadata_json,
                        "created_at": (
                            row.created_at.isoformat() if row.created_at else None
                        ),
                    },
                )
        except Exception as e:
            logger.exception("PostgreSQL retrieve failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))

    # ── delete ───────────────────────────────────────────────────

    async def _delete(
        self,
        validated: MemorySummarizationInput,
        user_id: int | None,
    ) -> ToolResult:
        """Remove a stored summary."""
        key = validated.key
        namespace = validated.namespace
        deleted_pg = False
        deleted_redis = False

        # PostgreSQL
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(AgentMemory).where(
                    AgentMemory.agent_id == self._agent_id(key, namespace),
                    AgentMemory.user_id == (user_id or 0),
                    AgentMemory.content_type == "memory_summary",
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                for row in rows:
                    await session.delete(row)
                if rows:
                    await session.commit()
                    deleted_pg = True
                    logger.info(
                        "Deleted %d memory summary entries: key=%s namespace=%s",
                        len(rows),
                        key,
                        namespace,
                    )
        except Exception as e:
            logger.error("PostgreSQL delete failed: %s", e)

        # Redis
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

    # ── summarization engines ────────────────────────────────────

    @staticmethod
    def _extractive_summary(text: str, max_sentences: int = 5) -> str:
        """Extractive summarization: keep the most information-dense sentences."""
        if not text:
            return ""

        sentences = re.split(r"(?<=[.!?])\s+", text)
        if len(sentences) <= max_sentences:
            return text

        # Score sentences by information density:
        #   - Length (longer = more info, but penalize very long)
        #   - Presence of key phrases
        #   - Position (first sentences are usually more important)
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
            "goal",
            "result",
            "finding",
            "recommend",
            "next step",
        ]

        scored = []
        for i, s in enumerate(sentences):
            words = s.split()
            if not words:
                scored.append((i, s, -1))
                continue

            # Length score: reward medium-length sentences, penalize very short/long
            length = len(words)
            if length < 5:
                length_score = 0.2
            elif length < 50:
                length_score = 0.6 + (length / 100)
            else:
                length_score = 1.0 - min((length - 50) / 100, 0.5)

            # Keyword score
            s_lower = s.lower()
            kw_score = sum(0.3 for kw in key_phrases if kw in s_lower)

            # Position score: first sentences weighted higher
            pos_score = 1.0 - (i / len(sentences)) * 0.5

            scored.append((i, s, length_score + kw_score + pos_score))

        # Select top-scoring sentences, preserve original order
        scored.sort(key=lambda x: x[2], reverse=True)
        selected = scored[:max_sentences]
        selected.sort(key=lambda x: x[0])  # restore original order

        return " ".join(s[1] for s in selected)

    @staticmethod
    def _extract_keywords(text: str, max_keywords: int = 15) -> list[str]:
        """Extract important keywords using frequency + stopword filtering."""
        if not text:
            return []

        # Common stopwords to filter out
        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "can",
            "shall",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "out",
            "off",
            "over",
            "under",
            "again",
            "further",
            "then",
            "once",
            "here",
            "there",
            "when",
            "where",
            "why",
            "how",
            "all",
            "both",
            "each",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "no",
            "nor",
            "not",
            "only",
            "own",
            "same",
            "so",
            "than",
            "too",
            "very",
            "just",
            "because",
            "about",
            "up",
            "down",
            "this",
            "that",
            "these",
            "those",
            "it",
            "its",
            "and",
            "but",
            "or",
            "if",
            "while",
            "also",
            "we",
            "you",
            "he",
            "she",
            "they",
            "me",
            "him",
            "her",
            "us",
            "their",
            "our",
        }

        # Tokenize and clean
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
        filtered = [w for w in words if w not in stopwords]

        # Frequency ranking
        freq = Counter(filtered)
        return [word for word, _ in freq.most_common(max_keywords)]


# ── Register ──────────────────────────────────────────────────────────

register_tool(MemorySummarizationTool())
