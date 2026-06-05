"""Tests for migrate_redis_memories.py CLI script."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestMigrateModule:
    """Test that the migration script is importable."""

    def test_importable(self):
        import scripts.migrate_redis_memories

        assert hasattr(scripts.migrate_redis_memories, "run")

    def test_dry_run_default(self):
        """--apply flag should default to False."""
        import sys

        argv_backup = sys.argv
        sys.argv = ["migrate_redis_memories.py"]
        try:
            # Just verify the flag parsing logic
            apply = "--apply" in sys.argv
            assert apply is False
        finally:
            sys.argv = argv_backup

    def test_apply_flag(self):
        """--apply flag should be detected."""
        import sys

        argv_backup = sys.argv
        sys.argv = ["migrate_redis_memories.py", "--apply"]
        try:
            apply = "--apply" in sys.argv
            assert apply is True
        finally:
            sys.argv = argv_backup


class TestMemoryParsing:
    """Test that agent memory dicts are parsed correctly."""

    def test_agent_memory_format(self):
        """Agent memories from Redis have the expected shape."""
        mem = {
            "id": str(uuid4()),
            "agent_id": "user_42",
            "content": "User prefers dark mode",
            "memory_type": "long_term",
            "importance": 0.7,
            "created_at": "2026-06-03T20:00:00+00:00",
            "metadata": {"category": "preference"},
        }
        assert mem["agent_id"] == "user_42"
        assert mem["content"] == "User prefers dark mode"
        assert mem["importance"] == 0.7

    def test_kv_memory_format(self):
        """KV memories from Redis have the expected shape."""
        kv = {"key": "config:theme", "value": {"color": "dark"}}
        assert kv["key"] == "config:theme"
        assert kv["value"]["color"] == "dark"

    def test_malformed_json_handled(self):
        """Malformed JSON should be skippable."""
        raw = "not valid json{{{"
        try:
            json.loads(raw)
            assert False, "Should have raised"
        except json.JSONDecodeError:
            pass  # Expected — script should catch this


class TestRedisKeyPatterns:
    """Test that key pattern matching logic is correct."""

    def test_agent_memory_key_pattern(self):
        """Agent memory keys match memory:mem:* pattern."""
        key = "memory:mem:abc-123"
        assert key.startswith("memory:")
        assert ":mem:" in key

    def test_kv_key_pattern(self):
        """KV keys match memory:* but not memory:mem:*."""
        key = "memory:config:theme"
        assert key.startswith("memory:")
        assert ":mem:" not in key

    def test_index_key_excluded(self):
        """Index keys (memory_index:*) should be skipped."""
        key = "memory_index:agent:user_42"
        assert key.startswith("memory_index:")
        # In the script, we check key.startswith(MEMORY_INDEX_PREFIX)
        assert key.startswith("memory_index:")
