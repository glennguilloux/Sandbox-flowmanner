"""Memory Service — Postgres-first durable store with optional Redis cache.

Source of truth: Postgres ``memory_entries`` table.
Redis: optional read-through cache for hot entries.  Redis outage means
slower reads, NOT memory loss.

Two public interfaces are preserved for backward compatibility:

1. **Simple KV** — ``store(key, value)`` / ``retrieve(key)``
   Stores under ``namespace="kv"``, uses the ``key`` column.

2. **Agent memory** — ``store(agent_id=…, content=…, …)`` / ``retrieve_by_query(…)``
   Stores under ``namespace="agent"``, indexes by agent_id + memory_type.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

MEMORY_KEY_PREFIX = "memory:"
MEMORY_INDEX_PREFIX = "memory_index:"


class MemoryService:
    """Postgres-first memory store with optional Redis cache layer.

    Parameters
    ----------
    db : AsyncSession | None
        Legacy positional arg kept for backward compat with callers that
        pass a session directly (e.g. ``MemoryService(self.db)``).
        When provided, the service uses this session for writes.
        When *not* provided, the service creates short-lived sessions
        from ``AsyncSessionLocal`` for each operation.
    """

    def __init__(self, db=None):
        self._db = db  # optional pre-existing session (legacy compat)
        self._redis = None  # lazy-init

    # ── Redis helpers (optional cache layer) ──────────────────────────

    async def _get_redis(self):
        """Lazy-init Redis client. Returns None if Redis is unavailable."""
        if self._redis is not None:
            return self._redis
        try:
            from redis.asyncio import Redis

            from app.config import settings

            client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
            await client.ping()
            self._redis = client
            return self._redis
        except Exception as e:
            logger.debug("Redis unavailable (cache disabled): %s", e)
            self._redis = None
            return None

    async def _cache_set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """Best-effort cache write. Never raises."""
        try:
            redis = await self._get_redis()
            if redis is not None:
                await redis.set(key, json.dumps(value, default=str), ex=ttl)
        except Exception:
            pass

    async def _cache_get(self, key: str) -> Any:
        """Best-effort cache read. Returns sentinel on miss."""
        try:
            redis = await self._get_redis()
            if redis is not None:
                raw = await redis.get(key)
                if raw is not None:
                    return json.loads(raw)
        except Exception:
            pass
        return _MISSING

    async def _cache_delete(self, key: str) -> None:
        """Best-effort cache invalidation."""
        try:
            redis = await self._get_redis()
            if redis is not None:
                await redis.delete(key)
        except Exception:
            pass

    # ── DB session management ─────────────────────────────────────────

    async def _get_session(self):
        """Return (session, owns_session: bool).

        If a session was injected at __init__, reuse it (caller owns txn).
        Otherwise create a short-lived session from the async factory.
        """
        if self._db is not None:
            return self._db, False
        from app.database import AsyncSessionLocal

        session = AsyncSessionLocal()
        return session, True

    # ── Public store interface ────────────────────────────────────────

    async def store(
        self,
        key: str = "",
        value: Any = None,
        *,
        agent_id: str = "",
        content: str = "",
        memory_type: str = "episodic",
        importance: float = 0.5,
        metadata: dict | None = None,
        tags: list[str] | None = None,
        user_id: int | None = None,
    ) -> bool | dict | None:
        """Store data. Supports two signatures (backward compatible):

        Simple KV:  ``store(key, value)``           → True/False
        Agent mem:  ``store(agent_id=…, content=…)`` → dict or None
        """
        if agent_id and content:
            return await self._store_memory(
                agent_id,
                content,
                memory_type,
                importance,
                metadata,
                tags=tags,
                user_id=user_id,
            )
        if key:
            return await self._store_simple(key, value)
        logger.warning("MemoryService.store called without key or agent_id+content")
        return False

    async def _store_simple(self, key: str, value: Any) -> bool:
        """Store a simple key-value pair in Postgres."""
        session, owns = await self._get_session()
        try:
            from sqlalchemy import delete as sa_delete

            from app.models.memory_models import MemoryEntry

            # Upsert: delete existing entry for this key before inserting
            await session.execute(
                sa_delete(MemoryEntry).where(
                    MemoryEntry.namespace == "kv",
                    MemoryEntry.key == key,
                )
            )

            content = json.dumps(value, default=str)
            entry = MemoryEntry(
                namespace="kv",
                key=key,
                content=content,
                memory_type="kv",
                importance=1.0,
            )
            session.add(entry)
            if owns:
                await session.commit()
            else:
                await session.flush()

            await self._cache_set(f"{MEMORY_KEY_PREFIX}kv:{key}", value)
            return True
        except Exception as e:
            logger.warning("Memory store failed for key %s: %s", key, e)
            if owns:
                await session.rollback()
            return False
        finally:
            if owns:
                await session.close()

    async def retrieve(self, key: str) -> Any:
        """Retrieve a value by key (simple KV). Returns None if not found."""
        cache_key = f"{MEMORY_KEY_PREFIX}kv:{key}"

        # 1. Try cache
        cached = await self._cache_get(cache_key)
        if cached is not _MISSING:
            return cached

        # 2. Postgres (canonical)
        session, owns = await self._get_session()
        try:
            from sqlalchemy import select

            from app.models.memory_models import MemoryEntry

            result = await session.execute(
                select(MemoryEntry).where(
                    MemoryEntry.namespace == "kv",
                    MemoryEntry.key == key,
                )
            )
            entry = result.scalar_one_or_none()
            if entry is None:
                return None

            value = json.loads(entry.content)
            # 3. Warm cache
            await self._cache_set(cache_key, value)
            return value
        except Exception as e:
            logger.warning("Memory retrieve failed for key %s: %s", key, e)
            return None
        finally:
            if owns:
                await session.close()

    # ── Agent memory implementation ───────────────────────────────────

    async def _store_memory(
        self,
        agent_id: str,
        content: str,
        memory_type: str = "episodic",
        importance: float = 0.5,
        metadata: dict | None = None,
        tags: list[str] | None = None,
        user_id: int | None = None,
    ) -> dict | None:
        """Store an agent memory entry in Postgres. Optionally mirror to Redis."""
        memory_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        meta = dict(metadata or {})
        if tags:
            meta["tags"] = tags

        memory_dict = {
            "id": memory_id,
            "agent_id": agent_id,
            "content": content,
            "memory_type": memory_type,
            "importance": importance,
            "created_at": now.isoformat(),
            "metadata": meta,
        }

        # 1. Write to Postgres (canonical)
        session, owns = await self._get_session()
        try:
            from app.models.memory_models import MemoryEntry

            entry = MemoryEntry(
                id=memory_id,
                user_id=user_id,
                agent_id=agent_id,
                namespace="agent",
                memory_type=memory_type,
                content=content,
                importance=importance,
                meta=meta,
            )
            session.add(entry)
            if owns:
                await session.commit()
            else:
                await session.flush()
        except Exception as e:
            logger.warning("Postgres memory store failed for agent %s: %s", agent_id, e)
            if owns:
                await session.rollback()
            return None
        finally:
            if owns:
                await session.close()

        # 2. Best-effort mirror to Redis cache
        await self._cache_set(
            f"{MEMORY_KEY_PREFIX}mem:{memory_id}",
            memory_dict,
            ttl=86400,
        )

        logger.info("Stored memory %s for agent %s", memory_id, agent_id)
        return memory_dict

    async def retrieve_by_query(
        self,
        agent_id: str,
        query: str = "",
        limit: int = 5,
        min_importance: float = 0.0,
    ) -> list[dict]:
        """Retrieve memories for an agent, optionally filtered by query.

        Reads from Postgres (canonical). Uses simple keyword matching.
        """
        session, owns = await self._get_session()
        try:
            from sqlalchemy import select

            from app.models.memory_models import MemoryEntry

            stmt = (
                select(MemoryEntry)
                .where(
                    MemoryEntry.namespace == "agent",
                    MemoryEntry.agent_id == agent_id,
                    MemoryEntry.importance >= min_importance,
                )
                .order_by(MemoryEntry.importance.desc(), MemoryEntry.created_at.desc())
                .limit(limit * 3)  # extra for post-filtering
            )
            result = await session.execute(stmt)
            entries = result.scalars().all()

            memories = []
            for entry in entries:
                mem = {
                    "id": str(entry.id),
                    "agent_id": entry.agent_id,
                    "content": entry.content,
                    "memory_type": entry.memory_type,
                    "importance": entry.importance,
                    "created_at": (
                        entry.created_at.isoformat() if entry.created_at else ""
                    ),
                    "metadata": entry.meta or {},
                }
                memories.append(mem)

            # Keyword filter
            if query:
                query_lower = query.lower()
                scored: list[tuple[int, dict]] = []
                for m in memories:
                    score = sum(
                        1
                        for word in query_lower.split()
                        if len(word) > 2 and word in m.get("content", "").lower()
                    )
                    if score > 0:
                        scored.append((score, m))
                scored.sort(
                    key=lambda x: (x[1].get("importance", 0), x[0]), reverse=True
                )
                memories = [m for _, m in scored]

            return memories[:limit]
        except Exception as e:
            logger.warning(
                "Memory retrieve_by_query failed for agent %s: %s", agent_id, e
            )
            return []
        finally:
            if owns:
                await session.close()

    async def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory by ID from Postgres and invalidate cache."""
        session, owns = await self._get_session()
        try:
            from sqlalchemy import delete as sa_delete

            from app.models.memory_models import MemoryEntry

            result = await session.execute(
                sa_delete(MemoryEntry).where(MemoryEntry.id == memory_id)
            )
            if owns:
                await session.commit()

            deleted = result.rowcount > 0

            # Invalidate cache
            await self._cache_delete(f"{MEMORY_KEY_PREFIX}mem:{memory_id}")

            if deleted:
                logger.info("Deleted memory %s", memory_id)
            return deleted
        except Exception as e:
            logger.warning("Memory delete failed for %s: %s", memory_id, e)
            if owns:
                await session.rollback()
            return False
        finally:
            if owns:
                await session.close()


# Sentinel for cache miss
_MISSING = object()


# ── Singleton ──────────────────────────────────────────────────────

_memory_service_instance: MemoryService | None = None


def get_memory_service() -> MemoryService:
    """Get or create the global MemoryService singleton."""
    global _memory_service_instance
    if _memory_service_instance is None:
        _memory_service_instance = MemoryService()
    return _memory_service_instance
