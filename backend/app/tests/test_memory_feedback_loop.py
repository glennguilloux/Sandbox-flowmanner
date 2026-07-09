"""GOV-1.6 — close feedback -> durable memory loop (wiring, not building).

No-DB unit tests. Everything datastore-side is mocked so this runs in the
sandbox. Covers:

* (C5) Defensively-dropped candidates are persisted as durable ``drop``
  MemoryCorrectionEvents in the same privacy trail (not just logged).
* (C3 read-side) ``GET /personal_memory/corrections`` surfaces the
  correction trail through ``MemoryCorrectionService.list_for_user`` and
  maps the rows into the v2 envelope schema.
* The new ``drop`` event_type is part of the model's ``ALL_EVENT_TYPES``
  tuple AND the GOV-1.6 migration's type list (kept in lockstep per
  AGENTS.md ritual rule 6 — model + migration ship together).

This is the lightweight, defensible 1.6 wiring: the write path was already
wired (GOV-1.4); 1.6 (a) makes dropped candidates durable/visible and
(b) surfaces the existing trail read-side. Full auto-decay-feedback is
Epic 3, out of scope.
"""

from __future__ import annotations

import importlib
import os
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


def _drop_candidate(*, claim_type: str = "sensitive", scope: str = "personal") -> CandidateClaim:
    """A candidate the defensive filter removes (sensitive claim_type)."""
    return _claim(confidence=0.95, claim_type=claim_type, scope=scope)


# ── model + migration lockstep ────────────────────────────────────────


def test_drop_event_type_in_model_tuple():
    from app.models.memory_correction_models import ALL_EVENT_TYPES

    assert "drop" in ALL_EVENT_TYPES


def test_drop_event_type_in_migration_tuple():
    import importlib.util
    import os

    _mig_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "alembic",
        "versions",
        "20260709_gov16_drop_event_type.py",
    )
    _spec = importlib.util.spec_from_file_location("gov16_drop_event_type", os.path.abspath(_mig_path))
    mig = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(mig)

    assert "drop" in mig.ALL_EVENT_TYPES
    # The migration tuple must be a superset of the model tuple (they stay
    # in lockstep; the migration is what actually relaxes the CHECK).
    from app.models.memory_correction_models import ALL_EVENT_TYPES as MODEL

    assert set(MODEL).issubset(set(mig.ALL_EVENT_TYPES))


# ── hook persistence (C5) ─────────────────────────────────────────────


def _build_drop_harness(claims):
    """Mirror test_memory_extraction_calibration._build_session but expose
    the MemoryCorrectionService the hook now uses to persist drops."""
    db = AsyncMock()
    thread = SimpleNamespace(id=1, workspace_id="ws-1")
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

    drop_svc = AsyncMock()
    drop_svc.record_event = AsyncMock()

    ws_row = SimpleNamespace(id="ws-1", member_count=1, created_at=None)

    return SimpleNamespace(
        db=db,
        extractor=extractor,
        pm_service=pm_service,
        review_service=review_service,
        drop_svc=drop_svc,
        ws_row=ws_row,
    )


async def _run_hook_with_drop_assert(claims):
    from app.services import chat_service

    harness = _build_drop_harness(claims)

    def _fresh_session():
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _cm():
            yield harness.db

        return _cm()

    with (
        patch("app.database.fresh_session", _fresh_session),
        patch("app.services.chat_service.PersonalMemoryExtractor", return_value=harness.extractor),
        patch(
            "app.services.memory.background_review_service.BackgroundReviewService",
            return_value=harness.review_service,
        ),
        patch("app.services.personal_memory_service.PersonalMemoryService", return_value=harness.pm_service),
        patch(
            "app.services.chat_service.get_chat_thread",
            AsyncMock(return_value=SimpleNamespace(id=1, workspace_id="ws-1")),
        ),
        patch(
            "app.services.memory.background_review_service.compute_write_approval",
            return_value=False,
        ),
        patch(
            "app.services.memory_extraction_pause_service.MemoryExtractionPauseService",
            return_value=SimpleNamespace(is_paused=AsyncMock(return_value=False)),
        ),
        patch(
            "app.services.memory_correction_service.MemoryCorrectionService",
            return_value=harness.drop_svc,
        ),
        patch("sqlalchemy.select") as mock_select,
        patch("app.services.chat_service.Workspace", create=True),
    ):
        sel_result = MagicMock()
        sel_result.scalar_one_or_none = MagicMock(return_value=harness.ws_row)
        mock_select.return_value.where.return_value = MagicMock()
        harness.db.execute = AsyncMock(return_value=sel_result)

        await chat_service._maybe_extract_memory_claims(
            db=None,
            thread_id=1,
            user_id=1,
            user_message="I like secret stuff",
            assistant_response="Noted.",
        )

    return harness


@pytest.mark.asyncio
async def test_persists_one_drop_event_per_dropped_candidate():
    """C5: a defensively-dropped sensitive candidate is written as a drop event."""
    keep = _claim(confidence=0.9, source_type="user_explicit")
    sensitive = _drop_candidate()  # claim_type="sensitive" -> dropped

    harness = await _run_hook_with_drop_assert([keep, sensitive])

    # One drop event recorded, carrying the candidate shape in details.
    assert harness.drop_svc.record_event.await_count == 1
    call = harness.drop_svc.record_event.call_args.kwargs
    assert call["event_type"] == "drop"
    assert call["claim_id"] is None
    assert call["actor"] == "system"
    assert call["details"]["reason"] == "defensive_filter"
    assert call["details"]["claim_type"] == "sensitive"
    assert call["details"]["confidence"] == 0.95


@pytest.mark.asyncio
async def test_no_drop_event_when_nothing_dropped():
    """No drop rows when every candidate passes the defensive filter."""
    keep = _claim(confidence=0.9, source_type="user_explicit")
    harness = await _run_hook_with_drop_assert([keep])
    harness.drop_svc.record_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_drop_persistence_is_no_fail():
    """A broken correction sink must not break memory capture."""
    from app.services import chat_service

    keep = _claim(confidence=0.9, source_type="user_explicit")
    sensitive = _drop_candidate()
    harness = _build_drop_harness([keep, sensitive])

    # Make the correction sink raise on every call.
    harness.drop_svc.record_event.side_effect = RuntimeError("audit down")

    def _fresh_session():
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _cm():
            yield harness.db

        return _cm()

    with (
        patch("app.database.fresh_session", _fresh_session),
        patch("app.services.chat_service.PersonalMemoryExtractor", return_value=harness.extractor),
        patch(
            "app.services.memory.background_review_service.BackgroundReviewService",
            return_value=harness.review_service,
        ),
        patch("app.services.personal_memory_service.PersonalMemoryService", return_value=harness.pm_service),
        patch(
            "app.services.chat_service.get_chat_thread",
            AsyncMock(return_value=SimpleNamespace(id=1, workspace_id="ws-1")),
        ),
        patch(
            "app.services.memory.background_review_service.compute_write_approval",
            return_value=False,
        ),
        patch(
            "app.services.memory_extraction_pause_service.MemoryExtractionPauseService",
            return_value=SimpleNamespace(is_paused=AsyncMock(return_value=False)),
        ),
        patch(
            "app.services.memory_correction_service.MemoryCorrectionService",
            return_value=harness.drop_svc,
        ),
        patch("sqlalchemy.select") as mock_select,
        patch("app.services.chat_service.Workspace", create=True),
    ):
        sel_result = MagicMock()
        sel_result.scalar_one_or_none = MagicMock(return_value=harness.ws_row)
        mock_select.return_value.where.return_value = MagicMock()
        harness.db.execute = AsyncMock(return_value=sel_result)

        # The broken audit sink must NOT break memory capture.
        await chat_service._maybe_extract_memory_claims(
            db=None,
            thread_id=1,
            user_id=1,
            user_message="I like secret stuff",
            assistant_response="Noted.",
        )

    # Capture still happened despite the audit error.
    harness.pm_service.create.assert_awaited()


# ── corrections endpoint (C3 read-side) ──────────────────────────────


def _make_event(event_type: str, claim_id=None) -> SimpleNamespace:
    return SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        claim_id=claim_id,
        event_type=event_type,
        actor="user",
        source="personal_memory_service",
        details={"k": "v"},
        created_at=None,
    )


@pytest.mark.asyncio
async def test_corrections_handler_returns_ok_shape():
    """Call the route handler directly with stubbed DI deps + service."""
    from app.api.v2 import personal_memory as pm_mod
    from app.services.memory_correction_service import MemoryCorrectionService

    events = [_make_event("drop", None), _make_event("create", "22222222-2222-2222-2222-222222222222")]
    svc = AsyncMock(spec=MemoryCorrectionService)
    svc.list_for_user = AsyncMock(return_value=(events, 2))

    # Stub the DI callables the route references.
    with (
        patch.object(pm_mod, "MemoryCorrectionService", return_value=svc),
        patch.object(pm_mod, "get_current_user", return_value=SimpleNamespace(id=7)),
        patch.object(pm_mod, "get_workspace_id", return_value="ws-1"),
        patch.object(pm_mod, "get_db", return_value="db"),
    ):
        result = await pm_mod.list_corrections(
            workspace_id="ws-1",
            user=SimpleNamespace(id=7),
            db="db",
            event_type=None,
            page=1,
            per_page=50,
        )

    assert result["error"] is None
    data = result["data"]
    assert data["total"] == 2
    assert data["pages"] == 1
    assert data["items"][0]["event_type"] == "drop"
    assert data["items"][0]["claim_id"] is None
    assert data["items"][0]["details"] == {"k": "v"}
    # The drop event is surfaced alongside the create -> loop closed C3+C5.
    svc.list_for_user.assert_awaited_once()
