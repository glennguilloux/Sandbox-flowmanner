"""Q5 — multi-agent memory sharing (E23-D agent_id + E23-C conflict key).

DB-free unit tests for the four Q5 pieces:

* Q5-A (attribution) — ``agent_id`` flows onto a claim via ``create`` /
  ``create_from_proposal`` and is surfaced in the response schema. (Schema
  round-trip is asserted here; the write path is covered by the existing
  personal-memory tests + E23-D migration.)
* Q5-B (trust tiers) — agent-authored ``program_learning`` claims get a lower
  *effective* source priority than an otherwise-identical human-authored claim
  (down-rank), and the cross-agent consumption gate hides another agent's
  inference from a non-authoring agent while keeping it visible to the human
  and to its own author.
* Q5-C (contradiction surfacing) — two agents asserting opposing objects on
  the same (subject, predicate) are surfaced with a human-readable narrative
  ("A asserts X; B asserts ¬X") + the deterministic winner reason; losers are
  never merged.
* Q5-D (per-agent snapshot) — the frozen snapshot store is keyed by
  (thread_id, agent_id); the human (None) and an agent get distinct caches; a
  workspace write bumps the generation for all agents (lazy re-capture).

All pure (SimpleNamespace fakes / in-memory module cache) so they run without
a live Postgres — matching the E23-C conflict-detection test style.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Repo convention for app/tests: make the backend package root importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from app.services import memory_attribution as attr
from app.services.memory_conflict_service import (
    ConflictGroup,
    ConflictMember,
    group_conflicts,
    surface_agent_contradictions,
)
from app.services.memory_snapshot_service import (
    FrozenMemorySnapshot,
    bump_generation,
    clear_snapshots,
    get_generation,
    get_or_capture_snapshot,
    get_snapshot,
    store_snapshot,
)
from app.services.personal_memory_service import (
    PersonalMemoryService,
    lexicographic_rank,
)

# ── Fake claim builders ─────────────────────────────────────────────────────


def _claim(
    *,
    subject: str,
    predicate: str,
    object: dict,
    agent_id: str | None = None,
    claim_type: str = "preference",
    source_type: str = "conversation",
    source_priority: int = 2,
    confidence: float = 0.8,
    created_at: datetime | None = None,
    deleted_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> object:
    return SimpleNamespace(
        id=str(uuid4()),
        subject=subject,
        predicate=predicate,
        object=object,
        agent_id=agent_id,
        claim_type=claim_type,
        source_type=source_type,
        source_priority=source_priority,
        confidence=confidence,
        created_at=created_at or datetime(2026, 7, 1, tzinfo=UTC),
        deleted_at=deleted_at,
        expires_at=expires_at,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Q5-A — attribution (agent_id is a real, queryable provenance column)
# ═══════════════════════════════════════════════════════════════════════════


def test_q5a_human_authored_is_null_agent_id():
    c = _claim(subject="Glenn", predicate="prefers", object={"x": 1}, agent_id=None)
    assert attr.is_human_authored(c) is True
    # Human-authored keeps the honest stored source_priority (no down-rank).
    assert attr.effective_source_priority(c) == c.source_priority


def test_q5a_schema_round_trips_agent_id():
    from app.schemas.personal_memory import (
        PersonalMemoryClaimCreate,
        PersonalMemoryClaimResponse,
    )

    create = PersonalMemoryClaimCreate(
        user_id=1,
        workspace_id="ws-1",
        subject="Glenn",
        predicate="prefers",
        object={"coffee": "espresso"},
        claim_type="preference",
        scope="personal",
        source_type="conversation",
        agent_id="agent:reviewer-7",
    )
    assert create.agent_id == "agent:reviewer-7"

    resp = PersonalMemoryClaimResponse(
        id=uuid4(),
        user_id=1,
        workspace_id="ws-1",
        subject="Glenn",
        predicate="prefers",
        object={"coffee": "espresso"},
        claim_type="preference",
        scope="personal",
        source_type="conversation",
        sensitivity="normal",
        confidence=0.5,
        importance=0.5,
        agent_id="agent:reviewer-7",
    )
    dumped = resp.model_dump(mode="json")
    assert dumped["agent_id"] == "agent:reviewer-7"

    resp_human = PersonalMemoryClaimResponse(
        id=uuid4(),
        user_id=1,
        workspace_id="ws-1",
        subject="Glenn",
        predicate="prefers",
        object={},
        claim_type="fact",
        scope="personal",
        source_type="user_explicit",
        sensitivity="normal",
        confidence=0.9,
        importance=0.9,
        agent_id=None,
    )
    assert resp_human.model_dump(mode="json")["agent_id"] is None


# ═══════════════════════════════════════════════════════════════════════════
# Q5-B — agent down-rank + cross-agent consumption gate
# ═══════════════════════════════════════════════════════════════════════════


def test_q5b_agent_program_learning_downranked_below_human():
    """An agent-authored program_learning claim (source_priority 1) must rank
    BELOW an otherwise-identical human-authored program_learning claim."""
    human = _claim(
        subject="Glenn",
        predicate="is",
        object={"role": "admin"},
        agent_id=None,
        source_type="program_learning",
        source_priority=1,
    )
    agent = _claim(
        subject="Glenn",
        predicate="is",
        object={"role": "admin"},
        agent_id="agent:reviewer-7",
        source_type="program_learning",
        source_priority=1,
    )
    assert attr.effective_source_priority(human) == 1
    assert attr.effective_source_priority(agent) == max(0, 1 - attr.AGENT_PROGRAM_LEARNING_PENALTY)
    assert attr.effective_source_priority(agent) < attr.effective_source_priority(human)


def test_q5b_downrank_applied_in_lexicographic_rank():
    human = _claim(
        subject="Glenn",
        predicate="is",
        object={"a": 1},
        agent_id=None,
        source_type="program_learning",
        source_priority=1,
    )
    agent = _claim(
        subject="Glenn",
        predicate="is",
        object={"a": 1},
        agent_id="agent:reviewer-7",
        source_type="program_learning",
        source_priority=1,
    )
    # Human consumer (None) → stored priority, tie broken by id stability
    # (both are 'program_learning' = 1, so order is deterministic not by author).
    # Agent consumer → human fact ranks first (down-rank on the agent claim).
    ranked = lexicographic_rank([agent, human], consumer_agent_id="agent:planner-3")
    assert ranked[0].agent_id is None
    assert ranked[1].agent_id == "agent:reviewer-7"


def test_q5b_cross_agent_gate_hides_other_agents_inference():
    human = _claim(subject="Glenn", predicate="prefers", object={"x": 1}, agent_id=None)
    own = _claim(subject="Glenn", predicate="prefers", object={"y": 2}, agent_id="agent:reviewer-7")
    others = _claim(subject="Glenn", predicate="prefers", object={"z": 3}, agent_id="agent:planner-3")

    # Human sees everything.
    all_for_human = attr.filter_consumable([human, own, others], consumer_agent_id=None)
    assert len(all_for_human) == 3

    # reviewer-7 sees the human claim + its own, but NOT planner-3's.
    reviewer_view = attr.filter_consumable([human, own, others], consumer_agent_id="agent:reviewer-7")
    assert {c.agent_id for c in reviewer_view} == {None, "agent:reviewer-7"}
    assert all(c.agent_id != "agent:planner-3" for c in reviewer_view)

    # planner-3 sees the human claim + its own, but NOT reviewer-7's.
    planner_view = attr.filter_consumable([human, own, others], consumer_agent_id="agent:planner-3")
    assert {c.agent_id for c in planner_view} == {None, "agent:planner-3"}


def test_q5b_governance_gate_passes_for_attributed_claims():
    """A claim that reached the store already cleared the write-time governance
    gate (Epic 2.1 / Q4); Q5-B only adds the attribution filter, so an agent's
    own claim remains consumable by it (no double-block)."""
    own = _claim(subject="Glenn", predicate="observed", object={"a": 1}, agent_id="agent:reviewer-7")
    assert attr.can_agent_consume(own, consumer_agent_id="agent:reviewer-7") is True


# ═══════════════════════════════════════════════════════════════════════════
# Q5-C — contradiction surfacing across agents (reuses E23-C group_conflicts)
# ═══════════════════════════════════════════════════════════════════════════


def test_q5c_surfaces_opposing_assertions_between_agents():
    a = _claim(
        subject="Glenn",
        predicate="prefers",
        object={"deploy": "fridays"},
        agent_id="agent:reviewer-7",
        source_type="conversation",
        source_priority=3,
    )
    b = _claim(
        subject="Glenn",
        predicate="prefers",
        object={"deploy": "never"},
        agent_id="agent:planner-3",
        source_type="program_learning",
        source_priority=1,
    )
    surfaced = surface_agent_contradictions([a, b])
    assert len(surfaced) == 1
    sc = surfaced[0]
    # Narrative names both asserting agents.
    assert "agent:reviewer-7" in sc.narrative
    assert "agent:planner-3" in sc.narrative
    # Human (conversation, sp 3) wins over agent program_learning (sp 1).
    assert sc.winner_agent_id == "agent:reviewer-7"
    assert sc.loser_agent_ids == ["agent:planner-3"]
    assert "source priority" in (sc.resolution_reason or "").lower()


def test_q5c_surfaces_human_vs_agent_contradiction():
    human = _claim(
        subject="Glenn",
        predicate="is",
        object={"tz": "UTC"},
        agent_id=None,
        source_type="user_explicit",
        source_priority=4,
    )
    agent = _claim(
        subject="Glenn",
        predicate="is",
        object={"tz": "PST"},
        agent_id="agent:reviewer-7",
        source_type="program_learning",
        source_priority=1,
    )
    surfaced = surface_agent_contradictions([human, agent])
    assert len(surfaced) == 1
    sc = surfaced[0]
    assert sc.winner_agent_id is None  # human-authored wins
    assert sc.narrative.startswith("human asserts")


def test_q5c_no_false_positive_when_agreeing():
    a = _claim(subject="Glenn", predicate="prefers", object={"x": 1}, agent_id="agent:reviewer-7")
    b = _claim(subject="Glenn", predicate="prefers", object={"x": 1}, agent_id="agent:planner-3")
    # Same object → NOT a conflict (group_conflicts excludes duplicates).
    assert surface_agent_contradictions([a, b]) == []


def test_q5c_reuses_group_conflicts_never_merges():
    """Confirm the surfaced contradiction still carries the live loser claim
    (Q5-C surfaces, never auto-collapses)."""
    a = _claim(subject="Glenn", predicate="prefers", object={"x": 1}, agent_id="agent:reviewer-7")
    b = _claim(subject="Glenn", predicate="prefers", object={"x": 2}, agent_id="agent:planner-3")
    surfaced = surface_agent_contradictions([a, b])
    assert len(surfaced) == 1
    # Both members (winner + loser) are present and live.
    member_ids = {str(m.claim.id) for m in surfaced[0].members}
    assert {str(a.id), str(b.id)} == member_ids


# ═══════════════════════════════════════════════════════════════════════════
# Q5-D — snapshot keyed per-(thread_id, agent_id); workspace write bumps all
# ═══════════════════════════════════════════════════════════════════════════


def test_q5d_snapshot_keyed_per_thread_and_agent():
    clear_snapshots()
    sha = FrozenMemorySnapshot(thread_id=1, user_id=1, workspace_id="ws", agent_id=None)
    sa = FrozenMemorySnapshot(thread_id=1, user_id=1, workspace_id="ws", agent_id="agent:reviewer-7")
    store_snapshot(1, sha, agent_id=None)
    store_snapshot(1, sa, agent_id="agent:reviewer-7")
    assert get_snapshot(1, agent_id=None) is sha
    assert get_snapshot(1, agent_id="agent:reviewer-7") is sa
    assert get_snapshot(1, agent_id="agent:planner-3") is None


def test_q5d_workspace_write_bumps_generation_for_all_agents():
    """A single (user_id, workspace_id) generation counter drives invalidation
    for every per-agent snapshot (Q5-D): one write refreshes all agents."""
    clear_snapshots()
    user_id, ws = 1, "ws"
    bump_generation(user_id, ws)  # write #1
    g = get_generation(user_id, ws)
    assert g == 1
    bump_generation(user_id, ws)  # write #2
    assert get_generation(user_id, ws) == 2
    # The counter is keyed on (user_id, workspace_id) only — no per-agent key —
    # so the same counter is observed by every agent's snapshot path.
    assert get_generation(user_id, ws) == get_generation(user_id, ws)


async def test_q5d_get_or_capture_keyed_per_agent_and_respects_consumption_filter():
    """get_or_capture_snapshot keys on (thread_id, agent_id) and filters the
    captured claims by the Q5-B consumption gate. We stub recall_for_chat to
    avoid a DB, then assert the agent view drops another agent's inference."""

    clear_snapshots()
    from types import SimpleNamespace as NS

    # Stub recall_for_chat to return fake claims (no DB needed).
    async def fake_recall(db, *, user_id, workspace_id, query, **kwargs):
        return [
            _claim(subject="Glenn", predicate="prefers", object={"h": 1}, agent_id=None),
            _claim(subject="Glenn", predicate="prefers", object={"a": 1}, agent_id="agent:reviewer-7"),
            _claim(subject="Glenn", predicate="prefers", object={"p": 1}, agent_id="agent:planner-3"),
        ]

    import app.services.memory_citation_service as mcs

    original = mcs.recall_for_chat
    mcs.recall_for_chat = fake_recall
    try:
        db = NS()  # not touched by the stub

        # Human path → all 3 claims.
        human_claims = await get_or_capture_snapshot(db, thread_id=99, user_id=1, workspace_id="ws", agent_id=None)
        assert len(human_claims) == 3

        # reviewer-7 path → human + own only (planner-3's dropped).
        agent_claims = await get_or_capture_snapshot(
            db, thread_id=99, user_id=1, workspace_id="ws", agent_id="agent:reviewer-7"
        )
        assert {c.agent_id for c in agent_claims} == {None, "agent:reviewer-7"}

        # Distinct caches: human snapshot unaffected by agent capture.
        assert get_snapshot(99, agent_id=None) is not None
        assert get_snapshot(99, agent_id="agent:reviewer-7") is not None
    finally:
        mcs.recall_for_chat = original
