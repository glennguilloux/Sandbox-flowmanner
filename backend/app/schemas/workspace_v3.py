from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=100)


class WorkspaceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    logo_url: str | None = Field(default=None, max_length=500)
    settings: dict[str, Any] | None = Field(default=None)


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    slug: str
    owner_id: int
    plan: str = "free"
    member_count: int = 0
    member_limit: int = 5
    logo_url: str | None = None
    settings: dict[str, Any] = {}
    storage_used_bytes: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkspaceListItem(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    member_count: int
    logo_url: str | None = None
    role: str
    created_at: datetime


class InviteMemberRequest(BaseModel):
    email: str = Field(..., max_length=255, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    role: str = Field(default="member", pattern="^(member|viewer|admin)$")
    message: str | None = Field(default=None, max_length=1000)


class InvitationResponse(BaseModel):
    id: str
    workspace_id: str
    email: str
    role: str
    status: str
    message: str | None = None
    created_at: datetime
    expires_at: datetime


class InvitationCreatedResponse(InvitationResponse):
    token: str


class AcceptInvitationRequest(BaseModel):
    token: str = Field(..., min_length=64, max_length=64)


class TeamCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    workspace_id: str = Field(..., min_length=36)


class TeamResponse(BaseModel):
    id: str
    workspace_id: str
    name: str
    description: str
    member_count: int = 0
    created_at: datetime


class TeamMemberResponse(BaseModel):
    user_id: int
    role: str
    joined_at: datetime


class TeamMemberCreateRequest(BaseModel):
    user_id: int
    role: str = "member"


class TeamUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class AuditLogEntry(BaseModel):
    id: str
    actor_id: int | None = None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    activity_metadata: dict[str, Any] = {}
    created_at: datetime
