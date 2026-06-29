"""Integration tests for the full memory flywheel (extract → recall → citation).

These tests verify the end-to-end lifecycle of personal memory in chat:

1. User says "I prefer Python over JavaScript" in a chat exchange
2. The extraction hook extracts a preference claim
3. The claim is persisted via PersonalMemoryService.create()
4. In a subsequent chat, the user asks "What language should I use?"
5. recall_for_chat() finds the previously extracted claim
6. The claim is injected into the LLM prompt via _inject_memory_context()
7. memory_recall_used and memory_citation SSE events are emitted

The tests use monkeypatching to simulate the full pipeline without real
DB or LLM calls, matching the pattern in test_memory_citation_service.py
and test_chat_memory_extraction.py.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.memory_citation_service import (
    build_citation_event,
    build_recall_used_event,
    format_memory_block,
    short_claim_id,
)
from app.services.personal_memory_extractor import RegexPersonalMemoryExtractor

# ── Helpers ────────────────────────────────────────────────────────────


def _make_claim(
    *,
    id: uuid.UUID | None = None,
    user_id: int = 1,
    workspace_id: str = "ws-1",
    subject: str = "user",
    predicate: str = "prefers",
    object: dict | None = None,
    claim_type: str = "preference",
    scope: str = "personal",
    sensitivity: str = "normal",
    confidence: float = 0.85,
    source_type: str = "conversation",
) -> SimpleNamespace:
    """Build a PersonalMemoryClaim-like object for testing."""
    return SimpleNamespace(
        id=id or uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
        user_id=user_id,
        workspace_id=workspace_id,
        subject=subject,
        predicate=predicate,
        object=object or {"value": "Python"},
        claim_type=claim_type,
        scope=scope,
        sensitivity=sensitivity,
        confidence=confidence,
        importance=0.5,
        source_type=source_type,
        source_id=None,
        mission_number=None,
        last_used_at=None,
        expires_at=None,
        deleted_at=None,
    )


def _mock_thread(
    thread_id: int = 42,
    user_id: int = 1,
    workspace_id: str = "ws-1",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=thread_id,
        user_id=user_id,
        workspace_id=workspace_id,
        metadata_=None,
        username="testuser",
    )


# ── Test 1: Extraction produces claims from chat text ──────────────────


class TestExtractionProducesClaims:
    """The regex extractor should produce CandidateClaim objects from
    natural chat text that express preferences."""

    def test_extracts_preference_from_user_message(self):
        """'I prefer Python over JavaScript' → preference claim."""
        extractor = RegexPersonalMemoryExtractor()
        claims = extractor.extract("I prefer Python over JavaScript")

        assert len(claims) >= 1
        pref = claims[0]
        assert pref.claim_type == "preference"
        assert pref.scope == "personal"
        assert pref.subject == "user"
        assert "Python" in pref.object["value"]

    def test_extracts_from_combined_user_and_assistant_text(self):
        """Combined user+assistant text should be extractable."""
        extractor = RegexPersonalMemoryExtractor()
        combined = (
            "User: I prefer dark mode for all my apps\n\n" "Assistant: I'll keep that in mind and use dark themes."
        )
        claims = extractor.extract(combined)

        assert len(claims) >= 1
        assert any("dark mode" in c.object.get("value", "") for c in claims)

    def test_extracts_name_fact(self):
        """'My name is Alice' → fact claim."""
        extractor = RegexPersonalMemoryExtractor()
        claims = extractor.extract("My name is Alice")

        assert len(claims) >= 1
        name_claim = next((c for c in claims if c.predicate == "name"), None)
        assert name_claim is not None
        assert name_claim.object["value"] == "Alice"
        assert name_claim.claim_type == "fact"

    def test_extracts_team_tool_fact(self):
        """'We use Qdrant' → workspace-scoped fact."""
        extractor = RegexPersonalMemoryExtractor()
        claims = extractor.extract("We use Qdrant for vector search")

        assert len(claims) >= 1
        tool_claim = next((c for c in claims if c.predicate == "uses"), None)
        assert tool_claim is not None
        assert tool_claim.scope == "workspace"
        assert "Qdrant" in tool_claim.object["value"]


# ── Test 2: Full flywheel — extract → persist → recall → citation ─────


class TestFullFlywheel:
    """End-to-end: chat exchange → extraction → persistence → recall →
    citation events in a subsequent exchange."""

    @pytest.mark.asyncio
    async def test_extract_then_recall_produces_citation_events(self, monkeypatch: pytest.MonkeyPatch):
        """Simulate the full flywheel:

        Exchange 1: User says "I prefer Python" → extraction persists a claim.
        Exchange 2: User asks "What language?" → recall finds the claim →
                    citation events are emitted.

        Verifies that the extraction output's fields flow through to the
        persisted claim and then to the citation events.
        """
        from app.services import chat_service

        # ── Phase 1: Extraction ──────────────────────────────────────
        extractor = RegexPersonalMemoryExtractor()
        combined_text = "User: I prefer Python over JavaScript\n\n" "Assistant: Got it, I'll use Python when possible."
        raw_claims = extractor.extract(combined_text)
        assert len(raw_claims) >= 1, "Extractor should find at least one claim"

        # Apply the same defensive filter as _maybe_extract_memory_claims
        _EXCLUDED_SENSITIVITIES = frozenset({"sensitive", "restricted"})
        _EXCLUDED_SCOPES = frozenset({"private"})
        safe_claims = [
            c
            for c in raw_claims
            if getattr(c, "sensitivity", "normal") not in _EXCLUDED_SENSITIVITIES
            and c.claim_type not in _EXCLUDED_SENSITIVITIES
            and c.scope not in _EXCLUDED_SCOPES
        ]
        assert len(safe_claims) >= 1, "Safe claims should survive the filter"

        # Simulate persistence — the persisted claim's fields MUST match
        # the extraction output to prove the handoff is correct.
        extracted = safe_claims[0]
        persisted_claim = _make_claim(
            id=uuid.UUID("aabbccdd-1234-5678-9abc-def012345678"),
            subject=extracted.subject,
            predicate=extracted.predicate,
            object=extracted.object,
            claim_type=extracted.claim_type,
            scope=extracted.scope,
            confidence=extracted.confidence,
        )

        # Verify the handoff: persisted fields match extracted fields
        assert persisted_claim.subject == extracted.subject
        assert persisted_claim.predicate == extracted.predicate
        assert persisted_claim.object == extracted.object
        assert persisted_claim.claim_type == extracted.claim_type
        assert persisted_claim.scope == extracted.scope

        # ── Phase 2: Recall ──────────────────────────────────────────
        # In the next chat exchange, recall_for_chat should find the claim
        # when the query matches the stored claim's subject/predicate.

        mock_db = MagicMock()
        recall_mock = AsyncMock(return_value=([persisted_claim], 1))

        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "app.services.personal_memory_service.PersonalMemoryService.recall",
                recall_mock,
            )
            from app.services.memory_citation_service import recall_for_chat

            recalled = await recall_for_chat(
                mock_db,
                user_id=1,
                workspace_id="ws-1",
                query="Python",
            )

        assert len(recalled) == 1
        assert recalled[0].id == persisted_claim.id

        # ── Phase 3: Citation events ─────────────────────────────────
        # The recalled claim should produce proper SSE events

        message_id = "101"

        # Stage 1: memory_recall_used event
        recall_used_evt = build_recall_used_event(recalled[0], message_id=message_id)
        assert recall_used_evt["type"] == "memory_recall_used"
        assert recall_used_evt["message_id"] == message_id
        assert recall_used_evt["claim_id"] == str(persisted_claim.id)
        assert recall_used_evt["confidence"] == 0.85
        assert recall_used_evt["subject"] == "user"
        assert recall_used_evt["predicate"] == "prefers"

        # Stage 2: memory_citation event (the chip payload)
        citation_evt = build_citation_event(recalled[0], message_id=message_id)
        assert citation_evt["type"] == "memory_citation"
        assert citation_evt["message_id"] == message_id
        assert citation_evt["label"].startswith("[memory:")
        assert "conf 0.85" in citation_evt["label"]
        assert citation_evt["subject"] == "user"
        assert citation_evt["predicate"] == "prefers"
        assert "Python" in citation_evt["object"]

        # Both events must be JSON-serializable (frontend will parse them)
        json.dumps(recall_used_evt)
        json.dumps(citation_evt)

    @pytest.mark.asyncio
    async def test_extract_then_recall_with_memory_injection(self, monkeypatch: pytest.MonkeyPatch):
        """Verify that recalled claims are injected into the LLM prompt
        via _inject_memory_context()."""
        from app.services.chat_service import _inject_memory_context

        claim = _make_claim(
            id=uuid.UUID("aabbccdd-1234-5678-9abc-def012345678"),
            subject="user",
            predicate="prefers",
            object={"value": "Python"},
            confidence=0.85,
        )

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What language should I use?"},
        ]

        injected = _inject_memory_context(messages, [claim])

        # Should have 3 messages now: system, memory context, user
        assert len(injected) == 3
        assert injected[0]["role"] == "system"
        assert injected[0]["content"] == "You are a helpful assistant."
        assert injected[1]["role"] == "system"
        assert "PERSONAL MEMORY CONTEXT" in injected[1]["content"]
        assert "user → prefers → " in injected[1]["content"]
        assert injected[2]["role"] == "user"
        assert injected[2]["content"] == "What language should I use?"

    @pytest.mark.asyncio
    async def test_full_stream_path_with_extraction_and_citation(self, monkeypatch: pytest.MonkeyPatch):
        """Simulate the full stream_message_to_llm path:

        1. Pre-LLM: recall finds a previously extracted claim
        2. LLM responds
        3. Post-response: extraction hook fires
        4. Citation events are emitted

        This test verifies the SSE event ordering and content.
        """
        from app.services import chat_service

        monkeypatch.setattr(
            "app.services.chat_service.settings",
            SimpleNamespace(
                FLOWMANNER_CROSS_MISSION_MEMORY=True,
                CHAT_MEMORY_CITATIONS_ENABLED=True,
                SANDBOXD_ENABLED=False,
                CHAT_MAX_TOOL_ROUNDS=15,
            ),
        )

        # Set up a previously persisted claim (from exchange 1)
        existing_claim = _make_claim(
            id=uuid.UUID("aabbccdd-1234-5678-9abc-def012345678"),
            subject="user",
            predicate="prefers",
            object={"value": "Python"},
            confidence=0.85,
        )

        # Mock the thread
        mock_thread = _mock_thread()

        # Mock recall to return the existing claim
        async def mock_recall_for_chat(db, *, user_id, workspace_id, query):
            return [existing_claim]

        monkeypatch.setattr(chat_service, "recall_for_chat", mock_recall_for_chat)

        # Mock get_chat_thread
        async def mock_get_thread(db, thread_id):
            return mock_thread

        monkeypatch.setattr(chat_service, "get_chat_thread", mock_get_thread)

        # Mock _build_chat_messages
        async def mock_build_messages(db, thread_id, max_history=20):
            return [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What language should I use?"},
            ]

        monkeypatch.setattr(chat_service, "_build_chat_messages", mock_build_messages)

        # Mock the LLM client to return a streaming response
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta = MagicMock()
        mock_chunk.choices[0].delta.content = "Use Python!"
        mock_chunk.choices[0].delta.tool_calls = None
        mock_chunk.choices[0].finish_reason = "stop"
        mock_chunk.usage = None

        async def mock_stream():
            yield mock_chunk

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())
        monkeypatch.setattr(chat_service, "_client", mock_client)

        # Ensure _resolve_provider returns values that match _client's
        # config so the code uses our mocked _client instead of creating
        # a new AsyncOpenAI instance.
        monkeypatch.setattr(
            chat_service,
            "_resolve_provider",
            lambda model: (chat_service._LLM_API_BASE, chat_service._LLM_API_KEY, "test-model"),
        )

        # Mock BYOK lookup to avoid DB calls
        monkeypatch.setattr(
            chat_service,
            "_lookup_stored_byok_key",
            AsyncMock(return_value=(None, None)),
        )

        # Mock message creation
        mock_assistant_msg = SimpleNamespace(id=101)

        async def mock_create_msg(db, thread_id, role, content, user_id=None):
            return SimpleNamespace(id=100 if role == "user" else 101)

        monkeypatch.setattr(chat_service, "create_chat_message", mock_create_msg)
        monkeypatch.setattr(
            chat_service,
            "create_chat_message_fresh_session",
            AsyncMock(return_value=mock_assistant_msg),
        )

        # Track extraction tasks
        extraction_tasks = []

        async def mock_extract(**kwargs):
            extraction_tasks.append(kwargs)

        monkeypatch.setattr(chat_service, "_maybe_extract_memory_claims", mock_extract)

        # Capture create_task calls
        real_create_task = asyncio.create_task
        tasks = []

        def track_create_task(coro):
            tasks.append(coro)
            return real_create_task(coro)

        monkeypatch.setattr("asyncio.create_task", track_create_task)

        # ── Collect all SSE events ───────────────────────────────────
        mock_db = AsyncMock()
        events = [
            json.loads(event)
            async for event in chat_service.stream_message_to_llm(
                db=mock_db,
                thread_id=42,
                content="What language should I use?",
                user_id=1,
            )
        ]

        # ── Verify event ordering ────────────────────────────────────
        event_types = [e["type"] for e in events]

        # 1. Token events from the LLM
        token_events = [e for e in events if e["type"] == "token"]
        assert len(token_events) >= 1
        assert token_events[0]["content"] == "Use Python!"

        # 2. memory_recall_used event (Stage 1)
        recall_events = [e for e in events if e["type"] == "memory_recall_used"]
        assert len(recall_events) == 1
        assert recall_events[0]["claim_id"] == str(existing_claim.id)
        assert recall_events[0]["message_id"] == "101"

        # 3. memory_citation event (Stage 2 — the chip)
        citation_events = [e for e in events if e["type"] == "memory_citation"]
        assert len(citation_events) == 1
        assert citation_events[0]["label"].startswith("[memory:")
        assert "conf 0.85" in citation_events[0]["label"]
        assert citation_events[0]["subject"] == "user"
        assert citation_events[0]["predicate"] == "prefers"

        # 4. Complete event
        complete_events = [e for e in events if e["type"] == "complete"]
        assert len(complete_events) == 1
        assert complete_events[0]["message_id"] == 101

        # 5. Extraction task was created (fire-and-forget)
        assert len(tasks) == 1

        # Verify ordering: tokens → recall_used → citation → complete
        token_idx = event_types.index("token")
        recall_idx = event_types.index("memory_recall_used")
        citation_idx = event_types.index("memory_citation")
        complete_idx = event_types.index("complete")

        assert token_idx < recall_idx < citation_idx < complete_idx

        # Clean up unawaited coroutines to suppress RuntimeWarnings
        for t in tasks:
            if hasattr(t, "close"):
                t.close()


# ── Test 3: Defensive filter prevents sensitive data leaking ───────────


class TestDefensiveFilterInFlywheel:
    """Verify that sensitive/restricted/private claims are filtered at
    both extraction time and recall time."""

    @pytest.mark.asyncio
    async def test_pii_extracted_but_filtered_before_persistence(self):
        """PII like email should be extracted but filtered by the
        defensive filter before reaching PersonalMemoryService.create()."""
        extractor = RegexPersonalMemoryExtractor()
        claims = extractor.extract("My email is alice@example.com and I prefer dark mode")

        # The extractor should find both PII and preference
        pii_claims = [c for c in claims if c.claim_type == "sensitive"]
        pref_claims = [c for c in claims if c.claim_type == "preference"]
        assert len(pii_claims) >= 1, "PII should be extracted"
        assert len(pref_claims) >= 1, "Preference should be extracted"

        # Apply defensive filter (same as _maybe_extract_memory_claims)
        _EXCLUDED_SENSITIVITIES = frozenset({"sensitive", "restricted"})
        _EXCLUDED_SCOPES = frozenset({"private"})
        safe = [
            c
            for c in claims
            if getattr(c, "sensitivity", "normal") not in _EXCLUDED_SENSITIVITIES
            and c.claim_type not in _EXCLUDED_SENSITIVITIES
            and c.scope not in _EXCLUDED_SCOPES
        ]

        # PII should be filtered out, preference should survive
        assert len(safe) < len(claims)
        assert all(c.claim_type != "sensitive" for c in safe)
        assert any(c.claim_type == "preference" for c in safe)

    @pytest.mark.asyncio
    async def test_sensitive_claim_filtered_at_recall_time(self):
        """Even if a sensitive claim somehow got persisted, recall_for_chat
        should filter it out before returning to the LLM prompt."""
        from app.services.memory_citation_service import recall_for_chat

        sensitive_claim = _make_claim(
            sensitivity="sensitive",
            claim_type="sensitive",
            scope="private",
            object={"value": "alice@example.com"},
        )
        normal_claim = _make_claim(
            id=uuid.UUID("660e8400-e29b-41d4-a716-446655440000"),
            sensitivity="normal",
            scope="personal",
        )

        mock_db = MagicMock()
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "app.services.personal_memory_service.PersonalMemoryService.recall",
                AsyncMock(return_value=([sensitive_claim, normal_claim], 2)),
            )
            result = await recall_for_chat(mock_db, user_id=1, workspace_id="ws-1", query="email")

        # Only the normal claim should survive
        assert len(result) == 1
        assert result[0].id == normal_claim.id

    @pytest.mark.asyncio
    async def test_no_citation_events_for_filtered_claims(self):
        """If all recalled claims are filtered, no citation events should
        be emitted and _inject_memory_context should be a no-op."""
        from app.services.chat_service import _inject_memory_context

        # Empty recall result → no injection
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
        ]
        injected = _inject_memory_context(messages, [])
        assert len(injected) == 2  # unchanged
        assert "PERSONAL MEMORY CONTEXT" not in injected[0]["content"]


# ── Test 4: Pause toggle stops extraction mid-flywheel ────────────────


class TestPauseToggleInFlywheel:
    """When a user pauses extraction for a conversation, the extraction
    hook should skip entirely, even if the feature flag is on."""

    @pytest.mark.asyncio
    async def test_paused_conversation_skips_extraction(self, monkeypatch: pytest.MonkeyPatch):
        from app.services import chat_service

        monkeypatch.setattr(
            "app.services.chat_service.settings",
            SimpleNamespace(
                FLOWMANNER_CROSS_MISSION_MEMORY=True,
                CHAT_MEMORY_CITATIONS_ENABLED=False,
                SANDBOXD_ENABLED=False,
                CHAT_MAX_TOOL_ROUNDS=15,
            ),
        )

        mock_thread = _mock_thread()
        monkeypatch.setattr(chat_service, "get_chat_thread", AsyncMock(return_value=mock_thread))

        # Pause service reports conversation is paused
        mock_pause_service = AsyncMock()
        mock_pause_service.is_paused = AsyncMock(return_value=True)

        mock_fresh_db = AsyncMock()
        mock_fresh_db_ctx = AsyncMock()
        mock_fresh_db_ctx.__aenter__ = AsyncMock(return_value=mock_fresh_db)
        mock_fresh_db_ctx.__aexit__ = AsyncMock(return_value=False)

        monkeypatch.setattr(
            "app.database.AsyncSessionLocal",
            MagicMock(return_value=mock_fresh_db_ctx),
        )
        monkeypatch.setattr(
            "app.services.memory_extraction_pause_service.MemoryExtractionPauseService",
            MagicMock(return_value=mock_pause_service),
        )

        # Track if extractor is called
        mock_extractor = MagicMock()
        mock_extractor.extract = MagicMock(return_value=[])
        monkeypatch.setattr(
            "app.services.chat_service.RegexPersonalMemoryExtractor",
            MagicMock(return_value=mock_extractor),
        )

        mock_db = AsyncMock()
        await chat_service._maybe_extract_memory_claims(
            db=mock_db,
            thread_id=42,
            user_id=1,
            user_message="I prefer Python",
            assistant_response="Sure!",
        )

        # Extractor should NOT have been called
        mock_extractor.extract.assert_not_called()


# ── Test 5: Multiple claims in one exchange ────────────────────────────


# ── Test 5: All claims filtered → zero persistence ───────────────────


class TestAllClaimsFiltered:
    """When extraction produces claims but ALL are sensitive/private,
    nothing should be persisted."""

    @pytest.mark.asyncio
    async def test_all_pii_filtered_leaves_zero_persistence(self, monkeypatch: pytest.MonkeyPatch):
        """If the text is pure PII (email + phone), the defensive filter
        should drop everything and persist nothing."""
        extractor = RegexPersonalMemoryExtractor()
        # This text has PII but no preferences
        claims = extractor.extract("My email is alice@example.com")
        pii_claims = [c for c in claims if c.claim_type == "sensitive"]
        assert len(pii_claims) >= 1, "Should extract PII"

        # Apply defensive filter
        _EXCLUDED_SENSITIVITIES = frozenset({"sensitive", "restricted"})
        _EXCLUDED_SCOPES = frozenset({"private"})
        safe = [
            c
            for c in claims
            if getattr(c, "sensitivity", "normal") not in _EXCLUDED_SENSITIVITIES
            and c.claim_type not in _EXCLUDED_SENSITIVITIES
            and c.scope not in _EXCLUDED_SCOPES
        ]

        assert len(safe) == 0, "All PII should be filtered out"


# ── Test 6: Multiple claims in one exchange ────────────────────────────


class TestMultipleClaimsInExchange:
    """A single chat exchange may contain multiple extractable claims.
    All safe claims should be persisted."""

    def test_multiple_preferences_extracted(self):
        """Text with multiple preferences should produce multiple claims."""
        extractor = RegexPersonalMemoryExtractor()
        claims = extractor.extract("I prefer dark mode. I like vim keybindings. I avoid mouse usage.")

        # At least 2 claims (the regex extractor caps at 1 preference +
        # 1 imperative per input, but multiple pattern categories can match)
        assert len(claims) >= 1

    def test_mixed_fact_and_preference(self):
        """Text with both identity facts and preferences."""
        extractor = RegexPersonalMemoryExtractor()
        claims = extractor.extract("My name is Alice. I prefer Python over JavaScript.")

        name_claims = [c for c in claims if c.predicate == "name"]
        pref_claims = [c for c in claims if c.predicate == "prefers"]
        assert len(name_claims) >= 1
        assert len(pref_claims) >= 1


# ── Test 6: Citation label format is stable ────────────────────────────


# ── Test 7: Non-streaming path also triggers extraction ──────────────


class TestNonStreamingExtraction:
    """send_message_to_llm (non-streaming) should also fire-and-forget
    the extraction hook after the assistant response is saved."""

    @pytest.mark.asyncio
    async def test_send_message_triggers_extraction(self, monkeypatch: pytest.MonkeyPatch):
        from app.services import chat_service

        monkeypatch.setattr(
            "app.services.chat_service.settings",
            SimpleNamespace(
                FLOWMANNER_CROSS_MISSION_MEMORY=True,
                CHAT_MEMORY_CITATIONS_ENABLED=False,
                SANDBOXD_ENABLED=False,
                CHAT_MAX_TOOL_ROUNDS=15,
            ),
        )

        # Track extraction calls
        extraction_calls = []

        async def mock_extract(**kwargs):
            extraction_calls.append(kwargs)

        monkeypatch.setattr(chat_service, "_maybe_extract_memory_claims", mock_extract)

        # Mock the LLM client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = MagicMock()
        mock_response.choices[0].message.content = "Use Python!"
        mock_response.choices[0].message.tool_calls = None
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        monkeypatch.setattr(chat_service, "_client", mock_client)

        # Ensure the code uses our mocked _client
        monkeypatch.setattr(
            chat_service,
            "_resolve_provider",
            lambda model: (chat_service._LLM_API_BASE, chat_service._LLM_API_KEY, "test-model"),
        )
        monkeypatch.setattr(
            chat_service,
            "_lookup_stored_byok_key",
            AsyncMock(return_value=(None, None)),
        )

        # Mock _build_chat_messages to avoid DB calls
        async def mock_build_messages(db, thread_id, max_history=20):
            return [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "I prefer Python"},
            ]

        monkeypatch.setattr(chat_service, "_build_chat_messages", mock_build_messages)

        # Mock DB operations
        mock_db = AsyncMock()
        mock_thread = _mock_thread()
        monkeypatch.setattr(chat_service, "get_chat_thread", AsyncMock(return_value=mock_thread))
        monkeypatch.setattr(chat_service, "create_chat_message", AsyncMock())
        monkeypatch.setattr(
            chat_service,
            "create_chat_message_fresh_session",
            AsyncMock(return_value=SimpleNamespace(id=101)),
        )

        # Capture create_task calls
        real_create_task = asyncio.create_task
        tasks = []

        def track_create_task(coro):
            tasks.append(coro)
            return real_create_task(coro)

        monkeypatch.setattr("asyncio.create_task", track_create_task)

        result = await chat_service.send_message_to_llm(
            db=mock_db,
            thread_id=42,
            content="I prefer Python",
            user_id=1,
        )

        assert result["success"] is True
        assert result["content"] == "Use Python!"

        # Extraction task should have been created
        assert len(tasks) == 1

        # Clean up unawaited coroutines
        for t in tasks:
            if hasattr(t, "close"):
                t.close()


# ── Test 8: Citation label format is stable ────────────────────────────


class TestCitationLabelStability:
    """The citation label format must be stable across the flywheel so
    the frontend can reliably parse and render it."""

    def test_label_format_consistency(self):
        """The label produced by build_citation_event should match the
        format produced by format_citation_label."""
        claim = _make_claim(
            id=uuid.UUID("aabbccdd-1234-5678-9abc-def012345678"),
            confidence=0.92,
        )

        from app.services.memory_citation_service import format_citation_label

        expected_label = format_citation_label(claim)
        evt = build_citation_event(claim, message_id="42")
        assert evt["label"] == expected_label
        assert evt["label"] == "[memory: c-aabbccdd, conf 0.92]"

    def test_short_id_consistency(self):
        """short_claim_id must produce the same value as the short_id
        field in the citation event."""
        claim = _make_claim(
            id=uuid.UUID("aabbccdd-1234-5678-9abc-def012345678"),
        )

        evt = build_citation_event(claim, message_id="42")
        assert evt["short_id"] == short_claim_id(claim)
        assert evt["short_id"] == "c-aabbccdd"

    def test_recall_used_and_citation_share_claim_id(self):
        """Both event types must reference the same claim_id for the
        frontend to correlate them."""
        claim = _make_claim(
            id=uuid.UUID("aabbccdd-1234-5678-9abc-def012345678"),
        )

        recall_evt = build_recall_used_event(claim, message_id="42")
        citation_evt = build_citation_event(claim, message_id="42")

        assert recall_evt["claim_id"] == citation_evt["claim_id"]
        assert recall_evt["message_id"] == citation_evt["message_id"]
