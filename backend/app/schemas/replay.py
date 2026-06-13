from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ReplayEvent(BaseModel):
    id: str
    sequence: int
    run_id: str
    mission_id: str | None = None
    task_id: str | None = None
    blueprint_id: str | None = None
    type: str
    payload: dict | None = None
    causal_parent: int | None = None
    actor: str
    timestamp: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class ReplayPage(BaseModel):
    events: list[ReplayEvent]
    total: int
    next_after_sequence: int | None = None


class MissionReplayResponse(BaseModel):
    events: list[ReplayEvent]
    total: int
    mission: dict[str, Any]
    run_id: str | None
    next_after_sequence: int | None = None
    message: str | None = None
