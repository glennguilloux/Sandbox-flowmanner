"""Pydantic schemas for role CRUD and permission operations."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    permission_keys: list[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None


class PermissionAdd(BaseModel):
    permission_key: str = Field(..., min_length=1, max_length=200)


class RolePermissionResponse(BaseModel):
    id: str
    permission_key: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RoleResponse(BaseModel):
    id: str
    workspace_id: str | None
    name: str
    description: str | None
    is_system: bool
    created_by: int | None
    created_at: datetime
    updated_at: datetime
    permissions: list[RolePermissionResponse] = []

    model_config = ConfigDict(from_attributes=True)


class RoleListResponse(BaseModel):
    roles: list[RoleResponse]
    total: int


class PermissionKeyResponse(BaseModel):
    key: str
    description: str


class UserRoleAssignmentResponse(BaseModel):
    id: str
    user_id: int
    role_id: str
    workspace_id: str
    assigned_by: int | None
    assigned_at: datetime

    model_config = ConfigDict(from_attributes=True)
