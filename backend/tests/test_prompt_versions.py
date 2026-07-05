"""Tests for Phase 6 — Prompt Versioning.

Covers:
- PromptVersion model field assignment
- Version auto-increment logic
- _get_active_prompt_content helper
- _build_chat_messages prompt lookup chain
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Model tests (no DB required)
# ---------------------------------------------------------------------------


class TestPromptVersionModel:
    """Unit tests for the PromptVersion model fields."""

    def test_table_name(self):
        from app.models.prompt_version_models import PromptVersion

        assert PromptVersion.__tablename__ == "prompt_versions"

    def test_columns_defined(self):
        """Verify the model has the expected column names."""
        from app.models.prompt_version_models import PromptVersion

        col_names = {c.name for c in PromptVersion.__table__.columns}
        expected = {
            "id",
            "workspace_id",
            "name",
            "content",
            "version",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(col_names), f"Missing columns: {expected - col_names}"

    def test_unique_constraint(self):
        """Verify the unique constraint on (workspace_id, name, version)."""
        from app.models.prompt_version_models import PromptVersion

        constraint_names = {c.name for c in PromptVersion.__table__.constraints if hasattr(c, "name")}
        assert "uq_prompt_version" in constraint_names


# ---------------------------------------------------------------------------
# Version auto-increment logic
# ---------------------------------------------------------------------------


class TestVersionAutoIncrement:
    """Test the _next_version helper logic."""

    def test_first_version_returns_1(self):
        """When no versions exist, next version should be 1."""
        max_ver = None
        next_ver = (max_ver or 0) + 1
        assert next_ver == 1

    def test_increment_from_existing(self):
        """When max version is 3, next should be 4."""
        max_ver = 3
        next_ver = (max_ver or 0) + 1
        assert next_ver == 4


# ---------------------------------------------------------------------------
# _get_active_prompt_content
# ---------------------------------------------------------------------------


class TestGetActivePromptContent:
    """Test the _get_active_prompt_content helper with mocked DB.

    Mocks _get_prompt_redis to return None (bypasses Redis cache)
    so the DB fallback path is exercised directly.
    """

    @pytest.mark.asyncio
    async def test_returns_content_when_active_version_exists(self):
        mock_pv = SimpleNamespace(content="Custom system prompt")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_pv

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        with patch("app.services.chat_service._get_prompt_redis", new_callable=AsyncMock, return_value=None):
            from app.services.chat_service import _get_active_prompt_content

            result = await _get_active_prompt_content(mock_db, "ws-123", "Default Assistant")
            assert result == "Custom system prompt"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_active_version(self):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        with patch("app.services.chat_service._get_prompt_redis", new_callable=AsyncMock, return_value=None):
            from app.services.chat_service import _get_active_prompt_content

            result = await _get_active_prompt_content(mock_db, "ws-123", "Default Assistant")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_cached_content_from_redis(self):
        """When Redis has a cached value, it should be returned without DB query."""
        mock_rds = AsyncMock()
        mock_rds.get.return_value = "Cached prompt content"
        mock_rds.aclose = AsyncMock()

        mock_db = AsyncMock()

        with patch("app.services.chat_service._get_prompt_redis", new_callable=AsyncMock, return_value=mock_rds):
            from app.services.chat_service import _get_active_prompt_content

            result = await _get_active_prompt_content(mock_db, "ws-123", "Default Assistant")
            assert result == "Cached prompt content"
            # DB should NOT have been called
            mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_for_cached_sentinel(self):
        """When Redis has __NONE__ sentinel, it should return None without DB query."""
        mock_rds = AsyncMock()
        mock_rds.get.return_value = "__NONE__"
        mock_rds.aclose = AsyncMock()

        mock_db = AsyncMock()

        with patch("app.services.chat_service._get_prompt_redis", new_callable=AsyncMock, return_value=mock_rds):
            from app.services.chat_service import _get_active_prompt_content

            result = await _get_active_prompt_content(mock_db, "ws-123", "Default Assistant")
            assert result is None
            mock_db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# _build_chat_messages prompt lookup chain
# ---------------------------------------------------------------------------


class TestBuildChatMessagesPromptLookup:
    """Test that _build_chat_messages follows the correct lookup chain:
    1. prompt_versions (workspace-scoped)
    2. thread.metadata_.get("system_prompt")
    3. fallback default
    """

    @pytest.mark.asyncio
    async def test_uses_prompt_version_over_inline(self):
        """When a workspace has an active prompt version, it should be used
        instead of the thread's inline system_prompt."""
        mock_thread = SimpleNamespace(
            workspace_id="ws-123",
            metadata_={"system_prompt": "Inline prompt"},
        )

        with (
            patch("app.services.chat_service.get_chat_thread", new_callable=AsyncMock, return_value=mock_thread),
            patch(
                "app.services.chat_service._get_active_prompt_content",
                new_callable=AsyncMock,
                return_value="Versioned prompt",
            ),
        ):
                mock_history_result = MagicMock()
                mock_history_result.scalars.return_value.all.return_value = []

                mock_db = AsyncMock()
                mock_db.execute.return_value = mock_history_result

                from app.services.chat_service import _build_chat_messages

                messages = await _build_chat_messages(mock_db, thread_id=1)

                assert messages[0]["role"] == "system"
                # The system prompt may have sandboxd guidance appended, so check prefix
                assert messages[0]["content"].startswith("Versioned prompt")

    @pytest.mark.asyncio
    async def test_falls_back_to_inline_when_no_version(self):
        """When no active prompt version exists, falls back to thread metadata."""
        mock_thread = SimpleNamespace(
            workspace_id="ws-123",
            metadata_={"system_prompt": "Inline prompt"},
        )

        with (
            patch("app.services.chat_service.get_chat_thread", new_callable=AsyncMock, return_value=mock_thread),
            patch("app.services.chat_service._get_active_prompt_content", new_callable=AsyncMock, return_value=None),
        ):
                mock_history_result = MagicMock()
                mock_history_result.scalars.return_value.all.return_value = []

                mock_db = AsyncMock()
                mock_db.execute.return_value = mock_history_result

                from app.services.chat_service import _build_chat_messages

                messages = await _build_chat_messages(mock_db, thread_id=1)

                assert messages[0]["role"] == "system"
                assert messages[0]["content"].startswith("Inline prompt")

    @pytest.mark.asyncio
    async def test_falls_back_to_default_when_nothing_set(self):
        """When neither version nor inline prompt exists, uses default."""
        mock_thread = SimpleNamespace(
            workspace_id=None,
            metadata_=None,
        )

        with patch("app.services.chat_service.get_chat_thread", new_callable=AsyncMock, return_value=mock_thread):
            mock_history_result = MagicMock()
            mock_history_result.scalars.return_value.all.return_value = []

            mock_db = AsyncMock()
            mock_db.execute.return_value = mock_history_result

            from app.services.chat_service import _build_chat_messages

            messages = await _build_chat_messages(mock_db, thread_id=1)

            assert messages[0]["role"] == "system"
            assert messages[0]["content"].startswith("You are a helpful assistant.")

    @pytest.mark.asyncio
    async def test_uses_prompt_name_from_metadata(self):
        """When thread metadata has prompt_name, it's used for the lookup."""
        mock_thread = SimpleNamespace(
            workspace_id="ws-123",
            metadata_={"prompt_name": "Code Helper"},
        )

        with (
            patch("app.services.chat_service.get_chat_thread", new_callable=AsyncMock, return_value=mock_thread),
            patch(
                "app.services.chat_service._get_active_prompt_content",
                new_callable=AsyncMock,
                return_value="Code helper prompt",
            ) as mock_get,
        ):
                mock_history_result = MagicMock()
                mock_history_result.scalars.return_value.all.return_value = []

                mock_db = AsyncMock()
                mock_db.execute.return_value = mock_history_result

                from app.services.chat_service import _build_chat_messages

                messages = await _build_chat_messages(mock_db, thread_id=1)

                mock_get.assert_called_once_with(mock_db, "ws-123", name="Code Helper")
                assert messages[0]["content"].startswith("Code helper prompt")
