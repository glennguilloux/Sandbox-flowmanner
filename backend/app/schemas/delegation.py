"""Pydantic schemas for delegation and cross-workspace membership."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DelegationCreate(BaseModel):
    delegatee_id: int
    role_id: str
    workspace_id: str | None = None
    reason: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class DelegationResponse(BaseModel):
    id: str
    delegator_id: int
    delegatee_id: int
    workspace_id: str | None = None
    role_id: str
    reason: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool
    created_at: datetime
    audit_notes: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DelegationListResponse(BaseModel):
    delegations: list[DelegationResponse]
    total: int


class WorkspaceMemberAdd(BaseModel):
    user_id: int
    role: str = Field(default="member", max_length=50)
    is_primary: bool = False


class WorkspaceMemberUpdate(BaseModel):
    role: str | None = Field(None, max_length=50)
    is_primary: bool | None = None


class WorkspaceMemberResponse(BaseModel):
    id: str
    user_id: int
    workspace_id: str
    role: str
    is_primary: bool
    joined_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkspaceMemberListResponse(BaseModel):
    members: list[WorkspaceMemberResponse]
    total: int
