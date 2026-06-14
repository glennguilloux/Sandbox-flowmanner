"""Pydantic v2 schemas for Mission Programs (T2).

Schemas for:
- Program CRUD: ``ProgramCreate``, ``ProgramUpdate``, ``ProgramResponse``
- Program runs: ``ProgramRunResponse``
- Operations: ``ConsolidateRequest``, ``ConsolidateResponse``, ``FireRequest``
- Learning brief: ``LearningBriefBase`` (read-write structured brief, with
  the user-controlled ``user_notes`` field that consolidation MUST NEVER touch)
- Trigger config: discriminated union on ``type`` (``cron`` | ``webhook`` | ``manual``)

Style notes (mirrors ``app/schemas/mission.py``):
- ``ConfigDict(extra="forbid")`` on create / update / request models.
- ``ConfigDict(from_attributes=True)`` on response models.
- Pydantic v2 idiom only (no v1 ``Config`` class).
- No cross-program reference fields (locked scope).
- No ``next_consolidation_at`` (no auto-consolidation per Glenn's decision).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


# ── Trigger config discriminated union ────────────────────────────────────


class CronTrigger(BaseModel):
    """Cron-style recurring trigger."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["cron"]
    expression: str
    timezone: str = "UTC"


class WebhookTrigger(BaseModel):
    """Webhook-driven trigger (incoming HTTP POST)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["webhook"]
    secret: str
    path: str


class ManualTrigger(BaseModel):
    """Manual / on-demand trigger (no schedule)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["manual"]


# Discriminated union: Pydantic v2 routes by the ``type`` field.
TriggerConfig = Annotated[
    Union[CronTrigger, WebhookTrigger, ManualTrigger],
    Field(discriminator="type"),
]


# ── Learning brief ────────────────────────────────────────────────────────


class LearningBriefBase(BaseModel):
    """Structured learning brief — read-write.

    Documented sub-keys mirror the JSONB column on ``MissionProgram.learning_brief``.
    The LLM-driven consolidation path updates the structured fields; the
    user-driven path updates ``user_notes``. The two paths are intentionally
    isolated: consolidation MUST NEVER overwrite ``user_notes`` (column-level
    UPDATE discipline in the service layer; this schema is the contract).
    """

    model_config = ConfigDict(extra="forbid")

    total_runs: int = 0
    success_rate: float = 0.0
    avg_cost_usd: float = 0.0
    avg_tokens: int = 0
    common_failures: list[dict[str, Any]] = Field(default_factory=list)
    effective_tools: list[str] = Field(default_factory=list)
    ineffective_tools: list[str] = Field(default_factory=list)
    hitl_history: list[dict[str, Any]] = Field(default_factory=list)
    plan_adjustments: str = ""
    last_consolidated_at: str | None = None
    # SEPARATE field — consolidation MUST NEVER touch this. User-owned.
    user_notes: str = ""


# ── Program CRUD ──────────────────────────────────────────────────────────


class ProgramCreate(BaseModel):
    """Request body for ``POST /programs``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    mission_type: str | None = None
    base_constraints: dict[str, Any] | None = None
    base_context_files: dict[str, Any] | None = None
    base_context_urls: dict[str, Any] | None = None
    trigger_config: TriggerConfig | None = None
    per_run_budget_usd: float | None = Field(default=None, ge=0)
    monthly_budget_usd: float | None = Field(default=None, ge=0)


class ProgramUpdate(BaseModel):
    """Request body for ``PATCH /programs/{id}`` — PATCH semantics.

    All fields Optional. ``status`` is restricted to the documented literals
    so a typo in the client returns 422, not 500.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    mission_type: str | None = None
    base_constraints: dict[str, Any] | None = None
    base_context_files: dict[str, Any] | None = None
    base_context_urls: dict[str, Any] | None = None
    trigger_config: TriggerConfig | None = None
    per_run_budget_usd: float | None = Field(default=None, ge=0)
    monthly_budget_usd: float | None = Field(default=None, ge=0)
    status: Literal["active", "paused", "archived"] | None = None


class ProgramResponse(BaseModel):
    """Response body for program endpoints.

    Uses ``from_attributes=True`` so it can be constructed directly from a
    ``MissionProgram`` ORM instance via ``ProgramResponse.model_validate(obj)``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: int
    workspace_id: str
    name: str
    description: str
    mission_type: str | None = None
    base_constraints: dict[str, Any] | None = None
    base_context_files: dict[str, Any] | None = None
    base_context_urls: dict[str, Any] | None = None
    # trigger_config and learning_brief are stored as JSONB dicts; we expose
    # them as raw dicts in the response (clients re-validate against the
    # TriggerConfig / LearningBriefBase schemas if they need type checking).
    trigger_config: dict[str, Any] | None = None
    learning_brief: dict[str, Any] | None = None
    status: str
    per_run_budget_usd: float | None = None
    monthly_budget_usd: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ProgramRunResponse(BaseModel):
    """Response body for program-run endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    program_id: uuid.UUID
    mission_id: uuid.UUID
    trigger_type: str
    trigger_payload: dict[str, Any] | None = None
    status: str
    cost_usd: float | None = None
    tokens_used: int | None = None
    duration_seconds: float | None = None
    outcome_summary: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


# ── Operations: consolidate + fire ────────────────────────────────────────


class ConsolidateRequest(BaseModel):
    """Request body for ``POST /programs/{id}/consolidate``.

    ``limit`` controls how many of the most-recent completed runs are fed to
    the consolidation LLM. Bounded 1..50 to prevent runaway consolidation
    runs.
    """

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=10, ge=1, le=50)


class ConsolidateResponse(BaseModel):
    """Response body for ``POST /programs/{id}/consolidate``."""

    consolidated_runs: int
    brief: LearningBriefBase
    duration_ms: int


class FireRequest(BaseModel):
    """Request body for ``POST /programs/{id}/fire``.

    ``trigger_payload`` is optional — manual fires need no payload, but
    webhook replays and cron re-fires do.
    """

    model_config = ConfigDict(extra="forbid")

    trigger_payload: dict[str, Any] | None = None
