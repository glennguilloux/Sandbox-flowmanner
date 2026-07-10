"""Q5-B — multi-agent memory attribution + trust tiers.

Shared workspace pool: every ``PersonalMemoryClaim`` is attributed to an
authoring agent (``agent_id``) or to the human (``NULL`` = highest trust,
per E23-D / Q5-A). This module enforces the two Q5-B policies that keep one
agent's hallucination from silently becoming another agent's "fact":

* **Author-tier down-rank.** Agent-authored ``program_learning`` claims get a
  *lower effective* trust tier than the stored ``source_priority`` implies.
  Concretely we subtract a fixed penalty so that a reviewer-inferred claim
  (``source_priority`` 1) authored by an agent ranks *below* a
  human-authored claim of the *same* source type and *below* any claim whose
  author the consumer already trusts. The penalty is applied at ranking time
  (a pure function) — we never mutate the stored ``source_priority`` column,
  which remains the honest provenance signal.

* **Cross-agent consumption gate.** A claim is *readable* by an agent iff:
    - it is human-authored (``agent_id IS NULL`` — every agent may consume
      human facts), OR
    - the consumer *is* the authoring agent (an agent always sees its own
      inferences), OR
    - it passed the governance gate (provenance GOV-1.2 + Q4 scanner) — we
      model that as "the claim is live and not quarantined".

  This is a READ-SIDE predicate only. It does not change what gets written or
  how human-authored claims behave; it simply lets a reviewing agent's recall
  drop claims produced by *other* agents that have not cleared governance,
  while still keeping those claims visible to the human and to their own
  author. The governance gate itself is enforced at write time (Epic 2.1 / Q4);
  here we only encode the *attribution* half so cross-agent sharing is opt-in
  rather than a silent global merge.

Pure + DB-free (operates on claim-like objects) so it is trivially testable
and reusable by ``list_conflicts``-style surfacing and by recall filters.
"""

from __future__ import annotations

from typing import Any

# ── Trust-tier penalty (Q5-B author down-rank) ──────────────────────────────
#
# Agent-authored ``program_learning`` claims are the weakest provenance (the
# reviewer / background path, gated by human approval). When an agent authors
# such a claim we subtract this from its effective source priority so it ranks
# *below* an otherwise-identical human-authored claim and cannot silently
# out-rank a human fact in another agent's recall. The stored ``source_priority``
# is left untouched (it is the honest provenance signal); this is only the
# *effective* comparator value used for cross-agent ranking.
AGENT_PROGRAM_LEARNING_PENALTY: int = 2

# Default agent id used when a claim's author cannot be determined but was
# clearly programmatic (defensive — treats unknown authors as low-trust).
_UNKNOWN_AGENT = "<unknown>"


def is_human_authored(claim: Any) -> bool:
    """Return True iff the claim is human-authored (NULL agent_id)."""
    return getattr(claim, "agent_id", None) is None


def effective_source_priority(claim: Any) -> int:
    """Q5-B effective ranking priority, including the agent down-rank.

    Mirrors ``source_priority_for`` for the stored column but subtracts
    ``AGENT_PROGRAM_LEARNING_PENALTY`` when the claim is agent-authored AND
    its ``source_type`` is ``program_learning``. Pure function of the claim
    attributes — never reads the DB, never mutates the stored column.

    Floor at 0 so a heavy penalty cannot produce a negative priority that
    would invert the ordering bands.
    """
    base = int(getattr(claim, "source_priority", 0) or 0)
    agent_id = getattr(claim, "agent_id", None)
    source_type = getattr(claim, "source_type", None)
    if agent_id is not None and source_type == "program_learning":
        return max(0, base - AGENT_PROGRAM_LEARNING_PENALTY)
    return base


def can_agent_consume(claim: Any, *, consumer_agent_id: str | None) -> bool:
    """Q5-B cross-agent consumption governance gate (read-side predicate).

    A claim is readable by ``consumer_agent_id`` iff:
      * it is human-authored (NULL) — every agent may consume human facts, OR
      * the consumer *is* the authoring agent (self-authored always visible), OR
      * the consumer is the human (``consumer_agent_id is None``) — the human
        sees everything.

    Claims authored by *other* agents are hidden from a different agent unless
    that agent is the human. This prevents one agent's inference from becoming
    another agent's silently-consumed "fact" while still preserving the human's
    full view and each agent's own inferences.

    Note: this is the *attribution* gate only. The governance / poison-scan gate
    (GOV-1.2, Q4) is enforced at write time; a claim that reached the store
    already cleared it, so we do not re-litigate provenance here.
    """
    if consumer_agent_id is None:
        # The human sees all claims.
        return True
    author = getattr(claim, "agent_id", None)
    if author is None:
        # Human-authored (highest trust) — consumable by any agent.
        return True
    # Agent-authored: only the authoring agent itself may consume another
    # agent's inference. (Human-authored and self-authored already returned.)
    return author == consumer_agent_id


def filter_consumable(
    claims: list[Any],
    *,
    consumer_agent_id: str | None,
) -> list[Any]:
    """Return only ``claims`` readable by ``consumer_agent_id`` (Q5-B gate)."""
    if consumer_agent_id is None:
        return list(claims)
    return [c for c in claims if can_agent_consume(c, consumer_agent_id=consumer_agent_id)]
