"""Pydantic v2 schemas for the Critique / Critic read API (D30-60, T28).

Schemas for the v2 ``/api/v2/critiques`` router (Memory Inspector +
Programs Brief UI inspection surface):

* ``CriticKind`` — ``str, Enum`` whose value set is kept in lockstep with
  ``ALL_CRITIC_KINDS`` in ``app.models.critique_models``. The SQL CHECK
  constraint reads that tuple directly; the enum is for in-process
  validation and OpenAPI documentation.
* ``CritiqueResponse`` — response body, ORM-backed (one row per critic
  run).
* ``CritiqueListResponse`` — paginated list wrapper for
  ``GET /critiques``.

T28 is read-only — ``POST /critiques`` is intentionally NOT exposed. New
critiques are created internally by the executor hook from T27
(``CritiqueService.create_from_critic``). The inspection surface is
read-only by design.

Style notes (mirrors ``app/schemas/personal_memory.py``):
* Pydantic v2 idiom only (no v1 ``Config`` class).
* ``ConfigDict(from_attributes=True)`` on response models so the route
  can build them from a ``Critique`` ORM instance via
  ``CritiqueResponse.model_validate(orm_row)``.
* All enums are ``str, Enum`` so ``CriticKind.RECRITIC == "red_team"``
  works naturally at every API boundary.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict

# ═══════════════════════════════════════════════════════════════════════════
# Enums — ``str, Enum`` so .value is a plain string at every API boundary
# ═══════════════════════════════════════════════════════════════════════════


class CriticKind(str, Enum):
    """Taxonomy of critic runs stored in a ``Critique`` row.

    Valid values mirror ``ALL_CRITIC_KINDS`` in
    ``app.models.critique_models``. The CHECK constraint on the
    ``critic_kind`` column enforces this; the enum is for in-process
    validation and OpenAPI documentation.

    * ``red_team`` — adversarial pass (T25 ``RedTeamAgent``).
    * ``critic`` — plain critic pass (T25 ``CriticAgent``).
    * ``improvement_generator`` — improvement-suggestion pass (T26
      ``ImprovementGenerator``).
    """

    RED_TEAM = "red_team"
    CRITIC = "critic"
    IMPROVEMENT_GENERATOR = "improvement_generator"


# ═══════════════════════════════════════════════════════════════════════════
# Response models
# ═══════════════════════════════════════════════════════════════════════════


class CritiqueResponse(BaseModel):
    """Response body for critique endpoints. ORM-backed.

    Uses ``from_attributes=True`` so the route can build it directly
    from a ``Critique`` ORM instance via
    ``CritiqueResponse.model_validate(critique)``.

    Every field is present even if the underlying column is nullable —
    Pydantic returns ``None`` for missing values, which is the right
    shape for an inspection UI (a partial critic run may legitimately
    have ``None`` scores).
    """

    model_config = ConfigDict(from_attributes=True)

    # Primary key + identity.
    id: uuid.UUID
    user_id: int
    workspace_id: str
    # Anchors.
    mission_id: uuid.UUID
    program_id: uuid.UUID | None = None
    # Critic taxonomy.
    critic_kind: str
    # Scores (all nullable; bounded 0.0-1.0 for score_overall at the DB).
    score_overall: float | None = None
    score_alignment: float | None = None
    score_safety: float | None = None
    score_completeness: float | None = None
    # Verdict text + structured findings.
    summary: str | None = None
    misses: list[Any] = []
    risks: list[Any] = []
    improvements: list[Any] = []
    alternatives: list[Any] = []
    raw_response: dict[str, Any] | None = None
    # LLM provenance / cost telemetry.
    model_id: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    duration_ms: int | None = None
    # TimestampMixin columns.
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CritiqueListResponse(BaseModel):
    """Paginated list wrapper for ``GET /critiques``.

    ``page`` is 1-indexed. ``per_page`` is bounded 1..200 by the route
    (Pydantic v2 doesn't enforce a max here; the route layer caps it).
    """

    items: list[CritiqueResponse]
    total: int
    page: int
    per_page: int
