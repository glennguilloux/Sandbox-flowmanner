"""Integration tests for ``PersonalMemoryService`` audit wiring (2c.1).

Verifies that ``_safe_audit`` now emits real audit rows
(``memory_correction_events``) through the ``MemoryCorrectionService``
adapter instead of the old no-op.

The service is exercised with a real in-process session against the
live PostgreSQL (inside the backend container / on the homelab host).
Every memory op must result in exactly the right audit event. Audit
writes are fire-and-forget (``BackgroundTaskManager``); each test uses
its OWN manager instance (scoped to the test's event loop) so tasks are
drained within the test and never leak across loops.

Run:
    docker compose exec backend pytest app/tests/test_personal_memory_service.py -v
"""

from __future__ import annotations

import sys
import uuid

import pytest

# Make ``app`` importable when tests run outside the backend container.
sys.path.insert(0, "/opt/flowmanner/backend")

from app.models.memory_correction_models import (
    ALL_ACTORS,
    ALL_EVENT_TYPES,
)
from app.services.background_task_manager import BackgroundTaskManager
from app.services.personal_memory_service import (
    PersonalMemoryService,
    _MemoryCorrectionAudit,
)


def _uid() -> int:
    """A fresh, globally-unique int user id (avoids PK collisions across
    re-runs and across tests, since we never roll back the seeded rows).
    """
    return 50_000_000 + (uuid.uuid4().int % 10_000_000)


def _wsid() -> str:
    return f"ws-{uuid.uuid4().hex[:12]}"


def _make_service(db):
    """Build a service whose audit writes go to a DEDICATED manager so the
    fire-and-forget tasks are scoped to this test's event loop.
    """
    manager = BackgroundTaskManager()
    audit = _MemoryCorrectionAudit(manager=manager)
    return PersonalMemoryService(db, audit=audit), manager


# ── Adapter unit tests ─────────────────────────────────────────────────────


class TestMemoryCorrectionAuditAdapter:
    """The adapter maps ``claim_*`` events to the audit table taxonomy."""

    @pytest.mark.asyncio(loop_scope="module")
    async def test_adapter_default_constructor_wires_spawn(self):
        """Calling any event method must not raise; the work is handed to
        BackgroundTaskManager (fire-and-forget). The spawned coroutines run
        and drop (no matching claim) without error.
        """
        audit = _MemoryCorrectionAudit()
        audit.claim_created(
            claim_id=str(uuid.uuid4()),
            user_id=1,
            workspace_id="ws-1",
        )
        audit.claim_updated(claim_id=str(uuid.uuid4()), user_id=1, workspace_id="ws-1")
        audit.claim_forgotten(claim_id=str(uuid.uuid4()), user_id=1, workspace_id="ws-1")
        audit.claim_recalled(user_id=1, workspace_id="ws-1", count=3)
        # Allow the spawned coroutines to run (and no-op against missing
        # rows) so they don't leak warnings.
        await background_task_manager_drain()

    def test_all_event_types_remain_valid_constants(self):
        # Defensive: if someone changes the taxonomy this test surfaces it.
        assert "create" in ALL_EVENT_TYPES
        assert "view" in ALL_EVENT_TYPES
        assert "forget" in ALL_EVENT_TYPES
        assert "edit" in ALL_EVENT_TYPES
        assert "user" in ALL_ACTORS

    def test_adapter_exposes_four_event_methods(self):
        audit = _MemoryCorrectionAudit()
        for m in ("claim_created", "claim_recalled", "claim_forgotten", "claim_updated"):
            assert callable(getattr(audit, m))


async def background_task_manager_drain():
    """Drain the process-wide manager (used by the adapter unit test)."""
    from app.services.background_task_manager import background_task_manager

    await background_task_manager.drain(timeout=3.0)


# ── Integration: real audit rows emitted on memory ops ────────────────────


def _make_user(db, user_id: int):
    from app.models.user import User

    user = User(
        email=f"audit-user-{user_id}@example.com",
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
        slug=f"ws-{workspace_id}",
        owner_id=owner_id,
    )
    db.add(ws)
    return ws


def _seed(db, user_id: int, workspace_id: str) -> None:
    _make_user(db, user_id)
    _make_workspace(db, workspace_id, user_id)


async def _read_events(user_id: int, workspace_id: str):
    """Read back audit rows for a (user, workspace) via a fresh session."""
    from sqlalchemy import select

    from app.database import fresh_session
    from app.models.memory_correction_models import MemoryCorrectionEvent

    async with fresh_session() as db:
        result = await db.execute(
            select(MemoryCorrectionEvent)
            .where(
                MemoryCorrectionEvent.user_id == user_id,
                MemoryCorrectionEvent.workspace_id == workspace_id,
            )
            .order_by(MemoryCorrectionEvent.created_at.asc())
        )
        return list(result.scalars().all())


@pytest.mark.asyncio(loop_scope="module")
async def test_create_emits_create_audit_event():
    """A ``create`` must produce one ``create`` audit row referencing the claim."""
    from app.database import fresh_session

    uid = _uid()
    ws = _wsid()
    async with fresh_session() as db:
        _seed(db, uid, ws)
        await db.commit()

        svc, manager = _make_service(db)
        claim = await svc.create(
            user_id=uid,
            workspace_id=ws,
            subject="likes",
            predicate="prefers",
            object={"value": "concise answers"},
            claim_type="preference",
            scope="personal",
            source_type="conversation",
            confidence=0.8,
            importance=0.7,
        )
        await db.commit()

    await manager.drain(timeout=5.0)
    rows = await _read_events(uid, ws)
    assert len(rows) == 1
    assert rows[0].event_type == "create"
    assert str(rows[0].claim_id) == str(claim.id)
    assert rows[0].actor == "user"


@pytest.mark.asyncio(loop_scope="module")
async def test_forget_emits_forget_audit_event():
    """A ``forget`` must produce one ``forget`` audit row."""
    from app.database import fresh_session

    uid = _uid()
    ws = _wsid()
    async with fresh_session() as db:
        _seed(db, uid, ws)
        await db.commit()
        svc, manager = _make_service(db)
        claim = await svc.create(
            user_id=uid,
            workspace_id=ws,
            subject="dislikes",
            predicate="avoids",
            object={"value": "long meetings"},
            claim_type="preference",
            scope="personal",
            source_type="conversation",
        )
        await db.commit()

        await svc.forget(user_id=uid, workspace_id=ws, claim_id=claim.id)
        await db.commit()

    await manager.drain(timeout=5.0)
    rows = await _read_events(uid, ws)
    assert len(rows) == 2  # create + forget
    forget_rows = [r for r in rows if r.event_type == "forget"]
    assert len(forget_rows) == 1
    assert str(forget_rows[0].claim_id) == str(claim.id)


@pytest.mark.asyncio(loop_scope="module")
async def test_update_emits_edit_audit_event():
    """An ``update`` must produce one ``edit`` audit row."""
    from app.database import fresh_session

    uid = _uid()
    ws = _wsid()
    async with fresh_session() as db:
        _seed(db, uid, ws)
        await db.commit()
        svc, manager = _make_service(db)
        claim = await svc.create(
            user_id=uid,
            workspace_id=ws,
            subject="uses",
            predicate="works with",
            object={"value": "Python"},
            claim_type="fact",
            scope="personal",
            source_type="conversation",
        )
        await db.commit()

        await svc.update(
            user_id=uid,
            workspace_id=ws,
            claim_id=claim.id,
            importance=0.9,
        )
        await db.commit()

    await manager.drain(timeout=5.0)
    rows = await _read_events(uid, ws)
    edit_rows = [r for r in rows if r.event_type == "edit"]
    assert len(edit_rows) == 1


@pytest.mark.asyncio(loop_scope="module")
async def test_recall_emits_view_audit_event():
    """A ``recall`` that returns items must produce one ``view`` row."""
    from app.database import fresh_session

    uid = _uid()
    ws = _wsid()
    async with fresh_session() as db:
        _seed(db, uid, ws)
        await db.commit()
        svc, manager = _make_service(db)
        await svc.create(
            user_id=uid,
            workspace_id=ws,
            subject="prefers",
            predicate="likes",
            object={"value": "tea"},
            claim_type="preference",
            scope="personal",
            source_type="conversation",
        )
        await db.commit()

        items, _ = await svc.recall(user_id=uid, workspace_id=ws, query="prefers")
        await db.commit()
        assert len(items) >= 1

    await manager.drain(timeout=5.0)
    rows = await _read_events(uid, ws)
    view_rows = [r for r in rows if r.event_type == "view"]
    assert len(view_rows) == 1


@pytest.mark.asyncio(loop_scope="module")
async def test_recall_writes_last_used_at():
    """Epic 3.1: ``recall`` must bump ``last_used_at`` on every returned claim.

    The column exists (personal_memory_models.py:166) and recall() sets it
    for each returned row, then flushes (personal_memory_service.py:684-690).
    This test proves the bump is actually persisted — not just mutating the
    in-memory object.
    """
    from sqlalchemy import select

    from app.database import fresh_session
    from app.models.personal_memory_models import PersonalMemoryClaim

    uid = _uid()
    ws = _wsid()
    async with fresh_session() as db:
        _seed(db, uid, ws)
        await db.commit()
        svc, manager = _make_service(db)
        claim = await svc.create(
            user_id=uid,
            workspace_id=ws,
            subject="prefers",
            predicate="likes",
            object={"value": "coffee"},
            claim_type="preference",
            scope="personal",
            source_type="conversation",
        )
        await db.commit()

        # Before recall, the column is unset.
        assert claim.last_used_at is None

        items, _ = await svc.recall(user_id=uid, workspace_id=ws, query="prefers")
        await db.commit()
        assert len(items) >= 1

        # Re-read the persisted row to prove the flush+commit landed.
        reread = (await db.execute(select(PersonalMemoryClaim).where(PersonalMemoryClaim.id == claim.id))).scalar_one()
        assert reread.last_used_at is not None

    await manager.drain(timeout=5.0)


@pytest.mark.asyncio(loop_scope="module")
async def test_recall_with_no_match_emits_no_view_event():
    """A ``recall`` that returns nothing must NOT audit a view."""
    from app.database import fresh_session

    uid = _uid()
    ws = _wsid()
    async with fresh_session() as db:
        _seed(db, uid, ws)
        await db.commit()
        svc, manager = _make_service(db)
        items, _ = await svc.recall(user_id=uid, workspace_id=ws, query="zzz-no-such-claim-zzz")
        await db.commit()
        assert len(items) == 0

    await manager.drain(timeout=5.0)
    rows = await _read_events(uid, ws)
    assert [r for r in rows if r.event_type == "view"] == []


@pytest.mark.asyncio(loop_scope="module")
async def test_hard_forget_still_audits_with_surviving_claim_ref():
    """A hard-forget deletes the claim but the audit row survives.

    The audit writer retries with the claim FK dropped so the privacy
    trail is preserved (claim id recorded in details when dropped).
    """
    from app.database import fresh_session

    uid = _uid()
    ws = _wsid()
    async with fresh_session() as db:
        _seed(db, uid, ws)
        await db.commit()
        svc, manager = _make_service(db)
        claim = await svc.create(
            user_id=uid,
            workspace_id=ws,
            subject="temp",
            predicate="ephemeral",
            object={"value": "x"},
            claim_type="fact",
            scope="personal",
            source_type="conversation",
        )
        await db.commit()

        await svc.forget(user_id=uid, workspace_id=ws, claim_id=claim.id, hard=True)
        # Hard-forget deletes the claim row. The audit writer retries with
        # claim_id=None so the privacy trail survives.
        await db.commit()

    await manager.drain(timeout=5.0)
    rows = await _read_events(uid, ws)
    forget_rows = [r for r in rows if r.event_type == "forget"]
    assert len(forget_rows) == 1
    # The forget row survives even though the claim is gone (claim_id may
    # be None with the id preserved in details).
    assert forget_rows[0].claim_id is None or str(forget_rows[0].claim_id) == str(claim.id)


@pytest.mark.asyncio(loop_scope="module")
async def test_100_claim_recall_does_not_lose_audit_events():
    """100 separate ``recall`` calls each emit one ``view`` event
    (no-fail, complete). Recall audits once per read action, not per
    returned claim.

    Perf guard (roadmap §9): audit writes are fire-and-forget so the
    recall loop is not blocked. We assert all 100 audit rows land after
    draining.
    """
    from app.database import fresh_session

    uid = _uid()
    ws = _wsid()
    async with fresh_session() as db:
        _seed(db, uid, ws)
        await db.commit()
        svc, manager = _make_service(db)
        for i in range(100):
            await svc.create(
                user_id=uid,
                workspace_id=ws,
                subject=f"topic-{i}",
                predicate="is",
                object={"value": str(i)},
                claim_type="fact",
                scope="personal",
                source_type="conversation",
            )
        await db.commit()

        # 100 distinct recall reads → 100 view events. Create+commit in
        # small batches so audit FK visibility is guaranteed and we don't
        # exhaust the connection pool with hundreds of concurrent
        # fire-and-forget sessions.
        for batch in range(10):
            for i in range(batch * 10, batch * 10 + 10):
                await svc.create(
                    user_id=uid,
                    workspace_id=ws,
                    subject=f"topic-{i}",
                    predicate="is",
                    object={"value": str(i)},
                    claim_type="fact",
                    scope="personal",
                    source_type="conversation",
                )
            await db.commit()
            await manager.drain(timeout=5.0)

        for i in range(100):
            items, _ = await svc.recall(user_id=uid, workspace_id=ws, query=f"topic-{i}", top_k=1)
            await db.commit()
            assert len(items) >= 1

    await manager.drain(timeout=10.0)
    rows = await _read_events(uid, ws)
    view_rows = [r for r in rows if r.event_type == "view"]
    assert len(view_rows) == 100
