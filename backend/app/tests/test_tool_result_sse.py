"""Tests that stream_message_to_llm emits tool_call_start / tool_call_result SSE events.

P2-2: server -> client streaming of tool outputs. The streaming path in
chat_service.stream_message_to_llm yields a `tool_call_start` event before
each tool executes and a `tool_call_result` event after, carrying the tool
name, call id, and result. Both flow through the SSE buffer (Redis) and are
replayable on reconnect via the /replay endpoint.

These tests assert the event SHAPE and ORDER directly from the generator,
without standing up Redis (append_to_buffer no-ops gracefully when Redis is
unavailable, per test_sse_buffer.py).
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from app.services.chat_service import stream_message_to_llm


class FakeTokenChunk:
    """Streaming chunk carrying plain text delta."""

    def __init__(self, content: str):
        self.choices = [MagicMock(delta=MagicMock(content=content, tool_calls=None))]


class FakeToolCallChunk:
    """Streaming chunk carrying a tool_call delta with finish_reason='tool_calls'
    so the stream loop (chat_service.py:1782) breaks after accumulating it."""

    def __init__(self, name: str, arguments: str, id_: str, index: int = 0):
        tc = MagicMock()
        tc.id = id_
        tc.index = index
        tc.function.name = name
        tc.function.arguments = arguments
        # delta.content=None, delta.tool_calls=[tc], and finish_reason ends the round
        self.choices = [
            MagicMock(
                delta=MagicMock(content=None, tool_calls=[tc]),
                finish_reason="tool_calls",
            )
        ]


def _fake_llm_stream(name: str, arguments: str, id_: str):
    """Yield a single tool-call chunk (finish_reason=tool_calls). The next LLM
    round (after tool results) is supplied by the mock's side_effect."""
    yield FakeToolCallChunk(name=name, arguments=arguments, id_=id_)


@pytest.fixture
def mock_db():
    db = AsyncMock()
    msg = MagicMock()
    msg.id = 42
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=msg)))
    return db


@pytest.mark.asyncio
async def test_stream_emits_tool_call_start_and_result(mock_db):
    """A tool-calling turn yields tool_call_start then tool_call_result with
    the correct tool name, call id, and result payload."""

    async def fake_llm_tool_call():
        for c in _fake_llm_stream("web_search_enhanced", '{"q": "weather"}', "call_abc"):
            yield c

    async def fake_llm_final_text():
        yield FakeTokenChunk("Here is the weather.")

    resp_tool = MagicMock()
    resp_tool.__aiter__ = lambda self: fake_llm_tool_call().__aiter__()
    resp_final = MagicMock()
    resp_final.__aiter__ = lambda self: fake_llm_final_text().__aiter__()

    with (
        patch("app.services.chat_service._client") as mock_client,
        patch("app.services.chat_service.AsyncOpenAI") as MockAsyncOpenAI,
        patch("app.services.chat_service.create_chat_message", new_callable=AsyncMock) as mock_msg,
        patch(
            "app.services.chat_service._execute_tool_call",
            new=AsyncMock(return_value=json.dumps({"answer": 42})),
        ),
        patch(
            "app.services.chat_service._record_tool_cost_fire_and_forget",
            new=AsyncMock(),
        ),
        # Force redis-unavailable path so the SSE buffer / prompt cache skip
        # gracefully (no real redis needed for this unit test).
        patch(
            "app.services.chat_service._get_prompt_redis",
            new=AsyncMock(return_value=None),
        ),
    ):
        m = MagicMock()
        m.id = 42
        mock_msg.return_value = m
        # 1st LLM call returns the tool call; 2nd (after tool results) returns text.
        mock_client.chat.completions.create = AsyncMock(side_effect=[resp_tool, resp_final])
        new_client = MagicMock()
        new_client.chat.completions.create = mock_client.chat.completions.create
        MockAsyncOpenAI.return_value = new_client

        events = [
            json.loads(e)
            async for e in stream_message_to_llm(
                db=mock_db,
                thread_id=1,
                content="look up the weather",
                user_id=1,
                user_api_key=None,
            )
        ]

    types = [e["type"] for e in events]
    assert "tool_call_start" in types
    assert "tool_call_result" in types

    start = next(e for e in events if e["type"] == "tool_call_start")
    result = next(e for e in events if e["type"] == "tool_call_result")

    # start carries the tool name + call id (before execution)
    assert start["tool"] == "web_search_enhanced"
    assert start["call_id"] == "call_abc"
    # result carries the tool name + call id + serialized result
    assert result["tool"] == "web_search_enhanced"
    assert result["call_id"] == "call_abc"
    assert json.loads(result["result"]) == {"answer": 42}

    # start MUST precede result (the events bracket the execution)
    assert types.index("tool_call_start") < types.index("tool_call_result")


@pytest.mark.asyncio
async def test_stream_emits_no_tool_events_when_no_tool_call(mock_db):
    """A plain text turn emits token/complete but NO tool_call_* events."""

    async def fake_llm():
        yield FakeTokenChunk("hello")
        yield FakeTokenChunk(" world")

    resp = MagicMock()
    resp.__aiter__ = lambda self: fake_llm().__aiter__()

    with (
        patch("app.services.chat_service._client") as mock_client,
        patch("app.services.chat_service.AsyncOpenAI") as MockAsyncOpenAI,
        patch("app.services.chat_service.create_chat_message", new_callable=AsyncMock) as mock_msg,
        # Force redis-unavailable path so the SSE buffer / prompt cache skip
        # gracefully (no real redis needed for this unit test).
        patch(
            "app.services.chat_service._get_prompt_redis",
            new=AsyncMock(return_value=None),
        ),
    ):
        m = MagicMock()
        m.id = 42
        mock_msg.return_value = m
        mock_client.chat.completions.create = AsyncMock(return_value=resp)
        new_client = MagicMock()
        new_client.chat.completions.create = mock_client.chat.completions.create
        MockAsyncOpenAI.return_value = new_client

        events = [
            json.loads(e)
            async for e in stream_message_to_llm(
                db=mock_db,
                thread_id=1,
                content="hi",
                user_id=1,
                user_api_key=None,
            )
        ]

    types = [e["type"] for e in events]
    assert "tool_call_start" not in types
    assert "tool_call_result" not in types
    assert "token" in types
    assert "complete" in types
