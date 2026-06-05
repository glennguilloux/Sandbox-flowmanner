from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class GraphWorkflowCreate(BaseModel):
    name: str
    description: str | None = None
    graph_definition: dict | None = None
    node_type_category: str | None = None  # H6 — transformation category
    transformation_config: dict | None = None  # H6 — transformation config


class GraphWorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    graph_definition: dict | None = None
    status: str | None = None
    node_type_category: str | None = None  # H6
    transformation_config: dict | None = None  # H6


class GraphWorkflowResponse(BaseModel):
    id: str | UUID
    name: str
    description: str | None = None
    graph_definition: dict | None = None
    status: str = "draft"
    user_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GraphExecutionCreate(BaseModel):
    input_data: dict | None = None


class GraphExecutionResponse(BaseModel):
    id: str | UUID
    workflow_id: str | UUID
    status: str
    input_data: dict | None = None
    output_data: dict | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class GraphExecutionDetailResponse(BaseModel):
    id: str | UUID
    workflow_id: str | UUID
    status: str
    input_data: dict | None = None
    output_data: dict | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    created_at: datetime
    completed_at: datetime | None = None
    node_states: list[dict] = []

    model_config = ConfigDict(from_attributes=True)


class GraphStateResponse(BaseModel):
    id: str | UUID
    workflow_id: str | UUID | None = None
    execution_id: str | UUID | None = None
    state_data: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
