from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SwarmCreate(BaseModel):
    swarm_name: str
    task_type: str | None = None
    task_description: str | None = None
    consensus_strategy: str | None = None
    consensus_config: dict | None = None
    daily_limit: float | None = None
    monthly_limit: float | None = None


class SwarmUpdate(BaseModel):
    swarm_name: str | None = None
    task_type: str | None = None
    task_description: str | None = None
    status: str | None = None
    consensus_strategy: str | None = None
    consensus_config: dict | None = None
    daily_limit: float | None = None
    monthly_limit: float | None = None


class SwarmResponse(BaseModel):
    id: int
    swarm_id: str
    swarm_name: str
    task_type: str | None = None
    task_description: str | None = None
    status: str | None = None
    consensus_strategy: str | None = None
    consensus_config: dict | None = None
    daily_limit: float | None = None
    monthly_limit: float | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    dissolved_at: datetime | None = None
    created_by: int | None = None

    model_config = ConfigDict(from_attributes=True)


class SwarmAgentCreate(BaseModel):
    agent_id: str
    role: str | None = None
    assigned_model: str | None = None


class SwarmAgentAdd(BaseModel):
    agent_template_id: int
    role: str | None = None
    assigned_model: str | None = None


class SwarmAgentFromSlug(BaseModel):
    template_slug: str
    role: str | None = None
    assigned_model: str | None = None


class SwarmAgentResponse(BaseModel):
    id: int
    agent_instance_id: str
    swarm_id: str
    agent_template_id: int | None = None
    role: str | None = None
    display_name: str | None = None
    capabilities: dict | None = None
    specializations: dict | None = None
    assigned_model: str | None = None
    status: str | None = None
    load: int | None = None
    max_concurrent_tasks: int | None = None
    rating_avg: float | None = None
    rating_count: int | None = None
    joined_at: datetime | None = None
    last_active_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SwarmPopulateRequest(BaseModel):
    division: str | None = None
    template_slugs: list[str] | None = None


class SwarmTaskCreate(BaseModel):
    task_type: str = "general"
    payload: dict | None = None
    assigned_agent_id: str | None = None
    priority: int | None = None
    max_retries: int | None = 3
    dependencies: dict | None = None


class SwarmTaskUpdate(BaseModel):
    status: str | None = None
    progress: int | None = None
    result: dict | None = None
    error: str | None = None
    assigned_agent_id: str | None = None


class SwarmTaskResponse(BaseModel):
    id: str
    swarm_id: str
    parent_task_id: str | None = None
    task_type: str
    priority: int | None = None
    payload: dict | None = None
    assigned_agent_id: str | None = None
    status: str | None = None
    progress: int | None = None
    result: dict | None = None
    error: str | None = None
    created_at: datetime | None = None
    assigned_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    retry_count: int | None = None
    max_retries: int | None = None
    dependencies: dict | None = None

    model_config = ConfigDict(from_attributes=True)


class SwarmStatsResponse(BaseModel):
    total_agents: int = 0
    active_agents: int = 0
    total_tasks: int = 0
    tasks_by_status: dict[str, int] = {}
