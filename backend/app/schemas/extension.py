"""Extension schemas (Task 3.5)."""

from typing import Any

from pydantic import BaseModel, ConfigDict


class ExtensionManifest(BaseModel):
    name: str
    version: str
    description: str | None = None
    author: str | None = None
    tools: list[dict[str, Any]] = []
    capabilities: list[str] = []
    config_schema: dict[str, Any] | None = None


class ExtensionCreate(BaseModel):
    name: str
    version: str = "1.0.0"
    description: str | None = None
    author: str | None = None
    manifest: dict[str, Any] = {}


class ExtensionUpdate(BaseModel):
    status: str | None = None
    config: dict[str, Any] | None = None


class ExtensionResponse(BaseModel):
    id: str
    name: str
    version: str
    description: str | None
    author: str | None
    status: str
    manifest: dict[str, Any]
    config: dict[str, Any] | None
    created_at: str | None
    updated_at: str | None

    model_config = ConfigDict(from_attributes=True)


class ExtensionListResponse(BaseModel):
    extensions: list[ExtensionResponse]
    total: int
