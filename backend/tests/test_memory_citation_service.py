"""Unit tests for the T33 MemoryCitationService.

TDD: tests first. Plan §10 specifies 8 backend test scenarios; this file
covers the pure-logic ones (no DB / no SSE):

  1. Defensive filter excludes ``sensitivity="sensitive"`` claims
  2. Defensive filter excludes ``sensitivity="restricted"`` claims
  3. Defensive filter excludes ``scope="private"`` claims
  4. Defensive filter keeps ``sensitivity="normal"`` + non-private
  5. format_memory_block returns "" for empty claim list
  6. format_memory_block renders the locked subject → predicate → object format
  7. short_claim_id produces ``c-<8-hex>`` from a UUID
  8. build_recall_used_event carries message_id + short label + confidence

The DB-bound tests (recall_for_chat hitting PostgreSQL) live in the
integration suite under ``tests/test_chat_memory_citations.py`` to keep
this file dependency-free and fast.
"""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.memory_citation_service import build_recall_used_event, format_memory_block, short_claim_id

# ── Fixtures ─────────────────────────────────────────────────────────


def _claim(
    *,
    id: uuid.UUID | None = None,
    subject: str = "Flowmanner",
    predicate: str = "uses",
    object: dict | None = None,
    sensitivity: str = "normal",
    scope: str = "workspace",
    confidence: float = 0.85,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=id or uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
        user_id=1,
        workspace_id="ws-1",
        subject=subject,
        predicate=predicate,
        object=object or {"framework": "Next.js"},
        claim_type="fact",
        scope=scope,
        source_type="mission",
        sensitivity=sensitivity,
        confidence=confidence,
        importance=0.5,
        source_id=None,
        last_used_at=None,
        expires_at=None,
        deleted_at=None,
    )


# ── Defensive filter tests (mocking PersonalMemoryService.recall) ────


class TestDefensiveFilter:
    """The T33 stop-rule mitigation: sensitive/restricted/private claims
    must NEVER reach the LLM prompt or the SSE event stream.
    """

    @pytest.mark.asyncio
    async def test_sensitive_claim_excluded(self) -> None:
        from app.services.memory_citation_service import recall_for_chat

        sensitive = _claim(sensitivity="sensitive")
        normal = _claim(id=uuid.UUID("660e8400-e29b-41d4-a716-446655440000"))
        mock_db = MagicMock()
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "app.services.personal_memory_service.PersonalMemoryService.recall",
                AsyncMock(return_value=([sensitive, normal], 2)),
            )
            result = await recall_for_chat(
                mock_db, user_id=1, workspace_id="ws-1", query="x"
            )
        assert result == [normal]

    @pytest.mark.asyncio
    async def test_restricted_claim_excluded(self) -> None:
        from app.services.memory_citation_service import recall_for_chat

        restricted = _claim(sensitivity="restricted")
        normal = _claim(id=uuid.UUID("770e8400-e29b-41d4-a716-446655440000"))
        mock_db = MagicMock()
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "app.services.personal_memory_service.PersonalMemoryService.recall",
                AsyncMock(return_value=([restricted, normal], 2)),
            )
            result = await recall_for_chat(
                mock_db, user_id=1, workspace_id="ws-1", query="x"
            )
        assert result == [normal]

    @pytest.mark.asyncio
    async def test_private_scope_claim_excluded(self) -> None:
        from app.services.memory_citation_service import recall_for_chat

        private = _claim(scope="private")
        personal = _claim(id=uuid.UUID("880e8400-e29b-41d4-a716-446655440000"), scope="personal")
        mock_db = MagicMock()
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "app.services.personal_memory_service.PersonalMemoryService.recall",
                AsyncMock(return_value=([private, personal], 2)),
            )
            result = await recall_for_chat(
                mock_db, user_id=1, workspace_id="ws-1", query="x"
            )
        assert result == [personal]

    @pytest.mark.asyncio
    async def test_normal_workspace_claim_kept(self) -> None:
        from app.services.memory_citation_service import recall_for_chat

        normal = _claim(sensitivity="normal", scope="workspace")
        mock_db = MagicMock()
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "app.services.personal_memory_service.PersonalMemoryService.recall",
                AsyncMock(return_value=([normal], 1)),
            )
            result = await recall_for_chat(
                mock_db, user_id=1, workspace_id="ws-1", query="x"
            )
        assert result == [normal]

    @pytest.mark.asyncio
    async def test_recall_called_with_min_confidence_0_7_and_top_k_5(self) -> None:
        """Lock down the recall contract: substring + conf≥0.7 + top-5."""
        from app.services.memory_citation_service import (
            CHAT_RECALL_MIN_CONFIDENCE,
            CHAT_RECALL_TOP_K,
            recall_for_chat,
        )

        assert CHAT_RECALL_MIN_CONFIDENCE == 0.7
        assert CHAT_RECALL_TOP_K == 5

        recall_mock = AsyncMock(return_value=([], 0))
        mock_db = MagicMock()
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "app.services.personal_memory_service.PersonalMemoryService.recall",
                recall_mock,
            )
            await recall_for_chat(mock_db, user_id=1, workspace_id="ws-1", query="x")
        recall_mock.assert_awaited_once_with(
            user_id=1,
            workspace_id="ws-1",
            query="x",
            scopes=["personal", "workspace", "program"],
            top_k=5,
            min_confidence=0.7,
        )


class TestFormatMemoryBlock:
    def test_empty_claims_returns_empty_string(self) -> None:
        assert format_memory_block([]) == ""

    def test_renders_subject_predicate_object_and_confidence(self) -> None:
        claim = _claim(
            subject="Flowmanner",
            predicate="uses",
            object={"framework": "Next.js"},
            confidence=0.85,
        )
        block = format_memory_block([claim])
        assert "PERSONAL MEMORY CONTEXT" in block
        assert "Flowmanner → uses → " in block
        assert '"framework": "Next.js"' in block
        assert "confidence: 0.85" in block

    def test_handles_non_json_object_safely(self) -> None:
        """If ``object`` contains non-serializable values, the formatter
        must fall back to ``str(object)`` rather than crash (the LLM
        will still get useful text)."""
        bad = _claim(object={"value:weird": object()})
        # json.dumps raises TypeError on the weird value, we fall back to str
        block = format_memory_block([bad])
        assert "Flowmanner → uses → " in block

    def test_multiple_claims_each_on_own_line(self) -> None:
        c1 = _claim(
            id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            subject="A",
            predicate="p1",
        )
        c2 = _claim(
            id=uuid.UUID("660e8400-e29b-41d4-a716-446655440000"),
            subject="B",
            predicate="p2",
        )
        block = format_memory_block([c1, c2])
        assert "A → p1" in block
        assert "B → p2" in block
        # Order is preserved
        assert block.index("A → p1") < block.index("B → p2")


# ── short_claim_id tests ─────────────────────────────────────────────


class TestShortClaimId:
    def test_format_is_c_eight_hex(self) -> None:
        claim = _claim(id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"))
        assert short_claim_id(claim) == "c-550e8400"

    def test_handles_already_lowercase_uuid(self) -> None:
        claim = _claim(id=uuid.UUID("abcdef12-3456-7890-abcd-ef1234567890"))
        assert short_claim_id(claim) == "c-abcdef12"

    def test_uppercase_uuid_normalized_to_lowercase(self) -> None:
        claim = _claim(id=uuid.UUID("ABCDEF12-3456-7890-ABCD-EF1234567890"))
        assert short_claim_id(claim) == "c-abcdef12"


# ── build_recall_used_event tests ────────────────────────────────────


class TestBuildRecallUsedEvent:
    def test_event_carries_message_id_and_short_label(self) -> None:
        claim = _claim(
            id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            subject="Flowmanner",
            predicate="uses",
            scope="workspace",
            confidence=0.85,
        )
        evt = build_recall_used_event(claim, message_id="42")
        assert evt["type"] == "memory_recall_used"
        assert evt["message_id"] == "42"
        assert evt["claim_id"] == "550e8400-e29b-41d4-a716-446655440000"
        assert evt["label"] == "c-550e8400"
        assert evt["subject"] == "Flowmanner"
        assert evt["predicate"] == "uses"
        assert evt["scope"] == "workspace"
        assert evt["confidence"] == 0.85
        assert evt["source"] == "pre_llm_context"

    def test_event_is_json_serializable(self) -> None:
        """The frontend SWR hook will JSON.parse this — no exotic types."""
        claim = _claim()
        evt = build_recall_used_event(claim, message_id="99")
        # Round-trip — should not raise
        round_tripped = json.loads(json.dumps(evt))
        assert round_tripped == evt
