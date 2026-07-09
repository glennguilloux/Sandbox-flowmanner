"""Epic 2.2 — frozen snapshot seam (Option A, no migration).

Integration tests against the live PostgreSQL for the agent-side frozen
snapshot of canonical memory (``memory_snapshot_service``). Each test seeds
its own ``(user, workspace)`` so rows never collide across re-runs, and
drives the real ``PersonalMemoryService`` / ``recall_for_chat`` path.

Coverage maps to the design doc acceptance criteria (docs/EPIC-2.2-...):

* Seed-capture assumption: ``recall_for_chat(query="")`` returns the
  ordered standing claim set (top-k by confidence, importance,
  last_used_at). Proves the empty-query substring semantics hold.
* Lazy capture: the first snapshot access performs exactly ONE
  ``recall_for_chat``; subsequent accesses in the same thread reuse the
  frozen set.
* last_used_at bumped ONCE per capture (per session), not per message.
* Write-invalidation via generation counter: a new claim write re-captures
  on the next snapshot access for a thread in that (user, workspace).
* TTL invalidation: a captured snapshot older than the TTL re-captures.

Run from backend/ with the host venv:
    /opt/flowmanner/backend/.venv/bin/python -m pytest \\
        app/tests/test_epic22_frozen_snapshot.py -v

These are real-DB integration tests (like test_personal_memory_service.py);
they require a live PostgreSQL at settings.DATABASE_URL.
"""

from __future__ import annotations

import os
import sys
import uuid

import pytest

# Make ``app`` importable. Resolve the backend root relative to this file
# so the test runs against the SAME tree it lives in (worktree or
# container), not a hardcoded /opt/flowmanner/backend path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# The chat_service module builds a module-global AsyncOpenAI client at
# import time; tests set a dummy key first (matches test_chat_streaming.py).
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from app.database import fresh_session
from app.services.memory_citation_service import (
    CHAT_RECALL_TOP_K,
    recall_for_chat,
)
from app.services.memory_snapshot_service import (
    FrozenMemorySnapshot,
    clear_snapshots,
    get_or_capture_snapshot,
    get_snapshot,
    store_snapshot,
)
from app.services.personal_memory_service import (
    PersonalMemoryService,
)


def _uid() -> int:
    return 70_000_000 + (uuid.uuid4().int % 10_000_000)


def _wsid() -> str:
    return f"ws-{uuid.uuid4().hex[:12]}"


def _make_user(db, user_id: int):
    from app.models.user import User

    user = User(
        id=user_id,
        email=f"e22-user-{user_id}@example.com",
        hashed_password="x",
        role="user",
    )
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


async def _seed(db, user_id: int, workspace_id: str) -> None:
    _make_user(db, user_id)
    _make_workspace(db, workspace_id, user_id)
    # Flush so the (user, workspace) FK parents exist before any claim is
    # inserted (the session uses autoflush=False, so an explicit flush is
    # required for the FK to be satisfiable within the same transaction).
    await db.flush()


def _make_service(db):
    """Build a service whose audit writes go to a DEDICATED manager so the
    fire-and-forget tasks are scoped to this test's event loop.
    """
    from app.services.background_task_manager import BackgroundTaskManager
    from app.services.personal_memory_service import _MemoryCorrectionAudit

    manager = BackgroundTaskManager()
    audit = _MemoryCorrectionAudit(manager=manager)
    return PersonalMemoryService(db, audit=audit), manager


def _make_claim(db, user_id: int, workspace_id: str, *, confidence: float, importance: float, subject: str):
    """Create a 'personal' preference claim (recallable in chat)."""
    svc, _manager = _make_service(db)
    return svc.create(
        user_id=user_id,
        workspace_id=workspace_id,
        subject=subject,
        predicate="prefers",
        object={"value": subject},
        claim_type="preference",
        scope="personal",
        source_type="conversation",
        confidence=confidence,
        importance=importance,
    )


# Wrap recall_for_chat to count invocations (recall is imported lazily inside
# get_or_capture_snapshot via ``from app.services.memory_citation_service
# import recall_for_chat``, so patching the module attribute is observed).
class _RecallCounter:
    def __init__(self, real):
        self._real = real
        self.calls = 0

    async def __call__(self, *args, **kwargs):
        self.calls += 1
        return await self._real(*args, **kwargs)


@pytest.fixture(autouse=True)
def _reset_caches():
    clear_snapshots()
    yield
    clear_snapshots()


# ── Acceptance: seed-capture assumption holds ──────────────────────────────


@pytest.mark.asyncio(loop_scope="module")
async def test_empty_query_recall_returns_ordered_standing_set():
    """recall_for_chat(query='') returns the top-k standing claims ordered by
    (confidence desc, importance desc, last_used_at desc). This is the
    seed-capture assumption the frozen snapshot relies on — it MUST hold."""
    uid = _uid()
    ws = _wsid()
    async with fresh_session() as db:
        await _seed(db, uid, ws)
        # Distinct confidence/importance so ordering is unambiguous.
        await _make_claim(db, uid, ws, confidence=0.5, importance=0.1, subject="low")
        await _make_claim(db, uid, ws, confidence=0.9, importance=0.2, subject="high")
        await _make_claim(db, uid, ws, confidence=0.9, importance=0.8, subject="high-imp")
        await _make_claim(db, uid, ws, confidence=0.7, importance=0.5, subject="mid")
        # A private-scope claim must be filtered out by the T33 defensive filter.
        svc, _m = _make_service(db)
        await svc.create(
            user_id=uid,
            workspace_id=ws,
            subject="secret",
            predicate="is",
            object={"value": "x"},
            claim_type="fact",
            scope="private",
            source_type="conversation",
            confidence=0.99,
            importance=0.99,
        )
        await db.commit()

        claims = await recall_for_chat(db, user_id=uid, workspace_id=ws, query="")

    # Non-empty standing set returned for the empty query.
    assert claims, "recall_for_chat(query='') returned no claims"
    # Private-scope claim excluded by the defensive filter.
    assert all(c.scope != "private" for c in claims)
    # Ordered by confidence desc, then importance desc.
    conf_imp = [(round(float(c.confidence), 3), round(float(c.importance), 3)) for c in claims]
    assert conf_imp == sorted(conf_imp, reverse=True), f"not ordered desc: {conf_imp}"
    # top_k cap respected.
    assert len(claims) <= CHAT_RECALL_TOP_K
    # The highest-confidence claim is first.
    assert claims[0].subject == "high-imp"


# ── Acceptance: lazy capture + reuse, last_used_at bumped once ─────────────


@pytest.mark.asyncio(loop_scope="module")
async def test_snapshot_lazy_capture_and_reuse():
    """First access captures once (recall called exactly once); subsequent
    accesses in the same thread reuse the frozen set WITHOUT re-calling
    recall. last_used_at is bumped once per capture, not per message."""
    uid = _uid()
    ws = _wsid()
    counter = _RecallCounter(recall_for_chat)
    import app.services.memory_citation_service as mcs

    async with fresh_session() as db:
        await _seed(db, uid, ws)
        await _make_claim(db, uid, ws, confidence=0.85, importance=0.6, subject="theme")
        await db.commit()

        # Patch the module-level recall_for_chat so get_or_capture_snapshot
        # (which imports it lazily) observes the wrapper.
        original = mcs.recall_for_chat
        mcs.recall_for_chat = counter
        try:
            thread_id = 12345

            # --- First message: cache miss -> one capture.
            claims1 = await get_or_capture_snapshot(db, thread_id=thread_id, user_id=uid, workspace_id=ws)
            assert counter.calls == 1, f"expected 1 recall on first access, got {counter.calls}"

            snap = get_snapshot(thread_id)
            assert isinstance(snap, FrozenMemorySnapshot)
            assert snap.query_used == ""
            assert snap.user_id == uid
            assert snap.workspace_id == ws
            assert len(claims1) == 1
            assert claims1[0].subject == "theme"

            # --- Second message (same thread): cache hit -> no new recall.
            claims2 = await get_or_capture_snapshot(db, thread_id=thread_id, user_id=uid, workspace_id=ws)
            assert counter.calls == 1, f"expected NO extra recall on hit, got {counter.calls}"
            # Same frozen objects reused.
            assert claims2[0].id == claims1[0].id

            # --- Nth message: still reusing, still one recall total.
            for _ in range(5):
                await get_or_capture_snapshot(db, thread_id=thread_id, user_id=uid, workspace_id=ws)
            assert counter.calls == 1, f"expected exactly 1 recall for the whole session, got {counter.calls}"
        finally:
            mcs.recall_for_chat = original


@pytest.mark.asyncio(loop_scope="module")
async def test_last_used_at_bumped_once_per_session():
    """Across N messages in one thread, recall's last_used_at bump happens
    exactly once (at capture), not per message."""
    uid = _uid()
    ws = _wsid()
    counter = _RecallCounter(recall_for_chat)
    import app.services.memory_citation_service as mcs

    async with fresh_session() as db:
        await _seed(db, uid, ws)
        claim = await _make_claim(db, uid, ws, confidence=0.8, importance=0.5, subject="theme")
        await db.commit()
        before = claim.last_used_at

        original = mcs.recall_for_chat
        mcs.recall_for_chat = counter
        try:
            thread_id = 99999
            # Simulate N messages in one thread.
            for _ in range(5):
                await get_or_capture_snapshot(db, thread_id=thread_id, user_id=uid, workspace_id=ws)
        finally:
            mcs.recall_for_chat = original

        assert counter.calls == 1, f"recall should run once per session, got {counter.calls}"
        # The single capture bumped last_used_at.
        assert before is None
        # Re-read the persisted claim to confirm the bump landed exactly once.
        reread = await recall_for_chat(db, user_id=uid, workspace_id=ws, query="theme")
        # recall_for_chat bumps again on this direct read, so just assert it is set.
        assert reread
        assert reread[0].last_used_at is not None


# ── Acceptance: write-invalidation (generation counter) ────────────────────


@pytest.mark.asyncio(loop_scope="module")
async def test_write_invalidation_recaptures():
    """A new reviewer write to (user, workspace) bumps the generation; the
    next snapshot access for a thread in that user+workspace re-captures
    (a new recall), picking up the freshly written claim."""
    uid = _uid()
    ws = _wsid()
    counter = _RecallCounter(recall_for_chat)
    import app.services.memory_citation_service as mcs

    async with fresh_session() as db:
        await _seed(db, uid, ws)
        await _make_claim(db, uid, ws, confidence=0.8, importance=0.5, subject="first")
        await db.commit()

        original = mcs.recall_for_chat
        mcs.recall_for_chat = counter
        try:
            thread_id = 55555
            # Capture first snapshot.
            claims1 = await get_or_capture_snapshot(db, thread_id=thread_id, user_id=uid, workspace_id=ws)
            assert counter.calls == 1
            assert len(claims1) == 1

            # New reviewer write to the same (user, workspace). This goes
            # through the canonical PersonalMemoryService.create surface,
            # which bumps the snapshot generation counter.
            new_claim = await _make_claim(db, uid, ws, confidence=0.9, importance=0.7, subject="second")
            assert new_claim.subject == "second"
            await db.commit()
            # Generation must have advanced.
            from app.services.memory_snapshot_service import get_generation

            assert get_generation(uid, ws) >= 1

            # Next access for the same thread re-captures (new recall).
            claims2 = await get_or_capture_snapshot(db, thread_id=thread_id, user_id=uid, workspace_id=ws)
            assert counter.calls == 2, f"expected re-capture after write, got {counter.calls}"
            subjects = {c.subject for c in claims2}
            assert "second" in subjects, "re-capture did not pick up the new claim"
            # The new high-confidence claim is now first.
            assert claims2[0].subject == "second"
        finally:
            mcs.recall_for_chat = original


# ── Acceptance: TTL invalidation ───────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="module")
async def test_ttl_invalidation_recaptures():
    """A captured snapshot older than the supplied TTL re-captures on the
    next access."""
    uid = _uid()
    ws = _wsid()
    counter = _RecallCounter(recall_for_chat)
    import app.services.memory_citation_service as mcs

    async with fresh_session() as db:
        await _seed(db, uid, ws)
        await _make_claim(db, uid, ws, confidence=0.8, importance=0.5, subject="ttl-theme")
        await db.commit()

        original = mcs.recall_for_chat
        mcs.recall_for_chat = counter
        try:
            thread_id = 42424
            # Capture with a tiny TTL.
            await get_or_capture_snapshot(db, thread_id=thread_id, user_id=uid, workspace_id=ws, ttl_seconds=1)
            assert counter.calls == 1
            # Manually age the cached snapshot past the TTL.
            snap = get_snapshot(thread_id)
            from datetime import UTC, datetime, timedelta

            snap.captured_at = datetime.now(UTC) - timedelta(seconds=10)
            store_snapshot(thread_id, snap)

            # Next access re-captures because the TTL expired.
            await get_or_capture_snapshot(db, thread_id=thread_id, user_id=uid, workspace_id=ws, ttl_seconds=1)
            assert counter.calls == 2, f"expected re-capture after TTL, got {counter.calls}"
        finally:
            mcs.recall_for_chat = original


# ── Acceptance: generation counter is the write-invalidation trigger ───────


@pytest.mark.asyncio(loop_scope="module")
async def test_bump_generation_isolates_other_users():
    """A write to (user A, ws) must NOT invalidate a snapshot for
    (user B, ws). Generation counters are per-(user, workspace)."""
    uid_a = _uid()
    uid_b = _uid()
    ws = _wsid()
    counter = _RecallCounter(recall_for_chat)
    import app.services.memory_citation_service as mcs

    async with fresh_session() as db:
        # Both users share ONE workspace — the point is to prove that a
        # write to (user A, ws) does NOT bump the generation for
        # (user B, ws), so B's snapshot survives.
        _make_workspace(db, ws, uid_a)
        _make_user(db, uid_a)
        _make_user(db, uid_b)
        await db.flush()
        await _make_claim(db, uid_a, ws, confidence=0.8, importance=0.5, subject="a-theme")
        await _make_claim(db, uid_b, ws, confidence=0.8, importance=0.5, subject="b-theme")
        await db.commit()

        original = mcs.recall_for_chat
        mcs.recall_for_chat = counter
        try:
            # Capture a snapshot for user B.
            await get_or_capture_snapshot(db, thread_id=111, user_id=uid_b, workspace_id=ws)
            assert counter.calls == 1
            # Write only to user A.
            await _make_claim(db, uid_a, ws, confidence=0.9, importance=0.7, subject="a-second")
            await db.commit()
            # User B's snapshot must be reused (B's generation unchanged).
            await get_or_capture_snapshot(db, thread_id=111, user_id=uid_b, workspace_id=ws)
            assert counter.calls == 1, "writing to user A must not evict user B's snapshot"
        finally:
            mcs.recall_for_chat = original
