"""Pydantic schemas for custom roles and permissions."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    workspace_id: str | None = None
    permissions: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None


class RoleResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    workspace_id: str | None = None
    is_system: bool
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime
    permissions: list[str] = []

    model_config = ConfigDict(from_attributes=True)


class RoleListResponse(BaseModel):
    roles: list[RoleResponse]
    total: int


class PermissionAdd(BaseModel):
    permission_key: str = Field(..., min_length=1, max_length=200)


class PermissionRemove(BaseModel):
    permission_key: str = Field(..., min_length=1, max_length=200)


class PermissionCheck(BaseModel):
    user_id: int
    permission_key: str
    workspace_id: str | None = None


class PermissionCheckResponse(BaseModel):
    has_permission: bool
    user_id: int
    permission_key: str
    source: str | None = None  # role name or delegation id
