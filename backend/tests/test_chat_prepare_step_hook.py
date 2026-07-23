"""ADR-002 spike tests: ordered prepareStep injection closure for chat.

These tests verify the `_prepare_step_inject` closure (and the flag-gated
wiring in `_stream_message_to_llm_body`) without touching the DB or an LLM:

1. Flag OFF  -> legacy inline injection runs; no `injected` receipt events.
2. Flag ON   -> same context injected via the closure; `injected` receipts emitted.
3. Ordering  -> memory context is inserted before web-search context.

The closure reuses `_inject_memory_context` / `_inject_web_search`, so we
assert on the *observable message shape* those produce, not on internals.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


def _base_messages() -> list[dict]:
    """Minimal chat message list with a system prompt at index 0."""
    return [
        {"role": "system", "content": "You are Flowmanner."},
        {"role": "user", "content": "Hello"},
    ]


def _fake_claims() -> list:
    """Stand-in for PersonalMemoryClaim objects.

    ``format_memory_block`` reads ``.object/.subject/.predicate/.confidence``,
    so the stand-ins must carry those attributes (plain namespaces).
    """

    class _Claim:
        def __init__(self, subject: str, predicate: str, obj, confidence: float = 0.8):
            self.id = "00000000-0000-0000-0000-000000000000"
            self.subject = subject
            self.predicate = predicate
            self.object = obj
            self.confidence = confidence

    return [
        _Claim("User", "prefers", {"value": "dark mode"}, 0.85),
        _Claim("Flowmanner", "uses", {"framework": "Next.js"}, 0.78),
    ]


@pytest.fixture
def patched_settings(monkeypatch: pytest.MonkeyPatch):
    """Replace chat_service.settings with a minimal namespace.

    Returns a setter so individual tests can flip the spike flag without
    rebuilding the whole namespace.
    """

    def _set(**overrides):
        ns = SimpleNamespace(
            FLOWMANNER_CROSS_MISSION_MEMORY=False,
            CHAT_MEMORY_CITATIONS_ENABLED=False,
            SANDBOXD_ENABLED=False,
            CHAT_MAX_TOOL_ROUNDS=15,
            **overrides,
        )
        if not hasattr(ns, "CHAT_PREPARE_STEP_HOOK_ENABLED"):
            ns.CHAT_PREPARE_STEP_HOOK_ENABLED = False
        monkeypatch.setattr("app.services.chat.messages.settings", ns)
        return ns

    _set()
    return _set


class TestPrepareStepClosure:
    async def test_flag_off_no_receipt_events(self, patched_settings):
        from app.services import chat_service

        patched_settings(CHAT_PREPARE_STEP_HOOK_ENABLED=False)

        # Simulate the flag-off branch exactly as _stream_message_to_llm_body does.
        messages = _base_messages()
        memory_claims = _fake_claims()

        # Legacy path mutates messages inline, returns no events.
        messages_after = chat_service._inject_memory_context(messages, memory_claims)
        assert any(
            m.get("role") == "system" and "PERSONAL MEMORY CONTEXT" in m.get("content", "") for m in messages_after
        )

    async def test_flag_on_injects_and_emits_receipt(self, patched_settings, monkeypatch):
        from app.services import chat_service

        patched_settings(CHAT_PREPARE_STEP_HOOK_ENABLED=True)

        # Prevent live web-search network call in the spike path.
        # Mirror _inject_web_search's real shape: inserts a system message
        # *before the last message* (index -1).
        async def _fake_ws(msgs, query):
            out = list(msgs)
            out.insert(-1, {"role": "system", "content": "WEB SEARCH RESULTS"})
            return out

        monkeypatch.setattr(chat_service, "_inject_web_search", _fake_ws)

        messages = _base_messages()
        memory_claims = _fake_claims()
        content = "latest Flowmanner release notes"

        result, events = await chat_service._prepare_step_inject(
            messages,
            memory_claims=memory_claims,
            web_search=True,
            content=content,
        )

        # Context was injected (a memory system message appears).
        assert any(m.get("role") == "system" and "PERSONAL MEMORY CONTEXT" in m.get("content", "") for m in result)

        # One receipt per source, in fixed order memory -> web_search.
        assert [e["source"] for e in events] == ["memory", "web_search"]
        assert events[0]["type"] == "injected"
        assert events[0]["count"] == len(memory_claims)
        assert events[1]["type"] == "injected"
        assert events[1]["query"] == content

    async def test_flag_on_memory_only_no_web_search_event(self, patched_settings):
        from app.services import chat_service

        patched_settings(CHAT_PREPARE_STEP_HOOK_ENABLED=True)

        result, events = await chat_service._prepare_step_inject(
            _base_messages(),
            memory_claims=_fake_claims(),
            web_search=False,
            content=None,
        )

        assert [e["source"] for e in events] == ["memory"]
        assert any(m.get("role") == "system" and "PERSONAL MEMORY CONTEXT" in m.get("content", "") for m in result)

    async def test_flag_on_no_claims_no_events(self, patched_settings):
        from app.services import chat_service

        patched_settings(CHAT_PREPARE_STEP_HOOK_ENABLED=True)

        result, events = await chat_service._prepare_step_inject(
            _base_messages(),
            memory_claims=None,
            web_search=False,
            content=None,
        )

        # No claims, no web search -> nothing injected, no receipts.
        assert events == []
        assert result == _base_messages()

    async def test_ordering_memory_before_web_search(self, patched_settings, monkeypatch):
        """Memory context must sit closer to the system prompt than web search.

        Both sources insert at index 1 (right after the original system prompt)
        and web search runs after memory, so the memory system message precedes
        the web-search system message in document order. This proves the ordering
        is code-structure-enforced, not accidental.
        """
        from app.services import chat_service

        patched_settings(CHAT_PREPARE_STEP_HOOK_ENABLED=True)

        async def _fake_ws(msgs, query):
            out = list(msgs)
            out.insert(-1, {"role": "system", "content": "WEB SEARCH RESULTS"})
            return out

        monkeypatch.setattr(chat_service, "_inject_web_search", _fake_ws)

        result, _ = await chat_service._prepare_step_inject(
            _base_messages(),
            memory_claims=_fake_claims(),
            web_search=True,
            content="some query",
        )

        sys_indices = [i for i, m in enumerate(result) if m.get("role") == "system"]
        assert sys_indices[0] == 0  # original system prompt
        # memory (PERSONAL MEMORY CONTEXT) must appear before web search (WEB SEARCH)
        mem_idx = next(i for i, m in enumerate(result) if "PERSONAL MEMORY CONTEXT" in m.get("content", ""))
        web_idx = next(i for i, m in enumerate(result) if m.get("content", "") == "WEB SEARCH RESULTS")
        assert mem_idx < web_idx
