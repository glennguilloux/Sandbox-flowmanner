"""Blueprint + Run Pydantic schemas — request/response models and definition validation.

The BlueprintDefinition model defines the declarative JSONB structure stored
in Blueprint.definition. It mirrors the Workflow Pydantic model but excludes
runtime fields (status, output_data, retry_count on nodes).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── Blueprint definition (declarative subset of Workflow) ────────────


class BlueprintNodeDefinition(BaseModel):
    """Declarative node definition — no runtime fields."""

    id: str
    type: str  # NodeType value string
    title: str = ""
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    assigned_model: str | None = None
    assigned_agent_id: str | None = None
    max_retries: int = 3
    fallback_strategy: str = "human_escalate"


class BlueprintEdgeDefinition(BaseModel):
    """Directed edge between two blueprint nodes."""

    source: str
    target: str
    condition: str | None = None
    label: str | None = None


class BlueprintBudgetDefinition(BaseModel):
    """Budget constraints for a blueprint run."""

    max_cost_usd: float = 10.0
    max_wall_time_seconds: int = 300
    max_iterations: int = 100
    max_depth: int = 5


class BlueprintDefinition(BaseModel):
    """The declarative part of a blueprint — stored in definition JSONB.

    This maps directly to the Workflow Pydantic model's static structure.
    At execution time, it's converted via blueprint_to_workflow().
    """

    blueprint_type: str = "solo"
    nodes: list[BlueprintNodeDefinition] = Field(default_factory=list)
    edges: list[BlueprintEdgeDefinition] = Field(default_factory=list)
    budget: BlueprintBudgetDefinition = Field(default_factory=BlueprintBudgetDefinition)
    config: dict[str, Any] = Field(default_factory=dict)


# ── Request schemas ─────────────────────────────────────────────────


class BlueprintCreate(BaseModel):
    """Create a new blueprint."""

    model_config = ConfigDict(extra="forbid")

    title: str
    description: str = ""
    blueprint_type: str = "solo"
    definition: BlueprintDefinition | None = None
    input_schema: dict | None = None
    output_schema: dict | None = None
    tags: list[str] | None = None
    category: str | None = None
    icon: str | None = None


class BlueprintUpdate(BaseModel):
    """Update an existing blueprint."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    description: str | None = None
    definition: BlueprintDefinition | None = None
    status: str | None = None
    input_schema: dict | None = None
    output_schema: dict | None = None
    tags: list[str] | None = None
    category: str | None = None
    icon: str | None = None


class RunCreate(BaseModel):
    """Create a run from a blueprint."""

    model_config = ConfigDict(extra="forbid")

    input_data: dict | None = None
    budget_override: BlueprintBudgetDefinition | None = None


# ── Response schemas ────────────────────────────────────────────────


class BlueprintResponse(BaseModel):
    """Response model for a blueprint."""

    id: str
    workspace_id: str | None = None
    user_id: int
    title: str
    description: str
    blueprint_type: str
    definition: dict
    input_schema: dict | None = None
    output_schema: dict | None = None
    status: str
    version: int
    tags: list | None = None
    category: str | None = None
    icon: str | None = None
    run_count: int = 0
    last_run_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("id", "workspace_id", mode="before")
    @classmethod
    def _coerce_uuid(cls, v: Any) -> Any:
        return str(v) if isinstance(v, UUID) else v


class RunResponse(BaseModel):
    """Response model for a run."""

    id: str
    blueprint_id: str | None = None
    workspace_id: str | None = None
    user_id: int | None = None
    status: str
    snapshot: dict
    output_data: dict | None = None
    error_message: str | None = None
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    budget_limit_usd: float | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    parent_run_id: str | None = None
    input_data: dict | None = None
    meta: dict | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator(
        "id", "blueprint_id", "workspace_id", "parent_run_id", mode="before"
    )
    @classmethod
    def _coerce_uuid(cls, v: Any) -> Any:
        return str(v) if isinstance(v, UUID) else v


class RunEventResponse(BaseModel):
    """Response model for a substrate event."""

    id: str
    sequence: int
    run_id: str
    mission_id: str | None = None
    type: str
    payload: dict | None = None
    actor: str
    task_id: str | None = None
    causal_parent: int | None = None
    timestamp: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("id", "run_id", "mission_id", "task_id", mode="before")
    @classmethod
    def _coerce_uuid(cls, v: Any) -> Any:
        return str(v) if isinstance(v, UUID) else v


class BlueprintVersionResponse(BaseModel):
    """Response model for a blueprint version."""

    id: str
    blueprint_id: str
    version: int
    snapshot: dict
    description: str | None = None
    created_by: int | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("id", "blueprint_id", mode="before")
    @classmethod
    def _coerce_uuid(cls, v: Any) -> Any:
        return str(v) if isinstance(v, UUID) else v
