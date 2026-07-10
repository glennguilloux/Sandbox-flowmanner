"""Epic 2.3 E23-C — conflict detection unit tests (pure, DB-free).

Asserts the two acceptance criteria from
``docs/EPIC-2.3-CONFLICT-RESOLUTION-POLICY-DESIGN.md`` §5 AC4:

* Given a ``conversation`` claim (conf 0.85) and a ``program_learning`` claim
  (conf 0.9) on the same (subject, predicate, differing object),
  ``group_conflicts`` picks the ``conversation`` claim as winner and explains
  "lower source priority" — confidence does NOT override source priority.
* With no overlapping live claims, ``group_conflicts`` returns an empty list
  (no false positives), and exact-duplicate ``object``s are NOT reported as
  conflicts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services.memory_conflict_service import group_conflicts


def _claim(
    *,
    subject: str,
    predicate: str,
    object: dict,
    claim_type: str = "preference",
    source_type: str = "conversation",
    source_priority: int = 2,
    confidence: float = 0.8,
    created_at: datetime | None = None,
    deleted_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> object:
    """Build a lightweight fake claim with the attrs group_conflicts reads."""
    return SimpleNamespace(
        id=str(uuid4()),
        subject=subject,
        predicate=predicate,
        object=object,
        claim_type=claim_type,
        source_type=source_type,
        source_priority=source_priority,
        confidence=confidence,
        created_at=created_at or datetime(2026, 7, 1, tzinfo=UTC),
        deleted_at=deleted_at,
        expires_at=expires_at,
    )


def test_conversation_beats_higher_confidence_program_learning():
    """AC4 — source priority wins over confidence (never silent override)."""
    human = _claim(
        subject="Glenn",
        predicate="prefers",
        object={"coffee": "espresso"},
        claim_type="preference",
        source_type="conversation",
        source_priority=2,
        confidence=0.85,
    )
    reviewer = _claim(
        subject="Glenn",
        predicate="prefers",
        object={"coffee": "tea"},
        claim_type="preference",
        source_type="program_learning",
        source_priority=1,
        confidence=0.90,  # higher conf, but lower source priority
    )

    groups = group_conflicts([human, reviewer])

    assert len(groups) == 1
    g = groups[0]
    assert g.subject == "glenn"
    assert g.predicate == "prefers"
    assert g.winner is human  # conversation wins despite lower confidence
    assert len(g.losers) == 1
    loser = g.members[1]
    assert loser.claim is reviewer
    assert "source priority" in (loser.superseded_because or "").lower()


def test_no_conflicts_when_objects_differ_on_distinct_subjects():
    """AC4 — no false positives across different subjects/predicates."""
    a = _claim(subject="Glenn", predicate="works_at", object={"org": "Acme"})
    b = _claim(subject="Glenn", predicate="prefers", object={"coffee": "espresso"})
    c = _claim(subject="Sara", predicate="works_at", object={"org": "Globex"})

    assert group_conflicts([a, b, c]) == []


def test_exact_duplicate_object_not_a_conflict():
    """AC4 — same subject+predicate+object is a duplicate, not a conflict."""
    a = _claim(subject="Glenn", predicate="prefers", object={"coffee": "espresso"})
    b = _claim(subject="Glenn", predicate="prefers", object={"coffee": "espresso"})

    assert group_conflicts([a, b]) == []


def test_constraint_outranks_fact_on_conflict():
    """Claim-type precedence: constraint > fact (E23-C §2)."""
    constraint = _claim(
        subject="Glenn",
        predicate="must",
        object={"deploy": "never on Fridays"},
        claim_type="constraint",
        source_type="user",
        source_priority=3,
        confidence=0.7,
    )
    fact = _claim(
        subject="Glenn",
        predicate="must",
        object={"deploy": "any day"},
        claim_type="fact",
        source_type="conversation",
        source_priority=2,
        confidence=0.99,
    )

    groups = group_conflicts([constraint, fact])
    assert len(groups) == 1
    assert groups[0].winner is constraint


def test_deleted_or_expired_claims_excluded():
    """Soft-deleted / expired claims never form a conflict group."""
    live = _claim(subject="Glenn", predicate="prefers", object={"x": 1})
    dead = _claim(
        subject="Glenn",
        predicate="prefers",
        object={"x": 2},
        deleted_at=datetime(2026, 7, 5, tzinfo=UTC),
    )
    expired = _claim(
        subject="Glenn",
        predicate="prefers",
        object={"x": 3},
        expires_at=datetime(2026, 7, 5, tzinfo=UTC),
    )

    assert group_conflicts([live, dead, expired]) == []
