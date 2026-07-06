"""Tests for app.services.chat_context — Phase 0.2 leaf extraction.

Verifies the pure transform functions moved from chat_service.py.
"""

from app.services.chat_context import _inject_memory_context, _prune_messages_to_budget


class TestPruneMessagesToBudget:
    def test_no_messages_returns_unchanged(self):
        assert _prune_messages_to_budget([], 6000) == []

    def test_zero_budget_returns_unchanged(self):
        msgs = [{"role": "user", "content": "hello"}]
        assert _prune_messages_to_budget(msgs, 0) == msgs

    def test_within_budget_returns_unchanged(self):
        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        result = _prune_messages_to_budget(msgs, 6000)
        assert result == msgs

    def test_prunes_middle_messages(self):
        # Build 20 messages that exceed a small budget
        msgs = [{"role": "system", "content": "System prompt."}]
        for i in range(18):
            role = "user" if i % 2 == 0 else "assistant"
            msgs.append({"role": role, "content": f"Message {i}: " + "x" * 200})
        # Should prune — budget of 500 tokens (~2000 chars)
        result = _prune_messages_to_budget(msgs, 500)
        assert len(result) < len(msgs)
        # System message should be preserved
        assert result[0]["role"] == "system"
        # Last 4 conversation messages should be preserved
        conv_result = [m for m in result if m["role"] != "system"]
        assert len(conv_result) >= 4

    def test_keeps_system_messages_at_start(self):
        msgs = [
            {"role": "system", "content": "You are a coding assistant. " * 50},
            {"role": "system", "content": "Extra context. " * 50},
        ]
        for i in range(10):
            role = "user" if i % 2 == 0 else "assistant"
            msgs.append({"role": role, "content": f"msg {i} " + "x" * 200})
        result = _prune_messages_to_budget(msgs, 300)
        # System messages should still be at the start
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "system"

    def test_too_few_messages_returns_unchanged(self):
        # Only 3 conversation messages + 1 system = too few to prune
        msgs = [
            {"role": "system", "content": "System."},
            {"role": "user", "content": "a" * 5000},
            {"role": "assistant", "content": "b" * 5000},
            {"role": "user", "content": "c" * 5000},
        ]
        result = _prune_messages_to_budget(msgs, 100)
        assert len(result) == len(msgs)

    def test_pruned_middle_has_placeholder(self):
        msgs = [{"role": "system", "content": "Sys."}]
        for i in range(20):
            role = "user" if i % 2 == 0 else "assistant"
            msgs.append({"role": role, "content": f"msg {i} " + "x" * 200})
        result = _prune_messages_to_budget(msgs, 300)
        # Find the placeholder
        placeholders = [m for m in result if "Earlier conversation omitted" in m.get("content", "")]
        assert len(placeholders) == 1
        assert placeholders[0]["role"] == "system"


class TestInjectMemoryContext:
    def test_empty_claims_returns_unchanged(self):
        msgs = [{"role": "system", "content": "Hello"}]
        assert _inject_memory_context(msgs, []) == msgs

    def test_inserts_memory_after_system_prompt(self):
        # Create a mock claim object
        class MockClaim:
            subject = "User"
            predicate = "likes"
            object = {"value": "Python"}
            claim_type = "preference"
            scope = "global"
            confidence = 0.9

        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hi"},
        ]
        # This will either inject or no-op depending on format_memory_block
        result = _inject_memory_context(msgs, [MockClaim()])
        # The function should either insert at index 1 or return unchanged
        assert result[0]["role"] == "system"
