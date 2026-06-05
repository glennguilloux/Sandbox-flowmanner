from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from app.models.mission_models import MissionStatus, MissionTaskStatus


class MissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    description: str = ""
    mission_type: str | None = None
    priority: str | None = None


class MissionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    description: str | None = None
    status: MissionStatus | None = None
    priority: str | None = None
    mission_type: str | None = None
    error_message: str | None = None
    results: dict | None = None
    tokens_used: int | None = None
    actual_cost: float | None = None


class MissionResponse(BaseModel):
    id: uuid.UUID
    user_id: int
    title: str
    description: str
    mission_type: str | None = None
    status: MissionStatus | None = None
    priority: str | None = None
    plan: dict | None = None
    results: dict | None = None
    error_message: str | None = None
    tokens_used: int | None = None
    estimated_cost: float | None = None
    actual_cost: float | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    progress: int | None = None
    eta: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MissionTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    description: str | None = None
    task_type: str = "general"
    order_index: int | None = None
    input_data: dict | None = None
    dependencies: list | dict | None = None
    assigned_agent_id: uuid.UUID | None = None
    assigned_model: str | None = None


class MissionTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    description: str | None = None
    status: MissionTaskStatus | None = None
    output_data: dict | None = None
    error_message: str | None = None
    tokens_used: int | None = None
    cost: float | None = None


class MissionTaskResponse(BaseModel):
    id: uuid.UUID
    mission_id: uuid.UUID
    title: str
    description: str | None = None
    task_type: str
    order_index: int | None = None
    assigned_agent_id: str | None = None
    assigned_model: str | None = None
    status: MissionTaskStatus | None = None
    input_data: dict | None = None
    output_data: dict | None = None
    dependencies: list | dict | None = None
    retry_count: int | None = None
    max_retries: int | None = None
    timeout_seconds: int | None = None
    tokens_used: int | None = None
    cost: float | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MissionLogCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    level: str = "info"
    data: dict | None = None


class MissionLogResponse(BaseModel):
    id: uuid.UUID
    mission_id: uuid.UUID
    task_id: uuid.UUID | None = None
    level: str | None = None
    message: str
    data: dict | None = None
    timestamp: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MissionExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_preference: str | None = None


class MissionExecutionStatus(BaseModel):
    mission_id: uuid.UUID | None = None
    status: MissionStatus | None = None
    current_task_index: int | None = None
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    total_tokens_used: int = 0
    started_at: datetime | None = None
    estimated_completion: datetime | None = None


class MissionImprovementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    failure_type: str
    failure_context: str | None = None


class MissionImprovementResponse(BaseModel):
    id: uuid.UUID
    mission_id: uuid.UUID
    suggestion: str
    priority: str
    status: str
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class MissionAnalyticsResponse(BaseModel):
    total_missions: int = 0
    success_rate: float = 0.0
    avg_completion_time: float | None = None
    total_tokens_used: int = 0


class PaginatedMissions(BaseModel):
    """Typed paginated response for mission list endpoints."""
    items: list[MissionResponse]
    total: int
    page: int
    per_page: int
    pages: int


class MissionListResult(BaseModel):
    """Typed mission list result (non-paginated)."""
    missions: list[MissionResponse]
    total: int


class MissionAnalyticsResult(BaseModel):
    """Typed mission analytics response — field types kept as Any for flexibility."""
    summary: Any = None
    over_time: Any = None
    token_usage: Any = None
    failure_analysis: Any = None

