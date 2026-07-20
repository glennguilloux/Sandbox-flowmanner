"""Tests for the CACHE_GET node handler (read-through Redis lookup).

Mirrors the T2-03 / T3-* substrate node-handler test pattern: instantiate a
``WorkflowNode`` of the new type and assert ``NodeExecutor._handle_cache_get``
returns the correct HIT/MISS shape. Redis is mocked at the shared client
seam (``app.tools.redis_cache.get_redis``) so no live Redis is required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.substrate.node_executor import NodeExecutor
from app.services.substrate.workflow_models import NodeType, WorkflowNode


def _executor() -> NodeExecutor:
    # NodeExecutor requires a UnifiedExecutor ref but _handle_cache_get does
    # not touch it, so a stub is sufficient for the unit test.
    return NodeExecutor(MagicMock())


def _make_cache_node(config: dict | None = None, assigned_model: str | None = None) -> WorkflowNode:
    return WorkflowNode(
        id="cache1",
        type=NodeType.CACHE_GET,
        title="Cache Get",
        config=config or {},
        assigned_model=assigned_model,
    )


async def test_cache_get_hit_with_derived_key():
    """A cached JSON value returns hit=True with the parsed value."""
    node = _make_cache_node(
        config={"modelId": "llamacpp/qwen", "prompt": "hello", "params": {"k": "v"}},
    )
    fake_redis = MagicMock()
    fake_redis.get = AsyncMock(return_value='{"answer": 42}')

    with patch("app.tools.redis_cache.get_redis", return_value=fake_redis):
        out = await _executor()._handle_cache_get(node, {}, None)

    assert out["success"] is True
    assert out["output"]["hit"] is True
    assert out["output"]["value"] == {"answer": 42}
    # Derived key is a sha256 hex digest namespaced under cache_get:.
    assert out["output"]["key"].startswith("cache_get:")
    assert len(out["output"]["key"]) == len("cache_get:") + 64
    # Redis.get was called with the derived key.
    fake_redis.get.assert_awaited_once_with(out["output"]["key"])
    # Deterministic: same inputs -> same key.
    node2 = _make_cache_node(
        config={"modelId": "llamacpp/qwen", "prompt": "hello", "params": {"k": "v"}},
    )
    with patch("app.tools.redis_cache.get_redis", return_value=fake_redis):
        out2 = await _executor()._handle_cache_get(node2, {}, None)
    assert out2["output"]["key"] == out["output"]["key"]


async def test_cache_get_miss_when_key_absent():
    """A None Redis response is a graceful MISS (never a failure)."""
    node = _make_cache_node(
        config={"modelId": "m", "prompt": "p", "params": {}},
    )
    fake_redis = MagicMock()
    fake_redis.get = AsyncMock(return_value=None)

    with patch("app.tools.redis_cache.get_redis", return_value=fake_redis):
        out = await _executor()._handle_cache_get(node, {}, None)

    assert out["success"] is True
    assert out["output"]["hit"] is False
    assert out["output"]["value"] is None
    assert out["output"]["key"].startswith("cache_get:")


async def test_cache_get_explicit_key_short_circuits_derivation():
    """An explicit `key` config is used verbatim and not hashed."""
    node = _make_cache_node(config={"key": "my-explicit-key"})
    fake_redis = MagicMock()
    fake_redis.get = AsyncMock(return_value="raw-string-value")

    with patch("app.tools.redis_cache.get_redis", return_value=fake_redis):
        out = await _executor()._handle_cache_get(node, {}, None)

    assert out["success"] is True
    assert out["output"]["hit"] is True
    # Non-JSON value falls back to the raw string.
    assert out["output"]["value"] == "raw-string-value"
    assert out["output"]["key"] == "my-explicit-key"
    fake_redis.get.assert_awaited_once_with("my-explicit-key")


async def test_cache_get_miss_when_redis_unavailable():
    """Redis client returning None (unprovisioned) yields a graceful MISS."""
    node = _make_cache_node(config={"key": "k"})

    with patch("app.tools.redis_cache.get_redis", return_value=None):
        out = await _executor()._handle_cache_get(node, {}, None)

    assert out["success"] is True
    assert out["output"]["hit"] is False
    assert out["output"]["value"] is None


async def test_cache_get_miss_on_redis_get_error():
    """A Redis GET exception is swallowed into a MISS, not a failure."""
    node = _make_cache_node(config={"key": "k"})
    fake_redis = MagicMock()
    fake_redis.get = AsyncMock(side_effect=RuntimeError("connection reset"))

    with patch("app.tools.redis_cache.get_redis", return_value=fake_redis):
        out = await _executor()._handle_cache_get(node, {}, None)

    assert out["success"] is True
    assert out["output"]["hit"] is False
    assert out["output"]["value"] is None


def test_cache_get_enum_member_exists():
    """The new enum member is wired so adapters/dispatch can reference it."""
    assert NodeType.CACHE_GET == "cache_get"


async def test_dispatch_routes_cache_get_to_handler():
    """_dispatch forwards CACHE_GET to _handle_cache_get with a MISS."""
    node = _make_cache_node(config={"key": "dispatch-key"})
    fake_redis = MagicMock()
    fake_redis.get = AsyncMock(return_value=None)

    executor = _executor()
    with patch("app.tools.redis_cache.get_redis", return_value=fake_redis):
        out = await executor._dispatch(
            db=None,
            node=node,
            context={},
            budget=None,
            run_id="run-1",
            workflow=None,
        )

    assert out["success"] is True
    assert out["output"]["hit"] is False
    assert out["output"]["key"] == "dispatch-key"
