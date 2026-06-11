"""Unit tests for the tool-calling loop in chat_service.py.

Tests:
- _get_chat_openai_tools() — returns sandboxd tools when enabled, None when disabled
- _execute_tool_call() — executes tools via registry, handles errors
- Streaming tool-calling loop — detects tool_calls, executes, loops until text
- Non-streaming tool-calling loop — same flow without streaming
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test-key-123")


# ── Helpers ──────────────────────────────────────────────────────────


class _AsyncIterator:
    """Wraps a list into an async-iterable object for mocking streaming responses."""

    def __init__(self, items):
        self._items = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._items)
        except StopIteration:
            raise StopAsyncIteration


# ── _get_chat_openai_tools ────────────────────────────────────────────


class TestGetChatOpenaiTools:
    """Test _get_chat_openai_tools returns correct tool schemas."""

    def test_returns_none_when_sandboxd_disabled(self):
        from app.services.chat_service import _get_chat_openai_tools

        with patch("app.services.chat_service.settings") as mock_settings:
            mock_settings.SANDBOXD_ENABLED = False
            result = _get_chat_openai_tools()

        assert result is None

    def test_returns_tools_when_sandboxd_enabled(self):
        from app.services.chat_service import _get_chat_openai_tools

        mock_tool = MagicMock()
        mock_tool.tool_id = "sandboxd_preview"
        mock_tool.to_openai_schema.return_value = {
            "type": "function",
            "function": {"name": "sandboxd_preview", "parameters": {}},
        }

        mock_registry = MagicMock()
        mock_registry.list_all.return_value = [mock_tool]

        with (
            patch("app.services.chat_service.settings") as mock_settings,
            patch("app.tools.base.get_tool_registry", return_value=mock_registry),
        ):
            mock_settings.SANDBOXD_ENABLED = True
            result = _get_chat_openai_tools()

        assert result is not None
        assert len(result) == 1
        assert result[0]["type"] == "function"

    def test_filters_to_sandboxd_tools_only(self):
        from app.services.chat_service import _get_chat_openai_tools

        sandboxd_tool = MagicMock()
        sandboxd_tool.tool_id = "sandboxd_preview"
        sandboxd_tool.to_openai_schema.return_value = {"type": "function"}

        other_tool = MagicMock()
        other_tool.tool_id = "browser_ping"
        other_tool.to_openai_schema.return_value = {"type": "function"}

        mock_registry = MagicMock()
        mock_registry.list_all.return_value = [sandboxd_tool, other_tool]

        with (
            patch("app.services.chat_service.settings") as mock_settings,
            patch("app.tools.base.get_tool_registry", return_value=mock_registry),
        ):
            mock_settings.SANDBOXD_ENABLED = True
            result = _get_chat_openai_tools()

        assert result is not None
        assert len(result) == 1  # only sandboxd_preview

    def test_returns_none_when_no_sandboxd_tools_registered(self):
        from app.services.chat_service import _get_chat_openai_tools

        other_tool = MagicMock()
        other_tool.tool_id = "some_other_tool"
        other_tool.to_openai_schema.return_value = {"type": "function"}

        mock_registry = MagicMock()
        mock_registry.list_all.return_value = [other_tool]

        with (
            patch("app.services.chat_service.settings") as mock_settings,
            patch("app.tools.base.get_tool_registry", return_value=mock_registry),
        ):
            mock_settings.SANDBOXD_ENABLED = True
            result = _get_chat_openai_tools()

        assert result is None


# ── _execute_tool_call ────────────────────────────────────────────────


class TestExecuteToolCall:
    """Test _execute_tool_call runs tools and handles errors."""

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        from app.services.chat_service import _execute_tool_call

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.result = {"sandbox_id": "sb-123", "status": "running"}

        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(return_value=mock_result)

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool

        with patch("app.tools.base.get_tool_registry", return_value=mock_registry):
            result = await _execute_tool_call("sandboxd_preview", '{"sandbox_id": "sb-123"}')

        parsed = json.loads(result)
        assert parsed["sandbox_id"] == "sb-123"
        mock_tool.execute.assert_called_once_with({"sandbox_id": "sb-123"})

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        from app.services.chat_service import _execute_tool_call

        mock_registry = MagicMock()
        mock_registry.get.return_value = None

        with patch("app.tools.base.get_tool_registry", return_value=mock_registry):
            result = await _execute_tool_call("nonexistent", "{}")

        parsed = json.loads(result)
        assert "error" in parsed
        assert "Unknown tool" in parsed["error"]

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self):
        from app.services.chat_service import _execute_tool_call

        mock_tool = MagicMock()
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool

        with patch("app.tools.base.get_tool_registry", return_value=mock_registry):
            result = await _execute_tool_call("sandboxd_preview", "not-json")

        parsed = json.loads(result)
        assert "error" in parsed
        assert "Invalid JSON" in parsed["error"]

    @pytest.mark.asyncio
    async def test_tool_error_propagated(self):
        from app.services.chat_service import _execute_tool_call

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "No sandbox available"

        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(return_value=mock_result)

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool

        with patch("app.tools.base.get_tool_registry", return_value=mock_registry):
            result = await _execute_tool_call("sandboxd_exec", '{"code": "ls"}')

        parsed = json.loads(result)
        assert parsed["error"] == "No sandbox available"

    @pytest.mark.asyncio
    async def test_empty_arguments(self):
        from app.services.chat_service import _execute_tool_call

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.result = {"sandbox_id": "sb-new"}

        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(return_value=mock_result)

        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool

        with patch("app.tools.base.get_tool_registry", return_value=mock_registry):
            result = await _execute_tool_call("sandboxd_preview", "")

        mock_tool.execute.assert_called_once_with({})


# ── Streaming tool-calling loop ───────────────────────────────────────


def _make_stream_chunk(content=None, tool_calls=None, finish_reason=None):
    """Create a mock streaming chunk."""
    chunk = MagicMock()
    choice = MagicMock()
    delta = MagicMock()

    delta.content = content
    delta.tool_calls = tool_calls

    choice.delta = delta
    choice.finish_reason = finish_reason
    chunk.choices = [choice]
    return chunk


def _make_tool_call_delta(index, tc_id=None, name=None, arguments=None):
    """Create a mock tool_call delta."""
    tc = MagicMock()
    tc.index = index
    tc.id = tc_id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments
    return tc


class TestStreamingToolLoop:
    """Test the streaming tool-calling loop in stream_message_to_llm."""

    @pytest.mark.asyncio
    async def test_simple_text_no_tools(self):
        """Without tools, behaves like the original function."""
        from app.services.chat_service import stream_message_to_llm

        mock_db = AsyncMock()

        text_chunk = _make_stream_chunk(content="Hello!", finish_reason="stop")
        mock_response = _AsyncIterator([text_chunk])

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_msg = AsyncMock()
        mock_msg.id = 42

        with (
            patch("app.services.chat_service._get_chat_openai_tools", return_value=None),
            patch("app.services.chat_service._client", mock_client),
            patch("app.services.chat_service._LLM_API_BASE", "http://test/v1"),
            patch("app.services.chat_service._LLM_API_KEY", "test-key"),
            patch("app.services.chat_service._LLM_MODEL", "deepseek/deepseek-v4-flash"),
            patch(
                "app.services.chat_service._lookup_stored_byok_key",
                new_callable=AsyncMock,
                return_value=(None, None),
            ),
            patch(
                "app.services.chat_service._build_chat_messages",
                new_callable=AsyncMock,
                return_value=[{"role": "user", "content": "Hi"}],
            ),
            patch(
                "app.services.chat_service.create_chat_message",
                new_callable=AsyncMock,
                return_value=mock_msg,
            ),
            patch("app.services.chat_service.AsyncOpenAI", return_value=mock_client),
        ):
            events = []
            async for event in stream_message_to_llm(mock_db, thread_id=1, content="Hi", user_id=1):
                events.append(json.loads(event))

        token_events = [e for e in events if e["type"] == "token"]
        assert len(token_events) == 1
        assert token_events[0]["content"] == "Hello!"

        complete_events = [e for e in events if e["type"] == "complete"]
        assert len(complete_events) == 1
        assert complete_events[0]["message_id"] == 42

    @pytest.mark.asyncio
    async def test_tool_call_executed_and_loops(self):
        """When LLM returns tool_calls, they are executed and the loop continues."""
        from app.services.chat_service import stream_message_to_llm

        mock_db = AsyncMock()

        # Round 1: LLM returns a tool call
        tc_delta = _make_tool_call_delta(
            index=0,
            tc_id="call_1",
            name="sandboxd_preview",
            arguments="{}",
        )
        tool_chunk = _make_stream_chunk(tool_calls=[tc_delta], finish_reason="tool_calls")

        # Round 2: LLM returns final text
        text_chunk = _make_stream_chunk(content="Preview ready!", finish_reason="stop")

        # Mock client that returns different responses per call
        call_count = 0

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _AsyncIterator([tool_chunk])
            else:
                return _AsyncIterator([text_chunk])

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=mock_create)

        # Mock tool execution
        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.result = {"sandbox_id": "sb-123"}
        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(return_value=mock_tool_result)
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool
        mock_registry.list_all.return_value = []

        _VALID_TOOL = [
            {
                "type": "function",
                "function": {
                    "name": "sandboxd_preview",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        mock_msg = AsyncMock()
        mock_msg.id = 99

        with (
            patch(
                "app.services.chat_service._get_chat_openai_tools",
                return_value=_VALID_TOOL,
            ),
            patch("app.services.chat_service._client", mock_client),
            patch("app.services.chat_service._LLM_API_BASE", "http://test/v1"),
            patch("app.services.chat_service._LLM_API_KEY", "test-key"),
            patch("app.services.chat_service._LLM_MODEL", "deepseek/deepseek-v4-flash"),
            patch(
                "app.services.chat_service._lookup_stored_byok_key",
                new_callable=AsyncMock,
                return_value=(None, None),
            ),
            patch(
                "app.services.chat_service._build_chat_messages",
                new_callable=AsyncMock,
                return_value=[{"role": "user", "content": "Build a landing page"}],
            ),
            patch(
                "app.services.chat_service.create_chat_message",
                new_callable=AsyncMock,
                return_value=mock_msg,
            ),
            patch("app.services.chat_service.AsyncOpenAI", return_value=mock_client),
            patch("app.tools.base.get_tool_registry", return_value=mock_registry),
        ):
            events = []
            async for event in stream_message_to_llm(mock_db, thread_id=1, content="Build a landing page", user_id=1):
                events.append(json.loads(event))

        # Verify tool call events
        start_events = [e for e in events if e["type"] == "tool_call_start"]
        assert len(start_events) == 1
        assert start_events[0]["tool"] == "sandboxd_preview"

        result_events = [e for e in events if e["type"] == "tool_call_result"]
        assert len(result_events) == 1
        assert json.loads(result_events[0]["result"])["sandbox_id"] == "sb-123"

        # Verify final text
        token_events = [e for e in events if e["type"] == "token"]
        assert any(e["content"] == "Preview ready!" for e in token_events)

        complete_events = [e for e in events if e["type"] == "complete"]
        assert len(complete_events) == 1

        # Verify LLM was called twice (tool loop)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_multi_tool_calls_in_one_round(self):
        """LLM calls multiple tools in a single round."""
        from app.services.chat_service import stream_message_to_llm

        mock_db = AsyncMock()

        # Round 1: LLM returns 2 tool calls
        tc0 = _make_tool_call_delta(index=0, tc_id="call_a", name="sandboxd_preview", arguments="{}")
        tc1 = _make_tool_call_delta(
            index=1,
            tc_id="call_b",
            name="sandboxd_file_write",
            arguments='{"path":"index.html","content":"<h1>Hi</h1>"}',
        )
        tool_chunk = _make_stream_chunk(tool_calls=[tc0, tc1], finish_reason="tool_calls")

        text_chunk = _make_stream_chunk(content="Done!", finish_reason="stop")

        call_count = 0

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            return _AsyncIterator([tool_chunk] if call_count == 1 else [text_chunk])

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=mock_create)

        mock_tool = MagicMock()
        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.result = {"ok": True}
        mock_tool.execute = AsyncMock(return_value=mock_tool_result)
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool
        mock_registry.list_all.return_value = []

        _TOOLS = [
            {
                "type": "function",
                "function": {
                    "name": "sandboxd_preview",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "sandboxd_file_write",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]
        mock_msg = MagicMock()
        mock_msg.id = 77

        with (
            patch("app.services.chat_service._get_chat_openai_tools", return_value=_TOOLS),
            patch("app.services.chat_service._client", mock_client),
            patch("app.services.chat_service._LLM_API_BASE", "http://test/v1"),
            patch("app.services.chat_service._LLM_API_KEY", "k"),
            patch("app.services.chat_service._LLM_MODEL", "deepseek/deepseek-v4-flash"),
            patch(
                "app.services.chat_service._lookup_stored_byok_key",
                new_callable=AsyncMock,
                return_value=(None, None),
            ),
            patch(
                "app.services.chat_service._build_chat_messages",
                new_callable=AsyncMock,
                return_value=[{"role": "user", "content": "Build page"}],
            ),
            patch(
                "app.services.chat_service.create_chat_message",
                new_callable=AsyncMock,
                return_value=mock_msg,
            ),
            patch("app.services.chat_service.AsyncOpenAI", return_value=mock_client),
            patch("app.tools.base.get_tool_registry", return_value=mock_registry),
        ):
            events = []
            async for event in stream_message_to_llm(mock_db, 1, "Build page", 1):
                events.append(json.loads(event))

        starts = [e for e in events if e["type"] == "tool_call_start"]
        assert len(starts) == 2
        assert starts[0]["call_id"] == "call_a"
        assert starts[1]["call_id"] == "call_b"


# ── Non-streaming tool loop ───────────────────────────────────────────


class TestNonStreamingToolLoop:
    """Test the non-streaming tool-calling loop in send_message_to_llm."""

    @pytest.mark.asyncio
    async def test_simple_text_no_tools(self):
        from app.services.chat_service import send_message_to_llm

        mock_db = AsyncMock()

        mock_message = MagicMock()
        mock_message.content = "Hello!"
        mock_message.tool_calls = None

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=mock_message)]
        mock_response.usage = MagicMock(total_tokens=10, prompt_tokens=5, completion_tokens=5)

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with (
            patch("app.services.chat_service._get_chat_openai_tools", return_value=None),
            patch("app.services.chat_service._client", mock_client),
            patch("app.services.chat_service._LLM_API_BASE", "http://test/v1"),
            patch("app.services.chat_service._LLM_API_KEY", "test-key"),
            patch("app.services.chat_service._LLM_MODEL", "deepseek/deepseek-v4-flash"),
            patch(
                "app.services.chat_service._lookup_stored_byok_key",
                new_callable=AsyncMock,
                return_value=(None, None),
            ),
            patch(
                "app.services.chat_service._build_chat_messages",
                new_callable=AsyncMock,
                return_value=[{"role": "user", "content": "Hi"}],
            ),
            patch("app.services.chat_service.create_chat_message", new_callable=AsyncMock),
            patch("app.services.chat_service.AsyncOpenAI", return_value=mock_client),
        ):
            result = await send_message_to_llm(mock_db, thread_id=1, content="Hi", user_id=1)

        assert result["success"] is True
        assert result["content"] == "Hello!"

    @pytest.mark.asyncio
    async def test_tool_call_loops_until_text(self):
        from app.services.chat_service import send_message_to_llm

        mock_db = AsyncMock()

        # Round 1 response: tool call
        tc1 = MagicMock()
        tc1.id = "call_1"
        tc1.function = MagicMock(name="sandboxd_preview", arguments="{}")

        tool_response_msg = MagicMock()
        tool_response_msg.content = None
        tool_response_msg.tool_calls = [tc1]

        tool_response = MagicMock()
        tool_response.choices = [MagicMock(message=tool_response_msg)]
        tool_response.usage = MagicMock(total_tokens=10, prompt_tokens=5, completion_tokens=5)

        # Round 2 response: final text
        final_msg = MagicMock()
        final_msg.content = "Done! Preview URL shared."
        final_msg.tool_calls = None

        final_response = MagicMock()
        final_response.choices = [MagicMock(message=final_msg)]
        final_response.usage = MagicMock(total_tokens=20, prompt_tokens=10, completion_tokens=10)

        call_count = 0

        async def mock_create(**kwargs):
            nonlocal call_count
            call_count += 1
            return tool_response if call_count == 1 else final_response

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=mock_create)

        mock_tool_result = MagicMock()
        mock_tool_result.success = True
        mock_tool_result.result = {"sandbox_id": "sb-abc"}
        mock_tool = MagicMock()
        mock_tool.execute = AsyncMock(return_value=mock_tool_result)
        mock_registry = MagicMock()
        mock_registry.get.return_value = mock_tool

        _VALID_TOOL = [
            {
                "type": "function",
                "function": {
                    "name": "sandboxd_preview",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

        with (
            patch(
                "app.services.chat_service._get_chat_openai_tools",
                return_value=_VALID_TOOL,
            ),
            patch("app.services.chat_service._client", mock_client),
            patch("app.services.chat_service._LLM_API_BASE", "http://test/v1"),
            patch("app.services.chat_service._LLM_API_KEY", "test-key"),
            patch("app.services.chat_service._LLM_MODEL", "deepseek/deepseek-v4-flash"),
            patch(
                "app.services.chat_service._lookup_stored_byok_key",
                new_callable=AsyncMock,
                return_value=(None, None),
            ),
            patch(
                "app.services.chat_service._build_chat_messages",
                new_callable=AsyncMock,
                return_value=[{"role": "user", "content": "Build a page"}],
            ),
            patch("app.services.chat_service.create_chat_message", new_callable=AsyncMock),
            patch("app.services.chat_service.AsyncOpenAI", return_value=mock_client),
            patch("app.tools.base.get_tool_registry", return_value=mock_registry),
        ):
            result = await send_message_to_llm(mock_db, thread_id=1, content="Build a page", user_id=1)

        assert result["success"] is True
        assert result["content"] == "Done! Preview URL shared."
        assert call_count == 2
