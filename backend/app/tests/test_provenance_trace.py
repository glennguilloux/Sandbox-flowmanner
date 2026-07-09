"""Provenance-trace endpoint tests (Epic 3.6).

Covers ``GET /api/v2/personal_memory/claims/{claim_id}/provenance`` — the
"Why does the agent believe X?" surface. The endpoint composes three
already-existing data sources for a single claim:

* ``claim`` — the ``PersonalMemoryClaim`` record.
* ``provenance`` — origin projection (source_type, source_id, the
  mission-only ``source_mission_id`` alias, created_at, confidence,
  importance, scope).
* ``corrections`` — the durable ``memory_correction_events`` trail scoped
  to the claim.
* ``audit_summary`` — the T32 event-count roll-up (preserved, no regression).

What the tests assert:

1. A claim with NO corrections returns the full shape, an empty
   ``corrections`` list, and ``audit_summary.event_count == 0``.
2. A claim WITH corrections returns them most-recent-first and the
   ``audit_summary`` counts/last_* reflect the recorded events.
3. ``source_mission_id`` is populated only when ``source_type == "mission"``
   (it aliases ``source_id``); it's ``None`` for other source types.
4. Scope isolation: a claim owned by another user / workspace surfaces as a
   404 envelope (never a cross-tenant leak).

These are real-DB integration tests against the live PostgreSQL (same
harness as ``test_scope_isolation.py`` / ``test_personal_memory_service.py``).
The route *handler function* is called directly with real dependencies so
the test avoids importing the full FastAPI app (which pulls in
``chat_service`` and its OpenAI-client construction at import time).

Run:
    cd backend && /opt/flowmanner/backend/.venv/bin/python -m pytest \
        app/tests/test_provenance_trace.py -v
"""

from __future__ import annotations

import os
import sys
import uuid

import pytest

# Make ``app`` importable when tests run outside the backend container, and
# satisfy the eager OpenAI-client construction in chat_service (imported
# transitively by some app modules) with a dummy key. Insert THIS worktree's
# backend dir first so the edits under test are the ones imported (not the
# deployed /opt/flowmanner/backend tree). The sys.path.insert must be the
# last statement before the app imports: ruff's E402 tolerates a bare
# sys.path.insert as an import-group separator but flags any other preamble
# statement (e.g. os.environ.setdefault) after it.
os.environ.setdefault("OPENAI_API_KEY", "test-provenance-trace")
sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
)

from app.api.v2.personal_memory import claim_provenance
from app.services.background_task_manager import BackgroundTaskManager
from app.services.memory_correction_service import MemoryCorrectionService
from app.services.personal_memory_service import (
    PersonalMemoryService,
    _MemoryCorrectionAudit,
)

# ── Fixtures / helpers (mirror test_scope_isolation.py) ────────────────────


def _uid() -> int:
    """A fresh, globally-unique int user id (avoids PK collisions across
    re-runs, since seeded rows are never rolled back)."""
    return 910_000_000 + (uuid.uuid4().int % 80_000_000)


def _wsid() -> str:
    return f"ws-{uuid.uuid4().hex}"


def _make_service(db):
    """Build a service whose audit writes go to a DEDICATED manager so the
    fire-and-forget tasks are scoped to this test's event loop."""
    manager = BackgroundTaskManager()
    audit = _MemoryCorrectionAudit(manager=manager)
    return PersonalMemoryService(db, audit=audit), manager


class _NoopAudit:
    """Audit sink that records nothing.

    ``PersonalMemoryService.create()`` fires a fire-and-forget ``create``
    correction event through its audit hook. That background write races
    the synchronous read in these tests and would pollute the correction
    trail non-deterministically (2 vs 3 events). Passing this no-op audit
    makes ``create()`` write zero correction events, so each test controls
    the trail entirely via explicit ``MemoryCorrectionService.record_event``
    calls — deterministic, no background tasks to drain.
    """

    def __getattr__(self, _name):  # dynamic no-op
        def _noop(*_args, **_kwargs):
            return None

        return _noop


def _make_silent_service(db):
    """A service whose ``create()`` emits no correction events (see
    ``_NoopAudit``). Use when the test asserts on an exact correction
    trail it builds itself."""
    return PersonalMemoryService(db, audit=_NoopAudit())


def _make_user(db, user_id: int):
    from app.models.user import User

    user = User(
        email=f"prov-user-{user_id}@example.com",
        hashed_password="x",
        role="user",
    )
    user.id = user_id
    db.add(user)
    return user


def _make_workspace(db, workspace_id: str, owner_id: int):
    from app.models.workspace_models import Workspace

    ws = Workspace(
        id=workspace_id,
        name=f"ws-{workspace_id}",
        slug=f"ws-{workspace_id}-{uuid.uuid4().hex[:6]}",
        owner_id=owner_id,
    )
    db.add(ws)
    return ws


class _StubUser:
    """Minimal stand-in for the ``User`` dependency the route reads
    ``user.id`` from."""

    def __init__(self, user_id: int) -> None:
        self.id = user_id


async def _call_provenance(*, db, service, user_id: int, workspace_id: str, claim_id: uuid.UUID):
    """Invoke the route handler directly with real dependencies."""
    return await claim_provenance(
        claim_id=claim_id,
        workspace_id=workspace_id,
        user=_StubUser(user_id),
        service=service,
        db=db,
    )


async def _create_claim(
    svc,
    user_id,
    workspace_id,
    subject,
    *,
    source_type="conversation",
    source_id=None,
    confidence=0.5,
    importance=0.5,
):
    return await svc.create(
        user_id=user_id,
        workspace_id=workspace_id,
        subject=subject,
        predicate="is",
        object={"value": subject},
        claim_type="fact",
        scope="personal",
        source_type=source_type,
        source_id=source_id,
        confidence=confidence,
        importance=importance,
    )


# ── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="module")
async def test_provenance_trace_no_corrections():
    """A claim with no correction events returns the full trace shape with
    an empty corrections list and a zero-count audit summary."""
    from app.database import fresh_session

    uid = _uid()
    ws = _wsid()
    async with fresh_session() as db:
        _make_user(db, uid)
        _make_workspace(db, ws, uid)
        await db.commit()

        svc = _make_silent_service(db)
        claim = await _create_claim(svc, uid, ws, "likes-dark-mode", confidence=0.8, importance=0.6)
        await db.commit()

        result = await _call_provenance(db=db, service=svc, user_id=uid, workspace_id=ws, claim_id=claim.id)

    # Envelope: {"data": {...}, "meta": {...}, "error": None}
    assert result["error"] is None
    data = result["data"]

    # Top-level trace shape.
    assert set(data.keys()) == {"claim", "provenance", "corrections", "audit_summary"}

    # Claim block echoes the stored claim.
    assert data["claim"]["id"] == str(claim.id)
    assert data["claim"]["subject"] == "likes-dark-mode"

    # Provenance projection.
    prov = data["provenance"]
    assert prov["source_type"] == "conversation"
    assert prov["source_mission_id"] is None  # not a mission source
    assert prov["confidence"] == 0.8
    assert prov["importance"] == 0.6
    assert prov["scope"] == "personal"
    assert prov["created_at"] is not None

    # No corrections recorded yet.
    assert data["corrections"] == []

    # Audit summary is present and empty.
    summary = data["audit_summary"]
    assert summary["claim_id"] == str(claim.id)
    assert summary["event_count"] == 0
    assert summary["last_event_type"] is None
    # events_by_type is a stable, fully-populated bucket map (all zeros).
    assert isinstance(summary["events_by_type"], dict)
    assert set(summary["events_by_type"].values()) == {0}
    # _make_silent_service emits no background audit tasks, so no drain needed.


@pytest.mark.asyncio(loop_scope="module")
async def test_provenance_trace_with_corrections():
    """A claim with correction events returns them most-recent-first and the
    audit summary reflects the recorded events."""
    from app.database import fresh_session

    uid = _uid()
    ws = _wsid()
    mission_id = uuid.uuid4()
    async with fresh_session() as db:
        _make_user(db, uid)
        _make_workspace(db, ws, uid)
        await db.commit()

        svc = _make_silent_service(db)
        # A mission-sourced claim so source_mission_id is exercised too.
        claim = await _create_claim(
            svc,
            uid,
            ws,
            "prefers-python",
            source_type="mission",
            source_id=mission_id,
        )
        await db.commit()

        # Record two correction events directly via the correction service.
        corr = MemoryCorrectionService(db)
        await corr.record_event(
            user_id=uid,
            workspace_id=ws,
            claim_id=claim.id,
            event_type="edit",
            actor="user",
            details={"field": "confidence", "old": 0.5, "new": 0.9},
        )
        await corr.record_event(
            user_id=uid,
            workspace_id=ws,
            claim_id=claim.id,
            event_type="view",
            actor="user",
        )
        await db.commit()

        result = await _call_provenance(db=db, service=svc, user_id=uid, workspace_id=ws, claim_id=claim.id)

    assert result["error"] is None
    data = result["data"]

    # Mission source → source_mission_id aliases source_id.
    prov = data["provenance"]
    assert prov["source_type"] == "mission"
    assert prov["source_id"] == str(mission_id)
    assert prov["source_mission_id"] == str(mission_id)

    # Corrections present, most-recent-first (view was recorded last).
    corrections = data["corrections"]
    assert len(corrections) == 2
    assert corrections[0]["event_type"] == "view"
    assert corrections[1]["event_type"] == "edit"
    assert all(c["claim_id"] == str(claim.id) for c in corrections)

    # Audit summary reflects the two events.
    summary = data["audit_summary"]
    assert summary["event_count"] == 2
    assert summary["last_event_type"] == "view"
    assert summary["events_by_type"]["edit"] == 1
    assert summary["events_by_type"]["view"] == 1
    # _make_silent_service emits no background audit tasks, so no drain needed.


@pytest.mark.asyncio(loop_scope="module")
async def test_provenance_trace_cross_tenant_returns_404():
    """A claim owned by another user/workspace must surface as a 404
    envelope — never a cross-tenant leak of the claim or its trail."""
    from fastapi.responses import JSONResponse

    from app.database import fresh_session

    owner_uid = _uid()
    other_uid = _uid()
    ws_owner = _wsid()
    ws_other = _wsid()
    async with fresh_session() as db:
        _make_user(db, owner_uid)
        _make_user(db, other_uid)
        _make_workspace(db, ws_owner, owner_uid)
        _make_workspace(db, ws_other, other_uid)
        await db.commit()

        svc, manager = _make_service(db)
        claim = await _create_claim(svc, owner_uid, ws_owner, "owner-secret")
        await db.commit()

        # A different user in a different workspace asks for the trace.
        result = await _call_provenance(
            db=db,
            service=svc,
            user_id=other_uid,
            workspace_id=ws_other,
            claim_id=claim.id,
        )

    assert isinstance(result, JSONResponse)
    assert result.status_code == 404

    await manager.drain(timeout=5.0)
