"""Q2 — ranking + token budget (Epic 2.3 E23-B consumer).

Pure-Python tests for ``rank_and_budget_claims``: Tier-0 constraint
protection (Q2-A) and deterministic, lowest-rank-first truncation under a
token budget (Q2-C). No DB required — claims are built in-memory.

The ranking axes (source_priority > recency > confidence > importance) are
covered by ``test_epic23_source_priority.py``; here we assert the *policy
composition*: constraints are never dropped while competitive claims remain,
and overflow drops the lowest-ranked competitive claim first.

Run from backend/ with the host venv:
    .venv/bin/python -m pytest app/tests/test_q2_rank_and_budget.py -v
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta

sys.path.insert(0, "/opt/flowmanner/backend")

from app.models.personal_memory_models import PersonalMemoryClaim, source_priority_for
from app.services.personal_memory_service import rank_and_budget_claims


def _claim(
    *,
    claim_type: str = "preference",
    source_type: str = "conversation",
    confidence: float = 0.5,
    importance: float = 0.5,
    age_days: float = 0.0,
    object_value: str = "x",
    subject: str = "user",
    predicate: str = "prefers",
) -> PersonalMemoryClaim:
    """Build an in-memory claim (no DB) for budget/tier tests."""
    created_at = datetime.now(UTC) - timedelta(days=age_days)
    c = PersonalMemoryClaim(
        user_id=1,
        workspace_id="ws-test",
        subject=subject,
        predicate=predicate,
        object={"value": object_value},
        claim_type=claim_type,
        scope="personal",
        source_type=source_type,
        confidence=confidence,
        importance=importance,
    )
    c.created_at = created_at
    c.id = str(uuid.uuid4())
    # The Python model default for source_priority only fires at DB flush,
    # not object construction — set it explicitly so the E23-B ranking sees
    # the real priority (mirrors recall() which reads the stored column).
    c.source_priority = source_priority_for(source_type)
    return c


class TestTier0ConstraintProtection:
    def test_constraint_kept_when_competitive_claims_dropped(self) -> None:
        """Q2-A: a constraint must survive even when the budget is too small
        for everything. Competitive claims are dropped; the constraint stays.
        """
        constraint = _claim(claim_type="constraint", object_value="never deploy Fridays")
        # Large competitive claim that alone exceeds a tiny budget.
        big_pref = _claim(claim_type="preference", object_value="z" * 2000, confidence=0.99)
        selected, dropped = rank_and_budget_claims([big_pref, constraint], token_budget=50)
        assert constraint in selected
        assert big_pref in dropped
        # The constraint is first (Tier-0 spent before Tier-1).
        assert selected[0] is constraint

    def test_constraint_never_ranked_against_preference(self) -> None:
        """Constraints occupy Tier-0 and are never compared on the E23-B
        competitive axis — a low-priority constraint still beats a
        high-priority preference in selection order.
        """
        constraint = _claim(claim_type="constraint", source_type="program_learning")
        pref = _claim(claim_type="preference", source_type="user_explicit", confidence=0.99)
        selected, dropped = rank_and_budget_claims([pref, constraint], token_budget=10_000)
        assert selected[0] is constraint
        assert dropped == []


class TestTokenBudgetTruncation:
    def test_lowest_ranked_competitive_dropped_first(self) -> None:
        """Q2-C: with a tight budget, the lowest-ranked competitive claim
        (lowest source_priority) is dropped before a higher-ranked one.
        """
        user_explicit = _claim(source_type="user_explicit", confidence=0.3)
        conv = _claim(source_type="conversation", confidence=0.8)
        prog = _claim(source_type="program_learning", confidence=0.95)
        # Budget fits exactly two small claims (~7 tokens each → 14).
        selected, dropped = rank_and_budget_claims([prog, conv, user_explicit], token_budget=14)
        assert prog in dropped  # lowest source_priority → dropped first
        assert conv in selected
        assert user_explicit in selected

    def test_zero_budget_selects_nothing(self) -> None:
        claim = _claim(claim_type="preference")
        selected, dropped = rank_and_budget_claims([claim], token_budget=0)
        assert selected == []
        assert claim in dropped

    def test_empty_claims_returns_empty(self) -> None:
        selected, dropped = rank_and_budget_claims([], token_budget=1000)
        assert selected == []
        assert dropped == []

    def test_unbounded_budget_keeps_all_competitive(self) -> None:
        claims = [_claim(source_type=t) for t in ("program_learning", "conversation", "mission", "user_explicit")]
        selected, dropped = rank_and_budget_claims(claims, token_budget=1_000_000)
        assert len(selected) == 4
        assert dropped == []
        # Selected is E23-B ordered: user_explicit first, program_learning last.
        assert selected[0].source_type == "user_explicit"
        assert selected[-1].source_type == "program_learning"
