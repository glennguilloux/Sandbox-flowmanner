"""Migrate existing Redis memories into the Postgres memory_entries table.

Usage:
    cd /opt/flowmanner/backend
    python -m scripts.migrate_redis_memories          # dry-run (default)
    python -m scripts.migrate_redis_memories --apply   # actually migrate

This is a ONE-TIME migration script. It:
1. Scans Redis for all memory:mem:* keys (agent memories)
2. Scans Redis for all memory:* keys (simple KV memories)
3. Inserts each into the Postgres memory_entries table
4. Reports counts (skipped if already exists in Postgres)
"""

import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime, timezone
from uuid import uuid4

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MEMORY_KEY_PREFIX = "memory:"
MEMORY_INDEX_PREFIX = "memory_index:"


async def run(apply: bool = False):
    from app.config import settings

    # ── 1. Connect to Redis ──────────────────────────────────────────
    try:
        from redis.asyncio import Redis

        redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        await redis.ping()
        logger.info("Connected to Redis at %s", settings.REDIS_URL)
    except Exception as e:
        logger.error("Cannot connect to Redis: %s", e)
        return

    # ── 2. Connect to Postgres ───────────────────────────────────────
    from sqlalchemy import text as sa_text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(settings.DATABASE_URL, echo=False)

    async with engine.begin() as conn:
        exists = await conn.execute(
            sa_text(
                "SELECT 1 FROM information_schema.tables WHERE table_name = 'memory_entries'"
            )
        )
        if not exists.fetchone():
            logger.error("memory_entries table does not exist. Run migration first.")
            await engine.dispose()
            await redis.aclose()
            return

    # ── 3. Scan Redis for agent memories (memory:mem:*) ──────────────
    agent_memories = []
    cursor = 0
    while True:
        cursor, keys = await redis.scan(
            cursor=cursor, match=f"{MEMORY_KEY_PREFIX}mem:*", count=100
        )
        for key in keys:
            raw = await redis.get(key)
            if raw:
                try:
                    mem = json.loads(raw)
                    agent_memories.append(mem)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed key %s", key)
        if cursor == 0:
            break

    logger.info("Found %d agent memories in Redis", len(agent_memories))

    # ── 4. Scan Redis for simple KV memories (memory:*, not memory:mem:*) ──
    kv_memories = []
    cursor = 0
    while True:
        cursor, keys = await redis.scan(
            cursor=cursor, match=f"{MEMORY_KEY_PREFIX}*", count=100
        )
        for key in keys:
            # Skip agent memories and index keys
            if ":mem:" in key or key.startswith(MEMORY_INDEX_PREFIX):
                continue
            raw = await redis.get(key)
            if raw:
                try:
                    value = json.loads(raw)
                except json.JSONDecodeError:
                    value = raw
                # Extract the key name after the prefix
                kv_key = key[len(MEMORY_KEY_PREFIX) :]
                kv_memories.append({"key": kv_key, "value": value})
        if cursor == 0:
            break

    logger.info("Found %d simple KV memories in Redis", len(kv_memories))

    total = len(agent_memories) + len(kv_memories)
    if total == 0:
        logger.info("No memories found in Redis. Nothing to migrate.")
        await engine.dispose()
        await redis.aclose()
        return

    if not apply:
        logger.info(
            "DRY RUN: Would migrate %d agent memories + %d KV memories = %d total. Run with --apply to execute.",
            len(agent_memories),
            len(kv_memories),
            total,
        )
        await engine.dispose()
        await redis.aclose()
        return

    # ── 5. Insert into Postgres ──────────────────────────────────────
    now = datetime.now(UTC).isoformat()
    migrated = 0
    skipped = 0
    errors = 0

    async with engine.begin() as conn:
        # Migrate agent memories
        for mem in agent_memories:
            mem_id = mem.get("id", str(uuid4()))
            # Check if already exists
            existing = await conn.execute(
                sa_text("SELECT 1 FROM memory_entries WHERE id = :id"),
                {"id": mem_id},
            )
            if existing.fetchone():
                skipped += 1
                continue

            try:
                await conn.execute(
                    sa_text(
                        """
                        INSERT INTO memory_entries (
                            id, agent_id, namespace, memory_type, content,
                            importance, metadata, created_at, updated_at
                        ) VALUES (
                            :id, :agent_id, 'agent', :memory_type, :content,
                            :importance, :metadata::jsonb, :created_at, :updated_at
                        )
                    """
                    ),
                    {
                        "id": mem_id,
                        "agent_id": mem.get("agent_id", ""),
                        "memory_type": mem.get("memory_type", "episodic"),
                        "content": mem.get("content", ""),
                        "importance": mem.get("importance", 0.5),
                        "metadata": json.dumps(mem.get("metadata", {}), default=str),
                        "created_at": mem.get("created_at", now),
                        "updated_at": now,
                    },
                )
                migrated += 1
            except Exception as e:
                logger.warning("Failed to migrate agent memory %s: %s", mem_id, e)
                errors += 1

        # Migrate simple KV memories
        for kv in kv_memories:
            kv_key = kv["key"]
            value = kv["value"]

            # Check if already exists
            existing = await conn.execute(
                sa_text(
                    "SELECT 1 FROM memory_entries WHERE namespace = 'kv' AND key = :key"
                ),
                {"key": kv_key},
            )
            if existing.fetchone():
                skipped += 1
                continue

            try:
                content = (
                    json.dumps(value, default=str)
                    if not isinstance(value, str)
                    else value
                )
                await conn.execute(
                    sa_text(
                        """
                        INSERT INTO memory_entries (
                            id, namespace, key, memory_type, content,
                            importance, created_at, updated_at
                        ) VALUES (
                            :id, 'kv', :key, 'kv', :content,
                            1.0, :created_at, :updated_at
                        )
                    """
                    ),
                    {
                        "id": str(uuid4()),
                        "key": kv_key,
                        "content": content,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
                migrated += 1
            except Exception as e:
                logger.warning("Failed to migrate KV memory %s: %s", kv_key, e)
                errors += 1

    await engine.dispose()
    await redis.aclose()

    logger.info(
        "Migration complete: %d migrated, %d skipped (already exist), %d errors",
        migrated,
        skipped,
        errors,
    )


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    asyncio.run(run(apply=apply))
