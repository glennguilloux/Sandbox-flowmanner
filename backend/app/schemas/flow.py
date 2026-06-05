from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str | None
    user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FlowRunCreate(BaseModel):
    project_id: str
    name: str
    description: str | None = None


class FlowRunResponse(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None
    status: str
    user_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FlowStepCreate(BaseModel):
    flow_run_id: str
    name: str
    step_type: str
    config: dict | None = None


class FlowStepResponse(BaseModel):
    id: str
    flow_run_id: str
    name: str
    step_type: str
    status: str
    config: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
