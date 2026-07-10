"""Epic 2.3 E23-C — conflict detection (read-time, computed).

Pure, DB-free grouping of overlapping live claims so the Inspector can
*surface* (never silently merge) contradictions in the canonical personal
memory store. This is the detection half of the 2.3 policy; the ranking half
(E23-B lexicographic ordering) is already wired into ``recall()``.

Policy (per ``docs/EPIC-2.3-CONFLICT-RESOLUTION-POLICY-DESIGN.md`` §3.1 and
``.sisyphus/plans/Q1-Q6-IMPLEMENTATION-DECOMPOSITION.md`` §2 E23-C):

* Two live, non-deleted, non-expired claims **conflict** iff they share the
  same ``subject`` (case-insensitive) **and** the same ``predicate`` (exact),
  **and** their ``object`` values differ.
* Within a conflict group the **winner** is chosen by precedence:
  ``claim_type precedence > source_priority > created_at > confidence``.
  ``claim_type`` precedence: ``constraint``/``fact`` outrank
  ``preference``/``observation``/``sensitive`` — so a human-stated fact beats
  a reviewer-inferred (``program_learning``) claim instead of the higher
  confidence silently overriding it.
* The system **never deletes or merges**. Losers stay live and are returned
  alongside the winner with an explainable ``superseded_because`` string.

No migration, no write path change — this module is read-only grouping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.personal_memory_models import PersonalMemoryClaim

# ── Claim-type precedence (higher = wins a conflict) ────────────────────────
#
# Mirrors the ``SOURCE_PRIORITY``/``lexicographic_rank`` convention in
# ``personal_memory_service.py``: a single module constant, integer-ordered,
# documented. ``constraint`` and ``fact`` are authoritative; ``sensitive`` sits
# below them (it is a guarded claim, not necessarily more trustworthy);
# ``preference``/``observation`` are soft. Lower = more likely to be the loser
# when it disagrees with a human-authored fact.
CLAIM_TYPE_PRECEDENCE: dict[str, int] = {
    "constraint": 5,
    "fact": 4,
    "sensitive": 3,
    "observation": 2,
    "preference": 1,
}
_CLAIM_TYPE_DEFAULT_PRECEDENCE = 0


@dataclass
class ConflictMember:
    """One claim inside a conflict group, ranked."""

    claim: PersonalMemoryClaim
    rank: int
    superseded_because: str | None = None


@dataclass
class ConflictGroup:
    """A set of live claims that conflict on (subject, predicate)."""

    subject: str
    predicate: str
    members: list[ConflictMember] = field(default_factory=list)

    @property
    def winner(self) -> PersonalMemoryClaim | None:
        return self.members[0].claim if self.members else None

    @property
    def losers(self) -> list[PersonalMemoryClaim]:
        return [m.claim for m in self.members[1:]]


def _claim_type_precedence(claim: PersonalMemoryClaim) -> int:
    ct = (getattr(claim, "claim_type", None) or "").lower()
    return CLAIM_TYPE_PRECEDENCE.get(ct, _CLAIM_TYPE_DEFAULT_PRECEDENCE)


def _source_priority(claim: PersonalMemoryClaim) -> int:
    return int(getattr(claim, "source_priority", 0) or 0)


def _winner_sort_key(claim: PersonalMemoryClaim) -> tuple:
    """Higher tuple = wins. claim_type > source_priority > recency > confidence."""
    created = getattr(claim, "created_at", None)
    conf = float(getattr(claim, "confidence", 0.0) or 0.0)
    return (
        _claim_type_precedence(claim),
        _source_priority(claim),
        created,  # newer first; None sorts lowest
        conf,
        str(getattr(claim, "id", "")),  # stable tiebreak
    )


def _objects_equal(a: Any, b: Any) -> bool:
    """Shallow equality on the JSONB ``object`` dict (order-insensitive)."""
    try:
        return dict(a or {}) == dict(b or {})
    except (TypeError, ValueError):
        return a == b


def _predicates_conflict(a: PersonalMemoryClaim, b: PersonalMemoryClaim) -> bool:
    """Exact predicate match (the swappable seam 3.1 can later make semantic)."""
    pa = (getattr(a, "predicate", None) or "").strip().lower()
    pb = (getattr(b, "predicate", None) or "").strip().lower()
    return bool(pa) and pa == pb


# ── Q5-C — agent-assertion contradiction surfacing (reuses group_conflicts) ──
#
# Multi-agent memory sharing needs to surface, not silently collapse,
# *opposing* assertions made by different agents (or an agent vs a human) on
# the same (subject, predicate). E23-C's ``group_conflicts`` already groups
# by (subject, predicate) with differing ``object`` and picks a winner by
# claim-type precedence then provenance, keeping losers live with an
# explainable ``superseded_because``. Q5-C wraps that with a contradiction
# *narrative* string: "A asserts X, B asserts ¬X" + the deterministic winner
# reason, returned to the orchestrator so it can decide (never auto-merged).


@dataclass
class SurfacedContradiction:
    """One surfaced contradiction between two (or more) agents' assertions."""

    subject: str
    predicate: str
    # The human/orchestrator-facing narrative, e.g.
    #   "agent:reviewer-7 asserts {object_a}; agent:planner-3 asserts {object_b}"
    narrative: str
    winner_agent_id: str | None
    loser_agent_ids: list[str]
    # The deterministic E23-C precedence reason (why winner won).
    resolution_reason: str
    # Raw members so a caller can inspect the full set if needed.
    members: list[ConflictMember] = field(default_factory=list)


def _author_label(claim: PersonalMemoryClaim) -> str:
    agent_id = getattr(claim, "agent_id", None)
    if agent_id is None:
        return "human"
    return f"agent:{agent_id}"


def surface_agent_contradictions(
    claims: list[PersonalMemoryClaim],
) -> list[SurfacedContradiction]:
    """Q5-C — surface (subject, predicate) contradictions across agents.

    Reuses E23-C ``group_conflicts`` (which already keys on
    (subject, predicate) with opposing ``object`` and resolves by claim-type
    precedence then provenance). For each conflict group we emit a
    ``SurfacedContradiction`` with a human-readable narrative naming the
    asserting agents and the deterministic winner reason. Losers are never
    deleted or merged — the orchestrator decides.

    Returns an empty list when no live, multi-author contradictions exist.
    """
    groups = group_conflicts(claims)
    out: list[SurfacedContradiction] = []
    for g in groups:
        if not g.members:
            continue
        # Build "X asserts <obj>; Y asserts <obj>" narrative, one clause per
        # member, in ranked order (winner first) so the narrative reads with
        # the winner first.
        clauses: list[str] = []
        for m in g.members:
            c = m.claim
            obj = getattr(c, "object", None)
            try:
                import json

                obj_text = json.dumps(obj, default=str, sort_keys=True)
            except (TypeError, ValueError):
                obj_text = str(obj)
            clauses.append(f"{_author_label(c)} asserts {obj_text}")
        narrative = "; ".join(clauses)
        winner = g.winner
        winner_agent_id = getattr(winner, "agent_id", None)
        loser_agent_ids = [
            str(getattr(m.claim, "agent_id", None))
            for m in g.members[1:]
            if getattr(m.claim, "agent_id", None) is not None
        ]
        resolution_reason = g.members[1].superseded_because or "lower composite precedence"
        out.append(
            SurfacedContradiction(
                subject=g.subject,
                predicate=g.predicate,
                narrative=narrative,
                winner_agent_id=winner_agent_id,
                loser_agent_ids=loser_agent_ids,
                resolution_reason=resolution_reason,
                members=g.members,
            )
        )
    return out


def group_conflicts(
    claims: list[PersonalMemoryClaim],
) -> list[ConflictGroup]:
    """Group live ``claims`` into conflict groups.

    Only live (non-deleted, non-expired) claims are considered. Two claims
    conflict iff same ``subject`` (case-insensitive) + same ``predicate`` +
    differing ``object``. Returns **only** groups with more than one member.
    """
    live: list[PersonalMemoryClaim] = [
        c for c in claims if not getattr(c, "deleted_at", None) and not getattr(c, "expires_at", None)
    ]

    groups: dict[tuple[str, str], list[PersonalMemoryClaim]] = {}
    for c in live:
        subj = (getattr(c, "subject", None) or "").strip().lower()
        pred = (getattr(c, "predicate", None) or "").strip().lower()
        if not subj or not pred:
            continue
        key = (subj, pred)
        bucket = groups.setdefault(key, [])
        # Only join claims that actually differ in object (a duplicate is not
        # a conflict — it is flagged separately by the caller if desired).
        if not any(_objects_equal(c.object, b.object) for b in bucket):
            bucket.append(c)

    result: list[ConflictGroup] = []
    for (subj, pred), members in groups.items():
        if len(members) < 2:
            continue
        ranked = sorted(members, key=_winner_sort_key, reverse=True)
        group = ConflictGroup(subject=subj, predicate=pred)
        winner = ranked[0]
        for i, m in enumerate(ranked):
            reason: str | None = None
            if i > 0:
                reason = _explain_supersede(m, winner)
            group.members.append(ConflictMember(claim=m, rank=i, superseded_because=reason))
        result.append(group)
    return result


def _explain_supersede(loser: PersonalMemoryClaim, winner: PersonalMemoryClaim) -> str:
    """Explain why ``loser`` lost to ``winner`` (the audit trail 2.3 owes)."""
    lt = _claim_type_precedence(loser)
    wt = _claim_type_precedence(winner)
    if lt != wt:
        return (
            f"lower claim-type precedence ({getattr(loser, 'claim_type', '?')} < {getattr(winner, 'claim_type', '?')})"
        )
    ls = _source_priority(loser)
    ws = _source_priority(winner)
    if ls != ws:
        return f"lower source priority ({ls} < {ws})"
    lc = float(getattr(loser, "created_at", None) is not None)
    if getattr(loser, "created_at", None) != getattr(winner, "created_at", None):
        return "older write (recency)"
    if float(getattr(loser, "confidence", 0.0) or 0.0) != float(getattr(winner, "confidence", 0.0) or 0.0):
        return "lower confidence"
    return "lower composite precedence"


async def list_conflicts(
    db: Any,
    user_id: int,
    workspace_id: str,
    scope: str | None = None,
) -> list[ConflictGroup]:
    """Fetch live claims for (user, workspace) and return conflict groups.

    Thin read helper: pulls all live claims via ``PersonalMemoryService``
    semantics (filtered by tenant) then delegates to ``group_conflicts``. The
    grouping stays in Python — for a personal-memory store (hundreds–low
    thousands of claims per user) this is fine (see design doc §4 risk 4).
    """
    from app.services.personal_memory_service import PersonalMemoryService

    service = PersonalMemoryService(db)
    claims, _total = await service.list_for_user(
        user_id=user_id,
        workspace_id=workspace_id,
        scope=scope,
        limit=10_000,
        offset=0,
    )
    return group_conflicts(claims)
