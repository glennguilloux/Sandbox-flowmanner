from __future__ import annotations

"""Provenance-gated approval policy — GOV-1.2 (the reliable control).

This module is the single, deterministic authority for *whether a
PersonalMemoryClaim may be written directly to durable storage, or must
instead be routed to human approval (``pending_writes``).

Why this exists (GOV-1.2 background):
  The backlog skeleton specifies the policy as ``source_type ∈
  {fetched, tool_output, third_party} → mandatory human approval, no
  confidence bypass``. The as-built vocabulary differs from that proposal
  — the real ``source_type`` enum (``app/models/personal_memory_models.py``
  ``ALL_SOURCE_TYPES``) is ``{mission, conversation, user_explicit,
  program_learning}``. The *intent* maps cleanly:

    - ``user_explicit``    → the user said it directly ("Remember I prefer
                             tabs"). Highest-trust. MAY write directly.
    - ``conversation``     → inferred by the chat extractor from a normal
                             turn. Externally-derived, NOT user-affirmed.
                             Mandatory approval.
    - ``mission``          → produced by an autonomous agent run. External,
                             potentially poisoned. Mandatory approval.
    - ``program_learning`` → derived by a programmatic/background process.
                             External. Mandatory approval.

The ONLY source_type that bypasses approval is ``user_explicit``.
Everything else — including high-confidence claims — requires a human in
the loop. This is the deterministic, reliable control; the 1.3a scan is a
triage aid and the 1.3b scrub is harm reduction — neither may *de-escalate*
a provenance-mandated approval.

Invariant (do not drift): ``requires_provenance_approval`` must never
return ``False`` for an externally-derived source_type just because a
scanner or confidence score looked good. If it ever returns ``False`` for
a non-``user_explicit`` source, that re-opens the GOV-1.2 hole via a side
door and must be treated as a regression.
"""


from typing import Any

# Source types that are authored BY the user directly. These are the only
# claims we trust enough to persist without an explicit approval gate.
USER_AUTHORED_SOURCES: frozenset[str] = frozenset({"user_explicit"})

# Source types that are derived externally (agent runs, background
# programs, or inferred from ordinary conversation). All of these require
# human approval before they reach durable memory.
EXTERNALLY_DERIVED_SOURCES: frozenset[str] = frozenset({"conversation", "mission", "program_learning"})


def requires_provenance_approval(source_type: str | None) -> bool:
    """Deterministic GOV-1.2 gate.

    Returns ``True`` when the claim MUST be routed to human approval
    (``pending_writes``) instead of written directly.

    Rules:
      - ``user_explicit``   → ``False`` (user authored it; direct write OK).
      - ``None`` / unknown  → ``True``  (fail safe — never auto-write an
                              unverifiable provenance; ask the human).
      - anything else       → ``True``  (externally-derived; mandatory
                              approval, regardless of confidence).

    This function takes NO confidence/sensitivity arguments on purpose:
    provenance, not score, is the gate. A high-confidence claim from an
    external source is still an external claim.
    """
    # A missing/unknown provenance is unverifiable → fail safe and require
    # approval (stage for review, never silently commit). Only the literal
    # user-authored set may bypass; anything else — including every
    # externally-derived source_type and any typo'd value — requires
    # approval.
    return source_type not in USER_AUTHORED_SOURCES


def requires_provenance_approval_for_claim(claim: Any) -> bool:
    """Convenience wrapper that reads ``source_type`` off a claim object.

    Accepts either a ``PersonalMemoryClaim`` ORM row, a ``CandidateClaim``
    DTO (which currently carries no ``source_type`` — see caller notes),
    or any object exposing ``source_type``. Returns ``True`` (require
    approval) when the attribute is missing, to fail safe.
    """
    source_type = getattr(claim, "source_type", None)
    return requires_provenance_approval(source_type)
