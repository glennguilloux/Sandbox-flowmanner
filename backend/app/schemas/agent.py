from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# AgentTemplate schemas (aligned to actual agent_templates DB table)
# ---------------------------------------------------------------------------


class AgentTemplateCreate(BaseModel):
    name: str
    description: str | None = None
    system_prompt: str | None = None
    agent_type: str = "domain"
    config_data: dict | None = None
    is_active: bool = True


class AgentTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    agent_type: str | None = None
    config_data: dict | None = None
    is_active: bool | None = None


class AgentTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    template_id: str
    name: str
    description: str | None
    agent_type: str
    system_prompt: str | None
    config_data: dict | None = None
    is_active: bool | None
    created_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def from_orm_template(cls, template: Any) -> "AgentTemplateResponse":
        return cls(
            id=template.template_id,
            template_id=template.template_id,
            name=template.name,
            description=template.description,
            agent_type=template.agent_type,
            system_prompt=template.system_prompt,
            config_data=template.model_config,
            is_active=template.is_active,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )


# ---------------------------------------------------------------------------
# Catalog schemas (lightweight views for the domain agents API)
# ---------------------------------------------------------------------------


def _cfg(template: Any) -> dict:
    return template.model_config if isinstance(template.model_config, dict) else {}


class AgentCatalogItem(BaseModel):
    id: str
    name: str
    description: str | None
    agent_type: str
    emoji: str
    color: str
    division: str
    slug: str

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_template(cls, template: Any) -> "AgentCatalogItem":
        cfg = _cfg(template)
        return cls(
            id=template.template_id,
            name=template.name,
            description=template.description,
            agent_type=template.agent_type,
            emoji=cfg.get("emoji", ""),
            color=cfg.get("color", "#6B7280"),
            division=cfg.get("division", ""),
            slug=cfg.get("slug", ""),
        )


class AgentCatalogDetail(BaseModel):
    id: str
    name: str
    description: str | None
    agent_type: str
    system_prompt: str | None
    emoji: str
    color: str
    vibe: str
    division: str
    slug: str

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_template(cls, template: Any) -> "AgentCatalogDetail":
        cfg = _cfg(template)
        return cls(
            id=template.template_id,
            name=template.name,
            description=template.description,
            agent_type=template.agent_type,
            system_prompt=template.system_prompt,
            emoji=cfg.get("emoji", ""),
            color=cfg.get("color", "#6B7280"),
            vibe=cfg.get("vibe", ""),
            division=cfg.get("division", ""),
            slug=cfg.get("slug", ""),
        )


class AgentCreate(BaseModel):
    name: str
    description: str | None = None
    system_prompt: str | None = None
    model_preference: str | None = None
    config: dict | None = None


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    model_preference: str | None = None
    config: dict | None = None


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    name: str
    description: str | None = None
    owner_id: str
    model_preference: str | None = None
    system_prompt: str | None = None
    is_active: bool = True
    is_public: bool = False
    template_id: str | None = None
    config: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DivisionInfo(BaseModel):
    name: str
    count: int
