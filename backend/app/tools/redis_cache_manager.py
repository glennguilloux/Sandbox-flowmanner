"""
Database Querying & Storage Tools — Redis Cache Manager.

redis_cache_manager → Get, set, and expire key-value pairs in a Redis instance.
"""

from __future__ import annotations

import json
import logging
import os

import redis.asyncio as redis_asyncio
from pydantic import Field

from app.tools.base import BaseTool, ToolInput, ToolMetadata, ToolResult, register_tool

logger = logging.getLogger(__name__)

_redis: redis_asyncio.Redis | None = None
_redis_available: bool | None = None


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
            logger.warning("Redis unavailable for cache manager")
            _redis_available = False
            return None
    return _redis


class RedisCacheManagerInput(ToolInput):
    action: str = Field(
        ...,
        description="Action: 'get', 'set', 'delete', 'exists', 'expire', 'ttl', 'keys', 'incr', 'hget', 'hset', 'hgetall'",
    )
    key: str | None = Field(None, description="Redis key")
    value: str | None = Field(None, description="Value to set (string or JSON)")
    ttl: int | None = Field(None, ge=0, description="Time-to-live in seconds (0 = no expiry)")
    field: str | None = Field(None, description="Hash field name (for hget/hset)")
    pattern: str | None = Field(None, description="Key pattern for 'keys' action (e.g., 'cache:*')")


class RedisCacheManagerTool(BaseTool):
    def __init__(self):
        metadata = ToolMetadata(
            tool_id="redis_cache_manager",
            name="Redis Cache Manager",
            description="Get, set, and expire key-value pairs in a Redis instance",
            category="database",
            input_schema=RedisCacheManagerInput.schema_extra(),
            tags=["redis", "cache", "key-value", "database"],
            requires_auth=True,
        )
        super().__init__(metadata=metadata)

    async def execute(self, input_data: dict) -> ToolResult:
        try:
            validated = RedisCacheManagerInput(**input_data)
        except Exception as e:
            return ToolResult.error_result(tool_id=self.tool_id, error=f"Invalid input: {e}")

        r = _get_redis()
        if not r:
            return ToolResult.error_result(
                tool_id=self.tool_id,
                error="Redis is not available",
            )

        action = validated.action.lower().strip()

        try:
            if action == "get":
                if not validated.key:
                    return ToolResult.error_result(tool_id=self.tool_id, error="key is required")
                val = await r.get(validated.key)
                if val is None:
                    return ToolResult.success_result(
                        tool_id=self.tool_id,
                        result={
                            "action": "get",
                            "key": validated.key,
                            "value": None,
                            "found": False,
                        },
                    )
                # Try JSON parse
                try:
                    parsed = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    parsed = val
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "get",
                        "key": validated.key,
                        "value": parsed,
                        "found": True,
                    },
                )

            elif action == "set":
                if not validated.key or validated.value is None:
                    return ToolResult.error_result(tool_id=self.tool_id, error="key and value are required")
                if validated.ttl and validated.ttl > 0:
                    await r.setex(validated.key, validated.ttl, validated.value)
                else:
                    await r.set(validated.key, validated.value)
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "set",
                        "key": validated.key,
                        "ttl": validated.ttl,
                        "ok": True,
                    },
                )

            elif action == "delete":
                if not validated.key:
                    return ToolResult.error_result(tool_id=self.tool_id, error="key is required")
                count = await r.delete(validated.key)
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "delete",
                        "key": validated.key,
                        "deleted_count": count,
                    },
                )

            elif action == "exists":
                if not validated.key:
                    return ToolResult.error_result(tool_id=self.tool_id, error="key is required")
                exists = await r.exists(validated.key)
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "exists",
                        "key": validated.key,
                        "exists": bool(exists),
                    },
                )

            elif action == "expire":
                if not validated.key or not validated.ttl:
                    return ToolResult.error_result(tool_id=self.tool_id, error="key and ttl are required")
                ok = await r.expire(validated.key, validated.ttl)
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "expire",
                        "key": validated.key,
                        "ttl": validated.ttl,
                        "ok": bool(ok),
                    },
                )

            elif action == "ttl":
                if not validated.key:
                    return ToolResult.error_result(tool_id=self.tool_id, error="key is required")
                ttl = await r.ttl(validated.key)
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={"action": "ttl", "key": validated.key, "ttl_seconds": ttl},
                )

            elif action == "keys":
                pattern = validated.pattern or "*"
                keys = await r.keys(pattern)
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "keys",
                        "pattern": pattern,
                        "keys": keys,
                        "count": len(keys),
                    },
                )

            elif action == "incr":
                if not validated.key:
                    return ToolResult.error_result(tool_id=self.tool_id, error="key is required")
                new_val = await r.incr(validated.key)
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={"action": "incr", "key": validated.key, "value": new_val},
                )

            elif action == "hget":
                if not validated.key or not validated.field:
                    return ToolResult.error_result(tool_id=self.tool_id, error="key and field are required")
                val = await r.hget(validated.key, validated.field)
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "hget",
                        "key": validated.key,
                        "field": validated.field,
                        "value": val,
                    },
                )

            elif action == "hset":
                if not validated.key or not validated.field or validated.value is None:
                    return ToolResult.error_result(tool_id=self.tool_id, error="key, field, and value are required")
                await r.hset(validated.key, validated.field, validated.value)
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "hset",
                        "key": validated.key,
                        "field": validated.field,
                        "ok": True,
                    },
                )

            elif action == "hgetall":
                if not validated.key:
                    return ToolResult.error_result(tool_id=self.tool_id, error="key is required")
                data = await r.hgetall(validated.key)
                return ToolResult.success_result(
                    tool_id=self.tool_id,
                    result={
                        "action": "hgetall",
                        "key": validated.key,
                        "data": data,
                        "field_count": len(data),
                    },
                )

            else:
                return ToolResult.error_result(
                    tool_id=self.tool_id,
                    error=f"Unknown action: {action}. Use 'get', 'set', 'delete', 'exists', 'expire', 'ttl', 'keys', 'incr', 'hget', 'hset', or 'hgetall'.",
                )

        except Exception as e:
            logger.exception("redis_cache_manager failed")
            return ToolResult.error_result(tool_id=self.tool_id, error=str(e))


register_tool(RedisCacheManagerTool())
