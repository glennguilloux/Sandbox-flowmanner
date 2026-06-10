"""Unit tests for sandboxd system prompt injection in chat_service.py.

Verifies that ``_build_chat_messages`` appends the sandboxd preview guidance
to the system prompt when ``SANDBOXD_ENABLED=True``, and omits it when False.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

# These are pure unit tests with mocked DB and chat service — no integration marker needed.


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    """Async db session with proper SQLAlchemy query chain mocking."""
    db = AsyncMock()
    # _build_chat_messages calls: history_result = await db.execute(stmt)
    # then: history_result.scalars().all() — needs proper chain
    history_result = MagicMock()
    history_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=history_result)
    return db


def _make_thread(system_prompt: str | None = None) -> MagicMock:
    """Create a mock ChatThread with optional custom system_prompt."""
    thread = MagicMock()
    thread.id = 1
    thread.user_id = 1
    thread.username = "testuser"
    if system_prompt is not None:
        thread.metadata_ = {"system_prompt": system_prompt}
    else:
        thread.metadata_ = None
    return thread


# ── Tests ──────────────────────────────────────────────────────────────


class TestSandboxdSystemPromptInjection:
    """Verify sandboxd guidance is injected into the system prompt."""

    @pytest.mark.asyncio
    async def test_guidance_appended_when_enabled(self, mock_db):
        """SANDBOXD_ENABLED=True → system prompt contains sandboxd guidance."""
        from app.services.chat_service import (
            _SANDBOXD_SYSTEM_GUIDANCE,
            _build_chat_messages,
        )

        thread = _make_thread()

        with (
            patch(
                "app.services.chat_service.get_chat_thread",
                new_callable=AsyncMock,
                return_value=thread,
            ),
            patch("app.services.chat_service.settings") as mock_settings,
        ):
            mock_settings.SANDBOXD_ENABLED = True
            messages = await _build_chat_messages(mock_db, thread_id=1)

        system_msg = messages[0]
        assert system_msg["role"] == "system"
        assert "sandboxd_preview" in system_msg["content"]
        assert "Live Preview Tools" in system_msg["content"]
        assert _SANDBOXD_SYSTEM_GUIDANCE in system_msg["content"]

    @pytest.mark.asyncio
    async def test_guidance_not_appended_when_disabled(self, mock_db):
        """SANDBOXD_ENABLED=False → system prompt does NOT contain sandboxd guidance."""
        from app.services.chat_service import _build_chat_messages

        thread = _make_thread()

        with (
            patch(
                "app.services.chat_service.get_chat_thread",
                new_callable=AsyncMock,
                return_value=thread,
            ),
            patch("app.services.chat_service.settings") as mock_settings,
        ):
            mock_settings.SANDBOXD_ENABLED = False
            messages = await _build_chat_messages(mock_db, thread_id=1)

        system_msg = messages[0]
        assert system_msg["role"] == "system"
        assert "sandboxd_preview" not in system_msg["content"]
        assert "Live Preview Tools" not in system_msg["content"]

    @pytest.mark.asyncio
    async def test_default_prompt_gets_guidance_when_enabled(self, mock_db):
        """Default 'You are a helpful assistant.' + sandboxd guidance when enabled."""
        from app.services.chat_service import _build_chat_messages

        thread = _make_thread()  # No custom system_prompt

        with (
            patch(
                "app.services.chat_service.get_chat_thread",
                new_callable=AsyncMock,
                return_value=thread,
            ),
            patch("app.services.chat_service.settings") as mock_settings,
        ):
            mock_settings.SANDBOXD_ENABLED = True
            messages = await _build_chat_messages(mock_db, thread_id=1)

        content = messages[0]["content"]
        assert content.startswith("You are a helpful assistant.")
        assert "sandboxd_preview" in content

    @pytest.mark.asyncio
    async def test_custom_prompt_gets_guidance_when_enabled(self, mock_db):
        """Custom system_prompt from thread metadata + sandboxd guidance when enabled."""
        from app.services.chat_service import _build_chat_messages

        thread = _make_thread(system_prompt="You are a code reviewer.")

        with (
            patch(
                "app.services.chat_service.get_chat_thread",
                new_callable=AsyncMock,
                return_value=thread,
            ),
            patch("app.services.chat_service.settings") as mock_settings,
        ):
            mock_settings.SANDBOXD_ENABLED = True
            messages = await _build_chat_messages(mock_db, thread_id=1)

        content = messages[0]["content"]
        assert content.startswith("You are a code reviewer.")
        assert "sandboxd_preview" in content

    @pytest.mark.asyncio
    async def test_custom_prompt_no_guidance_when_disabled(self, mock_db):
        """Custom system_prompt without sandboxd guidance when disabled."""
        from app.services.chat_service import _build_chat_messages

        thread = _make_thread(system_prompt="You are a code reviewer.")

        with (
            patch(
                "app.services.chat_service.get_chat_thread",
                new_callable=AsyncMock,
                return_value=thread,
            ),
            patch("app.services.chat_service.settings") as mock_settings,
        ):
            mock_settings.SANDBOXD_ENABLED = False
            messages = await _build_chat_messages(mock_db, thread_id=1)

        content = messages[0]["content"]
        assert content == "You are a code reviewer."
        assert "sandboxd" not in content

    @pytest.mark.asyncio
    async def test_empty_system_prompt_falls_back_to_default(self, mock_db):
        """Empty string system_prompt in metadata falls back to default + guidance."""
        from app.services.chat_service import _build_chat_messages

        thread = _make_thread(system_prompt="")

        with (
            patch(
                "app.services.chat_service.get_chat_thread",
                new_callable=AsyncMock,
                return_value=thread,
            ),
            patch("app.services.chat_service.settings") as mock_settings,
        ):
            mock_settings.SANDBOXD_ENABLED = True
            messages = await _build_chat_messages(mock_db, thread_id=1)

        content = messages[0]["content"]
        assert content.startswith("You are a helpful assistant.")
        assert "sandboxd_preview" in content

    @pytest.mark.asyncio
    async def test_no_double_injection_on_rebuild(self, mock_db):
        """Each call to _build_chat_messages rebuilds from scratch — no accumulation."""
        from app.services.chat_service import _build_chat_messages

        thread = _make_thread()

        with (
            patch(
                "app.services.chat_service.get_chat_thread",
                new_callable=AsyncMock,
                return_value=thread,
            ),
            patch("app.services.chat_service.settings") as mock_settings,
        ):
            mock_settings.SANDBOXD_ENABLED = True
            messages1 = await _build_chat_messages(mock_db, thread_id=1)
            messages2 = await _build_chat_messages(mock_db, thread_id=1)

        # Each call should have exactly one copy of the guidance
        for msg in [messages1, messages2]:
            content = msg[0]["content"]
            assert content.count("Live Preview Tools (sandboxd)") == 1

    @pytest.mark.asyncio
    async def test_guidance_contains_expected_workflow(self, mock_db):
        """The sandboxd guidance mentions the expected workflow steps."""
        from app.services.chat_service import _build_chat_messages

        thread = _make_thread()

        with (
            patch(
                "app.services.chat_service.get_chat_thread",
                new_callable=AsyncMock,
                return_value=thread,
            ),
            patch("app.services.chat_service.settings") as mock_settings,
        ):
            mock_settings.SANDBOXD_ENABLED = True
            messages = await _build_chat_messages(mock_db, thread_id=1)

        content = messages[0]["content"]
        assert "sandboxd_preview" in content
        assert "sandboxd_file_write" in content
        assert "sandboxd_exec" in content
        assert "preview.flowmanner.com" in content
        assert "35 minutes" in content

    @pytest.mark.asyncio
    async def test_thread_not_found_still_injects_guidance(self, mock_db):
        """Even if the thread is not found (returns None), guidance is still injected."""
        from app.services.chat_service import _build_chat_messages

        with (
            patch(
                "app.services.chat_service.get_chat_thread",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("app.services.chat_service.settings") as mock_settings,
        ):
            mock_settings.SANDBOXD_ENABLED = True
            messages = await _build_chat_messages(mock_db, thread_id=999)

        content = messages[0]["content"]
        assert content.startswith("You are a helpful assistant.")
        assert "sandboxd_preview" in content


class TestSandboxdGuidanceConstant:
    """Verify the _SANDBOXD_SYSTEM_GUIDANCE constant itself."""

    def test_guidance_is_nonempty_string(self):
        from app.services.chat_service import _SANDBOXD_SYSTEM_GUIDANCE

        assert isinstance(_SANDBOXD_SYSTEM_GUIDANCE, str)
        assert len(_SANDBOXD_SYSTEM_GUIDANCE) > 100

    def test_guidance_starts_with_newline(self):
        """Guidance is appended to the system prompt, so it starts with a newline."""
        from app.services.chat_service import _SANDBOXD_SYSTEM_GUIDANCE

        assert _SANDBOXD_SYSTEM_GUIDANCE.startswith("\n")

    def test_guidance_mentions_all_sandboxd_tools(self):
        from app.services.chat_service import _SANDBOXD_SYSTEM_GUIDANCE

        assert "sandboxd_preview" in _SANDBOXD_SYSTEM_GUIDANCE
        assert "sandboxd_file_write" in _SANDBOXD_SYSTEM_GUIDANCE
        assert "sandboxd_exec" in _SANDBOXD_SYSTEM_GUIDANCE
