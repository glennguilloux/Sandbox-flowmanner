"""Regression tests for the idle-in-transaction bug fix.

Before the fix: send_message_to_llm / stream_message_to_llm saved the user
message, committed, then made a multi-minute LLM call. The session sat idle
while the LLM ran, and PostgreSQL's idle_in_transaction_session_timeout
killed the connection mid-call.

After the fix: the session is *closed* (not just committed) before the LLM
call, so PostgreSQL has no idle transaction to kill. The assistant message
is saved via a fresh session.

These tests verify the ordering invariant: db.close() must happen BEFORE
client.chat.completions.create(). They do this by mocking AsyncOpenAI at
the module level so any AsyncOpenAI(...) construction uses our fake, then
recording the order in which db.close() and chat.completions.create() are
called.
"""

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import chat_service


def _install_fake_openai(stack: ExitStack, call_order: list[str], response_factory):
    """Patch AsyncOpenAI in chat_service so chat.completions.create is our fake.

    Any AsyncOpenAI(...) call inside chat_service returns a MagicMock whose
    chat.completions.create appends to call_order and returns response_factory().
    """
    fake_client = MagicMock()

    async def fake_create(**_kwargs):
        call_order.append("llm_create")
        return response_factory()

    fake_client.chat.completions.create = AsyncMock(side_effect=fake_create)
    fake_client_cls = MagicMock(return_value=fake_client)
    stack.enter_context(patch.object(chat_service, "AsyncOpenAI", fake_client_cls))
    return fake_client_cls


def _non_stream_response() -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message = MagicMock(content="hello", tool_calls=None)
    resp.usage = MagicMock(prompt_tokens=5, completion_tokens=3, total_tokens=8)
    return resp


def _stream_response() -> MagicMock:
    """Build an async iterator that yields one chunk then stops."""

    class _FakeStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            if getattr(self, "_done", False):
                raise StopAsyncIteration
            self._done = True
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta = MagicMock(content="x", tool_calls=None)
            chunk.choices[0].finish_reason = "stop"
            chunk.usage = None
            return chunk

    fake: MagicMock = MagicMock(spec=_FakeStream)
    fake.__aiter__ = _FakeStream.__aiter__  # type: ignore[method-assign]
    fake.__anext__ = _FakeStream.__anext__  # type: ignore[method-assign]
    return fake


def _make_db_mock(call_order: list[str]) -> MagicMock:
    db = MagicMock()
    db.commit = AsyncMock(side_effect=lambda: call_order.append("commit"))
    db.close = AsyncMock(side_effect=lambda: call_order.append("close"))
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    return db


def _common_patches(stack: ExitStack):
    """Install the patches that don't differ between send and stream."""
    stack.enter_context(patch.object(chat_service, "create_chat_message", AsyncMock(return_value=MagicMock(id=1))))
    stack.enter_context(patch.object(chat_service, "_build_chat_messages", AsyncMock(return_value=[])))
    stack.enter_context(patch.object(chat_service, "_get_chat_openai_tools", return_value=None))
    stack.enter_context(
        patch.object(
            chat_service,
            "create_chat_message_fresh_session",
            AsyncMock(return_value=MagicMock(id=2)),
        )
    )
    stack.enter_context(patch.object(chat_service, "_resolve_provider", return_value=("http://x", "k", "glm-4-plus")))
    stack.enter_context(patch.object(chat_service, "_validate_byok_key_matches_model", return_value=None))
    stack.enter_context(patch.object(chat_service, "_lookup_stored_byok_key", AsyncMock(return_value=(None, None))))
    gcb_p = stack.enter_context(patch("app.core.circuit_breaker.get_circuit_breaker"))
    gcb_p.return_value.protect = MagicMock()
    gcb_p.return_value.protect.return_value.__aenter__ = AsyncMock(return_value=None)
    gcb_p.return_value.protect.return_value.__aexit__ = AsyncMock(return_value=None)


@pytest.mark.asyncio
async def test_send_message_closes_db_before_llm_call():
    """send_message_to_llm must call db.close() BEFORE client.chat.completions.create()."""
    call_order: list[str] = []
    db = _make_db_mock(call_order)

    with ExitStack() as stack:
        _install_fake_openai(stack, call_order, _non_stream_response)
        _common_patches(stack)
        result = await chat_service.send_message_to_llm(
            db=db,
            thread_id=1,
            content="hi",
            user_id=1,
            model_id="glm-4-plus",
        )

    assert result["success"] is True
    assert "close" in call_order, f"db.close() never called; order={call_order}"
    assert "llm_create" in call_order, f"llm_create never called; order={call_order}"
    assert call_order.index("close") < call_order.index(
        "llm_create"
    ), f"db.close() must happen BEFORE llm_create. Actual order: {call_order}"


@pytest.mark.asyncio
async def test_stream_message_closes_db_before_llm_call():
    """stream_message_to_llm must call db.close() BEFORE client.chat.completions.create()."""
    call_order: list[str] = []
    db = _make_db_mock(call_order)

    with ExitStack() as stack:
        _install_fake_openai(stack, call_order, _stream_response)
        _common_patches(stack)
        # Drain the async generator
        async for _ in chat_service.stream_message_to_llm(
            db=db,
            thread_id=1,
            content="hi",
            user_id=1,
            model_id="glm-4-plus",
        ):
            pass

    assert "close" in call_order, f"db.close() never called; order={call_order}"
    assert "llm_create" in call_order, f"llm_create never called; order={call_order}"
    assert call_order.index("close") < call_order.index(
        "llm_create"
    ), f"db.close() must happen BEFORE llm_create. Actual order: {call_order}"
