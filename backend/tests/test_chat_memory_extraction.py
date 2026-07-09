"""TDD tests for post-chat memory extraction hook (Gap 1).

The chat_service should fire-and-forget a RegexPersonalMemoryExtractor call
after each assistant response, persisting candidate claims as
``source_type="conversation"`` via PersonalMemoryService.create().

Tests use monkeypatching to isolate the extraction hook from the DB layer,
matching the pattern in test_memory_citation_service.py.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Helpers ────────────────────────────────────────────────────────────


def _candidate_claim(
    *,
    subject: str = "user",
    predicate: str = "prefers",
    value: str = "dark mode",
    claim_type: str = "preference",
    scope: str = "personal",
    confidence: float = 0.85,
    rationale: str | None = None,
) -> SimpleNamespace:
    """Build a minimal CandidateClaim-like object."""
    return SimpleNamespace(
        subject=subject,
        predicate=predicate,
        object={"value": value},
        claim_type=claim_type,
        scope=scope,
        confidence=confidence,
        rationale=rationale,
    )


def _sensitive_claim() -> SimpleNamespace:
    """A claim that should be filtered by the defensive filter."""
    return _candidate_claim(
        subject="user",
        predicate="has_email",
        value="alice@example.com",
        claim_type="sensitive",
        scope="private",
        confidence=0.7,
    )


def _mock_thread(workspace_id: str = "ws-1") -> SimpleNamespace:
    return SimpleNamespace(
        id=42,
        workspace_id=workspace_id,
        user_id=1,
    )


# ── Tests ──────────────────────────────────────────────────────────────


class TestExtractionSkippedWhenFlagOff:
    """When FLOWMANNER_CROSS_MISSION_MEMORY=False, extraction must not run."""

    async def test_no_extraction_when_flag_off(self, monkeypatch: pytest.MonkeyPatch):
        """RegexPersonalMemoryExtractor.extract must NOT be called when flag is off."""
        from app.services import chat_service

        monkeypatch.setattr(
            "app.services.chat_service.settings",
            SimpleNamespace(
                FLOWMANNER_CROSS_MISSION_MEMORY=False,
                CHAT_MEMORY_CITATIONS_ENABLED=False,
                SANDBOXD_ENABLED=False,
                CHAT_MAX_TOOL_ROUNDS=15,
            ),
        )

        mock_db = AsyncMock()
        # _maybe_extract_memory_claims should return immediately without
        # touching the DB or calling the extractor.
        await chat_service._maybe_extract_memory_claims(
            db=mock_db,
            thread_id=42,
            user_id=1,
            user_message="I prefer Python",
            assistant_response="Sure, I'll use Python.",
        )


class TestExtractionSkippedWhenPaused:
    """When the conversation is paused, extraction must not run."""

    async def test_no_extraction_when_paused(self, monkeypatch: pytest.MonkeyPatch):
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

        # Mock pause service to report conversation is paused
        mock_pause_service = AsyncMock()
        mock_pause_service.is_paused = AsyncMock(return_value=True)

        # Set up the fresh DB session
        mock_fresh_db = AsyncMock()
        mock_fresh_db_ctx = AsyncMock()
        mock_fresh_db_ctx.__aenter__ = AsyncMock(return_value=mock_fresh_db)
        mock_fresh_db_ctx.__aexit__ = AsyncMock(return_value=False)

        # Patch at the correct import locations. The function imports
        # AsyncSessionLocal locally and MemoryExtractionPauseService locally.
        # We need to patch the *modules* they come from, not chat_service.
        monkeypatch.setattr(
            "app.database.AsyncSessionLocal",
            MagicMock(return_value=mock_fresh_db_ctx),
        )
        monkeypatch.setattr(
            "app.services.memory_extraction_pause_service.MemoryExtractionPauseService",
            MagicMock(return_value=mock_pause_service),
        )

        # Also need to patch get_chat_thread used inside the function
        # (it's called on fresh_db, not the original db).
        monkeypatch.setattr(chat_service, "get_chat_thread", AsyncMock(return_value=mock_thread))

        # Patch the regex extractor to track if it's called
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
            assistant_response="Sure, I'll use Python.",
        )

        # Extraction should NOT have been called (paused)
        mock_extractor.extract.assert_not_called()


class TestExtractionPersistsClaims:
    """When the flag is ON and not paused, claims should be persisted."""

    async def test_claims_persisted_via_create(self, monkeypatch: pytest.MonkeyPatch):
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

        # Not paused
        mock_pause_service = AsyncMock()
        mock_pause_service.is_paused = AsyncMock(return_value=False)

        # Mock PersonalMemoryService with a create that returns a mock claim
        mock_pm_service = AsyncMock()
        mock_pm_service.create = AsyncMock(return_value=SimpleNamespace(id="claim-1"))

        # Set up the fresh DB session
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
        monkeypatch.setattr(
            "app.services.personal_memory_service.PersonalMemoryService",
            MagicMock(return_value=mock_pm_service),
        )
        mock_review_service = AsyncMock()
        mock_review_service.stage_pending_write = AsyncMock(return_value="pw-1")
        monkeypatch.setattr(chat_service, "get_chat_thread", AsyncMock(return_value=mock_thread))
        monkeypatch.setattr(
            "app.services.memory.background_review_service.BackgroundReviewService",
            MagicMock(return_value=mock_review_service),
        )

        # Mock LLM extractor to return empty (falls through to regex)
        mock_llm_extractor = AsyncMock()
        mock_llm_extractor.extract_with_fallback = AsyncMock(return_value=([], "empty"))
        monkeypatch.setattr(
            "app.services.chat_service.PersonalMemoryExtractor",
            MagicMock(return_value=mock_llm_extractor),
        )
        monkeypatch.setattr(
            "app.services.model_router.get_model_router",
            MagicMock(return_value=MagicMock()),
        )

        # Mock regex extractor to return 2 claims
        claims = [
            _candidate_claim(predicate="prefers", value="dark mode"),
            _candidate_claim(predicate="likes", value="vim keybindings"),
        ]
        mock_extractor = MagicMock()
        mock_extractor.extract = MagicMock(return_value=claims)
        monkeypatch.setattr(
            "app.services.chat_service.RegexPersonalMemoryExtractor",
            MagicMock(return_value=mock_extractor),
        )

        mock_db = AsyncMock()
        await chat_service._maybe_extract_memory_claims(
            db=mock_db,
            thread_id=42,
            user_id=1,
            user_message="I prefer dark mode and like vim keybindings",
            assistant_response="Got it, noted!",
        )

        # Per the GOV-1.2 provenance gate, conversation-sourced claims are
        # staged for HITL approval (not direct-written). Both claims stage.
        assert mock_review_service.stage_pending_write.call_count == 2
        assert mock_pm_service.create.call_count == 0


class TestTeamWorkspaceStaging:
    """Team workspaces should stage claims for approval, not direct-write."""

    async def test_team_workspace_stages_claims(self, monkeypatch: pytest.MonkeyPatch):
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

        mock_pause_service = AsyncMock()
        mock_pause_service.is_paused = AsyncMock(return_value=False)

        mock_pm_service = AsyncMock()
        mock_pm_service.create = AsyncMock(return_value=SimpleNamespace(id="claim-1"))

        # Mock review service to track staged writes
        mock_review_service = AsyncMock()
        mock_review_service.stage_pending_write = AsyncMock(return_value="pw-1")

        # Mock workspace that requires approval (team, >30 days)
        mock_workspace = SimpleNamespace(
            id="ws-1",
            member_count=5,
            created_at="2025-01-01T00:00:00Z",
            members=None,
        )

        mock_fresh_db = AsyncMock()
        mock_fresh_db_ctx = AsyncMock()
        mock_fresh_db_ctx.__aenter__ = AsyncMock(return_value=mock_fresh_db)
        mock_fresh_db_ctx.__aexit__ = AsyncMock(return_value=False)

        # Make the execute call return the workspace
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_workspace)
        mock_fresh_db.execute = AsyncMock(return_value=mock_result)

        monkeypatch.setattr(
            "app.database.AsyncSessionLocal",
            MagicMock(return_value=mock_fresh_db_ctx),
        )
        monkeypatch.setattr(
            "app.services.memory_extraction_pause_service.MemoryExtractionPauseService",
            MagicMock(return_value=mock_pause_service),
        )
        monkeypatch.setattr(
            "app.services.personal_memory_service.PersonalMemoryService",
            MagicMock(return_value=mock_pm_service),
        )
        monkeypatch.setattr(
            "app.services.memory.background_review_service.BackgroundReviewService",
            MagicMock(return_value=mock_review_service),
        )

        # Mock LLM extractor to return empty (falls through to regex)
        mock_llm_extractor = AsyncMock()
        mock_llm_extractor.extract_with_fallback = AsyncMock(return_value=([], "empty"))
        monkeypatch.setattr(
            "app.services.chat_service.PersonalMemoryExtractor",
            MagicMock(return_value=mock_llm_extractor),
        )
        monkeypatch.setattr(
            "app.services.model_router.get_model_router",
            MagicMock(return_value=MagicMock()),
        )

        # Regex returns 2 claims
        claims = [
            _candidate_claim(predicate="prefers", value="dark mode"),
            _candidate_claim(predicate="likes", value="vim"),
        ]
        mock_extractor = MagicMock()
        mock_extractor.extract = MagicMock(return_value=claims)
        monkeypatch.setattr(
            "app.services.chat_service.RegexPersonalMemoryExtractor",
            MagicMock(return_value=mock_extractor),
        )

        mock_db = AsyncMock()
        await chat_service._maybe_extract_memory_claims(
            db=mock_db,
            thread_id=42,
            user_id=1,
            user_message="I prefer dark mode and like vim",
            assistant_response="Noted!",
        )

        # Claims should be STAGED, not directly written
        assert mock_review_service.stage_pending_write.call_count == 2
        assert mock_pm_service.create.call_count == 0

    async def test_solo_workspace_direct_writes(self, monkeypatch: pytest.MonkeyPatch):
        """Solo workspaces (1 member) stage conversation-sourced claims for HITL approval.

        Per the GOV-1.2 provenance gate (chat_service.py:1768), every claim the
        chat extractor produces is source_type="conversation", which
        requires_provenance_approval() always returns True for. So even a solo
        workspace stages claims via BackgroundReviewService.stage_pending_write
        rather than direct-writing. Direct writes are only reachable from a
        user_explicit source_type, which the chat path never emits.
        """
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

        mock_pause_service = AsyncMock()
        mock_pause_service.is_paused = AsyncMock(return_value=False)

        mock_pm_service = AsyncMock()
        mock_pm_service.create = AsyncMock(return_value=SimpleNamespace(id="claim-1"))

        mock_review_service = AsyncMock()
        mock_review_service.stage_pending_write = AsyncMock(return_value="pw-1")

        # Mock workspace that does NOT require approval (solo)
        mock_workspace = SimpleNamespace(
            id="ws-1",
            member_count=1,
            created_at="2026-06-01T00:00:00Z",
            members=None,
        )

        mock_fresh_db = AsyncMock()
        mock_fresh_db_ctx = AsyncMock()
        mock_fresh_db_ctx.__aenter__ = AsyncMock(return_value=mock_fresh_db)
        mock_fresh_db_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_workspace)
        mock_fresh_db.execute = AsyncMock(return_value=mock_result)

        monkeypatch.setattr(
            "app.database.AsyncSessionLocal",
            MagicMock(return_value=mock_fresh_db_ctx),
        )
        monkeypatch.setattr(
            "app.services.memory_extraction_pause_service.MemoryExtractionPauseService",
            MagicMock(return_value=mock_pause_service),
        )
        monkeypatch.setattr(
            "app.services.personal_memory_service.PersonalMemoryService",
            MagicMock(return_value=mock_pm_service),
        )
        monkeypatch.setattr(
            "app.services.memory.background_review_service.BackgroundReviewService",
            MagicMock(return_value=mock_review_service),
        )

        mock_llm_extractor = AsyncMock()
        mock_llm_extractor.extract_with_fallback = AsyncMock(return_value=([], "empty"))
        monkeypatch.setattr(
            "app.services.chat_service.PersonalMemoryExtractor",
            MagicMock(return_value=mock_llm_extractor),
        )
        monkeypatch.setattr(
            "app.services.model_router.get_model_router",
            MagicMock(return_value=MagicMock()),
        )

        claims = [_candidate_claim(predicate="prefers", value="dark mode")]
        mock_extractor = MagicMock()
        mock_extractor.extract = MagicMock(return_value=claims)
        monkeypatch.setattr(
            "app.services.chat_service.RegexPersonalMemoryExtractor",
            MagicMock(return_value=mock_extractor),
        )

        mock_db = AsyncMock()
        await chat_service._maybe_extract_memory_claims(
            db=mock_db,
            thread_id=42,
            user_id=1,
            user_message="I prefer dark mode",
            assistant_response="Noted!",
        )

        # Conversation-sourced claims route to HITL staging, not direct write.
        assert mock_pm_service.create.call_count == 0
        assert mock_review_service.stage_pending_write.call_count == 1


class TestDefensiveFilterApplied:
    """Sensitive/restricted/private claims must be dropped before persistence."""

    async def test_sensitive_claims_filtered(self, monkeypatch: pytest.MonkeyPatch):
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

        mock_pause_service = AsyncMock()
        mock_pause_service.is_paused = AsyncMock(return_value=False)

        mock_pm_service = AsyncMock()
        mock_pm_service.create = AsyncMock(return_value=SimpleNamespace(id="claim-1"))

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
        monkeypatch.setattr(
            "app.services.personal_memory_service.PersonalMemoryService",
            MagicMock(return_value=mock_pm_service),
        )
        mock_review_service = AsyncMock()
        mock_review_service.stage_pending_write = AsyncMock(return_value="pw-1")
        monkeypatch.setattr(chat_service, "get_chat_thread", AsyncMock(return_value=mock_thread))
        monkeypatch.setattr(
            "app.services.memory.background_review_service.BackgroundReviewService",
            MagicMock(return_value=mock_review_service),
        )

        # Mock LLM extractor to return empty (falls through to regex)
        mock_llm_extractor = AsyncMock()
        mock_llm_extractor.extract_with_fallback = AsyncMock(return_value=([], "empty"))
        monkeypatch.setattr(
            "app.services.chat_service.PersonalMemoryExtractor",
            MagicMock(return_value=mock_llm_extractor),
        )
        monkeypatch.setattr(
            "app.services.model_router.get_model_router",
            MagicMock(return_value=MagicMock()),
        )

        # Mix of safe and sensitive claims
        claims = [
            _candidate_claim(predicate="prefers", value="dark mode", scope="personal"),
            _sensitive_claim(),  # should be filtered (sensitive + private)
            _candidate_claim(
                predicate="uses", value="Flowmanner", scope="private"
            ),  # should be filtered (private scope)
        ]
        mock_extractor = MagicMock()
        mock_extractor.extract = MagicMock(return_value=claims)
        monkeypatch.setattr(
            "app.services.chat_service.RegexPersonalMemoryExtractor",
            MagicMock(return_value=mock_extractor),
        )

        mock_db = AsyncMock()
        await chat_service._maybe_extract_memory_claims(
            db=mock_db,
            thread_id=42,
            user_id=1,
            user_message="My email is alice@example.com, I prefer dark mode",
            assistant_response="Noted!",
        )

        # Only the safe claim should be staged for HITL approval (1 of 3)
        assert mock_review_service.stage_pending_write.call_count == 1
        assert mock_pm_service.create.call_count == 0


class TestExtractionIsFireAndForget:
    """The extraction must NOT block the SSE stream (fire-and-forget)."""

    async def test_extraction_does_not_block_stream(self, monkeypatch: pytest.MonkeyPatch):
        """Verify _maybe_extract_memory_claims returns immediately."""
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

        mock_pause_service = AsyncMock()
        mock_pause_service.is_paused = AsyncMock(return_value=False)

        mock_pm_service = AsyncMock()
        mock_pm_service.create = AsyncMock(return_value=SimpleNamespace(id="claim-1"))

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
        monkeypatch.setattr(
            "app.services.personal_memory_service.PersonalMemoryService",
            MagicMock(return_value=mock_pm_service),
        )
        mock_review_service = AsyncMock()
        mock_review_service.stage_pending_write = AsyncMock(return_value="pw-1")
        monkeypatch.setattr(chat_service, "get_chat_thread", AsyncMock(return_value=mock_thread))
        monkeypatch.setattr(
            "app.services.memory.background_review_service.BackgroundReviewService",
            MagicMock(return_value=mock_review_service),
        )

        # Mock LLM extractor to return empty (falls through to regex)
        mock_llm_extractor = AsyncMock()
        mock_llm_extractor.extract_with_fallback = AsyncMock(return_value=([], "empty"))
        monkeypatch.setattr(
            "app.services.chat_service.PersonalMemoryExtractor",
            MagicMock(return_value=mock_llm_extractor),
        )
        monkeypatch.setattr(
            "app.services.model_router.get_model_router",
            MagicMock(return_value=MagicMock()),
        )

        mock_extractor = MagicMock()
        mock_extractor.extract = MagicMock(return_value=[_candidate_claim()])
        monkeypatch.setattr(
            "app.services.chat_service.RegexPersonalMemoryExtractor",
            MagicMock(return_value=mock_extractor),
        )

        mock_db = AsyncMock()
        # The function should return without blocking
        await chat_service._maybe_extract_memory_claims(
            db=mock_db,
            thread_id=42,
            user_id=1,
            user_message="I prefer Python",
            assistant_response="Sure!",
        )

        # If we got here without hanging, the call completed.
        # Conversation-sourced claim stages for HITL approval.
        assert mock_review_service.stage_pending_write.call_count == 1
        assert mock_pm_service.create.call_count == 0


class TestExtractionSkipsWhenNoWorkspace:
    """Threads without workspace_id should skip extraction."""

    async def test_no_workspace_skips(self, monkeypatch: pytest.MonkeyPatch):
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

        mock_thread = _mock_thread(workspace_id=None)
        monkeypatch.setattr(chat_service, "get_chat_thread", AsyncMock(return_value=mock_thread))

        mock_pm_service = AsyncMock()
        mock_pm_service.create = AsyncMock()

        mock_fresh_db = AsyncMock()
        mock_fresh_db_ctx = AsyncMock()
        mock_fresh_db_ctx.__aenter__ = AsyncMock(return_value=mock_fresh_db)
        mock_fresh_db_ctx.__aexit__ = AsyncMock(return_value=False)

        monkeypatch.setattr(
            "app.database.AsyncSessionLocal",
            MagicMock(return_value=mock_fresh_db_ctx),
        )

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

        # No extraction should happen
        mock_extractor.extract.assert_not_called()
        mock_pm_service.create.assert_not_called()


class TestExtractionErrorDoesNotPropagate:
    """Errors in extraction must be swallowed (fire-and-forget semantics)."""

    async def test_error_swallowed(self, monkeypatch: pytest.MonkeyPatch):
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

        # Make get_chat_thread raise
        monkeypatch.setattr(
            chat_service,
            "get_chat_thread",
            AsyncMock(side_effect=RuntimeError("DB connection lost")),
        )

        mock_db = AsyncMock()
        # Should NOT raise
        await chat_service._maybe_extract_memory_claims(
            db=mock_db,
            thread_id=42,
            user_id=1,
            user_message="I prefer Python",
            assistant_response="Sure!",
        )


class TestLLMExtractionWithFallback:
    """Verify the LLM-first extraction path with regex fallback."""

    async def test_llm_extraction_succeeds(self, monkeypatch: pytest.MonkeyPatch):
        """When LLM extraction succeeds, its claims are used."""
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

        mock_pause_service = AsyncMock()
        mock_pause_service.is_paused = AsyncMock(return_value=False)

        mock_pm_service = AsyncMock()
        mock_pm_service.create = AsyncMock(return_value=SimpleNamespace(id="claim-1"))

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
        monkeypatch.setattr(
            "app.services.personal_memory_service.PersonalMemoryService",
            MagicMock(return_value=mock_pm_service),
        )
        mock_review_service = AsyncMock()
        mock_review_service.stage_pending_write = AsyncMock(return_value="pw-1")
        monkeypatch.setattr(
            "app.services.memory.background_review_service.BackgroundReviewService",
            MagicMock(return_value=mock_review_service),
        )

        # Mock PersonalMemoryExtractor to return LLM-sourced claims
        llm_claims = [_candidate_claim(predicate="prefers", value="dark mode")]
        mock_llm_extractor = AsyncMock()
        mock_llm_extractor.extract_with_fallback = AsyncMock(return_value=(llm_claims, "llm"))
        monkeypatch.setattr(
            "app.services.chat_service.PersonalMemoryExtractor",
            MagicMock(return_value=mock_llm_extractor),
        )
        # Mock get_model_router so it doesn't try to initialize a real router
        monkeypatch.setattr(
            "app.services.model_router.get_model_router",
            MagicMock(return_value=MagicMock()),
        )

        mock_db = AsyncMock()
        await chat_service._maybe_extract_memory_claims(
            db=mock_db,
            thread_id=42,
            user_id=1,
            user_message="I prefer dark mode",
            assistant_response="Noted!",
        )

        # LLM extractor should have been called
        mock_llm_extractor.extract_with_fallback.assert_awaited_once()
        # Claim should be staged for HITL approval (conversation-sourced)
        assert mock_review_service.stage_pending_write.call_count == 1
        assert mock_pm_service.create.call_count == 0

    async def test_llm_timeout_falls_back_to_regex(self, monkeypatch: pytest.MonkeyPatch):
        """When LLM extraction times out, regex fallback is used."""
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

        mock_pause_service = AsyncMock()
        mock_pause_service.is_paused = AsyncMock(return_value=False)

        mock_pm_service = AsyncMock()
        mock_pm_service.create = AsyncMock(return_value=SimpleNamespace(id="claim-1"))

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
        monkeypatch.setattr(
            "app.services.personal_memory_service.PersonalMemoryService",
            MagicMock(return_value=mock_pm_service),
        )
        mock_review_service = AsyncMock()
        mock_review_service.stage_pending_write = AsyncMock(return_value="pw-1")
        monkeypatch.setattr(
            "app.services.memory.background_review_service.BackgroundReviewService",
            MagicMock(return_value=mock_review_service),
        )

        # Mock PersonalMemoryExtractor to raise TimeoutError
        mock_llm_extractor = AsyncMock()

        async def slow_extract(**kwargs):
            raise TimeoutError("LLM timed out")

        mock_llm_extractor.extract_with_fallback = slow_extract
        monkeypatch.setattr(
            "app.services.chat_service.PersonalMemoryExtractor",
            MagicMock(return_value=mock_llm_extractor),
        )
        monkeypatch.setattr(
            "app.services.model_router.get_model_router",
            MagicMock(return_value=MagicMock()),
        )

        # Mock the regex fallback to return a claim
        regex_claims = [_candidate_claim(predicate="likes", value="vim")]
        mock_regex = MagicMock()
        mock_regex.extract = MagicMock(return_value=regex_claims)
        monkeypatch.setattr(
            "app.services.chat_service.RegexPersonalMemoryExtractor",
            MagicMock(return_value=mock_regex),
        )

        mock_db = AsyncMock()
        await chat_service._maybe_extract_memory_claims(
            db=mock_db,
            thread_id=42,
            user_id=1,
            user_message="I like vim",
            assistant_response="Noted!",
        )

        # Regex fallback should have been used
        mock_regex.extract.assert_called_once()
        # Claim stages for HITL approval (conversation-sourced)
        assert mock_review_service.stage_pending_write.call_count == 1
        assert mock_pm_service.create.call_count == 0

    async def test_llm_error_falls_back_to_regex(self, monkeypatch: pytest.MonkeyPatch):
        """When LLM extraction raises any error, regex fallback is used."""
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

        mock_pause_service = AsyncMock()
        mock_pause_service.is_paused = AsyncMock(return_value=False)

        mock_pm_service = AsyncMock()
        mock_pm_service.create = AsyncMock(return_value=SimpleNamespace(id="claim-1"))

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
        monkeypatch.setattr(
            "app.services.personal_memory_service.PersonalMemoryService",
            MagicMock(return_value=mock_pm_service),
        )
        mock_review_service = AsyncMock()
        mock_review_service.stage_pending_write = AsyncMock(return_value="pw-1")
        monkeypatch.setattr(
            "app.services.memory.background_review_service.BackgroundReviewService",
            MagicMock(return_value=mock_review_service),
        )

        # Mock PersonalMemoryExtractor to raise RuntimeError
        mock_llm_extractor = AsyncMock()

        async def failing_extract(**kwargs):
            raise RuntimeError("ModelRouter not available")

        mock_llm_extractor.extract_with_fallback = failing_extract
        monkeypatch.setattr(
            "app.services.chat_service.PersonalMemoryExtractor",
            MagicMock(return_value=mock_llm_extractor),
        )
        monkeypatch.setattr(
            "app.services.model_router.get_model_router",
            MagicMock(return_value=MagicMock()),
        )

        # Mock the regex fallback
        regex_claims = [_candidate_claim(predicate="name", value="Alice")]
        mock_regex = MagicMock()
        mock_regex.extract = MagicMock(return_value=regex_claims)
        monkeypatch.setattr(
            "app.services.chat_service.RegexPersonalMemoryExtractor",
            MagicMock(return_value=mock_regex),
        )

        mock_db = AsyncMock()
        await chat_service._maybe_extract_memory_claims(
            db=mock_db,
            thread_id=42,
            user_id=1,
            user_message="My name is Alice",
            assistant_response="Hello Alice!",
        )

        # Regex fallback should have been used
        mock_regex.extract.assert_called_once()
        # Claim stages for HITL approval (conversation-sourced)
        assert mock_review_service.stage_pending_write.call_count == 1
        assert mock_pm_service.create.call_count == 0


class TestRegexExtractorPatterns:
    """Verify the regex extractor catches common preference patterns."""

    def test_prefers_pattern(self):
        from app.services.personal_memory_extractor import (
            RegexPersonalMemoryExtractor,
        )

        claims = RegexPersonalMemoryExtractor().extract("I prefer Python over JavaScript")
        assert len(claims) >= 1
        assert any("Python" in c.object.get("value", "") for c in claims)

    def test_likes_pattern(self):
        from app.services.personal_memory_extractor import (
            RegexPersonalMemoryExtractor,
        )

        claims = RegexPersonalMemoryExtractor().extract("I like dark mode")
        assert len(claims) >= 1

    def test_name_pattern(self):
        from app.services.personal_memory_extractor import (
            RegexPersonalMemoryExtractor,
        )

        claims = RegexPersonalMemoryExtractor().extract("My name is Alice")
        assert len(claims) >= 1
        assert any(c.predicate == "name" for c in claims)

    def test_pii_filtered_as_sensitive(self):
        """PII claims should have claim_type='sensitive' and scope='private'."""
        from app.services.personal_memory_extractor import (
            RegexPersonalMemoryExtractor,
        )

        claims = RegexPersonalMemoryExtractor().extract("Reach me at alice@example.com")
        pii_claims = [c for c in claims if c.claim_type == "sensitive"]
        assert len(pii_claims) >= 1
        assert pii_claims[0].scope == "private"


class TestExtractionCalledInStreamPath:
    """Verify stream_message_to_llm calls extraction via create_task."""

    async def test_stream_calls_extraction(self, monkeypatch: pytest.MonkeyPatch):
        """After yielding memory_citation events, stream_message_to_llm should
        fire-and-forget _maybe_extract_memory_claims via asyncio.create_task."""
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

        # Track if _maybe_extract_memory_claims was called
        called_with = {}

        async def mock_extract(**kwargs):
            called_with.update(kwargs)

        monkeypatch.setattr(chat_service, "_maybe_extract_memory_claims", mock_extract)

        # Mock the OpenAI client to return a simple response
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta = MagicMock()
        mock_chunk.choices[0].delta.content = "Hello!"
        mock_chunk.choices[0].delta.tool_calls = None
        mock_chunk.choices[0].finish_reason = "stop"
        mock_chunk.usage = None

        async def mock_stream():
            yield mock_chunk

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())

        monkeypatch.setattr(chat_service, "_client", mock_client)

        # Mock DB operations
        mock_db = AsyncMock()
        mock_thread = SimpleNamespace(id=42, workspace_id="ws-1", user_id=1, metadata_=None)

        async def mock_get_thread(db, thread_id):
            return mock_thread

        monkeypatch.setattr(chat_service, "get_chat_thread", mock_get_thread)

        # Mock _build_chat_messages to avoid internal DB calls
        async def mock_build_messages(db, thread_id, max_history=20):
            return [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "I prefer Python"},
            ]

        monkeypatch.setattr(chat_service, "_build_chat_messages", mock_build_messages)

        # Mock create_chat_message for user message
        mock_user_msg = SimpleNamespace(id=100)
        mock_assistant_msg = SimpleNamespace(id=101)

        async def mock_create_msg(db, thread_id, role, content, user_id=None):
            if role == "user":
                return mock_user_msg
            return mock_assistant_msg

        monkeypatch.setattr(chat_service, "create_chat_message", mock_create_msg)
        monkeypatch.setattr(
            chat_service,
            "create_chat_message_fresh_session",
            AsyncMock(return_value=mock_assistant_msg),
        )

        # Mock create_task to capture the coroutine
        tasks = []

        def mock_create_task(coro):
            tasks.append(coro)
            task = MagicMock()
            task.done.return_value = True
            return task

        monkeypatch.setattr("asyncio.create_task", mock_create_task)

        # Collect all yielded events
        events = [
            json.loads(event)
            async for event in chat_service.stream_message_to_llm(
                db=mock_db,
                thread_id=42,
                content="I prefer Python",
                user_id=1,
            )
        ]

        # Should have token + complete events
        event_types = [e["type"] for e in events]
        assert "token" in event_types
        assert "complete" in event_types

        # An extraction task should have been created
        assert len(tasks) == 1, f"Expected 1 extraction task, got {len(tasks)}"
