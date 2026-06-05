from datetime import datetime

from pydantic import BaseModel, ConfigDict


class WorkflowCreate(BaseModel):
    name: str
    description: str | None = None


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: str | None
    user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkflowRunCreate(BaseModel):
    workflow_id: str
    input_data: dict | None = None


class WorkflowRunResponse(BaseModel):
    id: str
    workflow_id: str
    status: str
    input_data: dict | None
    output_data: dict | None
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class WorkflowExecutionCreate(BaseModel):
    workflow_id: str
    input_data: dict | None = None


class WorkflowExecutionResponse(BaseModel):
    id: str
    workflow_id: str
    status: str
    input_data: dict | None
    output_data: dict | None
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
