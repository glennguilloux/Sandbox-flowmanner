"""Epic 2.3 — E23-A (source_priority column) + E23-B (lexicographic rank).

Pure-Python unit tests for the ranking policy + an integration test for
``recall()`` ordering (the 2.2 handoff requirement: the frozen snapshot must
capture a *resolved* view, so recall must return the source-priority winner
first, not the highest-confidence claim).

Policy (Q1-Q6 decomposition E23-B):

    source_priority > recency_half_life_band > confidence > importance

* Higher source_priority wins even if the loser has higher confidence
  (a reviewer ``program_learning`` inference must NOT silently override a
  human ``conversation`` claim).
* Recency is bucketed into half-life bands so tiny time deltas never flip
  order (cross-machine reproducibility).
* Integer-only comparisons, never floating weighted sums.

Run from backend/ with the host venv + live PostgreSQL:
    DATABASE_URL=postgresql+asyncpg://flowmanner:<pw>@127.0.0.1:5432/flowmanner \\
        .venv/bin/python -m pytest app/tests/test_epic23_source_priority.py -v
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta

import pytest

sys.path.insert(0, "/opt/flowmanner/backend")

from app.models.personal_memory_models import (
    SOURCE_PRIORITY,
    SOURCE_PRIORITY_DEFAULT,
    PersonalMemoryClaim,
    recency_half_life_band,
    source_priority_for,
)
from app.services.personal_memory_service import lexicographic_rank


def _claim(
    *,
    source_type: str,
    confidence: float = 0.5,
    importance: float = 0.5,
    age_days: float = 0.0,
    source_priority: int | None = None,
    created_at: datetime | None = None,
) -> PersonalMemoryClaim:
    """Build an in-memory PersonalMemoryClaim for ranking tests (no DB)."""
    if created_at is None:
        created_at = datetime.now(UTC) - timedelta(days=age_days)
    c = PersonalMemoryClaim(
        user_id=1,
        workspace_id="ws-test",
        subject="user",
        predicate="prefers",
        object={"value": "x"},
        claim_type="preference",
        scope="personal",
        source_type=source_type,
        confidence=confidence,
        importance=importance,
    )
    c.created_at = created_at
    c.id = str(uuid.uuid4())
    if source_priority is not None:
        c.source_priority = source_priority
    else:
        c.source_priority = source_priority_for(source_type)
    return c


# ── SOURCE_PRIORITY map (E23-A) ────────────────────────────────────────────


class TestSourcePriorityMap:
    def test_map_ordering_user_explicit_highest(self) -> None:
        assert SOURCE_PRIORITY["user_explicit"] > SOURCE_PRIORITY["conversation"]
        assert SOURCE_PRIORITY["conversation"] > SOURCE_PRIORITY["mission"]
        assert SOURCE_PRIORITY["mission"] > SOURCE_PRIORITY["program_learning"]

    def test_source_priority_for_resolves_known_types(self) -> None:
        assert source_priority_for("user_explicit") == SOURCE_PRIORITY["user_explicit"]
        assert source_priority_for("conversation") == SOURCE_PRIORITY["conversation"]
        assert source_priority_for("mission") == SOURCE_PRIORITY["mission"]
        assert source_priority_for("program_learning") == SOURCE_PRIORITY["program_learning"]

    def test_source_priority_for_unknown_defaults_to_zero(self) -> None:
        assert source_priority_for(None) == SOURCE_PRIORITY_DEFAULT
        assert source_priority_for("some_future_type") == SOURCE_PRIORITY_DEFAULT


# ── Recency half-life bands (E23-B) ───────────────────────────────────────


class TestRecencyHalfLifeBand:
    def test_newer_claims_rank_in_higher_band(self) -> None:
        now = datetime.now(UTC)
        band_new = recency_half_life_band(now - timedelta(hours=1))
        band_old = recency_half_life_band(now - timedelta(days=200))
        assert band_new > band_old

    def test_band_boundaries_are_deterministic(self) -> None:
        now = datetime.now(UTC)
        # <1d -> top band (len(RECENCY_BANDS_DAYS) == 4)
        assert recency_half_life_band(now - timedelta(hours=12)) == 4
        # ~3d -> band 3 (between 1d and 7d)
        assert recency_half_life_band(now - timedelta(days=3)) == 3
        # ~15d -> band 2
        assert recency_half_life_band(now - timedelta(days=15)) == 2
        # ~45d -> band 1
        assert recency_half_life_band(now - timedelta(days=45)) == 1
        # >90d -> band 0 (oldest)
        assert recency_half_life_band(now - timedelta(days=200)) == 0

    def test_none_created_at_maps_to_oldest_band(self) -> None:
        assert recency_half_life_band(None) == 0

    def test_tiny_delta_does_not_flip_band(self) -> None:
        now = datetime.now(UTC)
        a = recency_half_life_band(now - timedelta(seconds=1))
        b = recency_half_life_band(now - timedelta(seconds=30))
        assert a == b, "tiny time deltas must not flip the recency band"


# ── lexicographic_rank (E23-B) ─────────────────────────────────────────────


class TestLexicographicRank:
    def test_source_priority_beats_confidence(self) -> None:
        """The acceptance criterion: a high-confidence program_learning claim
        must NOT outrank a lower-confidence conversation claim."""
        conv = _claim(source_type="conversation", confidence=0.85)
        prog = _claim(source_type="program_learning", confidence=0.95)
        ranked = lexicographic_rank([prog, conv])
        assert ranked[0] is conv
        assert ranked[1] is prog

    def test_higher_source_priority_wins_regardless_of_confidence(self) -> None:
        user_explicit = _claim(source_type="user_explicit", confidence=0.1)
        mission = _claim(source_type="mission", confidence=0.99)
        ranked = lexicographic_rank([mission, user_explicit])
        assert ranked[0] is user_explicit

    def test_same_source_priority_then_recency_band(self) -> None:
        # Two conversation claims; the newer (higher band) wins.
        old = _claim(source_type="conversation", confidence=0.5, age_days=60)
        new = _claim(source_type="conversation", confidence=0.5, age_days=0)
        ranked = lexicographic_rank([old, new])
        assert ranked[0] is new

    def test_same_source_priority_and_recency_then_confidence(self) -> None:
        low = _claim(source_type="conversation", confidence=0.4, age_days=0)
        high = _claim(source_type="conversation", confidence=0.9, age_days=0)
        ranked = lexicographic_rank([low, high])
        assert ranked[0] is high

    def test_deterministic_reproducible(self) -> None:
        claims = [
            _claim(source_type="program_learning", confidence=0.9),
            _claim(source_type="conversation", confidence=0.85),
            _claim(source_type="mission", confidence=0.7),
            _claim(source_type="user_explicit", confidence=0.3),
        ]
        fwd = lexicographic_rank(list(claims))
        rev = lexicographic_rank(list(reversed(claims)))
        assert [c.id for c in fwd] == [c.id for c in rev]

    def test_reverse_false_sorts_winner_last(self) -> None:
        conv = _claim(source_type="conversation", confidence=0.85)
        prog = _claim(source_type="program_learning", confidence=0.95)
        ranked = lexicographic_rank([conv, prog], reverse=False)
        assert ranked[-1] is conv

    def test_recency_axis_wins_within_same_source_priority(self) -> None:
        """E23-B recency axis: within a source_priority band, a newer claim
        must outrank an older one even when the older claim has higher
        confidence. This is the exact axis the recall() SQL window must
        preserve (via ``created_at DESC``) before the Python re-sort, so the
        window never truncates a high-recency claim that the comparator would
        promote. Regression guard for the recall() ORDER BY fix.
        """
        # Same source_type -> same source_priority band.
        old_high_conf = _claim(source_type="conversation", confidence=0.95, age_days=120)
        new_low_conf = _claim(source_type="conversation", confidence=0.40, age_days=0)
        ranked = lexicographic_rank([old_high_conf, new_low_conf])
        assert ranked[0] is new_low_conf
        assert (
            ranked[0].source_priority == ranked[1].source_priority
        ), "test precondition: must be within the same source_priority band"


# ── Integration: recall() ordering picks the source-priority winner ───────


def _uid() -> int:
    return 80_000_000 + (uuid.uuid4().int % 10_000_000)


def _wsid() -> str:
    return f"ws-{uuid.uuid4().hex[:12]}"


def _make_user(db, user_id: int):
    from app.models.user import User

    user = User(
        id=user_id,
        email=f"e23-user-{user_id}@example.com",
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


@pytest.mark.asyncio(loop_scope="module")
async def test_recall_returns_source_priority_winner_first() -> None:
    """2.2 handoff requirement: recall returns the highest source_priority
    claim first even when a lower-priority claim has higher confidence."""
    from app.database import fresh_session
    from app.services.personal_memory_service import PersonalMemoryService

    uid = _uid()
    ws = _wsid()
    async with fresh_session() as db:
        _make_user(db, uid)
        _make_workspace(db, ws, uid)
        await db.flush()

        svc = PersonalMemoryService(db)
        # High-confidence reviewer claim.
        await svc.create(
            user_id=uid,
            workspace_id=ws,
            subject="user",
            predicate="prefers",
            object={"coffee": "tea"},
            claim_type="preference",
            scope="personal",
            source_type="program_learning",
            confidence=0.95,
            importance=0.5,
        )
        # Lower-confidence human conversation claim — must win.
        await svc.create(
            user_id=uid,
            workspace_id=ws,
            subject="user",
            predicate="prefers",
            object={"coffee": "espresso"},
            claim_type="preference",
            scope="personal",
            source_type="conversation",
            confidence=0.85,
            importance=0.5,
        )
        await db.commit()

        claims, _total = await svc.recall(user_id=uid, workspace_id=ws, query="prefers")

    assert claims, "recall returned nothing"
    assert (
        claims[0].source_type == "conversation"
    ), f"source-priority winner should be first, got {claims[0].source_type}"
    assert claims[0].source_priority > claims[1].source_priority


@pytest.mark.asyncio(loop_scope="module")
async def test_migration_seeded_source_priority_from_source_type() -> None:
    """Verify the E23-A migration backfilled source_priority from source_type
    (proves the column + seed actually landed on the live schema)."""
    from sqlalchemy import text

    from app.database import fresh_session

    async with fresh_session() as db:
        result = await db.execute(
            text(
                "SELECT source_type, source_priority FROM "
                "personal_memory_claims WHERE source_type IS NOT NULL "
                "ORDER BY source_type LIMIT 100"
            )
        )
        rows = result.all()

    assert rows, "no seeded claims to verify"
    for source_type, sp in rows:
        expected = source_priority_for(source_type)
        assert sp == expected, f"seeded source_priority mismatch for {source_type!r}: " f"got {sp}, expected {expected}"
