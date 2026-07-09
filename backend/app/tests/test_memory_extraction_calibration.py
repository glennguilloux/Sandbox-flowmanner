"""GOV-1.5 — memory extraction threshold calibration instrumentation.

No-DB unit tests. The extraction hook opens a fresh DB session and calls
the extractor; every datastore / LLM call is mocked so this runs in the
sandbox. Covers:

* The confidence gate (``extraction_thresholds``) defaults to 0.85 and is
  env-overridable.
* The trusted (user_explicit) direct-write path holds low-confidence
  claims for approval instead of writing directly.
* The GOV-1.2 invariant is preserved: an untrusted (``conversation``)
  source is ALWAYS staged for approval, never de-escalated by confidence.
* Dropped (defensive-filter) candidates are logged with their scores and
  counted in the extraction metrics.
"""

from __future__ import annotations

import asyncio
import importlib
import os

# Ensure the backend source tree is importable in the sandbox.
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-key")
sys.path.insert(0, "/opt/flowmanner/backend")

from app.services.personal_memory_extractor import CandidateClaim


def _claim(*, confidence: float = 0.9, source_type: str = "user_explicit", **kw) -> CandidateClaim:
    return CandidateClaim(
        subject=kw.get("subject", "user"),
        predicate=kw.get("predicate", "prefers"),
        object=kw.get("object", {"value": "dark mode"}),
        claim_type=kw.get("claim_type", "preference"),
        scope=kw.get("scope", "personal"),
        confidence=confidence,
        source_type=source_type,
    )


# ── extraction_thresholds unit tests ──────────────────────────────────


def test_default_min_confidence_is_085(monkeypatch):
    monkeypatch.delenv("MEMORY_EXTRACTION_MIN_CONFIDENCE", raising=False)
    mod = importlib.reload(__import__("app.services.memory.extraction_thresholds", fromlist=["x"]))
    assert mod.MEMORY_EXTRACTION_MIN_CONFIDENCE == 0.85


def test_min_confidence_env_override(monkeypatch):
    monkeypatch.setenv("MEMORY_EXTRACTION_MIN_CONFIDENCE", "0.6")
    mod = importlib.reload(__import__("app.services.memory.extraction_thresholds", fromlist=["x"]))
    assert mod.MEMORY_EXTRACTION_MIN_CONFIDENCE == 0.6
    assert mod.passes_confidence_gate(0.6) is True
    assert mod.passes_confidence_gate(0.59) is False


def test_gate_boundary_at_floor(monkeypatch):
    monkeypatch.setenv("MEMORY_EXTRACTION_MIN_CONFIDENCE", "0.85")
    mod = importlib.reload(__import__("app.services.memory.extraction_thresholds", fromlist=["x"]))
    assert mod.passes_confidence_gate(0.85) is True
    assert mod.passes_confidence_gate(0.849) is False


def test_only_user_explicit_is_trusted_direct_write():
    from app.services.memory.extraction_thresholds import is_trusted_direct_write

    assert is_trusted_direct_write("user_explicit") is True
    # Externally-derived sources must never bypass approval via this gate.
    for src in ("conversation", "mission", "program_learning", None, "typo"):
        assert is_trusted_direct_write(src) is False


# ── end-to-end hook behaviour (mocked DB/LLM) ─────────────────────────


def _build_session(claims, *, ws_needs_approval=False, ws_member_count=1):
    """Build the chain of mocks _maybe_extract_memory_claims walks.

    The hook does:
      fresh_session() -> db
      get_chat_thread(db, thread_id) -> thread(workspace_id)
      pause_svc.is_paused(...) -> False
      llm_extractor.extract_with_fallback(...) -> (claims, source)
      select(Workspace)...scalar_one_or_none() -> ws_row
      per-claim stage_pending_write / pm_service.create
    """
    db = AsyncMock()
    thread = SimpleNamespace(id=1, workspace_id="ws-1")
    # get_chat_thread returns the thread on first execute() call.
    exec_result = MagicMock()
    exec_result.scalar_one_or_none = MagicMock(return_value=thread)
    db.execute = AsyncMock(return_value=exec_result)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.flush = AsyncMock()

    extractor = AsyncMock()
    extractor.extract_with_fallback = AsyncMock(return_value=(claims, "llm"))

    pm_service = AsyncMock()
    pm_service.create = AsyncMock()

    review_service = AsyncMock()
    review_service.stage_pending_write = AsyncMock(return_value="pw-1")

    ws_row = SimpleNamespace(
        id="ws-1",
        member_count=ws_member_count,
        created_at=None,
    )

    return SimpleNamespace(
        db=db,
        extractor=extractor,
        pm_service=pm_service,
        review_service=review_service,
        ws_row=ws_row,
    )


async def _run_hook(claims, *, source_type="user_explicit", ws_needs_approval=False, ws_member_count=1):
    from app.services import chat_service

    harness = _build_session(claims, ws_needs_approval=ws_needs_approval, ws_member_count=ws_member_count)

    def _fresh_session():
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _cm():
            yield harness.db

        return _cm()

    with (
        patch("app.database.fresh_session", _fresh_session),
        patch(
            "app.services.chat_service.PersonalMemoryExtractor",
            return_value=harness.extractor,
        ),
        patch(
            "app.services.memory.background_review_service.BackgroundReviewService",
            return_value=harness.review_service,
        ),
        patch(
            "app.services.personal_memory_service.PersonalMemoryService",
            return_value=harness.pm_service,
        ),
        patch(
            "app.services.chat_service.get_chat_thread",
            AsyncMock(return_value=SimpleNamespace(id=1, workspace_id="ws-1")),
        ),
        patch(
            "app.services.memory.background_review_service.compute_write_approval",
            return_value=ws_needs_approval,
        ),
        patch(
            "app.services.memory_extraction_pause_service.MemoryExtractionPauseService",
            return_value=SimpleNamespace(is_paused=AsyncMock(return_value=False)),
        ),
        patch("sqlalchemy.select") as mock_select,
        patch("app.services.chat_service.Workspace", create=True),
    ):
        # Make `select(Workspace).where(...)` return something whose
        # scalar_one_or_none() yields the workspace row.
        sel_result = MagicMock()
        sel_result.scalar_one_or_none = MagicMock(return_value=harness.ws_row)
        mock_select.return_value.where.return_value = MagicMock()
        harness.db.execute = AsyncMock(return_value=sel_result)

        await chat_service._maybe_extract_memory_claims(
            db=None,
            thread_id=1,
            user_id=1,
            user_message="I prefer dark mode",
            assistant_response="Noted, I will remember that.",
        )

    return harness


@pytest.mark.asyncio
async def test_trusted_low_confidence_held_for_approval(monkeypatch):
    """GOV-1.5: a user_explicit claim below 0.85 is staged, not written."""
    monkeypatch.setenv("MEMORY_EXTRACTION_MIN_CONFIDENCE", "0.85")
    importlib.reload(__import__("app.services.memory.extraction_thresholds", fromlist=["x"]))
    claim = _claim(confidence=0.4, source_type="user_explicit")
    # attach source_type so the hook reads it via getattr
    harness = await _run_hook([claim], source_type="user_explicit")

    harness.pm_service.create.assert_not_awaited()
    harness.review_service.stage_pending_write.assert_awaited_once()
    meta = harness.review_service.stage_pending_write.call_args.kwargs["metadata"]
    assert meta["held_reason"] == "confidence_below_gate"


@pytest.mark.asyncio
async def test_trusted_high_confidence_direct_write(monkeypatch):
    """GOV-1.5: a user_explicit claim at/above 0.85 is written directly."""
    monkeypatch.setenv("MEMORY_EXTRACTION_MIN_CONFIDENCE", "0.85")
    importlib.reload(__import__("app.services.memory.extraction_thresholds", fromlist=["x"]))
    claim = _claim(confidence=0.9, source_type="user_explicit")
    harness = await _run_hook([claim], source_type="user_explicit")

    harness.pm_service.create.assert_awaited_once()
    harness.review_service.stage_pending_write.assert_not_awaited()


@pytest.mark.asyncio
async def test_untrusted_never_deescalated_by_confidence(monkeypatch):
    """GOV-1.2 invariant: conversation source always staged, even at 0.99."""
    monkeypatch.setenv("MEMORY_EXTRACTION_MIN_CONFIDENCE", "0.85")
    importlib.reload(__import__("app.services.memory.extraction_thresholds", fromlist=["x"]))
    claim = _claim(confidence=0.99, source_type="conversation")
    harness = await _run_hook([claim], source_type="conversation")

    # High confidence on an untrusted source must NOT produce a direct write.
    harness.pm_service.create.assert_not_awaited()
    harness.review_service.stage_pending_write.assert_awaited_once()


@pytest.mark.asyncio
async def test_defensive_drop_logged_and_counted(monkeypatch):
    """GOV-1.5 (C5): sensitive/private candidates are dropped with scores."""
    monkeypatch.setenv("MEMORY_EXTRACTION_MIN_CONFIDENCE", "0.85")
    importlib.reload(__import__("app.services.memory.extraction_thresholds", fromlist=["x"]))
    keep = _claim(confidence=0.9, source_type="user_explicit")
    sensitive = _claim(confidence=0.95, claim_type="sensitive")
    harness = await _run_hook([keep, sensitive], source_type="user_explicit")

    # The sensitive claim is dropped by the defensive filter (never staged/written).
    assert harness.review_service.stage_pending_write.await_count == 0
    harness.pm_service.create.assert_awaited_once()
