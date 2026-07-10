"""Pydantic v2 schemas for the Personal Memory MVP (D0-30, T19).

Schemas for ``PersonalMemoryClaim`` CRUD + recall/forget operations:

* ``ClaimType`` / ``Scope`` / ``SourceType`` / ``Sensitivity`` — ``str, Enum``
  classes whose value sets are kept in lockstep with the four
  ``ALL_*`` tuples in ``app.models.personal_memory_models``. The SQL
  CHECK constraints read those tuples directly; the enums are for
  in-process validation and OpenAPI documentation.
* ``PersonalMemoryClaimCreate`` — request body for ``POST /claims``
* ``PersonalMemoryClaimUpdate`` — PATCH body (all fields Optional)
* ``PersonalMemoryClaimResponse`` — response body, ORM-backed
* ``PersonalMemoryRecallRequest`` — query, scopes, top_k, min_confidence
* ``PersonalMemoryRecallItem`` — one recalled claim + similarity
* ``PersonalMemoryRecallResponse`` — list + total wrapper
* ``PersonalMemoryListResponse`` — paginated list wrapper
* ``PersonalMemoryForgetRequest`` — ``{ hard: bool = False }`` for the
  explicit POST /forget endpoint

Style notes (mirrors ``app/schemas/program.py``):
* ``ConfigDict(extra="forbid")`` on create / update / request models.
* ``ConfigDict(from_attributes=True)`` on response models.
* Pydantic v2 idiom only (no v1 ``Config`` class).
* All enums are ``str, Enum`` so ``ClaimType.FACT == "fact"`` works
  naturally at every API boundary.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ═══════════════════════════════════════════════════════════════════════════
# Enums — ``str, Enum`` so .value is a plain string at every API boundary
# ═══════════════════════════════════════════════════════════════════════════


class ClaimType(str, Enum):
    """Taxonomy of claim kinds stored in a ``PersonalMemoryClaim``.

    Valid values mirror ``ALL_CLAIM_TYPES`` in
    ``app.models.personal_memory_models``. The CHECK constraint on the
    DB column enforces this; the enum is for in-process validation and
    OpenAPI documentation.
    """

    FACT = "fact"
    PREFERENCE = "preference"
    OBSERVATION = "observation"
    SENSITIVE = "sensitive"
    CONSTRAINT = "constraint"


class Scope(str, Enum):
    """Visibility scope of a claim.

    * ``personal`` — owned by the user, never shared.
    * ``workspace`` — shared with workspace members.
    * ``program`` — shared with a mission program's participants.
    * ``private`` — encrypted at rest, only readable by the owner.
    """

    PERSONAL = "personal"
    WORKSPACE = "workspace"
    PROGRAM = "program"
    PRIVATE = "private"


class SourceType(str, Enum):
    """Where a claim came from. Used for provenance + trust weighting."""

    MISSION = "mission"
    CONVERSATION = "conversation"
    USER_EXPLICIT = "user_explicit"
    PROGRAM_LEARNING = "program_learning"


class Sensitivity(str, Enum):
    """PII / redaction level. Drives downstream filtering and redaction."""

    NORMAL = "normal"
    SENSITIVE = "sensitive"
    RESTRICTED = "restricted"


# ═══════════════════════════════════════════════════════════════════════════
# CRUD: Create / Update / Response
# ═══════════════════════════════════════════════════════════════════════════


class PersonalMemoryClaimCreate(BaseModel):
    """Request body for ``POST /claims`` (create a new claim).

    All ``*_type`` / ``*_sensitivity`` fields are constrained to the
    enum value sets by the SQL CHECK constraint. Pydantic v2 also
    validates the enum on parse so a typo in the client returns 422,
    not 500.
    """

    model_config = ConfigDict(extra="forbid")

    user_id: int
    workspace_id: str
    subject: str = Field(min_length=1, max_length=255)
    predicate: str = Field(min_length=1, max_length=100)
    object: dict[str, Any]
    claim_type: ClaimType
    scope: Scope
    source_type: SourceType
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    sensitivity: Sensitivity = Sensitivity.NORMAL
    source_id: uuid.UUID | None = None
    expires_at: datetime | None = None
    # Epic 2.3 E23-D / Q5-A — provenance of the authoring agent. Omit (NULL)
    # for human-authored claims (highest trust). Agent-written claims carry
    # the authoring agent id so they can be attributed and down-ranked (Q5-B).
    agent_id: str | None = None


class PersonalMemoryClaimUpdate(BaseModel):
    """Request body for ``PATCH /claims/{id}`` (PATCH semantics).

    All fields Optional. Fields NOT in this schema (user_id,
    workspace_id, id, claim_type, scope, source_type, created_at,
    updated_at) cannot be changed via PATCH — ``extra="forbid"``
    raises 422 if a client tries.

    Note: ``claim_type`` / ``scope`` / ``source_type`` are
    intentionally NOT editable via PATCH because changing a claim's
    taxonomy would invalidate provenance. Re-create the claim if you
    need to reclassify.
    """

    model_config = ConfigDict(extra="forbid")

    subject: str | None = Field(default=None, min_length=1, max_length=255)
    predicate: str | None = Field(default=None, min_length=1, max_length=100)
    object: dict[str, Any] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    sensitivity: Sensitivity | None = None
    expires_at: datetime | None = None


class PersonalMemoryClaimResponse(BaseModel):
    """Response body for claim endpoints. ORM-backed.

    Uses ``from_attributes=True`` so the route / CQRS handler can
    build it directly from a ``PersonalMemoryClaim`` ORM instance via
    ``PersonalMemoryClaimResponse.model_validate(claim)``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: int
    workspace_id: str
    subject: str
    predicate: str
    object: dict[str, Any]
    claim_type: str
    scope: str
    source_type: str
    sensitivity: str
    confidence: float
    importance: float
    source_id: uuid.UUID | None = None
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Epic 2.3 E23-D / Q5-A — authoring agent id. NULL = human-authored
    # (highest trust). Surfaced to the Memory Inspector so an agent's
    # inferences are distinguishable from user-stated facts.
    agent_id: str | None = None


# ═══════════════════════════════════════════════════════════════════════════
# Operations: Recall / List / Forget
# ═══════════════════════════════════════════════════════════════════════════


class PersonalMemoryRecallRequest(BaseModel):
    """Request body for ``POST /claims/recall``.

    ``query`` is matched against (subject, predicate) via a simple
    case-insensitive substring search in T19. T20+ will replace this
    with semantic search via embeddings.
    """

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=512)
    scopes: list[Scope] | None = None
    top_k: int = Field(default=10, ge=1, le=100)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class PersonalMemoryRecallItem(PersonalMemoryClaimResponse):
    """One recalled claim in a recall response.

    Inherits all claim fields from ``PersonalMemoryClaimResponse``
    (so callers get a flat shape: ``id``, ``subject``, ``predicate``,
    etc.) and adds a ``similarity`` score (T20+ semantic search
    scoring). For T19 (substring match) it's always ``None``.

    Inherits ``from_attributes=True`` from the parent — instantiable
    from an ORM instance via ``PersonalMemoryRecallItem(**claim.__dict__)``.
    """

    similarity: float | None = None


class PersonalMemoryRecallResponse(BaseModel):
    """Response body for ``POST /claims/recall``."""

    items: list[PersonalMemoryRecallItem]
    total: int


class PersonalMemoryListResponse(BaseModel):
    """Paginated list wrapper for ``GET /claims``.

    ``page`` is 1-indexed. ``per_page`` is bounded 1..100 by the route
    (Pydantic v2 doesn't enforce a max here; the route layer caps it).
    """

    items: list[PersonalMemoryClaimResponse]
    total: int
    page: int
    per_page: int


class PersonalMemoryForgetRequest(BaseModel):
    """Request body for the explicit ``POST /forget`` endpoint.

    ``claim_id`` is the UUID of the claim to forget. ``hard=False`` (the
    default) is a soft-delete (sets ``deleted_at``); ``hard=True`` removes
    the row from the table.
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=36, max_length=36)
    hard: bool = False


# ═══════════════════════════════════════════════════════════════════════════
# Provenance (T32) — per-claim audit summary for the Memory Inspector's
# "Why does FlowManner think this?" drawer.
# ═══════════════════════════════════════════════════════════════════════════


class PersonalMemoryProvenanceResponse(BaseModel):
    """Response body for ``GET /api/v2/personal_memory/claims/{id}/provenance``.

    Mirrors the shape returned by
    ``MemoryCorrectionService.get_provenance()`` (D30-60, T29 service),
    re-exported through the v2 envelope so the Memory Inspector UI can
    render the audit trail.

    Notes:
    * ``events_by_type`` always contains every key in
      ``app.models.memory_correction_models.ALL_EVENT_TYPES`` (zero-count
      buckets are filled in by the service layer). This lets the UI
      render a stable "Activity" widget without checking for missing
      keys.
    * ``last_event_type`` and ``last_actor`` are strings, not enums, so
      a future ALL_* change in the model doesn't require a schema
      version bump.
    * All datetime fields are nullable — a claim with no recorded audit
      events returns ``event_count: 0`` and ``*_at: None``.
    """

    model_config = ConfigDict(from_attributes=True)

    claim_id: uuid.UUID
    event_count: int
    first_event_at: datetime | None = None
    last_event_at: datetime | None = None
    last_event_type: str | None = None
    last_actor: str | None = None
    events_by_type: dict[str, int]


# ═══════════════════════════════════════════════════════════════════════════
# Provenance trace (Epic 3.6) — the full "Why does the agent believe X?"
# surface for a single claim: the claim itself + its origin provenance +
# the durable correction/audit trail. Pure exposure over data that already
# exists (PersonalMemoryClaim + MemoryCorrectionEvent rows).
# ═══════════════════════════════════════════════════════════════════════════


class PersonalMemoryProvenanceInfo(BaseModel):
    """Origin provenance for a single claim (Epic 3.6).

    These are the columns on ``PersonalMemoryClaim`` that answer "where did
    this belief come from and how much do we trust it": the source type +
    the source row id, when it was first learned, and the confidence /
    importance / scope weighting.

    Note on ``source_mission_id``: the claim model stores a *generic*
    ``source_id`` (UUID) whose meaning is disambiguated by ``source_type``.
    ``source_mission_id`` is a convenience projection — it equals
    ``source_id`` when ``source_type == "mission"`` and is ``None``
    otherwise, so a UI can link straight to the originating mission without
    re-deriving the relationship.
    """

    model_config = ConfigDict(from_attributes=True)

    source_type: str
    source_id: uuid.UUID | None = None
    source_mission_id: uuid.UUID | None = None
    created_at: datetime | None = None
    confidence: float
    importance: float
    scope: str


class PersonalMemoryProvenanceTraceResponse(BaseModel):
    """Response body for ``GET /claims/{id}/provenance`` (Epic 3.6).

    The full provenance trace for one claim:

    * ``claim`` — the claim itself (ORM-backed full record).
    * ``provenance`` — the origin provenance projection
      (``PersonalMemoryProvenanceInfo``).
    * ``corrections`` — the durable ``memory_correction_events`` audit
      trail scoped to this claim, most-recent-first.
    * ``audit_summary`` — the T32 aggregate summary (event counts by type,
      first/last event). Preserved from the original ``/provenance``
      endpoint so nothing regresses for callers that relied on the
      roll-up view.

    Always scoped to ``(user_id, workspace_id)`` at the service layer — a
    claim not visible to the caller yields a 404 envelope (never a
    cross-tenant leak).
    """

    claim: PersonalMemoryClaimResponse
    provenance: PersonalMemoryProvenanceInfo
    corrections: list[PersonalMemoryCorrectionResponse]
    audit_summary: PersonalMemoryProvenanceResponse


# ═══════════════════════════════════════════════════════════════════════════
# Memory corrections / audit trail listing (GOV-1.6, C3 read-side + C5)
#
# GET /api/v2/personal_memory/corrections surfaces the durable
# ``memory_correction_events`` audit trail (the same privacy trail every
# memory op writes to via ``PersonalMemoryService._safe_audit``) so the
# Inspector can finally READ the feedback loop that was closed at write
# time but never surfaced. ``drop`` events (GOV-1.6 / C5) are dropped
# extraction candidates — claim_id is None, the candidate shape lives in
# ``details``.
# ═══════════════════════════════════════════════════════════════════════════


class PersonalMemoryCorrectionResponse(BaseModel):
    """One row of the ``memory_correction_events`` audit trail.

    Maps directly onto the ``MemoryCorrectionEvent`` ORM row. ``claim_id``
    is nullable (``drop`` events and memory-drain ``review`` events carry
    no ``PersonalMemoryClaim`` FK). ``details`` is the free-form JSONB
    forensic blob (old/new value, drop reason, reviewer decision, …).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_id: uuid.UUID | None = None
    event_type: str
    actor: str
    source: str | None = None
    details: dict[str, Any] | None = None
    created_at: datetime | None = None


class PersonalMemoryCorrectionListResponse(BaseModel):
    """Paginated envelope body for ``GET /personal_memory/corrections``."""

    items: list[PersonalMemoryCorrectionResponse]
    total: int
    page: int
    per_page: int
    pages: int


# ═══════════════════════════════════════════════════════════════════════════
# Epic 2.3 E23-C — conflict surfacing (read-only, never silent-merge)
# ═══════════════════════════════════════════════════════════════════════════


class ConflictMemberResponse(BaseModel):
    """One claim inside a conflict group, with its rank + why it lost."""

    claim: PersonalMemoryClaimResponse
    rank: int
    superseded_because: str | None = None


class ConflictGroupResponse(BaseModel):
    """A set of live claims that conflict on (subject, predicate)."""

    subject: str
    predicate: str
    winner: PersonalMemoryClaimResponse
    losers: list[ConflictMemberResponse]


class ConflictListResponse(BaseModel):
    """Envelope body for ``GET /personal_memory/conflicts``."""

    items: list[ConflictGroupResponse]
    total: int
