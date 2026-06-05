from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AgentExecutionResponse(BaseModel):
    id: str
    agent_id: str
    status: str
    result: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class AgentMemoryCreate(BaseModel):
    key: str
    value: str


class AgentMemoryResponse(BaseModel):
    id: str
    agent_id: str
    key: str
    value: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentToolCreate(BaseModel):
    name: str
    description: str | None = None
    enabled: bool = True


class AgentToolResponse(BaseModel):
    id: str
    name: str
    description: str | None
    enabled: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentToolUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
